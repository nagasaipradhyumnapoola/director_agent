"""Deterministic artifact scan: links, secrets, syntax and honest coverage.

No model calls. Unsupported formats are never reported as checked-clean.
"""

from __future__ import annotations

import ast
import json
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

from .evidence import EvidenceLedger, environment_snapshot
from .models import TaskContract
from .policy import PolicyGateway
from .security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    canonical_json,
    dump_bounded,
    ensure_within,
    is_link_like,
    redact_text,
    safe_read_bytes,
    scan_secrets,
    sha256_bytes,
    sha256_text,
)
from .store import Store, utc_now

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".director",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "var",
}
CREDENTIAL_DIRS = {".ssh", ".aws", ".gnupg"}
CREDENTIAL_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
}
CREDENTIAL_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}

SYNTAX_EXTS = {".py", ".json"}
TEXT_EXTS = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".sql",
    ".ps1",
    ".sh",
    ".bat",
    ".cmd",
    ".csv",
    ".xml",
    ".svg",
}

EVALUATOR_VERSION = "artifact-scan/1.0"


@dataclass
class ScanConfig:
    max_files: int = 2000
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 64 * 1024 * 1024
    max_findings: int = 500
    ignored_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_IGNORED_DIRS))
    max_secret_findings_per_file: int = 20


@dataclass
class ScanResult:
    receipt_id: str
    criterion_key: str
    outcome: str
    files_scanned: int
    bytes_scanned: int
    artifacts: int
    findings: list[dict[str, Any]]
    counts: dict[str, int]
    coverage: dict[str, int]
    unknown_formats: int
    partial: bool
    omitted: int
    duration_seconds: float
    report_ref: str
    report_sha256: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "criterion_key": self.criterion_key,
            "outcome": self.outcome,
            "files_scanned": self.files_scanned,
            "bytes_scanned": self.bytes_scanned,
            "artifacts": self.artifacts,
            "counts": self.counts,
            "coverage": self.coverage,
            "unknown_formats": self.unknown_formats,
            "partial": self.partial,
            "omitted": self.omitted,
            "duration_seconds": round(self.duration_seconds, 4),
            "report_ref": self.report_ref,
            "report_sha256": self.report_sha256,
            "findings": self.findings,
            "limitations": self.limitations,
        }


