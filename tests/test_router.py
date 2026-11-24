from __future__ import annotations

from director.router import classify, route


def test_router_classifies_code_design_context_clarity_selfdev():
    assert classify("Write a Python function to slugify text") == "coding"
    assert classify("Make an accessible responsive HTML card") == "design"
    assert classify("Compress this brief into a context pack") == "context"
    assert classify("Explain the tradeoff between worktree and container") == "clarity"
    assert classify("Fix the failing test with a selfdev patch") == "selfdev"
    assert classify("Do something vague") == "general"


def test_route_returns_procedure_and_reason():
    result = route("implement a python parser")
    assert result["kind"] == "coding"
    assert result["procedure"] == "director.recipe"
    assert result["reason"]
    assert route("design a landing page")["procedure"] == "ui-ux-pro-max"
    assert route("explain the tradeoff")["procedure"] == "director.clarity"
    assert route("compress a context")["procedure"] == "DIRECTOR"
