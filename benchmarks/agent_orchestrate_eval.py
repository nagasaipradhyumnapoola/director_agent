"""Agent-level end-to-end: the agent calls the orchestrator and grades the result."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from director.agent import run_agent  # noqa: E402
from director.store import Store  # noqa: E402
from benchmarks import matrix_tasks  # noqa: E402


def main() -> int:
    store = Store.open(ROOT)
    try:
        result = run_agent(
            store,
            "Design an accessible release card; explain the worktree vs container tradeoff",
            model_fn=lambda _prompt: (_ for _ in ()).throw(AssertionError("model must not be called")),
            max_steps=1,
        )
        observation = result["transcript"][0]["observation"]
        design = matrix_tasks.design_rubric(observation["results"][0]["output"])
        clarity = matrix_tasks.clarity_rubric(observation["results"][1]["output"])
        payload = {
            "kind": "agent_orchestrator_e2e",
            "mode": result.get("mode"),
            "status": result["status"],
            "steps": observation["executed"],
            "design": {"ok": design["ok"], "raw": design["raw"], "max": design["max"]},
            "clarity": {"ok": clarity["ok"], "raw": clarity["raw"], "max": clarity["max"]},
            "passed": int(design["ok"]) + int(clarity["ok"]),
            "total": 2,
            "note": "Agent calls the deterministic orchestrator; no model call.",
        }
        out = ROOT / "benchmarks" / "results" / "agent_orchestrate_eval.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        lines = [
            "# Agent → orchestrator end-to-end",
            "",
            f"Mode: `{payload['mode']}` · status: `{payload['status']}` · steps: {payload['steps']}",
            "",
            f"- Design: {design['raw']}/{design['max']}",
            f"- Clarity: {clarity['raw']}/{clarity['max']}",
            "",
            "The agent invoked the deterministic orchestrator and graded both outputs; no model call.",
        ]
        out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({k: payload[k] for k in ("mode", "status", "passed", "total")}, indent=2))
        return 0 if payload["passed"] == 2 else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
