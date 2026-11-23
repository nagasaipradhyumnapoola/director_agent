"""Domain capability contracts, fixture snapshots and pilot persistence."""

from __future__ import annotations

import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ..evidence import EvidenceLedger, environment_snapshot
from ..models import TaskContract
from ..policy import PolicyDenied, PolicyGateway
from ..runner import Runner, Workspace
from ..security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    bounded_json_loads,
    canonical_json,
    ensure_within,
    is_link_like,
    redact_text,
    safe_hash_file,
    sha256_bytes,
    sha256_object,
    sha256_text,
)
from ..store import BudgetExceeded, Store, utc_after, utc_now

PILOT_STATUSES = ("pass", "fail", "blocked", "error")


@dataclass(frozen=True)
class DomainProfile:
    name: str
    version: str
    description: str
    supported_formats: tuple[str, ...]
    required_tools: tuple[str, ...]
    required_actions: tuple[str, ...]
    risks: tuple[str, ...]
    evidence_schema: tuple[str, ...]
    evaluators: tuple[str, ...]
    unsupported: tuple[str, ...]
    default_timeout: float = 120.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "supported_formats": list(self.supported_formats),
            "required_tools": list(self.required_tools),
            "required_actions": list(self.required_actions),
            "risks": list(self.risks),
            "evidence_schema": list(self.evidence_schema),
            "evaluators": list(self.evaluators),
            "unsupported": list(self.unsupported),
            "default_timeout": self.default_timeout,
        }


PROFILES: dict[str, DomainProfile] = {
    "general": DomainProfile(
        name="general",
        version="1.0",
        description="Deterministic artifact scan, contracts, evidence and budgets.",
        supported_formats=(".py", ".json", ".md", ".txt", ".html", ".css", ".js"),
        required_tools=(),
        required_actions=(),
        risks=("secrets", "links", "unsupported formats"),
        evidence_schema=("artifact_scan",),
        evaluators=("artifact_scan",),
        unsupported=("semantic correctness", "runtime behavior"),
    ),
    "website": DomainProfile(
        name="website",
        version="1.0",
        description="Browser journey, keyboard, responsive and static accessibility checks.",
        supported_formats=(".html", ".css", ".js", ".mjs"),
        required_tools=("node", "chromium-family-browser"),
        required_actions=("run_local_subprocess", "launch_browser"),
        risks=("console errors", "broken journey", "keyboard traps", "mobile overflow", "external network"),
        evidence_schema=("static_checks", "browser_probe", "screenshots"),
        evaluators=("static_checks", "browser_probe"),
        unsupported=("visual taste", "screen readers", "auth", "backend data"),
        default_timeout=90.0,
    ),
    "ml": DomainProfile(
        name="ml",
        version="1.0",
        description="Small CPU experiment with manifest, leakage, held-out, reproducibility and slice checks.",
        supported_formats=(".csv", ".json"),
        required_tools=("python",),
        required_actions=("run_local_subprocess",),
        risks=("split leakage", "target-derived features", "weak baseline", "nondeterminism"),
        evidence_schema=("metrics", "resource_report", "determinism"),
        evaluators=("manifest", "leakage", "heldout", "reproducibility", "slices"),
        unsupported=("large-scale training", "GPU workloads", "model deployment"),
        default_timeout=120.0,
    ),
    "research": DomainProfile(
        name="research",
        version="1.0",
        description="Claim-source mapping, conflict/date handling, calculations and rendered document checks.",
        supported_formats=(".md", ".txt", ".json"),
        required_tools=("python-docx(optional)",),
        required_actions=(),
        risks=("fabricated citations", "stale sources", "calculation errors", "unrendered output"),
        evidence_schema=("claim_map", "calculation", "render"),
        evaluators=("sources", "claims", "calculation", "conflicts", "render"),
        unsupported=("live web freshness", "subjective prose quality"),
        default_timeout=60.0,
    ),
}


