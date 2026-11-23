from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

import pytest

from director.demo import build_contract, run_demo
from director.domains import fixture_snapshot, provision_pilot_grants
from director.policy import PolicyGateway
from director.store import Store


def _repo(tmp_path: Path, domains: tuple[str, ...]) -> Path:
    repo = tmp_path / "repo"
    (repo / "fixtures").mkdir(parents=True)
    for domain in domains:
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "fixtures" / domain,
            repo / "fixtures" / domain,
        )
    return repo


def test_general_ml_research_clean_pass_broken_fail(tmp_path):
    repo = _repo(tmp_path, ("general", "ml", "research"))
    summary = run_demo(repo, domains=("general", "ml", "research"), modes=("clean", "broken"))
    assert summary["expectations_met"] is True
    assert summary["model_calls"] == 0
    by_key = {(item["domain"], item["mode"]): item for item in summary["results"]}
    assert by_key[("general", "clean")]["status"] == "pass"
    assert by_key[("general", "broken")]["status"] == "fail"
    assert by_key[("ml", "clean")]["status"] == "pass"
    assert by_key[("ml", "broken")]["status"] == "fail"
    assert by_key[("research", "clean")]["status"] == "pass"
    assert by_key[("research", "broken")]["status"] == "fail"

    leaky = by_key[("ml", "broken")]
    checks = {check["criterion_key"]: check for check in leaky["checks"]}
    assert checks["ml.leakage"]["passed"] is False
    assert checks["ml.heldout"]["passed"] is True
    assert checks["ml.heldout"]["details"]["test_accuracy"] >= 0.99
    assert "target_enc" in str(checks["ml.leakage"]["details"])


@pytest.mark.browser
def test_website_clean_pass_broken_fail(tmp_path):
    import shutil as _shutil

    if _shutil.which("node") is None:
        pytest.skip("node unavailable")
    candidates = [
        os.environ.get("DIRECTOR_BROWSER"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    if not any(candidate and Path(candidate).is_file() for candidate in candidates):
        pytest.skip("no Chromium-family browser")
    repo = _repo(tmp_path, ("website",))
    summary = run_demo(repo, domains=("website",), modes=("clean", "broken"))
    assert summary["expectations_met"] is True
    by_key = {(item["domain"], item["mode"]): item for item in summary["results"]}
    clean = by_key[("website", "clean")]
    broken = by_key[("website", "broken")]
    assert clean["status"] == "pass"
    assert broken["status"] == "fail"
    broken_checks = {check["criterion_key"]: check for check in broken["checks"]}
    assert broken_checks["website.journey"]["passed"] is False
    assert broken_checks["website.keyboard"]["passed"] is False
    assert broken_checks["website.mobile"]["passed"] is False
    assert broken_checks["website.network"]["passed"] is False
    assert broken_checks["website.a11y"]["passed"] is False
    assert any(item["kind"] == "website_console_error" for item in broken["findings"])

def test_research_nan_calculation_is_rejected(tmp_path):
    repo = _repo(tmp_path, ("research",))
    claims_path = repo / "fixtures" / "research" / "clean" / "claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    claims["calculation"]["tolerance"] = 1e12
    claims["calculation"]["claimed"] = 999
    claims_path.write_text(json.dumps(claims, indent=2), encoding="utf-8")
    summary = run_demo(repo, domains=("research",), modes=("clean",))
    result = summary["results"][0]
    checks = {check["criterion_key"]: check for check in result["checks"]}
    assert result["status"] == "fail"
    assert checks["research.calculation"]["passed"] is False


def test_research_answer_requires_current_citation(tmp_path):
    repo = _repo(tmp_path, ("research",))
    answer_path = repo / "fixtures" / "research" / "clean" / "answer.md"
    answer = answer_path.read_text(encoding="utf-8").replace("[s2]", "").replace("[s1]", "")
    answer_path.write_text(answer, encoding="utf-8")
    summary = run_demo(repo, domains=("research",), modes=("clean",))
    result = summary["results"][0]
    checks = {check["criterion_key"]: check for check in result["checks"]}
    assert result["status"] == "fail"
    assert checks["research.conflicts"]["passed"] is False
    assert checks["research.render"]["passed"] is False


def test_ml_thresholds_are_not_taken_from_fixture(tmp_path):
    repo = _repo(tmp_path, ("ml",))
    data_path = repo / "fixtures" / "ml" / "clean" / "data.csv"
    rows = list(csv.DictReader(data_path.open("r", encoding="utf-8")))
    fields = list(rows[0].keys())
    for index, row in enumerate(rows):
        row["label"] = "1" if index % 2 else "0"
    with data_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    config_path = repo / "fixtures" / "ml" / "clean" / "run_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["acceptance"] = {
        "heldout_margin_over_baseline": 0.0,
        "minimum_test_accuracy": 0.0,
        "minimum_slice_accuracy": 0.0,
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    summary = run_demo(repo, domains=("ml",), modes=("clean",))
    result = summary["results"][0]
    checks = {check["criterion_key"]: check for check in result["checks"]}
    assert result["status"] == "fail"
    assert checks["ml.heldout"]["passed"] is False
    assert checks["ml.heldout"]["details"]["fixture_declared_acceptance"]["minimum_test_accuracy"] == 0.0


def test_ml_fixture_cannot_shadow_stdlib(tmp_path):
    repo = _repo(tmp_path, ("ml",))
    marker = tmp_path / "shadow_marker.txt"
    shadow = repo / "fixtures" / "ml" / "clean" / "csv.py"
    shadow.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    summary = run_demo(repo, domains=("ml",), modes=("clean",))
    assert marker.exists() is False
    assert summary["results"][0]["status"] == "pass"


def test_provision_refreshes_an_insufficient_grant(tmp_path):
    repo = _repo(tmp_path, ("ml",))
    project_root = repo / "project"
    project_root.mkdir()
    shutil.copytree(repo / "fixtures" / "ml" / "clean", project_root / "fixture")
    store = Store.open_or_create(project_root, "ml-provision")
    try:
        store.save_contract(build_contract(store.project_id, ("ml",)))
        provision_pilot_grants(store, "ml", "fixture", timeout_seconds=1)
        provision_pilot_grants(store, "ml", "fixture")
        grants = [
            grant
            for grant in store.list_grants()
            if grant["action"] == "run_local_subprocess" and grant["effect"] == "allow"
        ]
        assert grants
        limits = [json.loads(grant["limits"])["timeout_seconds"] for grant in grants]
        assert max(limits) >= 120
        fixture_sha, _entries, _bytes = fixture_snapshot(project_root, "fixture")
        selected = PolicyGateway(store).check(
            "director.domain.ml",
            "run_local_subprocess",
            "fixture",
            1,
            payload={"fixture_sha256": fixture_sha},
        )
        assert selected.allowed
        assert json.loads(store.get_grant(selected.grant_id)["limits"])["timeout_seconds"] >= 120
    finally:
        store.close()
