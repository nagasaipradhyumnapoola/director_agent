from __future__ import annotations

from benchmarks import orchestrate_eval


def test_orchestrator_end_to_end_passes():
    assert orchestrate_eval.main() == 0
