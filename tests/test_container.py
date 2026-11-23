from __future__ import annotations

import pytest

from director.container import available, run
from director.models import Budgets, PermissionPolicy
from director.policy import PolicyDenied, PolicyGateway
from tests.helpers import new_store


def _store(tmp_path, allow_container=True):
    actions = ("read_artifact", "container_run") if allow_container else ("read_artifact",)
    return new_store(
        tmp_path,
        permissions=PermissionPolicy(allowed_actions=actions),
        budgets=Budgets(max_wall_seconds=120),
    )


def test_container_requires_contract_action(tmp_path):
    store = _store(tmp_path, allow_container=False)
    try:
        PolicyGateway(store).grant("director.container", "container_run", "container", 1)
        with pytest.raises(PolicyDenied):
            run(store, "python:3.12-slim", ["python", "-V"], tmp_path)
    finally:
        store.close()


def test_container_requires_owner_grant(tmp_path):
    store = _store(tmp_path)
    try:
        with pytest.raises(PolicyDenied):
            run(store, "python:3.12-slim", ["python", "-V"], tmp_path)
    finally:
        store.close()


def test_container_daemon_check():
    result = available()
    assert isinstance(result["available"], bool)
    if not result["available"]:
        pytest.skip("docker daemon not available: " + str(result.get("reason", ""))[:120])


def test_container_runs_read_only_without_network(tmp_path):
    state = available()
    if not state["available"]:
        pytest.skip("docker daemon not available")
    store = _store(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "probe.txt").write_text("mounted-ok", encoding="utf-8")
    try:
        PolicyGateway(store).grant("director.container", "container_run", "container", 1)
        result = run(
            store,
            "python:3.12-slim",
            [
                "python",
                "-c",
                (
                    "import os,socket;"
                    "print('uid', os.getuid());"
                    "print('read', open('/work/probe.txt').read().strip());"
                    "open('/work/write.txt','w').write('x')"
                ),
            ],
            work,
            timeout=120,
        )
        assert "uid 65534" in result["stdout"]
        assert "read mounted-ok" in result["stdout"]
        assert result["exit_code"] != 0
        assert "Read-only file system" in result["stderr"]
        assert result["network"] is False
        assert not (work / "write.txt").exists()
    finally:
        store.close()
