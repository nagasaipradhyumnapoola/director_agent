from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from director.models import Budgets
from director.store import BudgetExceeded, ConflictError, FencedWriteError, Store
from tests.helpers import make_contract, new_store


def test_contract_roundtrip_and_conflicting_revision(tmp_path):
    store = new_store(tmp_path, criteria=("c1",))
    latest = store.latest_contract()
    assert latest is not None
    assert latest[0]["revision"] == 1
    assert [c["key"] for c in store.criteria()] == ["c1"]
    with pytest.raises(ConflictError):
        store.save_contract(
            make_contract(store.project_id, criteria=("c2",), revision=1)
        )
    store.close()


def test_lease_fencing_and_reclaim(tmp_path):
    store = new_store(tmp_path)
    investigation_id = store.enqueue_investigation("scan", "hypothesis", dedupe_key="one")
    first = store.claim_next("w1", lease_seconds=0.01)
    assert first is not None and first.generation == 1
    time.sleep(0.03)
    with pytest.raises(FencedWriteError):
        store.complete_investigation(first)
    second = store.claim_next("w2", lease_seconds=30)
    assert second is not None
    assert second.id == investigation_id
    assert second.generation == 2
    with pytest.raises(FencedWriteError):
        store.publish(first, [], [])
    store.complete_investigation(second)
    row = store.list_investigations(status="completed")
    assert len(row) == 1
    store.close()


def test_retry_cap_includes_crashes(tmp_path):
    store = new_store(tmp_path)
    store.enqueue_investigation("scan", "hypothesis", max_attempts=2)
    for _ in range(2):
        claim = store.claim_next("worker", lease_seconds=0.001)
        assert claim is not None
        time.sleep(0.01)
    assert store.claim_next("worker", lease_seconds=30) is None
    failed = store.list_investigations(status="failed")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 2
    store.close()


def test_concurrent_claim_has_one_winner(tmp_path):
    store = new_store(tmp_path)
    store.enqueue_investigation("scan", "hypothesis", dedupe_key="race")
    store.close()
    root = tmp_path / "project"
    barrier = threading.Barrier(8)
    results: list[str | None] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        local = Store.open(root)
        try:
            barrier.wait(timeout=10)
            claim = local.claim_next(f"w{index}", lease_seconds=30)
            with lock:
                results.append(claim.id if claim else None)
        finally:
            local.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len([item for item in results if item]) == 1


def test_budget_reservation_is_atomic(tmp_path):
    store = new_store(tmp_path)
    store.set_budget_limit("findings", 10)
    store.close()
    root = tmp_path / "project"
    barrier = threading.Barrier(20)
    successes: list[str] = []
    failures: list[int] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        local = Store.open(root)
        try:
            barrier.wait(timeout=10)
            try:
                reservation = local.reserve_budget("findings", 1, 1, note=f"t{index}")
                with lock:
                    successes.append(reservation)
            except BudgetExceeded:
                with lock:
                    failures.append(index)
        finally:
            local.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(successes) == 10
    assert len(failures) == 10
    verify = Store.open(root)
    status = {row["unit"]: row for row in verify.budget_status()}
    assert status["findings"]["reserved"] == 10
    assert status["findings"]["available"] == 0
    verify.close()


def test_event_dedupe_and_memory_delete(tmp_path):
    store = new_store(tmp_path)
    first = store.record_event("file.changed", "path:a", {"a": 1})
    second = store.record_event("file.changed", "path:a", {"a": 2})
    assert first == second
    assert len(store.pending_events()) == 1
    source = store.add_memory_source("alpha beta gamma evidence", "doc", tainted=True)
    assert store.search_memory("alpha")
    store.forget_memory_source(source)
    assert store.search_memory("alpha") == []
    store.close()


def test_memory_can_be_reingested_after_forget(tmp_path):
    store = new_store(tmp_path)
    source = store.add_memory_source("repeatable evidence text", "doc")
    store.forget_memory_source(source)
    assert store.search_memory("repeatable") == []
    source2 = store.add_memory_source("repeatable evidence text", "doc")
    assert source2
    assert store.search_memory("repeatable")
    store.close()


def test_project_memory_isolation(tmp_path):
    one = new_store(tmp_path / "one")
    two = new_store(tmp_path / "two")
    one.add_memory_source("only in project one", "doc")
    assert one.search_memory("project")
    assert two.search_memory("project") == []
    one.close()
    two.close()


def test_checkpoint_roundtrip(tmp_path):
    store = new_store(tmp_path)
    checkpoint_id = store.save_checkpoint({"next": "test"})
    latest = store.latest_checkpoint()
    assert latest is not None
    assert latest["id"] == checkpoint_id
    assert latest["payload"]["next"] == "test"
    store.close()
