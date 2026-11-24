from __future__ import annotations

import json
import subprocess

import pytest

from director.agent import run_agent
from director.models import PermissionPolicy
from director.policy import PolicyDenied
from tests.helpers import new_store


def _store(tmp_path):
    return new_store(
        tmp_path,
        permissions=PermissionPolicy(
            allowed_actions=("read_artifact", "run_local_subprocess", "launch_browser")
        ),
    )


def _actions(*items):
    seq = iter(items)
    return lambda _prompt: next(seq)


def test_agent_reads_and_finishes(tmp_path):
    store = _store(tmp_path)
    try:
        (tmp_path / "project" / "README.md").write_text("hello evidence\n", encoding="utf-8")
        result = run_agent(
            store,
            "inspect the readme",
            model_fn=_actions(
                json.dumps({"tool": "read_file", "path": "README.md"}),
                json.dumps({"tool": "finish", "summary": "read it"}),
            ),
            max_steps=4,
        )
        assert result["status"] == "finished"
        assert result["summary"] == "read it"
        assert result["steps"] == 2
        assert "hello evidence" in json.dumps(result["transcript"])
    finally:
        store.close()


def test_agent_rejects_path_escape(tmp_path):
    store = _store(tmp_path)
    try:
        result = run_agent(
            store,
            "try escape",
            model_fn=_actions(
                json.dumps({"tool": "read_file", "path": "../outside.txt"}),
                json.dumps({"tool": "finish", "summary": "blocked"}),
            ),
            max_steps=3,
        )
        assert "escapes the project" in json.dumps(result["transcript"])
        assert result["status"] == "finished"
    finally:
        store.close()


def test_agent_command_allowlist_blocks(tmp_path):
    store = _store(tmp_path)
    try:
        from director.policy import PolicyGateway

        PolicyGateway(store).grant("director.agent", "run_local_subprocess", "project", 1)
        result = run_agent(
            store,
            "try a command",
            model_fn=_actions(
                json.dumps({"tool": "run_command", "argv": ["rm", "-rf", "x"]}),
                json.dumps({"tool": "finish", "summary": "blocked"}),
            ),
            max_steps=3,
        )
        assert "command not allowed" in json.dumps(result["transcript"])
    finally:
        store.close()


def test_agent_routes_and_uses_recipe(tmp_path):
    store = _store(tmp_path)
    try:
        result = run_agent(
            store,
            "dispatch the work",
            model_fn=_actions(
                json.dumps({"tool": "route", "task": "Design an accessible card"}),
                json.dumps({"tool": "recipe", "name": "slugify", "args": ["Café"]}),
                json.dumps({"tool": "finish", "summary": "dispatched"}),
            ),
            max_steps=4,
        )
        transcript = json.dumps(result["transcript"])
        assert "ui-ux-pro-max" in transcript
        assert "cafe" in transcript
        assert result["status"] == "finished"
    finally:
        store.close()


def test_agent_auto_orchestrates_design_and_clarity(tmp_path):
    store = _store(tmp_path)
    try:
        result = run_agent(
            store,
            "Design an accessible card; explain the worktree vs container tradeoff",
            model_fn=lambda _prompt: (_ for _ in ()).throw(AssertionError("model should not be called")),
            max_steps=1,
        )
        assert result["status"] == "finished"
        assert result["mode"] == "deterministic_orchestrator"
        assert result["transcript"][0]["observation"]["executed"] == 2
    finally:
        store.close()


def test_agent_requires_model_grant(tmp_path):
    store = _store(tmp_path)
    try:
        with pytest.raises(PolicyDenied):
            run_agent(store, "inspect", provider="stub", max_steps=1)
    finally:
        store.close()


def test_agent_proposes_a_patch(tmp_path):
    store = _store(tmp_path)
    try:
        root = tmp_path / "project"
        (root / ".gitignore").write_text(".director/\nvar/\n", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "x.py").write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=root, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=root, capture_output=True)
        (root / "src" / "x.py").write_text("value = 2\n", encoding="utf-8")
        diff = subprocess.run(["git", "diff"], cwd=root, capture_output=True, text=True).stdout
        (root / "src" / "x.py").write_text("value = 1\n", encoding="utf-8")

        result = run_agent(
            store,
            "propose a patch",
            model_fn=_actions(
                json.dumps({"tool": "propose_patch", "title": "change value", "diff": diff}),
                json.dumps({"tool": "finish", "summary": "proposed"}),
            ),
            max_steps=3,
        )
        assert result["status"] == "finished"
        transcript = json.dumps(result["transcript"])
        assert "patch_" in transcript
        assert "changed_files" in transcript
    finally:
        store.close()
