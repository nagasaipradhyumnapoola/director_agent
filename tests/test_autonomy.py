from __future__ import annotations

import json

from director.autonomy import disable, enable, maybe_run, status
from director.improve import add_manual_proposal
from tests.helpers import new_store


def test_autonomy_enqueues_one_author_job_then_waits(tmp_path):
    store = new_store(tmp_path)
    try:
        proposal = add_manual_proposal(
            store,
            "Add a tested helper",
            "A local model can propose a small patch.",
            [],
            [],
        )
        enabled = enable(store, interval_minutes=60, max_per_day=2)
        assert enabled["enabled"] is True
        assert status(store)["due_in_seconds"] == 0.0

        first = maybe_run(store)
        assert first is not None
        assert first["status"] == "queued"
        assert first["proposal_id"]
        queued = [row for row in store.list_investigations(status="ready") if json.loads(row["payload"]).get("action") == "selfdev_author"]
        assert queued, "expected a ready selfdev author investigation"
        payload = json.loads(queued[-1]["payload"])
        assert payload["proposal_id"] == first["proposal_id"]
        assert payload["test"] is True

        # The interval is not due yet, so no second job.
        assert maybe_run(store) is None
        assert disable(store)["enabled"] is False
        assert maybe_run(store) is None
    finally:
        store.close()
