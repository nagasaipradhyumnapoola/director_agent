from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "benchmarks" / "results" / "skill_matrix.json"


def _module():
    spec = importlib.util.spec_from_file_location("bench_skill_report", ROOT / "benchmarks" / "skill_report.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_matrix_coverage_is_complete():
    report = _module()
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    runs = payload["runs"]
    tools = sorted({run["tool"] for run in runs})
    tasks = sorted({run["task"] for run in runs})
    seeds = len({run["seed"] for run in runs})
    assert report.validate(runs, tools, tasks, seeds) == []
    assert len(runs) == 7 * 7 * 2


def test_skill_report_has_task_winners_and_best_at():
    report = _module()
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    runs = payload["runs"]
    tools = sorted({run["tool"] for run in runs})
    tasks = sorted({run["task"] for run in runs})
    cards = report.per_tool(runs, tools, tasks)
    lead = report.leaders(cards)
    winners = report.task_winners(cards, tasks)
    assert set(cards) == set(tools)
    assert len(winners) == len(tasks)
    assert report.best_at("director", cards, lead)
    assert report.best_at("ui_ux", cards, lead) == ["design"]
