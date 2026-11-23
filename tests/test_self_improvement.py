from __future__ import annotations

import json
from pathlib import Path

import pytest

from director.improve import apply_proposal, generate_proposals
from director.lifecycle import process_one
from director.security import ValidationError
from tests.helpers import new_store, write


def _seed_finding(store, root: Path) -> None:
    write(root, "src/bug.py", "def broken(:\n")
    sha = "a" * 64
    store.add_finding(
        {
            "severity": "high",
            "kind": "syntax_error",
            "message": "Python syntax error at line 1",
            "path": "src/bug.py",
            "source_sha256": sha,
            "evaluator_version": "test/1",
            "receipt_id": "ev_test",
        }
    )


def test_proposals_are_deterministic_bounded_and_deduplicated(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    _seed_finding(store, Path(store.root))
    result = generate_proposals(store)
    assert result["created_count"] >= 2
    assert result["budget"]["model_calls"] == 0
    assert "proposal-only" in result["autonomy"]
    proposals = store.list_proposals()
    assert any(p["category"] == "defect" for p in proposals)
    assert any(p["category"] == "evidence" for p in proposals)
    for proposal in proposals:
        assert proposal["autonomy_level"] == "proposal-only"
        artifact = Path(store.root) / ".director" / "proposals" / f"{proposal['id']}.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["autonomy"]["code_write_allowed"] is False
        assert data["autonomy"]["requires_owner_approval"] is True
    again = generate_proposals(store)
    assert again["created_count"] == 0
    store.close()


def test_owner_approval_does_not_apply_code(tmp_path):
    store = new_store(tmp_path)
    _seed_finding(store, Path(store.root))
    result = generate_proposals(store)
    proposal_id = result["created"][0]
    before = (Path(store.root) / "src" / "bug.py").read_text(encoding="utf-8")
    with pytest.raises(ValidationError):
        apply_proposal(store, proposal_id)
    approval_id = store.decide_proposal(proposal_id, "approved", decided_by="owner", reason="reviewed")
    assert approval_id.startswith("appr_")
    assert store.get_proposal(proposal_id)["status"] == "approved"
    applied = apply_proposal(store, proposal_id)
    assert applied["status"] == "blocked"
    assert applied["code_write_allowed"] is False
    after = (Path(store.root) / "src" / "bug.py").read_text(encoding="utf-8")
    assert before == after
    with pytest.raises(ValidationError):
        store.decide_proposal(proposal_id, "approved", decided_by="model")
    store.close()


def test_worker_processes_improve_investigation_with_zero_model_calls(tmp_path):
    store = new_store(tmp_path)
    _seed_finding(store, Path(store.root))
    model_calls = store.model_calls_spent()
    store.enqueue_investigation(
        "Generate self-improvement proposals",
        "Current failures imply work.",
        payload={"action": "improve"},
        dedupe_key="improve:test",
    )
    result = process_one(store, worker="test")
    assert result["claimed"] is True
    assert result["status"] == "completed"
    assert result["created_proposals"] >= 1
    assert store.model_calls_spent() == model_calls
    store.close()
