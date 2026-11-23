from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

import pytest

from director import audit, cli
from director.backup import create_backup, prune_backups, restore_backup, verify_backup
from director.keychain import available, delete_secret, get_secret, set_secret
from director.maintenance import disable as maintenance_disable
from director.maintenance import enable as maintenance_enable
from director.maintenance import maybe_run as maintenance_maybe_run
from director.maintenance import status as maintenance_status
from director.service import install, remove, status
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


def test_scheduled_maintenance_creates_one_backup(tmp_path):
    store = new_store(tmp_path)
    try:
        enabled = maintenance_enable(store, interval_hours=24, keep=1)
        assert enabled["enabled"] is True
        assert maintenance_status(store)["due_in_seconds"] == 0.0
        first = maintenance_maybe_run(store)
        assert first is not None and first["backup"].endswith(".zip")
        assert maintenance_maybe_run(store) is None
        assert maintenance_status(store)["due_in_seconds"] > 0
        assert maintenance_disable(store)["enabled"] is False
        assert maintenance_maybe_run(store) is None
    finally:
        store.close()


def test_backup_prune_keeps_latest(tmp_path):
    store = new_store(tmp_path)
    try:
        first = create_backup(store)
        second = create_backup(store)
        result = prune_backups(store, keep=1)
        assert result["kept"] == 1
        assert len(result["deleted"]) >= 1
        remaining = list((Path(store.root) / ".director" / "backups").glob("*.zip"))
        assert len(remaining) == 1
        assert first["backup"] != second["backup"]
    finally:
        store.close()


def test_audit_log_redacts_and_reads(tmp_path):
    store = new_store(tmp_path)
    try:
        audit.log(store, "director.test", "probe", "secret-aws AKIAABCDEFGHIJKLMNOP", "ok")
        rows = audit.read(store, limit=10)
        assert rows
        assert rows[-1]["action"] == "probe"
        assert "AKIAABCDEFGHIJKLMNOP" not in str(rows[-1])
    finally:
        store.close()


def test_service_startup_folder_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    store = new_store(tmp_path)
    try:
        result = install(store)
        assert result["installed"] is True
        assert result["method"] in {"startup-folder", "task-scheduler"}
        checked = status(store)
        assert checked["installed"] is True
        removed = remove(store)
        assert removed["removed"] is True
        assert status(store)["installed"] is False
    finally:
        remove(store)
        store.close()


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
