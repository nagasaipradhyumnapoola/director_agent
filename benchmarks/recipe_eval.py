"""Evaluate the deterministic DIRECTOR recipes against the same coding tests."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from director import recipes  # noqa: E402
from benchmarks import matrix_tasks  # noqa: E402

CASES = {
    "slugify": (
        "slugify",
        "import re\nimport unicodedata\n"
        "_TRANSLIT = {'Æ': 'AE', 'æ': 'ae', 'Œ': 'OE', 'œ': 'oe', 'Ø': 'O', 'ø': 'o', 'Ł': 'L', 'ł': 'l', 'Đ': 'D', 'đ': 'd', 'Ð': 'D', 'ð': 'd', 'Þ': 'TH', 'þ': 'th', 'ß': 'ss', 'ẞ': 'SS'}\n",
        matrix_tasks.SLUGIFY_TEST,
    ),
    "parse_duration": (
        "parse_duration",
        "import re\n_DURATION_UNITS = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}\n_DURATION_RANK = {'d': 4, 'h': 3, 'm': 2, 's': 1}\n",
        matrix_tasks.DURATION_TEST,
    ),
    "merge_intervals": ("merge_intervals", "", matrix_tasks.INTERVAL_TEST),
}


def main() -> int:
    results = []
    for name, (fn_name, header, test_source) in CASES.items():
        source = inspect.getsource(getattr(recipes, fn_name))
        code = header + source + "\n"
        grade = matrix_tasks.run_python_task(code, test_source)
        results.append({"recipe": name, "ok": grade["ok"], "detail": grade["detail"][-600:]})
    coding_passed = sum(1 for item in results if item["ok"])
    clarity_text = recipes.clear_tradeoff(
        "running an untrusted coding patch",
        "a git worktree",
        "a Docker container",
        "mount the source read-only and keep the worktree disposable",
        "disable network access and block outside requests",
        "run unprivileged with capabilities dropped",
    )
    clarity = matrix_tasks.clarity_rubric(clarity_text)
    results.append({"recipe": "clear_tradeoff", "ok": clarity["ok"], "score": clarity["score"], "detail": clarity["detail"]})
    passed = sum(1 for item in results if item["ok"])
    payload = {
        "kind": "deterministic_recipe_eval",
        "tasks": len(results),
        "passed": passed,
        "rate": round(passed / len(results), 4),
        "coding": {"passed": coding_passed, "tasks": len(CASES), "rate": round(coding_passed / len(CASES), 4)},
        "clarity": {"passed": 1 if clarity["ok"] else 0, "tasks": 1, "rate": 1.0 if clarity["ok"] else 0.0, "rubric": clarity["score"]},
        "results": results,
        "note": "No model call. Coding uses the official tests; clarity uses the official rubric.",
    }
    out = ROOT / "benchmarks" / "results" / "recipe_eval.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("tasks", "passed", "rate")}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
