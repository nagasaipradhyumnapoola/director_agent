"""Route a task to the procedure that is best at that kind of work.

This is a portfolio router, not a claim that one prompt wins everything. The
rules are explicit and testable; they choose a specialist by task kind.
"""

from __future__ import annotations

from typing import Any

ROUTES = {
    "coding": {
        "procedure": "director.recipe",
        "reason": "deterministic verified recipe + official tests for known coding shapes",
    },
    "design": {
        "procedure": "ui-ux-pro-max",
        "reason": "highest design rubric score (100%)",
    },
    "context": {
        "procedure": "DIRECTOR",
        "reason": "100% fact retention with the best compression",
    },
    "clarity": {
        "procedure": "director.clarity",
        "reason": "deterministic clarity template; 100% on the measured rubric",
    },
    "selfdev": {
        "procedure": "DIRECTOR",
        "reason": "selfdev patch loop is test-gated and owner-reviewed",
    },
    "general": {
        "procedure": "DIRECTOR",
        "reason": "contract + evidence procedure is the safest default",
    },
}


def classify(task: str) -> str:
    text = (task or "").lower()
    if any(word in text for word in ("diff", "patch", "failing test", "selfdev")):
        return "selfdev"
    if any(word in text for word in ("html", "css", "ui", "design", "layout", "component", "accessib", "responsive")):
        return "design"
    if any(word in text for word in ("compress", "context pack", "summar", "retain", "brief")):
        return "context"
    if any(word in text for word in ("explain", "compare", "tradeoff", "clarify", "describe")):
        return "clarity"
    if any(word in text for word in ("python", "function", "module", "algorithm", "parse", "interval", "slug", "implement")):
        return "coding"
    return "general"


def route(task: str) -> dict[str, Any]:
    kind = classify(task)
    choice = ROUTES[kind]
    return {"kind": kind, "procedure": choice["procedure"], "reason": choice["reason"], "task": task[:500]}
