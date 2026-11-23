from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

import pytest

from director import cli
from director.backup import create_backup, restore_backup, verify_backup
from director.keychain import available, delete_secret, get_secret, set_secret
from director.store import Store
from tests.helpers import new_store


def test_keychain_roundtrip_or_skip(tmp_path):
    ok, _backend = available()
    if not ok:
        pytest.skip("OS keychain unavailable")
    store = new_store(tmp_path)
    name = "test/" + uuid.uuid4().hex
    try:
        set_secret(store.project_id, name, "not-a-real-secret")
        assert get_secret(store.project_id, name) == "not-a-real-secret"
        delete_secret(store.project_id, name)
        assert get_secret(store.project_id, name) is None
    finally:
        store.close()


def test_backup_verify_and_restore_to_new_project(tmp_path):
    store = new_store(tmp_path)
    source_id = store.add_memory_source("backup roundtrip evidence", "doc", path="docs/note.md")
    backup = create_backup(store)
    backup_path = Path(store.root) / backup["backup"]
    assert backup_path.is_file()
    verified = verify_backup(backup_path)
    assert verified["integrity"] == "ok"
    target = tmp_path / "restored"
    restored = restore_backup(backup_path, target)
    assert restored["project_id"] == store.project_id
    store.close()
    reopened = Store.open(target)
    try:
        assert reopened.project_id == restored["project_id"]
        results = reopened.search_memory("backup roundtrip")
        assert results
    finally:
        reopened.close()


def test_cli_secret_and_health(tmp_path, capsys, monkeypatch):
    root = tmp_path / "prod"
    root.mkdir()
    assert cli.main(["init", "--root", str(root), "--name", "prod", "--domain", "general"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(sys, "stdin", io.StringIO("local-secret-value\n"))
    assert cli.main(["secret", "set", "--root", str(root), "--name", "provider/test"]) == 0
    capsys.readouterr()
    assert cli.main(["secret", "status", "--root", str(root), "--name", "provider/test"]) == 0
    capsys.readouterr()
    assert cli.main(["health", "--root", str(root), "--json"]) == 0
    health = capsys.readouterr().out.strip().splitlines()[-1]
    assert '"ok": true' in health
    assert cli.main(["secret", "delete", "--root", str(root), "--name", "provider/test"]) == 0
