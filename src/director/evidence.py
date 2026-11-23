"""Evidence receipts, freshness verification and criterion acceptance."""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__
from .models import AcceptanceCriterion, TaskContract
from .policy import PolicyGateway
from .security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    atomic_write_text,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    redact_text,
    safe_hash_file,
    sha256_text,
)
from .store import Store, utc_after, utc_now


def environment_snapshot() -> dict[str, Any]:
    return {
        "director_version": __version__,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }


def _environment() -> dict[str, Any]:
    return environment_snapshot()


class EvidenceLedger:
    def __init__(self, store: Store):
        self.store = store
        self.project_id = store.project_id
        self.policy = PolicyGateway(store)

    def _latest_revision(self) -> int:
        latest = self.store.latest_contract()
        if not latest:
            raise ValidationError("no task contract saved")
        return int(latest[0]["revision"])

    def record(
        self,
        *,
        criterion_key: str,
        kind: str,
        collector: str,
        check_name: str,
        check_version: str,
        outcome: str,
        subject_path: str | None = None,
        subject_sha256: str | None = None,
        params: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        confidence: float = 1.0,
        limitations: str = "",
        raw_ref: str | None = None,
        valid_seconds: float | None = None,
        task_revision: int | None = None,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        if subject_path and not subject_sha256:
            subject_sha256, _ = safe_hash_file(
                ensure_within(self.store.root / subject_path, self.store.root), self.store.root
            )
        revision = task_revision or self._latest_revision()
        env = _environment()
        if environment:
            env.update({str(k): v for k, v in environment.items() if _safe_env_value(v)})
        item: dict[str, Any] = {
            "criterion_key": criterion_key,
            "kind": kind,
            "subject_path": subject_path,
            "subject_sha256": subject_sha256,
            "collector": collector,
            "check_name": check_name,
            "check_version": check_version,
            "params": dict(params or {}),
            "environment": env,
            "outcome": outcome,
            "confidence": float(confidence),
            "limitations": limitations,
            "raw_ref": raw_ref,
            "task_revision": revision,
            "policy_hash": self.policy.policy_hash(),
            "valid_until": utc_after(valid_seconds) if valid_seconds else None,
        }
        if evidence_id:
            item["id"] = evidence_id
        recorded_id = self.store.add_evidence(item)
        try:
            from . import audit

            audit.log(self.store, collector, "evidence.record", criterion_key, outcome)
        except Exception:
            pass
        return self.store.get_evidence(recorded_id)

    def save_raw_receipt(self, name: str, payload: Mapping[str, Any] | Any) -> tuple[str, str]:
        """Write a bounded receipt under .director/receipts and return (rel, sha)."""
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in "._-")[:80]
        if not safe_name:
            raise ValidationError("invalid receipt name")
        if not safe_name.endswith(".json"):
            safe_name += ".json"
        text, truncated = dump_bounded(payload, max_bytes=256 * 1024)
        if truncated:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    parsed["_receipt_truncated"] = True
                    text = dump_bounded(parsed, max_bytes=256 * 1024)[0]
            except json.JSONDecodeError:
                pass
        text = redact_text(text, max_chars=300_000)
        directory = Path(self.store.root) / ".director" / "receipts"
        os.makedirs(directory, exist_ok=True)
        target = ensure_within(directory / safe_name, self.store.root)
        atomic_write_text(target, text, root=self.store.root)
        return (
            target.relative_to(Path(self.store.root)).as_posix(),
            sha256_text(text),
        )

    def verify(
        self, evidence_id: str, _snapshot_cache: dict[str, str] | None = None
    ) -> dict[str, Any]:
        row = self.store.get_evidence(evidence_id)
        reasons: list[str] = []
        if row["status"] != "valid":
            reasons.append(f"status is {row['status']}")
        latest = self.store.latest_contract()
        if latest and int(row["task_revision"]) != int(latest[0]["revision"]):
            reasons.append("task contract revision changed")
        current_policy = self.policy.policy_hash()
        if row["policy_hash"] != current_policy:
            reasons.append("policy/grants changed")
        if row["valid_until"]:
            try:
                until = datetime.fromisoformat(row["valid_until"]).timestamp()
                if until < datetime.now(timezone.utc).timestamp():
                    reasons.append("evidence expired")
            except ValueError:
                reasons.append("invalid validity timestamp")
        subject = row.get("subject_path")
        recorded_sha = row.get("subject_sha256")
        current_sha = None
        if row.get("check_name") == "artifact_scan":
            try:
                from .analysis import ArtifactScanner, ScanConfig

                params = bounded_json_loads(row["params"], max_bytes=64 * 1024)
                config = ScanConfig(**dict(params.get("config") or {}))
                cache_key = json.dumps(
                    {"roots": params.get("roots") or ["."], "config": params.get("config") or {}},
                    sort_keys=True,
                )
                current_sha = None
                if _snapshot_cache is not None:
                    current_sha = _snapshot_cache.get(cache_key)
                if current_sha is None:
                    scanner = ArtifactScanner(self.store, config)
                    current_sha, _files, _partial = scanner.snapshot(params.get("roots") or ["."])
                    if _snapshot_cache is not None:
                        _snapshot_cache[cache_key] = current_sha
                if current_sha != recorded_sha:
                    reasons.append("scanned tree changed")
            except Exception:
                reasons.append("scan snapshot could not be recomputed")
        elif subject:
            try:
                current_sha, _ = safe_hash_file(
                    ensure_within(Path(self.store.root) / subject, self.store.root),
                    self.store.root,
                )
            except (PathSafetyError, BoundsError, OSError):
                reasons.append("subject is missing or unsafe")
            if current_sha and recorded_sha and current_sha != recorded_sha:
                reasons.append("subject content changed")
        fresh = not reasons
        if reasons and row["status"] == "valid":
            self.store.set_evidence_status(evidence_id, "stale", "; ".join(reasons))
        return {
            "evidence_id": evidence_id,
            "fresh": fresh,
            "reasons": reasons,
            "outcome": row["outcome"],
            "criterion_key": row["criterion_key"],
            "subject_sha256": recorded_sha,
            "current_sha256": current_sha,
            "created_at": row["created_at"],
            "check_name": row["check_name"],
            "check_version": row["check_version"],
        }

    def verify_all(self) -> list[dict[str, Any]]:
        cache: dict[str, str] = {}
        return [
            self.verify(row["id"], _snapshot_cache=cache)
            for row in self.store.list_evidence(limit=1000)
        ]

    def criterion_status(self, verify: bool = True) -> dict[str, Any]:  # noqa: F811
        """Latest evidence per criterion wins, regardless of outcome.

        A newer failing/blocked result supersedes an older pass. Completion
        requires that latest row to be a currently-fresh pass, or an owner
        waiver bound to the current contract revision.
        """
        latest = self.store.latest_contract()
        if not latest:
            return {"complete": False, "unmet": [], "waived": {}, "criteria": [], "reason": "no contract"}
        _, contract = latest
        waivers = self.store.waivers()
        results: list[dict[str, Any]] = []
        unmet: list[str] = []
        for criterion in contract.mandatory_criteria:
            rows = self.store.list_evidence(limit=1000, criterion_key=criterion.key)
            chosen = rows[0] if rows else None
            fresh = False
            reasons: list[str] = []
            if chosen is None:
                reasons.append("no evidence")
            elif chosen["outcome"] != "pass":
                reasons.append(f"latest evidence outcome is {chosen['outcome']}")
            elif verify:
                verification = self.verify(chosen["id"])
                fresh = bool(verification["fresh"])
                reasons.extend(verification["reasons"])
            else:
                fresh = chosen["status"] == "valid"
                if not fresh:
                    reasons.append(f"status is {chosen['status']} (unverified)")
            waived = criterion.key in waivers
            satisfied = fresh or waived
            if not satisfied:
                unmet.append(criterion.key)
            results.append(
                {
                    "criterion_key": criterion.key,
                    "description": criterion.description,
                    "mandatory": True,
                    "satisfied": satisfied,
                    "waived": waived,
                    "evidence_id": chosen["id"] if chosen else None,
                    "latest_outcome": chosen["outcome"] if chosen else None,
                    "verified": bool(verify),
                    "reasons": reasons,
                }
            )
        return {
            "complete": not unmet,
            "unmet": unmet,
            "waived": waivers,
            "criteria": results,
            "contract_revision": latest[0]["revision"],
        }

    def completion(self) -> dict[str, Any]:
        status = self.criterion_status(verify=True)
        status["complete"] = bool(status.get("complete"))
        return status


def _safe_env_value(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    return False


def evidence_index(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["outcome"])
        counts[key] = counts.get(key, 0) + 1
    return counts
