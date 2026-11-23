"""Deterministic demo: M0 substrate plus the three controlled M1 pilots."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import ArtifactScanner
from .domains import provision_pilot_grants, run_pilot
from .evidence import EvidenceLedger
from .models import (
    AcceptanceCriterion,
    Budgets,
    PermissionPolicy,
    Requirement,
    TaskContract,
)
from .security import atomic_write_text, dump_bounded
from .store import Store

DOMAIN_CRITERIA: dict[str, tuple[tuple[str, str, str], ...]] = {
    "general": (
        ("artifact.scan", "Static artifact scan has no high/critical finding and no unchecked format", "artifact_scan"),
    ),
    "website": (
        ("website.static", "Static HTML/CSS accessibility and network checks pass", "website_static"),
        ("website.journey", "Search, add-to-cart and checkout complete in a real browser", "website_journey"),
        ("website.keyboard", "Keyboard reaches and activates the primary action", "website_keyboard"),
        ("website.mobile", "No horizontal overflow at 390px or 1280px", "website_mobile"),
        ("website.network", "No external network requests", "website_network"),
        ("website.a11y", "Primary controls expose accessible roles and names", "website_a11y"),
    ),
    "ml": (
        ("ml.manifest", "Dataset manifest, rights and split specification are complete", "ml_manifest"),
        ("ml.leakage", "No split duplication or target-derived feature", "ml_leakage"),
        ("ml.heldout", "Held-out accuracy beats the baseline threshold", "ml_heldout"),
        ("ml.reproducible", "Two identical runs agree", "ml_reproducibility"),
        ("ml.slices", "Reported slices meet the minimum accuracy", "ml_slices"),
        ("ml.resources", "Resource and environment report recorded", "ml_resources"),
    ),
    "research": (
        ("research.sources", "Declared primary sources exist, are dated, and include a current source", "research_sources"),
        ("research.claims", "Claims map to sources with verbatim quotes", "research_claims"),
        ("research.calculation", "The calculation recomputes to the claimed value", "research_calculation"),
        ("research.conflicts", "Superseding evidence is acknowledged", "research_conflicts"),
        ("research.render", "Rendered answer has resolved citations and no placeholders", "research_render"),
    ),
}


def build_contract(project_id: str, domains: tuple[str, ...] | list[str]) -> TaskContract:
    requirements = []
    for domain in domains:
        criteria = DOMAIN_CRITERIA.get(domain)
        if criteria is None:
            raise ValueError("unknown domain for demo contract")
        requirements.append(
            Requirement(
                key=f"r.{domain}",
                text=f"Deliver and independently verify the controlled {domain} pilot.",
                domain=domain,
                criteria=tuple(
                    AcceptanceCriterion(key=key, description=description, evaluator=evaluator)
                    for key, description, evaluator in criteria
                ),
            )
        )
    return TaskContract(
        project_id=project_id,
        revision=1,
        intent=(
            "Demonstrate DIRECTOR v0.1 supervised core: state-bound evidence, default-deny "
            "budgets/policy, deterministic checks and three domain pilots on controlled fixtures."
        ),
        deliverables=tuple(f"{domain} pilot evidence" for domain in domains),
        constraints=(
            "local-only; zero model calls; no external network",
            "controlled fixtures; no production effects",
        ),
        non_goals=("autonomous provider routing", "billion-token scale", "general computer use"),
        assumptions=("the owner runs the demo locally",),
        domains=tuple(domains),
        requirements=tuple(requirements),
        budgets=Budgets(
            max_model_calls=0,
            max_cost_usd=0.0,
            max_wall_seconds=900,
            max_findings=500,
            max_scan_files=500,
            max_file_bytes=2 * 1024 * 1024,
        ),
        permissions=PermissionPolicy(
            allow_external_network=False,
            allow_cloud_spend=False,
            allowed_actions=(
                "read_artifact",
                "run_local_subprocess",
                "launch_browser",
            ),
        ),
        stopping_conditions=(
            "all mandatory criteria have current evidence or the run reports a block",
        ),
    )


def init_project(root: Path, name: str, domains: tuple[str, ...] | list[str]) -> Store:
    store = Store.open_or_create(root, name)
    if store.latest_contract() is None:
        store.save_contract(build_contract(store.project_id, domains))
    return store


def run_general(store: Store, fixture_rel: str, mode: str) -> dict[str, Any]:
    scan = ArtifactScanner(store).scan(roots=[fixture_rel], criterion_key="artifact.scan")
    acceptance = EvidenceLedger(store).criterion_status(verify=True)
    return {
        "domain": "general",
        "mode": mode,
        "status": scan.outcome,
        "receipt_id": scan.receipt_id,
        "checks": [
            {
                "criterion_key": "artifact.scan",
                "outcome": scan.outcome,
                "passed": scan.outcome == "pass",
                "details": {
                    "files_scanned": scan.files_scanned,
                    "coverage": scan.coverage,
                    "unknown_formats": scan.unknown_formats,
                    "partial": scan.partial,
                },
            }
        ],
        "findings": scan.findings,
        "acceptance": acceptance,
        "limitations": scan.limitations,
        "resources": {
            "duration_seconds": round(scan.duration_seconds, 4),
            "bytes_scanned": scan.bytes_scanned,
            "model_calls": store.model_calls_spent(),
        },
        "report_ref": scan.report_ref,
        "fixture_rel": fixture_rel,
    }


def run_demo(
    repo_root: Path,
    domains: tuple[str, ...] = ("general", "website", "ml", "research"),
    modes: tuple[str, ...] = ("clean", "broken"),
) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    run_root = Path(repo_root) / "var" / "demo" / run_id
    results: list[dict[str, Any]] = []
    for mode in modes:
        for domain in domains:
            source = Path(repo_root) / "fixtures" / domain / mode
            if not source.is_dir():
                results.append(
                    {
                        "domain": domain,
                        "mode": mode,
                        "status": "blocked",
                        "blocked_reason": "fixture directory missing",
                    }
                )
                continue
            project_root = run_root / mode / domain
            project_root.mkdir(parents=True, exist_ok=True)
            fixture_target = project_root / "fixture"
            if fixture_target.exists():
                shutil.rmtree(fixture_target)
            shutil.copytree(source, fixture_target)
            store = init_project(project_root, f"DIRECTOR demo {domain} {mode}", (domain,))
            try:
                if domain == "general":
                    outcome = run_general(store, "fixture", mode)
                else:
                    provision_pilot_grants(store, domain, "fixture")
                    pilot = run_pilot(store, domain, "fixture", mode)
                    outcome = pilot.to_dict()
            finally:
                store.close()
            outcome["project_root"] = str(project_root)
            results.append(outcome)
    expectations: list[dict[str, Any]] = []
    for result in results:
        mode = result.get("mode")
        status = result.get("status")
        if mode == "clean":
            ok = status == "pass"
            expectation = "clean fixture must pass"
        else:
            ok = status in {"fail", "partial"}
            expectation = "broken fixture must fail or report a partial check"
        expectations.append(
            {
                "domain": result.get("domain"),
                "mode": mode,
                "expected": expectation,
                "observed": status,
                "met": bool(ok),
            }
        )
    summary = {
        "schema": "director.demo.v1",
        "run_id": run_id,
        "run_root": str(run_root),
        "release_target": "v0.1-supervised-three-domain",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
        "expectations": expectations,
        "expectations_met": all(item["met"] for item in expectations),
        "model_calls": sum(float((r.get("resources") or {}).get("model_calls") or 0) for r in results),
        "limitations": [
            "Controlled fixtures only; not a broad domain-support claim.",
            "Website pilot uses one local Chromium-family browser and one scripted journey.",
            "Desktop DOCX/HTML inspection is structural, not editorial.",
        ],
    }
    text, truncated = dump_bounded(summary, max_bytes=2 * 1024 * 1024)
    if truncated:
        summary["_summary_truncated"] = True
        text, _ = dump_bounded(summary, max_bytes=2 * 1024 * 1024)
    atomic_write_text(run_root / "summary.json", text, root=Path(repo_root))
    return summary