@dataclass
class Check:
    criterion_key: str
    description: str
    passed: bool
    details: Mapping[str, Any] = field(default_factory=dict)
    subject_path: str | None = None
    subject_sha256: str | None = None
    confidence: float = 0.9
    limitations: str = ""
    outcome: str | None = None

    def effective_outcome(self) -> str:
        if self.outcome:
            return self.outcome
        return "pass" if self.passed else "fail"


@dataclass
class FindingDraft:
    severity: str
    kind: str
    message: str
    path: str | None = None
    source_sha256: str | None = None
    confidence: float = 0.8
    limitations: str = ""


@dataclass
class DomainResult:
    status: str
    checks: list[Check] = field(default_factory=list)
    findings: list[FindingDraft] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    blocked_reason: str | None = None


@dataclass
class PilotOutcome:
    domain: str
    mode: str
    status: str
    fixture_rel: str
    fixture_sha256: str
    receipt_id: str
    checks: list[dict[str, Any]]
    evidence_ids: list[str]
    findings: list[dict[str, Any]]
    limitations: list[str]
    resources: dict[str, Any]
    report_ref: str | None
    duration_seconds: float
    acceptance: dict[str, Any]
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "mode": self.mode,
            "status": self.status,
            "fixture_rel": self.fixture_rel,
            "fixture_sha256": self.fixture_sha256,
            "receipt_id": self.receipt_id,
            "checks": self.checks,
            "evidence_ids": self.evidence_ids,
            "findings": self.findings,
            "limitations": self.limitations,
            "resources": self.resources,
            "report_ref": self.report_ref,
            "duration_seconds": round(self.duration_seconds, 4),
            "acceptance": self.acceptance,
            "blocked_reason": self.blocked_reason,
        }


def fixture_snapshot(root: Path, fixture_rel: str) -> tuple[str, list[dict[str, Any]], int]:
    base = ensure_within(root / fixture_rel, root)
    entries: list[dict[str, Any]] = []
    total = 0
    if base.is_file():
        candidates = [base]
    else:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            current = Path(dirpath)
            keep = []
            for name in dirnames:
                child = current / name
                st = os.lstat(child)
                if is_link_like(st):
                    raise PathSafetyError("fixture contains a linked directory")
                keep.append(name)
            dirnames[:] = keep
            candidates.extend(current / name for name in filenames)
    if len(candidates) > 5000:
        raise BoundsError("fixture has too many files")
    for path in sorted(candidates):
        st = os.lstat(path)
        if is_link_like(st) or st.st_nlink > 1:
            raise PathSafetyError("fixture contains a linked or hardlinked file")
        if not stat.S_ISREG(st.st_mode):
            raise PathSafetyError("fixture contains a non-regular file")
        if st.st_size > 16 * 1024 * 1024:
            raise BoundsError("fixture file exceeds 16MB")
        data = path.read_bytes()
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise BoundsError("fixture exceeds 64MB")
        entries.append(
            {
                "path": path.relative_to(base).as_posix(),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
            }
        )
    return sha256_text(canonical_json(entries)), entries, total


class PilotContext:
    def __init__(
        self,
        store: Store,
        contract: TaskContract,
        contract_row: Mapping[str, Any],
        profile: DomainProfile,
        fixture_rel: str,
        fixture_sha: str,
        fixture_entries: list[dict[str, Any]],
        runner: Runner,
        timeout_seconds: float,
    ):
        self.store = store
        self.contract = contract
        self.contract_row = contract_row
        self.profile = profile
        self.revision = int(contract_row["revision"])
        self.fixture_rel = fixture_rel
        self.fixture_sha = fixture_sha
        self.fixture_entries = fixture_entries
        self.fixture_path = ensure_within(Path(store.root) / fixture_rel, Path(store.root))
        self.runner = runner
        self.ledger = EvidenceLedger(store)
        self.policy = PolicyGateway(store)
        self.actor = f"director.domain.{profile.name}"
        self.timeout_seconds = timeout_seconds

    def authorize(self, action: str) -> None:
        check = self.policy.require(
            self.actor,
            action,
            self.fixture_rel,
            self.revision,
            payload={"fixture_sha256": self.fixture_sha},
        )
        if not check.grant_id:
            raise PolicyDenied("an explicit owner grant is required")
        grant = self.store.get_grant(check.grant_id)
        limits = bounded_json_loads(grant["limits"], max_bytes=16 * 1024)
        if not isinstance(limits, dict):
            raise PolicyDenied("grant limits are invalid")
        allowed_timeout = float(limits.get("timeout_seconds", 0))
        if allowed_timeout < self.timeout_seconds:
            raise PolicyDenied("grant timeout limit is smaller than the pilot request")

    def create_workspace(self) -> Workspace:
        return self.runner.create_workspace()


