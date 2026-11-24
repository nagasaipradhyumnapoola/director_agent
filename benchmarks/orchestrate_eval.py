"""End-to-end orchestrator evaluation: plan → route → execute → grade."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from director.orchestrator import execute_task  # noqa: E402
from benchmarks import matrix_tasks  # noqa: E402


def main() -> int:
    cases = [
        ("Implement a Python slugify function", {"args": ["Straße", 80]}, lambda out: out == "strasse"),
        ("Implement a Python slugify function", {"args": ["Café déjà vu"]}, lambda out: out == "cafe-deja-vu"),
        ("Parse a duration", {"args": ["1h30m"]}, lambda out: out == 5400),
        ("Merge the intervals", {"args": [[(1, 3), (2, 6)]]}, lambda out: out == [(1, 6)]),
    ]
    results = []
    for task, payload, check in cases:
        result = execute_task(task, payload)
        ok = result["status"] == "executed" and check(result["output"])
        results.append({"task": task, "payload": payload, "status": result["status"], "ok": ok, "detail": result.get("recipe")})

    design = execute_task("Design an accessible release card")
    design_grade = matrix_tasks.design_rubric(design["output"])
    results.append({"task": "design", "status": design["status"], "ok": design_grade["ok"], "detail": f"{design_grade['raw']}/{design_grade['max']}"})

    clarity = execute_task("Explain the worktree vs container tradeoff")
    clarity_grade = matrix_tasks.clarity_rubric(clarity["output"])
    results.append({"task": "clarity", "status": clarity["status"], "ok": clarity_grade["ok"], "detail": f"{clarity_grade['raw']}/{clarity_grade['max']}"})

    context = execute_task("Compress this brief", {"facts": dict(matrix_tasks.CONTEXT_FACTS)})
    context_grade = matrix_tasks.context_rubric(context["output"])
    results.append({"task": "context", "status": context["status"], "ok": context_grade["ok"], "detail": f"{context_grade['retention']:.0%} retention / {context_grade['compression']:.0%} compression"})

    passed = sum(1 for item in results if item["ok"])
    payload = {
        "kind": "orchestrator_e2e",
        "steps": len(results),
        "passed": passed,
        "rate": round(passed / len(results), 4),
        "results": results,
        "note": "Plan → route → execute → grade. Deterministic recipes/templates; no model call.",
    }
    out = ROOT / "benchmarks" / "results" / "orchestrate_eval.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Orchestrator end-to-end",
        "",
        f"Plan → route → execute → grade: **{passed}/{len(results)}**.",
        "",
        "| Task | Status | Result |",
        "|---|---|---|",
    ]
    for item in results:
        lines.append(f"| {item['task']} | {item['status']} | {item['detail']} |")
    lines += ["", "No model call. Coding and clarity/design/context are deterministic recipes or templates."]
    (out.with_suffix(".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
