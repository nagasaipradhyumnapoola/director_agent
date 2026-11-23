from __future__ import annotations

import json

import pytest

from director.adapter import SUPPORTED_HOSTS, generate
from director.security import PathSafetyError, ValidationError
from tests.helpers import new_store


def test_generate_all_host_adapters_without_enabling(tmp_path):
    store = new_store(tmp_path)
    root = store.root
    db = store.path
    try:
        for host in SUPPORTED_HOSTS:
            out = root / f".{host}-adapter"
            created = generate(host, out, root, db)
            assert created
            for rel in created:
                assert (root / rel).is_file()
            if host == "opencode":
                config = json.loads((out / "opencode.jsonc").read_text(encoding="utf-8"))
                assert config["mcp"]["director"]["enabled"] is False
            elif host == "codex":
                text = (out / "codex.config.toml").read_text(encoding="utf-8")
                assert "[mcp_servers.director]" in text
            elif host == "claude":
                config = json.loads((out / ".mcp.json").read_text(encoding="utf-8"))
                assert "director" in config["mcpServers"]
            else:
                config = json.loads((out / "mcp.json").read_text(encoding="utf-8"))
                assert "director" in config["mcpServers"]
            with pytest.raises(ValidationError):
                generate(host, out, root, db)
    finally:
        store.close()


def test_adapter_rejects_database_outside_project(tmp_path):
    store = new_store(tmp_path)
    root = store.root
    outside = tmp_path / "outside"
    outside.mkdir()
    other = new_store(tmp_path / "other")
    try:
        with pytest.raises((ValidationError, PathSafetyError)):
            generate("generic", root / ".adapter", root, other.path)
    finally:
        other.close()
        store.close()