Evaluator = Callable[[PilotContext], DomainResult]


def provision_pilot_grants(
    store: Store,
    domain: str,
    fixture_rel: str,
    revision: int | None = None,
    timeout_seconds: float | None = None,
) -> list[str]:
    """Owner-side provisioning for a pilot. Never called by an evaluator."""
    profile = PROFILES.get(domain)
    if profile is None:
        raise ValidationError("unknown domain")
    latest = store.latest_contract()
    if not latest:
        raise ValidationError("no task contract saved")
    revision = int(latest[0]["revision"]) if revision is None else int(revision)
    fixture_sha, _entries, _bytes = fixture_snapshot(Path(store.root), fixture_rel)
    actor = f"director.domain.{domain}"
    timeout = float(timeout_seconds or profile.default_timeout)
    payload = {"fixture_sha256": fixture_sha}
    payload_hash = sha256_object(payload)
    granted: list[str] = []
    for action in profile.required_actions:
        existing = None
        for grant in store.list_grants(include_revoked=False):
            if (
                grant["actor"] == actor
                and grant["action"] == action
                and grant["resource"] == fixture_rel
                and grant["effect"] == "allow"
                and int(grant["task_revision"]) == revision
                and grant["payload_hash"] == payload_hash
            ):
                try:
                    limits = bounded_json_loads(grant["limits"], max_bytes=16 * 1024)
                    if float(limits.get("timeout_seconds", 0)) >= timeout:
                        existing = str(grant["id"])
                        break
                except Exception:
                    continue
        if existing:
            granted.append(existing)
            continue
        grant_id = store.add_grant(
            actor=actor,
            action=action,
            resource=fixture_rel,
            effect="allow",
            limits={"timeout_seconds": timeout, "max_output_bytes": 256 * 1024},
            task_revision=revision,
            approved_by="owner",
            expires_at=utc_after(3600),
            payload_hash=payload_hash,
        )
        granted.append(grant_id)
    return granted