class ArtifactScanner:
    def __init__(self, store: Store, config: ScanConfig | None = None):
        self.store = store
        self.root = Path(store.root)
        self.config = config or ScanConfig()
        self.ledger = EvidenceLedger(store)
        self.policy = PolicyGateway(store)
        self._contract: TaskContract | None = None
        latest = store.latest_contract()
        if latest:
            self._contract = latest[1]
        self._denied_paths = self._contract.permissions.denied_paths if self._contract else ()

    # -- helpers -----------------------------------------------------------
    def _denied(self, path: Path) -> bool:
        rel = path.relative_to(self.root).as_posix().lower()
        for denied in self._denied_paths:
            d = denied.replace("\\", "/").lower().rstrip("/")
            if rel == d or rel.startswith(d + "/"):
                return True
        return False

    def _finding(
        self,
        findings: list[dict[str, Any]],
        seen: set[tuple[str, str, str]],
        *,
        severity: str,
        kind: str,
        message: str,
        rel: str,
        sha: str,
        confidence: float = 0.9,
        limitations: str = "",
    ) -> int:
        key = (kind, rel, message)
        if key in seen:
            return 0
        if len(findings) >= self.config.max_findings:
            return 1
        seen.add(key)
        findings.append(
            {
                "severity": severity,
                "kind": kind,
                "message": redact_text(message)[:1000],
                "path": rel,
                "source_sha256": sha,
                "evaluator_version": EVALUATOR_VERSION,
                "confidence": float(confidence),
                "limitations": limitations,
            }
        )
        return 0

    def _iter_files(
        self,
        base: Path,
        findings: list[dict[str, Any]],
        seen: set[tuple[str, str, str]],
        dir_sink: list[tuple[Any, ...]] | None = None,
    ) -> Iterator[Path]:
        if base.is_file():
            yield base
            return
        for dirpath, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
            current = Path(dirpath)
            for name in list(dirnames):
                child = current / name
                try:
                    st = os.lstat(child)
                except OSError:
                    dirnames.remove(name)
                    continue
                rel = child.relative_to(self.root).as_posix()
                if is_link_like(st):
                    self._finding(
                        findings,
                        seen,
                        severity="critical",
                        kind="link_boundary",
                        message="directory link/junction/reparse point rejected; not traversed",
                        rel=rel,
                        sha=sha256_text("link:" + rel),
                        confidence=1.0,
                        limitations="content not traversed",
                    )
                    if dir_sink is not None:
                        dir_sink.append(("linkdir", rel, int(st.st_mtime_ns)))
                    dirnames.remove(name)
                elif name.lower() in self.config.ignored_dirs or name.lower() in CREDENTIAL_DIRS:
                    if name.lower() in CREDENTIAL_DIRS:
                        self._finding(
                            findings,
                            seen,
                            severity="high",
                            kind="potential_credential_path",
                            message="credential directory skipped without reading",
                            rel=rel,
                            sha=sha256_text("credential-dir:" + rel),
                            confidence=0.8,
                            limitations="content not read",
                        )
                        if dir_sink is not None:
                            dir_sink.append(("credentialdir", rel, int(st.st_mtime_ns)))
                    dirnames.remove(name)
                elif self._denied(child):
                    self._finding(
                        findings,
                        seen,
                        severity="info",
                        kind="denied_by_contract",
                        message="path on contract deny list skipped",
                        rel=rel,
                        sha=sha256_text("denied:" + rel),
                        confidence=1.0,
                        limitations="content not examined; scan is partial",
                    )
                    if dir_sink is not None:
                        dir_sink.append(("denieddir", rel, int(st.st_mtime_ns)))
                    dirnames.remove(name)
            for filename in filenames:
                yield current / filename

    def snapshot(self, roots: list[str] | None = None) -> tuple[str, int, bool]:
        """Recomputable digest of the scanned tree (no findings, no DB writes).

        Includes metadata for skipped files (links, credential-like names,
        oversized, denied) so adding one invalidates prior scan evidence.
        """
        entries: list[tuple[Any, ...]] = []
        files = 0
        total_bytes = 0
        partial = False
        dummy_findings: list[dict[str, Any]] = []
        dummy_seen: set[tuple[str, str, str]] = set()
        seen_paths: set[str] = set()
        selected: list[Path] = []
        selected_keys: set[str] = set()
        for rel in roots or ["."]:
            candidate = ensure_within(self.root / rel, self.root)
            key = os.path.normcase(str(candidate))
            if key in selected_keys:
                continue
            selected_keys.add(key)
            selected.append(candidate)
        for base in selected:
            if files >= self.config.max_files or total_bytes >= self.config.max_total_bytes:
                partial = True
                break
            for path in self._iter_files(base, dummy_findings, dummy_seen, dir_sink=entries):
                if files >= self.config.max_files or total_bytes >= self.config.max_total_bytes:
                    partial = True
                    break
                try:
                    rel = path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if rel in seen_paths:
                    continue
                seen_paths.add(rel)
                try:
                    st = os.lstat(path)
                except (ValueError, FileNotFoundError, OSError):
                    continue
                if is_link_like(st):
                    entries.append(("link", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                if path.name.lower() in CREDENTIAL_NAMES or path.suffix.lower() in CREDENTIAL_SUFFIXES:
                    entries.append(("credential", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                if self._denied(path):
                    entries.append(("denied", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                if st.st_size > self.config.max_file_bytes:
                    entries.append(("large", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    entries.append(("nonregular", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                try:
                    data = safe_read_bytes(path, self.root, max_bytes=self.config.max_file_bytes)
                except (PathSafetyError, BoundsError, OSError):
                    entries.append(("unreadable", rel, int(st.st_size), int(st.st_mtime_ns)))
                    continue
                entries.append(("file", rel, sha256_bytes(data), len(data)))
                files += 1
                total_bytes += len(data)
        digest = sha256_text(canonical_json([list(entry) for entry in sorted(entries)]))
        return digest, files, partial

    # -- main --------------------------------------------------------------
    def scan(
        self,
        roots: list[str] | None = None,
        criterion_key: str = "artifact.scan",
        claim: Any | None = None,
        valid_seconds: float | None = 24 * 3600,
    ) -> ScanResult:
        started = time.time()
        findings: list[dict[str, Any]] = []
        seen_findings: set[tuple[str, str, str]] = set()
        seen_paths: set[str] = set()
        coverage = {"syntax_checked": 0, "secret_scanned": 0, "unsupported": 0, "binary": 0}
        omitted = 0
        partial = False
        files_scanned = 0
        bytes_scanned = 0
        artifacts = 0
        limitations: list[str] = []

        if self._denied_paths:
            partial = True
            limitations.append("contract deny-list paths were not examined")

        selected: list[Path] = []
        selected_keys: set[str] = set()
        for rel in roots or ["."]:
            try:
                candidate = ensure_within(self.root / rel, self.root)
                key = os.path.normcase(str(candidate))
                if key not in selected_keys:
                    selected_keys.add(key)
                    selected.append(candidate)
            except PathSafetyError as exc:
                raise ValidationError(f"scan root rejected: {exc}") from exc

        for base in selected:
            if files_scanned >= self.config.max_files:
                partial = True
                limitations.append("file limit reached; scan is partial")
                break
            for path in self._iter_files(base, findings, seen_findings):
                if files_scanned >= self.config.max_files:
                    partial = True
                    limitations.append("file limit reached; scan is partial")
                    break
                if bytes_scanned >= self.config.max_total_bytes:
                    partial = True
                    limitations.append("byte limit reached; scan is partial")
                    break
                try:
                    rel = path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                key = rel.lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                try:
                    st = os.lstat(path)
                except FileNotFoundError:
                    partial = True
                    self._finding(
                        findings,
                        seen_findings,
                        severity="low",
                        kind="scan_race",
                        message="path disappeared during scan",
                        rel=rel,
                        sha=sha256_text("missing:" + rel),
                        limitations="snapshot may have changed",
                    )
                    continue
                if is_link_like(st):
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="critical",
                        kind="link_boundary",
                        message="file link/junction/reparse point rejected without reading",
                        rel=rel,
                        sha=sha256_text("link:" + rel),
                        confidence=1.0,
                        limitations="content not read",
                    )
                    partial = True
                    continue
                if not stat.S_ISREG(st.st_mode):
                    coverage["unsupported"] += 1
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="info",
                        kind="unsupported_format",
                        message="not a regular file; content unsupported",
                        rel=rel,
                        sha=sha256_text("nonregular:" + rel),
                        limitations="not checked",
                    )
                    partial = True
                    continue
                if st.st_nlink > 1:
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="high",
                        kind="hardlink_boundary",
                        message="hardlinked file rejected without reading",
                        rel=rel,
                        sha=sha256_text("hardlink:" + rel),
                        confidence=1.0,
                        limitations="content not read",
                    )
                    partial = True
                    continue
                name = path.name.lower()
                if name in CREDENTIAL_NAMES or path.suffix.lower() in CREDENTIAL_SUFFIXES:
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="high",
                        kind="potential_credential_path",
                        message="credential-like filename skipped without reading",
                        rel=rel,
                        sha=sha256_text("credential:" + rel),
                        confidence=0.8,
                        limitations="content not read; secret status unknown",
                    )
                    partial = True
                    continue
                if st.st_size > self.config.max_file_bytes:
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="medium",
                        kind="file_too_large",
                        message=f"file exceeds {self.config.max_file_bytes} byte scan limit",
                        rel=rel,
                        sha=sha256_text("toolarge:" + rel + ":" + str(st.st_size)),
                        limitations="content not checked",
                    )
                    partial = True
                    continue
                if self._denied(path):
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="info",
                        kind="denied_by_contract",
                        message="path on contract deny list skipped",
                        rel=rel,
                        sha=sha256_text("denied:" + rel),
                        limitations="content not examined; scan is partial",
                    )
                    partial = True
                    continue
                try:
                    data = safe_read_bytes(path, self.root, max_bytes=self.config.max_file_bytes)
                except (PathSafetyError, BoundsError, OSError) as exc:
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="high",
                        kind="unsafe_read",
                        message=f"file could not be read safely ({type(exc).__name__})",
                        rel=rel,
                        sha=sha256_text("unreadable:" + rel),
                        limitations="content not read",
                    )
                    partial = True
                    continue

                digest = sha256_bytes(data)
                files_scanned += 1
                bytes_scanned += len(data)
                suffix = path.suffix.lower()
                kind = "binary" if b"\x00" in data[:8192] else (suffix[1:] or "text")
                self.store.add_artifact(
                    rel,
                    digest,
                    len(data),
                    kind,
                    meta={"scan": EVALUATOR_VERSION, "suffix": suffix},
                )
                artifacts += 1

                if b"\x00" in data[:8192]:
                    coverage["binary"] += 1
                    partial = True
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="info",
                        kind="unsupported_format",
                        message="binary content unsupported by static scan",
                        rel=rel,
                        sha=digest,
                        limitations="content not checked",
                    )
                    continue

                text = data.decode("utf-8", "replace")
                if suffix not in TEXT_EXTS:
                    coverage["unsupported"] += 1
                    partial = True
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="info",
                        kind="unsupported_format",
                        message=f"unsupported extension '{suffix[:16] or '(none)'}'; static analysis not performed",
                        rel=rel,
                        sha=digest,
                        limitations="content not checked as a supported language",
                    )
                    continue

                coverage["secret_scanned"] += 1
                for hit in scan_secrets(text, max_hits=self.config.max_secret_findings_per_file):
                    omitted += self._finding(
                        findings,
                        seen_findings,
                        severity="high",
                        kind="secret_exposed",
                        message=f"possible {hit['kind']} secret at line {hit['line']}; value redacted",
                        rel=rel,
                        sha=digest,
                        confidence=0.8,
                        limitations="pattern-based detection; value never stored",
                    )

                if suffix == ".py":
                    try:
                        ast.parse(text, filename=rel)
                        coverage["syntax_checked"] += 1
                    except SyntaxError as exc:
                        partial = True
                        omitted += self._finding(
                            findings,
                            seen_findings,
                            severity="high",
                            kind="syntax_error",
                            message=f"Python syntax error at line {exc.lineno or 0}, column {exc.offset or 0}",
                            rel=rel,
                            sha=digest,
                            confidence=1.0,
                        )
                    except (ValueError, RecursionError):
                        partial = True
                        omitted += self._finding(
                            findings,
                            seen_findings,
                            severity="high",
                            kind="syntax_error",
                            message="Python parser rejected the file",
                            rel=rel,
                            sha=digest,
                        )
                elif suffix == ".json":
                    if len(data) > 4 * 1024 * 1024:
                        partial = True
                        omitted += self._finding(
                            findings,
                            seen_findings,
                            severity="medium",
                            kind="json_too_large",
                            message="JSON exceeds parser bound",
                            rel=rel,
                            sha=digest,
                        )
                    else:
                        try:
                            json.loads(text)
                            coverage["syntax_checked"] += 1
                        except json.JSONDecodeError as exc:
                            partial = True
                            omitted += self._finding(
                                findings,
                                seen_findings,
                                severity="high",
                                kind="json_error",
                                message=f"JSON parse error at line {exc.lineno}, column {exc.colno}",
                                rel=rel,
                                sha=digest,
                            )

        snapshot, snapshot_files, snapshot_partial = self.snapshot(roots)
        if snapshot_partial:
            partial = True
            limitations.append("snapshot hit a scan bound; freshness is partial")
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
        unknown = coverage["unsupported"] + coverage["binary"]
        if counts.get("critical", 0) or counts.get("high", 0):
            outcome = "fail"
        elif partial or unknown or omitted:
            outcome = "partial"
        else:
            outcome = "pass"
        if outcome == "pass" and files_scanned == 0:
            outcome = "partial"
            partial = True
            limitations.append("no regular files were scanned")

        receipt_id = "ev_" + uuid.uuid4().hex
        duration = time.time() - started
        report = {
            "schema": "director.scan.v1",
            "receipt_id": receipt_id,
            "evaluator": EVALUATOR_VERSION,
            "config": {
                "max_files": self.config.max_files,
                "max_file_bytes": self.config.max_file_bytes,
                "max_total_bytes": self.config.max_total_bytes,
                "max_findings": self.config.max_findings,
            },
            "files_scanned": files_scanned,
            "bytes_scanned": bytes_scanned,
            "artifacts": artifacts,
            "coverage": coverage,
            "counts": counts,
            "partial": partial,
            "unknown_formats": unknown,
            "omitted_findings": omitted,
            "duration_seconds": round(duration, 4),
            "snapshot": {
                "sha256": snapshot,
                "files": snapshot_files,
                "partial": snapshot_partial,
            },
            "findings": findings,
            "limitations": limitations
            + [
                "Static scan is not a security audit and does not prove absence of defects.",
                "Content not read (links, credentials, oversized or denied paths) remains unknown.",
            ],
        }
        report_ref, report_sha = self.ledger.save_raw_receipt(f"scan-{receipt_id}", report)
        latest = self.store.latest_contract()
        revision = int(latest[0]["revision"]) if latest else 0
        evidence_item = {
            "id": receipt_id,
            "criterion_key": criterion_key,
            "kind": "static_scan",
            "subject_path": None,
            "subject_sha256": snapshot,
            "collector": "director.artifact_scanner",
            "check_name": "artifact_scan",
            "check_version": EVALUATOR_VERSION,
            "params": {
                "roots": roots or ["."],
                "config": report["config"],
                "snapshot_hash": snapshot,
                "snapshot_files": snapshot_files,
                "snapshot_partial": snapshot_partial,
            },
            "environment": environment_snapshot(),
            "outcome": outcome,
            "confidence": 0.9 if outcome == "pass" else 0.7,
            "limitations": " | ".join(report["limitations"]),
            "raw_ref": report_ref,
            "task_revision": revision,
            "policy_hash": self.policy.policy_hash(),
            "valid_until": None,
        }
        finding_items: list[dict[str, Any]] = []
        for finding in findings:
            finding_items.append(
                {
                    **finding,
                    "receipt_id": receipt_id,
                    "evidence_id": receipt_id,
                }
            )

        if claim is not None:
            self.store.publish(claim, [evidence_item], finding_items)
        else:
            self.store.add_evidence(evidence_item)
            for item in finding_items:
                self.store.add_finding(item)
        self.store.record_event(
            "scan.completed",
            f"scan:{receipt_id}",
            {
                "outcome": outcome,
                "files": files_scanned,
                "partial": partial,
                "unknown": unknown,
            },
        )

        return ScanResult(
            receipt_id=receipt_id,
            criterion_key=criterion_key,
            outcome=outcome,
            files_scanned=files_scanned,
            bytes_scanned=bytes_scanned,
            artifacts=artifacts,
            findings=findings,
            counts=counts,
            coverage=coverage,
            unknown_formats=unknown,
            partial=partial,
            omitted=omitted,
            duration_seconds=duration,
            report_ref=report_ref,
            report_sha256=report_sha,
            limitations=report["limitations"],
        )

