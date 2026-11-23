from __future__ import annotations

import time

from director.lifecycle import process_one, recover, start, status, stop
from director.store import Store
from tests.helpers import new_store, write


def test_worker_once_and_lease_recovery(tmp_path):
    store = new_store(tmp_path)
    write(tmp_path / "project", "a.py", "print('ok')\n")
    store.enqueue_investigation(
        "scan",
        "scan should pass",
        payload={"action": "scan", "roots": ["."]},
        dedupe_key="scan:test",
    )
    result = process_one(store, worker="test")
    assert result["status"] == "completed"
    assert result["outcome"] == "pass"

    store.enqueue_investigation(
        "scan again",
        "stale lease",
        payload={"action": "scan", "roots": ["."]},
        dedupe_key="scan:stale",
    )
    claim = store.claim_next("dead", lease_seconds=0.001)
    assert claim is not None
    time.sleep(0.01)
    summary = recover(store)
    assert summary["reclaimed_leases"] == 1
    assert summary["checkpoint_id"].startswith("ckpt_")
    ready = store.list_investigations(status="ready")
    assert ready
    store.close()


def test_start_stop_worker_heartbeat(tmp_path):
    store = new_store(tmp_path)
    try:
        started = start(store)
        assert started["status"] == "running"
        deadline = time.time() + 12
        alive = False
        while time.time() < deadline:
            current = status(store)
            if current["heartbeat"]["present"] and current["pid_alive"]:
                alive = True
                break
            time.sleep(0.3)
        assert alive, "worker heartbeat did not appear"
        stopped = stop(store)
        assert stopped["status"] == "stopped"
        assert status(store)["lifecycle"]["status"] == "stopped"
    finally:
        try:
            stop(store)
        except Exception:
            pass
        store.close()