def _evidence_item(
    ctx: PilotContext,
    *,
    criterion_key: str,
    kind: str,
    outcome: str,
    subject_path: str | None,
    subject_sha: str | None,
    params: Mapping[str, Any],
    limitations: str,
    confidence: float,
    raw_ref: str | None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    resolved_path: str | None = None
    resolved_sha = subject_sha
    if subject_path:
        try:
            candidate = ensure_within(Path(ctx.store.root) / subject_path, Path(ctx.store.root))
            if candidate.is_file():
                resolved_path = subject_path
                resolved_sha, _ = safe_hash_file(candidate, Path(ctx.store.root))
            else:
                resolved_path = None
        except (PathSafetyError, BoundsError, OSError):
            resolved_path = None
    item: dict[str, Any] = {
        "criterion_key": criterion_key,
        "kind": kind,
        "subject_path": resolved_path,
        "subject_sha256": resolved_sha or ctx.fixture_sha,
        "collector": f"director.domain.{ctx.profile.name}",
        "check_name": f"{ctx.profile.name}_evaluator",
        "check_version": f"{ctx.profile.version}",
        "params": dict(params),
        "environment": environment_snapshot(),
        "outcome": outcome,
        "confidence": confidence,
        "limitations": limitations,
        "raw_ref": raw_ref,
        "task_revision": ctx.revision,
        "policy_hash": ctx.policy.policy_hash(),
        "valid_until": None,
    }
    if evidence_id:
        item["id"] = evidence_id
    return item


def run_pilot(
    store: Store,
    domain: str,
    fixture_rel: str,
    mode: str = "clean",
    evaluator: Evaluator | None = None,
) -> PilotOutcome:
    started = time.time()
    profile = PROFILES.get(domain)
    if profile is None:
        raise ValidationError("unknown domain")
    latest = store.latest_contract()
    if not latest:
        raise ValidationError("no task contract saved")
    contract_row, contract = latest
    if domain not in contract.domains:
        return PilotOutcome(
            domain=domain,
            mode=mode,
            status="blocked",
            fixture_rel=fixture_rel,
            fixture_sha256="",
            receipt_id="",
            checks=[],
            evidence_ids=[],
            findings=[],
            limitations=[f"domain '{domain}' is not declared in the contract"],
            resources={},
            report_ref=None,
            duration_seconds=time.time() - started,
            acceptance={},
            blocked_reason="domain not declared in contract",
        )
    try:
        fixture_sha, entries, _ = fixture_snapshot(Path(store.root), fixture_rel)
    except (PathSafetyError, BoundsError, OSError) as exc:
        return PilotOutcome(
            domain=domain,
            mode=mode,
            status="blocked",
            fixture_rel=fixture_rel,
            fixture_sha256="",
            receipt_id="",
            checks=[],
            evidence_ids=[],
            findings=[],
            limitations=[f"fixture rejected: {type(exc).__name__}"],
            resources={},
            report_ref=None,
            duration_seconds=time.time() - started,
            acceptance={},
            blocked_reason="fixture rejected",
        )
    runner = Runner(default_timeout=profile.default_timeout)
    ctx = PilotContext(
        store,
        contract,
        contract_row,
        profile,
        fixture_rel,
        fixture_sha,
        entries,
        runner,
        profile.default_timeout,
    )
    model_calls_before = store.model_calls_spent()
    reservation = None
    result: DomainResult
    try:
        reservation = store.reserve_budget(
            "wall_seconds", profile.default_timeout, ctx.revision, note=f"pilot {domain}"
        )
    except BudgetExceeded as exc:
        result = DomainResult(status="blocked", blocked_reason=str(exc))
        reservation = None

    if reservation is not None:
        try:
            for action in profile.required_actions:
                ctx.authorize(action)
            evaluator_fn = evaluator or _registry()[domain]
            result = evaluator_fn(ctx)
            if result.status not in PILOT_STATUSES:
                result.status = "error"
                result.limitations.append("evaluator returned an invalid status")
        except PolicyDenied as exc:
            result = DomainResult(status="blocked", blocked_reason=f"policy denied: {exc}")
        except BudgetExceeded as exc:
            result = DomainResult(status="blocked", blocked_reason=str(exc))
        except (PathSafetyError, BoundsError, ValidationError) as exc:
            result = DomainResult(status="error", blocked_reason=f"invalid input: {type(exc).__name__}")
        except Exception as exc:  # noqa: BLE001 - converted to honest error evidence
            result = DomainResult(
                status="error",
                blocked_reason=f"evaluator error: {type(exc).__name__}",
                limitations=["evaluator raised an unexpected error; no domain conclusion"],
            )
        finally:
            elapsed = time.time() - started
            try:
                store.settle_reservation(reservation, min(elapsed, profile.default_timeout))
            except Exception:
                pass

    model_calls_after = store.model_calls_spent()
    if model_calls_after != model_calls_before:
        result = DomainResult(
            status="error",
            blocked_reason="unexpected model call during a zero-model pilot",
            limitations=["pilot isolation violated; result rejected"],
        )

    receipt_id = "ev_" + os.urandom(16).hex()
    report = {
        "schema": "director.pilot.v1",
        "domain": domain,
        "profile": profile.to_dict(),
        "mode": mode,
        "fixture_rel": fixture_rel,
        "fixture_sha256": fixture_sha,
        "fixture_files": entries,
        "status": result.status,
        "checks": [
            {
                "criterion_key": c.criterion_key,
                "description": c.description,
                "passed": c.passed,
                "outcome": c.effective_outcome(),
                "details": c.details,
                "limitations": c.limitations,
            }
            for c in result.checks
        ],
        "findings": [
            {
                "severity": f.severity,
                "kind": f.kind,
                "message": f.message,
                "path": f.path,
            }
            for f in result.findings
        ],
        "limitations": result.limitations,
        "resources": result.resources,
        "blocked_reason": result.blocked_reason,
        "model_calls_before": model_calls_before,
        "model_calls_after": model_calls_after,
        "evaluator_versions": {"profile": profile.version, "check": f"{domain}-evaluator/{profile.version}"},
        "extra": result.report,
    }
    report_ref, _ = ctx.ledger.save_raw_receipt(f"pilot-{domain}-{receipt_id}", report)
    summary_outcome = result.status if result.status in {"pass", "fail", "blocked", "error"} else "error"
    evidence_ids: list[str] = []
    summary = _evidence_item(
        ctx,
        criterion_key=f"{domain}.run",
        kind="domain_run",
        outcome=summary_outcome,
        subject_path=fixture_rel,
        subject_sha=fixture_sha,
        params={"mode": mode, "status": result.status, "fixture_files": len(entries)},
        limitations=" | ".join(result.limitations),
        confidence=0.9 if result.status == "pass" else 0.6,
        raw_ref=report_ref,
        evidence_id=receipt_id,
    )
    try:
        store.add_evidence(summary)
        evidence_ids.append(receipt_id)
    except Exception:
        receipt_id = ""
    finding_records: list[dict[str, Any]] = []
    for draft in result.findings[: profile_limits(contract)[0]]:
        path = draft.path or fixture_rel
        sha = draft.source_sha256 or fixture_sha
        finding_records.append(
            {
                "severity": draft.severity,
                "kind": draft.kind,
                "message": draft.message,
                "path": path,
                "source_sha256": sha,
                "evaluator_version": f"{domain}-evaluator/{profile.version}",
                "receipt_id": receipt_id,
                "evidence_id": receipt_id or None,
                "confidence": draft.confidence,
                "limitations": draft.limitations,
            }
        )
    for check in result.checks:
        outcome = check.effective_outcome()
        item = _evidence_item(
            ctx,
            criterion_key=check.criterion_key,
            kind="domain_check",
            outcome=outcome,
            subject_path=check.subject_path or fixture_rel,
            subject_sha=check.subject_sha256 or fixture_sha,
            params={
                "description": check.description,
                "details": check.details,
                "mode": mode,
            },
            limitations=check.limitations,
            confidence=check.confidence,
            raw_ref=report_ref,
        )
        try:
            evidence_id = store.add_evidence(item)
            evidence_ids.append(evidence_id)
        except Exception:
            continue
    for record in finding_records:
        try:
            store.add_finding(record)
        except Exception:
            continue
    acceptance = ctx.ledger.criterion_status(verify=True)
    final_status = result.status
    if final_status == "pass" and not acceptance.get("complete"):
        final_status = "fail"
        if "mandatory acceptance evidence is incomplete" not in result.limitations:
            result.limitations.append("mandatory acceptance evidence is incomplete")
    return PilotOutcome(
        domain=domain,
        mode=mode,
        status=final_status,
        fixture_rel=fixture_rel,
        fixture_sha256=fixture_sha,
        receipt_id=receipt_id,
        checks=[
            {
                "criterion_key": c.criterion_key,
                "passed": c.passed,
                "outcome": c.effective_outcome(),
                "details": dict(c.details),
                "limitations": c.limitations,
            }
            for c in result.checks
        ],
        evidence_ids=evidence_ids,
        findings=[r for r in finding_records],
        limitations=result.limitations,
        resources=result.resources,
        report_ref=report_ref,
        duration_seconds=time.time() - started,
        acceptance=acceptance,
        blocked_reason=result.blocked_reason,
    )


def profile_limits(contract: TaskContract) -> tuple[int, int]:
    return contract.budgets.max_findings, contract.budgets.max_output_bytes


def _registry() -> dict[str, Evaluator]:
    from .ml import evaluate as ml_evaluate
    from .research import evaluate as research_evaluate
    from .website import evaluate as website_evaluate

    return {
        "ml": ml_evaluate,
        "research": research_evaluate,
        "website": website_evaluate,
    }
