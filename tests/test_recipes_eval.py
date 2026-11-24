from __future__ import annotations

from benchmarks import recipe_eval, router_score


def test_recipe_eval_passes_all_coding_tasks():
    assert recipe_eval.main() == 0


def test_router_score_is_a_strong_portfolio():
    assert router_score.main() == 0
