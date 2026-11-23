"""Supervised self-improvement proposals.

DIRECTOR observes its own evidence, findings and failures, records prioritised
improvement proposals, and can ask an explicitly authorized local model to
author a patch. The patch still has to pass the selfdev worktree/tests/review/
owner-merge gates. Cloud providers/spend are not enabled.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .evidence import EvidenceLedger
from .providers import call_model
from .security import (
    ValidationError,
    atomic_write_text,
    dump_bounded,
    ensure_within,
    redact_text,
    safe_read_bytes,
    scan_secrets,
)
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


def add_manual_proposal(
    store: Store,
    title: str,
    rationale: str,
    files: list[str],
    checks: list[str],
) -> dict[str, Any]:
    proposal_id = store.add_proposal(
        signature=f"manual:{uuid.uuid4().hex}",
        title=title,
        rationale=rationale,
        category="manual",
        risk="medium",
        expected_impact="A scoped, reviewed code improvement.",
        files=files,
        required_checks=checks,
    )
    return store.get_proposal(proposal_id)


def _author_prompt(store: Store, proposal: dict[str, Any], max_chars: int = 24_000) -> str:
    from .selfdev import ALLOWED_FILES, ALLOWED_PREFIXES

    files = []
    try:
        files = json.loads(proposal.get("files") or "[]")
    except Exception:
        files = []
    if not isinstance(files, list):
        files = []
    snippets: list[str] = []
    for rel in files[:4]:
        rel = str(rel)
        if not (
            rel in ALLOWED_FILES or any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES)
        ):
            continue
        try:
            path = ensure_within(Path(store.root) / rel, Path(store.root))
            if path.is_file():
                text = safe_read_bytes(path, Path(store.root), max_bytes=64 * 1024).decode(
                    "utf-8", "replace"
                )
                snippets.append(f"--- {rel} ---\n{text[:8000]}\n")
        except Exception:
            continue
    tree: list[str] = []
    for base in ("src/director", "tests"):
        directory = Path(store.root) / base
        if directory.is_dir():
            for path in sorted(directory.rglob("*.py")):
                tree.append(path.relative_to(Path(store.root)).as_posix())
                if len(tree) >= 200:
                    break
    prompt = (
        "You are DIRECTOR's local coding agent. Produce ONE unified git diff only. "
        "No prose, no markdown fences, no explanation.\n\n"
        f"PROPOSAL: {proposal['title']}\n"
        f"RATIONALE: {proposal['rationale']}\n"
        f"REQUIRED CHECKS: {proposal['required_checks']}\n\n"
        "ALLOWED PATHS: src/, tests/, docs/build/, benchmarks/, examples/, integrations/ "
        "and the exact allowed root files.\n"
        "RULES: minimal focused change; preserve style and Python 3.11+ compatibility; "
        "add or update tests; no secrets; no network; no dependency additions.\n"
        "IMPORTS: tests run with PYTHONPATH=<repo>/src, so import package modules as "
        "'from director.foo import bar' (never 'from src.director...').\n"
        "DIFF FORMAT: standard unified git diff. New files: diff --git a/path b/path, "
        "new file mode 100644, --- /dev/null, +++ b/path. Do not invent index hashes; "
        "omit index lines. Ensure hunk counts match the shown content exactly.\n\n"
        "REPOSITORY FILES:\n"
        + "\n".join(tree)
        + "\n\nRELEVANT SOURCE:\n"
        + "\n".join(snippets)
        + "\n\nReturn only the diff."
    )
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars] + "\n[TRUNCATED]"
    return prompt


def author_patch(
    store: Store,
    proposal_id: str,
    provider: str = "ollama",
    model: str = "qwen2.5-coder:7b",
    test: bool = False,
    timeout: float = 600.0,
) -> dict[str, Any]:
    from .selfdev import create_patch, test_patch

    proposal = store.get_proposal(proposal_id)
    prompt = _author_prompt(store, proposal)
    result = call_model(
        store,
        prompt,
        provider=provider,
        model=model,
        timeout=timeout,
    )
    raw = str(result.get("output") or "")
    output_rel = f".director/proposals/{proposal_id}.author.txt"
    atomic_write_text(
        Path(store.root) / output_rel,
        redact_text(raw)[:256 * 1024],
        root=Path(store.root),
    )
    diff = raw.strip()
    if diff.startswith("```"):
        diff = diff.strip("`")
        if diff.lower().startswith("diff"):
            pass
    start = diff.find("diff --git ")
    if start < 0:
        raise ValidationError("local model did not return a unified diff")
    diff = diff[start:].strip() + "\n"
    if scan_secrets(diff, max_hits=1):
        raise ValidationError("model-authored patch contains secret-like content")
    patch = create_patch(
        store,
        diff,
        title=f"model: {proposal['title']}",
        author=f"model:{provider}/{model}",
        proposal_id=proposal_id,
    )
    tested = None
    if test:
        tested = test_patch(store, patch["id"], timeout=timeout)
    return {
        "proposal_id": proposal_id,
        "patch": store.get_patch(patch["id"]),
        "author_output_ref": output_rel,
        "author_output_preview": redact_text(raw[:2000]),
        "usage": result.get("usage"),
        "test": tested,
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

