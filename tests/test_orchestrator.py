from __future__ import annotations

from director.orchestrator import execute, execute_task, plan


def test_orchestrator_executes_code_recipe():
    result = execute_task("Write a Python slugify function", {"args": ["Straße", 80]})
    assert result["status"] == "executed"
    assert result["recipe"] == "slugify"
    assert result["output"] == "strasse"


def test_orchestrator_executes_design_clarity_and_context():
    design = execute_task("Design an accessible status card")
    assert design["recipe"] == "design_card"
    assert "<!doctype html>" in design["output"]
    clarity = execute_task("Explain the worktree vs container tradeoff")
    assert "filesystem" in clarity["output"].lower()
    context = execute_task("Compress this brief", {"facts": {"project": "ORBIT-7", "budget": "$48,000"}})
    assert "ORBIT-7" in context["output"]
    assert "$48,000" in context["output"]


def test_orchestrator_plans_multiple_steps():
    steps = plan("Write a slugify function\nDesign a card")
    assert [step["kind"] for step in steps] == ["coding", "design"]
    result = execute("Write a slugify function\nDesign a card", [{"args": ["Hello"]}, {}])
    assert result["steps"] == 2
    assert result["executed"] == 2
    assert result["results"][0]["output"] == "hello"
