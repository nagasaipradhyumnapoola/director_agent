from __future__ import annotations

from pathlib import Path

from director.models import (
    AcceptanceCriterion,
    Budgets,
    PermissionPolicy,
    Requirement,
    TaskContract,
)
from director.store import Store


def make_contract(
    project_id: str,
    *,
    criteria: tuple[str, ...] = ("artifact.scan",),
    domain: str = "general",
    revision: int = 1,
    intent: str = "test intent",
    budgets: Budgets | None = None,
    permissions: PermissionPolicy | None = None,
) -> TaskContract:
    return TaskContract(
        project_id=project_id,
        revision=revision,
        intent=intent,
        deliverables=("deliverable",),
        constraints=(),
        non_goals=(),
        assumptions=(),
        domains=(domain,),
        requirements=(
            Requirement(
                key="r1",
                text="test requirement",
                domain=domain,
                criteria=tuple(
                    AcceptanceCriterion(key=key, description=key, evaluator="test")
                    for key in criteria
                ),
            ),
        ),
        budgets=budgets or Budgets(max_wall_seconds=60),
        permissions=permissions or PermissionPolicy(),
        stopping_conditions=(),
    )


def new_store(
    tmp_path: Path,
    criteria: tuple[str, ...] = ("artifact.scan",),
    permissions: PermissionPolicy | None = None,
    budgets: Budgets | None = None,
) -> Store:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    store = Store.open_or_create(root, "test-project")
    store.save_contract(
        make_contract(store.project_id, criteria=criteria, permissions=permissions, budgets=budgets)
    )
    return store


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

