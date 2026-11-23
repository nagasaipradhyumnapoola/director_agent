from __future__ import annotations

import pytest

from director.evidence import EvidenceLedger
from director.models import PermissionPolicy
from director.policy import PolicyDenied, PolicyGateway
from director.security import ValidationError
from director.store import Store
from tests.helpers import make_contract, new_store, write


def test_policy_default_deny_allow_deny_and_binding(tmp_path):
    store = new_store(
        tmp_path,
        permissions=PermissionPolicy(
            allowed_actions=("read_artifact", "run_local_subprocess")
        ),
    )
    gateway = PolicyGateway(store)
    actor = "director.test"
    assert not gateway.check(actor, "run_local_subprocess", "fixture", 1).allowed
    payload = {"fixture_sha256": "abc"}
    gateway.grant(actor, "run_local_subprocess", "fixture", 1, payload=payload)
    assert gateway.check(actor, "run_local_subprocess", "fixture", 1, payload=payload).allowed
    assert not gateway.check(actor, "run_local_subprocess", "fixture", 1, payload={"other": 1}).allowed
    assert not gateway.check(actor, "run_local_subprocess", "fixture", 2, payload=payload).allowed
    gateway.grant(actor, "run_local_subprocess", "fixture", 1, effect="deny", payload=payload)
    assert not gateway.check(actor, "run_local_subprocess", "fixture", 1, payload=payload).allowed
    with pytest.raises(PolicyDenied):
        gateway.require(actor, "network_read", "example.com", 1)
    store.close()


def test_policy_expiry_and_read_boundary(tmp_path):
    store = new_store(tmp_path)
    gateway = PolicyGateway(store)
    gateway.grant(
        "actor",
        "run_local_subprocess",
        "fixture",
        1,
        expires_at="2000-01-01T00:00:00+00:00",
    )
    assert not gateway.check("actor", "run_local_subprocess", "fixture", 1).allowed
    assert gateway.check("reader", "read_artifact", "src/app.py", 1).allowed
    assert not gateway.check("reader", "read_artifact", "../outside.txt", 1).allowed
    store.close()


def test_policy_denied_path(tmp_path):
    store = None
    try:
        store = new_store(
            tmp_path,
            permissions=PermissionPolicy(denied_paths=("secret",)),
        )
        gateway = PolicyGateway(store)
        assert not gateway.check("reader", "read_artifact", "secret/file.txt", 1).allowed
    finally:
        if store is not None:
            store.close()


def test_evidence_freshness_on_content_policy_and_revision(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    write(tmp_path / "project", "file.txt", "one")
    ledger = EvidenceLedger(store)
    evidence = ledger.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="1",
        outcome="pass",
        subject_path="file.txt",
    )
    assert ledger.verify(evidence["id"])["fresh"] is True
    write(tmp_path / "project", "file.txt", "two")
    result = ledger.verify(evidence["id"])
    assert result["fresh"] is False
    assert "subject content changed" in result["reasons"]

    store2 = new_store(tmp_path / "second", criteria=("c1",))
    write(tmp_path / "second" / "project", "file.txt", "one")
    ledger2 = EvidenceLedger(store2)
    evidence2 = ledger2.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="1",
        outcome="pass",
        subject_path="file.txt",
    )
    PolicyGateway(store2).grant("director.test", "run_local_subprocess", "fixture", 1)
    assert ledger2.verify(evidence2["id"])["fresh"] is False
    store2.save_contract(make_contract(store2.project_id, criteria=("c1",), revision=2))
    assert ledger2.verify(evidence2["id"])["fresh"] is False
    store.close()
    store2.close()


def test_acceptance_requires_pass_and_current_evidence(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    ledger = EvidenceLedger(store)
    assert ledger.criterion_status()["complete"] is False
    ledger.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="1",
        outcome="fail",
    )
    assert ledger.criterion_status()["complete"] is False
    ledger.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="1",
        outcome="pass",
    )
    assert ledger.criterion_status()["complete"] is True
    store.close()


def test_latest_failure_supersedes_older_pass(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    ledger = EvidenceLedger(store)
    ledger.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="1",
        outcome="pass",
    )
    assert ledger.criterion_status()["complete"] is True
    ledger.record(
        criterion_key="c1",
        kind="test",
        collector="tests",
        check_name="test",
        check_version="2",
        outcome="fail",
    )
    status = ledger.criterion_status()
    assert status["complete"] is False
    assert status["criteria"][0]["latest_outcome"] == "fail"
    store.close()


def test_scan_evidence_invalidated_by_new_file(tmp_path):
    from director.analysis import ArtifactScanner

    store = new_store(tmp_path)
    write(tmp_path / "project", "safe.py", "print('ok')\n")
    scan = ArtifactScanner(store).scan()
    assert scan.outcome == "pass"
    ledger = EvidenceLedger(store)
    assert ledger.verify(scan.receipt_id)["fresh"] is True
    assert ledger.criterion_status()["complete"] is True
    write(tmp_path / "project", "leak.txt", "aws AKIAABCDEFGHIJKLMNOP\n")
    result = ledger.verify(scan.receipt_id)
    assert result["fresh"] is False
    assert "scanned tree changed" in result["reasons"]
    assert ledger.criterion_status()["complete"] is False
    store.close()


def test_malformed_grant_expiry_is_rejected(tmp_path):
    store = new_store(tmp_path)
    gateway = PolicyGateway(store)
    with pytest.raises(ValidationError):
        gateway.grant(
            "actor",
            "run_local_subprocess",
            "fixture",
            1,
            expires_at="not-a-date",
        )
    store.close()


def test_waiver_is_bound_to_contract_revision(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    store.waive_criterion("c1", "release waiver")
    assert EvidenceLedger(store).criterion_status()["complete"] is True
    store.save_contract(make_contract(store.project_id, criteria=("c1",), revision=2))
    status = EvidenceLedger(store).criterion_status()
    assert status["complete"] is False
    assert status["waived"] == {}
    store.close()


def test_owner_waiver_and_finding_metadata_requirements(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    store.waive_criterion("c1", "owner accepts the gap for this release")
    status = EvidenceLedger(store).criterion_status()
    assert status["complete"] is True
    assert status["criteria"][0]["waived"] is True
    with pytest.raises(ValidationError):
        store.add_finding(
            {
                "severity": "high",
                "kind": "x",
                "message": "missing receipt",
                "path": "file.txt",
                "source_sha256": "a" * 64,
                "evaluator_version": "v1",
            }
        )
    with pytest.raises(ValidationError):
        store.add_finding(
            {
                "severity": "high",
                "kind": "x",
                "message": "missing hash",
                "path": "file.txt",
                "evaluator_version": "v1",
                "receipt_id": "ev_x",
            }
        )
    finding_id = store.add_finding(
        {
            "severity": "high",
            "kind": "x",
            "message": "complete",
            "path": "file.txt",
            "source_sha256": "a" * 64,
            "evaluator_version": "v1",
            "receipt_id": "ev_x",
        }
    )
    row = store.list_findings()[0]
    assert row["id"] == finding_id
    assert row["receipt_id"] == "ev_x"
    store.close()
