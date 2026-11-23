"""Supervised self-improvement proposals.

This is the safe 24/7 learning loop: DIRECTOR observes its own evidence,
findings and failures, then records prioritised improvement proposals. It does
NOT edit source code, spend money, call a model or apply changes. Approval only
records owner intent; autonomous code application is gated behind the M2
sandbox/provider contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceLedger
from .security import ValidationError, atomic_write_text, dump_bounded, redact_text
from .store import Store, utc_now

MAX_PROPOSALS_PER_RUN = 25


def _budget() -> dict[str, Any]:
    return {"model_calls": 0, "cost_usd": 0, "wall_seconds": 0, "external_network": False}


def _proposal(
    store: Store,
    *,
    signature: str,
    title: str,
    rationale: str,
    category: str,
    risk: str,
    expected_impact: str,
    files: list[str],
    checks: list[str],
    investigation_id: str | None,
    created: list[dict[str, Any]],
) -> None:
    if len(created) >= MAX_PROPOSALS_PER_RUN:
        return
    if store.find_proposal(signature) is not None:
        return
    proposal_id = store.add_proposal(
        signature=signature,
        title=title,
        rationale=rationale,
        category=category,
        risk=risk,
        expected_impact=expected_impact,
        files=files,
        required_checks=checks,
        investigation_id=investigation_id,
    )
    proposal = store.get_proposal(proposal_id)
    created.append(proposal)
    payload = {
        "schema": "director.proposal.v1",
        "generated_at": utc_now(),
        "proposal": proposal,
        "autonomy": {
            "level": "proposal-only",
            "requires_owner_approval": True,
            "code_write_allowed": False,
            "model_calls_allowed": 0,
            "reason": "v0.1 is supervised; code application needs the M2 sandbox and provider gates",
        },
        "budget": _budget(),
    }
    directory = Path(store.root) / ".director" / "proposals"
    text, _ = dump_bounded(payload, max_bytes=64 * 1024)
    atomic_write_text(directory / f"{proposal_id}.json", text, root=Path(store.root))


def generate_proposals(store: Store, investigation_id: str | None = None) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    findings = store.list_findings(limit=200)
    for finding in findings:
        if finding["severity"] not in {"critical", "high"}:
            continue
        signature = f"finding:{finding['kind']}:{finding.get('path') or 'project'}"
        _proposal(
            store,
            signature=signature,
            title=f"Address {finding['severity']} finding: {finding['kind']}",
            rationale=redact_text(finding["message"])[:1500],
            category="defect",
            risk="high" if finding["severity"] == "critical" else "medium",
            expected_impact="Remove a verified defect and add a regression check.",
            files=[finding["path"]] if finding.get("path") else [],
            checks=[
                "write a failing regression test that reproduces the finding",
                "run the full offline test suite",
                "run director scan and director verify",
            ],
            investigation_id=investigation_id,
            created=created,
        )

    acceptance = EvidenceLedger(store).criterion_status(verify=True)
    for criterion in acceptance.get("unmet", []):
        _proposal(
            store,
            signature=f"criterion:{criterion}",
            title=f"Collect current evidence for '{criterion}'",
            rationale="A mandatory acceptance criterion has no current passing evidence.",
            category="evidence",
            risk="medium",
            expected_impact="Move the task toward a verified completion instead of an unsupported claim.",
            files=[],
            checks=["run the criterion evaluator", "director evidence --verify", "director verify"],
            investigation_id=investigation_id,
            created=created,
        )

    stale: set[str] = set()
    for row in store.list_evidence(limit=500):
        if row["status"] != "stale":
            continue
        key = row["criterion_key"]
        if key in stale:
            continue
        stale.add(key)
        _proposal(
            store,
            signature=f"stale:{key}",
            title=f"Revalidate stale evidence for '{key}'",
            rationale="Subject, policy or contract changed after this evidence was recorded.",
            category="freshness",
            risk="medium",
            expected_impact="Prevent stale evidence from certifying the present state.",
            files=[row["subject_path"]] if row.get("subject_path") else [],
            checks=["rerun the evaluator against the current state", "director evidence --verify"],
            investigation_id=investigation_id,
            created=created,
        )

    for row in store.list_investigations(status="failed", limit=50):
        _proposal(
            store,
            signature=f"failed:{row['id']}",
            title=f"Harden failed investigation: {row['title'][:80]}",
            rationale=f"Investigation failed after {row['attempts']} attempt(s).",
            category="reliability",
            risk="medium",
            expected_impact="Turn a repeated failure into a tested, bounded check.",
            files=[],
            checks=["reproduce the failure locally", "add a regression test", "verify retry/fencing behaviour"],
            investigation_id=investigation_id,
            created=created,
        )

    for row in store.list_evidence(limit=500):
        if row["outcome"] != "blocked":
            continue
        signature = f"blocked:{row['criterion_key']}"
        _proposal(
            store,
            signature=signature,
            title=f"Resolve blocked prerequisite for '{row['criterion_key']}'",
            rationale=redact_text(row["limitations"])[:1000] or "An evaluator reported a missing prerequisite.",
            category="blocked",
            risk="high",
            expected_impact="Unblock a mandatory pilot without pretending it passed.",
            files=[],
            checks=["provide the missing local prerequisite", "rerun the pilot", "director verify"],
            investigation_id=investigation_id,
            created=created,
        )

    return {
        "created": [item["id"] for item in created],
        "created_count": len(created),
        "counts": store.proposal_counts(),
        "autonomy": "proposal-only; owner approval required; no code applied; zero model calls",
        "budget": _budget(),
    }


def apply_proposal(store: Store, proposal_id: str) -> dict[str, Any]:
    proposal = store.get_proposal(proposal_id)
    if proposal["status"] != "approved":
        raise ValidationError("owner approval is required before applying a proposal")
    return {
        "status": "blocked",
        "proposal_id": proposal_id,
        "reason": (
            "v0.1 does not apply code changes. Autonomous self-coding requires the M2 "
            "provider/keychain contract, a real sandbox, scoped budgets, a branch/worktree, "
            "independent review and an explicit owner authorization of the new release target."
        ),
        "next_steps": [
            "authorize an M2 self-improvement release target",
            "provide a scoped provider and budget; credentials in the OS keychain",
            "run the change in an isolated workspace with tests and independent review",
            "apply only after current evidence and owner approval",
            "never auto-push, deploy or spend beyond the cap",
        ],
        "code_write_allowed": False,
    }

