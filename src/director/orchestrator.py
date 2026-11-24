"""Plan → route → execute for a small set of verified task shapes.

The orchestrator is deterministic where a verified recipe exists (coding,
design card, clarity template, context pack). For open-ended tasks it returns a
plan and the selected procedure; the caller can hand that to `director agent` or
a model. It does not merge, push or claim unverified work.
"""

from __future__ import annotations

from typing import Any

from .recipes import clear_tradeoff, context_pack, design_card, run_recipe
from .router import route


def _code_recipe(task: str, payload: dict[str, Any]) -> str | None:
    explicit = payload.get("recipe")
    if explicit:
        return str(explicit)
    text = (task or "").lower()
    if "slug" in text:
        return "slugify"
    if "duration" in text or "parse" in text and "time" in text:
        return "parse_duration"
    if "interval" in text:
        return "merge_intervals"
    return None


def plan(goal: str) -> list[dict[str, Any]]:
    if not goal or not goal.strip():
        raise ValueError("goal is empty")
    parts = [part.strip(" -0123456789.)") for part in goal.replace(";", "\n").splitlines() if part.strip()]
    if not parts:
        parts = [goal.strip()]
    return [route(part) for part in parts]


def execute_task(task: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    choice = route(task)
    kind = choice["kind"]
    try:
        if kind == "coding":
            recipe = _code_recipe(task, payload)
            if recipe:
                args = payload.get("args") or []
                if not isinstance(args, list):
                    raise ValueError("args must be a list")
                return {"route": choice, "status": "executed", "recipe": recipe, "output": run_recipe(recipe, args)}
            return {"route": choice, "status": "planned", "note": "No verified recipe; hand to the coding agent or model."}
        if kind == "design":
            return {"route": choice, "status": "executed", "recipe": "design_card", "output": design_card()}
        if kind == "clarity":
            return {
                "route": choice,
                "status": "executed",
                "recipe": "clear_tradeoff",
                "output": clear_tradeoff(
                    payload.get("topic") or "running an untrusted coding patch",
                    payload.get("first") or "a git worktree",
                    payload.get("second") or "a Docker container",
                    payload.get("filesystem") or "mount the source read-only and keep the worktree disposable",
                    payload.get("network") or "disable network access and block outside requests",
                    payload.get("privilege") or "run unprivileged with capabilities dropped",
                ),
            }
        if kind == "context":
            facts = payload.get("facts")
            if not isinstance(facts, dict):
                raise ValueError("context route needs a facts object")
            return {"route": choice, "status": "executed", "recipe": "context_pack", "output": context_pack({str(k): str(v) for k, v in facts.items()})}
        return {"route": choice, "status": "planned", "note": "Hand to the selfdev/agent path; no deterministic recipe."}
    except Exception as exc:  # a bad payload is a result, not a crash
        return {"route": choice, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def execute(goal: str, payloads: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    steps = plan(goal)
    payloads = payloads or []
    results = []
    for index, step in enumerate(steps):
        payload = payloads[index] if index < len(payloads) and isinstance(payloads[index], dict) else {}
        results.append(execute_task(step["task"], payload))
    return {
        "goal": goal,
        "steps": len(steps),
        "executed": sum(1 for item in results if item["status"] == "executed"),
        "planned": sum(1 for item in results if item["status"] == "planned"),
        "results": results,
        "note": "Deterministic where a recipe exists; model/agent needed otherwise. No merge/push.",
    }
