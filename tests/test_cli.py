from __future__ import annotations

import json
from pathlib import Path

from director import cli


def _json_output(capsys) -> dict:
    captured = capsys.readouterr()
    return json.loads(captured.out.strip().splitlines()[-1])


def test_cli_init_scan_queue_worker_memory_adapters(tmp_path, capsys):
    root = tmp_path / "cli"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("# clean project\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "config.json").write_text('{"ok": true}\n', encoding="utf-8")
    assert cli.main(["init", "--root", str(root), "--name", "cli", "--domain", "general"]) == 0
    init = _json_output(capsys)
    assert init["contract"]["domains"] == ["general"]
    assert cli.main(["doctor", "--root", str(root), "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["scan", "--root", str(root), "--path", "."]) == 0
    capsys.readouterr()
    assert cli.main(["investigate", "--root", str(root), "--scan"]) == 0
    capsys.readouterr()
    assert cli.main(["investigate", "--root", str(root), "--run"]) == 0
    run = _json_output(capsys)
    assert run["status"] == "completed"
    assert cli.main(["memory", "add", "--root", str(root), "--path", "README.md"]) == 0
    capsys.readouterr()
    assert cli.main(["memory", "search", "--root", str(root), "clean"]) == 0
    search = _json_output(capsys)
    assert search["results"]
    assert search["results"][0]["tainted"] == 1
    assert cli.main(["preflight", "--root", str(root), "--query", "clean", "--max-bytes", "4096"]) == 0
    packet = _json_output(capsys)
    assert packet["schema"] == "director.context.v1"
    assert cli.main(["verify", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["adapters", "generate", "--root", str(root), "--host", "generic", "--out", ".mcp"]) == 0
    adapters = _json_output(capsys)
    assert any(path.endswith("mcp.json") for path in adapters["created"])
    config = json.loads((root / ".mcp" / "mcp.json").read_text(encoding="utf-8"))
    assert "director" in config["mcpServers"]
    assert cli.main(["adapters", "generate", "--root", str(root), "--host", "generic", "--out", ".mcp"]) == 2
    capsys.readouterr()
    assert cli.main(["verify", "--root", str(root)]) == 2


def test_cli_broken_project_and_improvement_gate(tmp_path, capsys):
    root = tmp_path / "broken"
    root.mkdir()
    (root / "BAD.PY").write_text("def x(:\n", encoding="utf-8")
    (root / "leak.txt").write_text("aws AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8")
    assert cli.main(["init", "--root", str(root), "--name", "broken", "--domain", "general"]) == 0
    capsys.readouterr()
    assert cli.main(["scan", "--root", str(root), "--path", "."]) == 2
    capsys.readouterr()
    assert cli.main(["improve", "propose", "--root", str(root)]) == 0
    proposals = _json_output(capsys)
    assert proposals["created_count"] >= 1
    assert proposals["budget"]["model_calls"] == 0
    assert cli.main(["improve", "list", "--root", str(root)]) == 0
    listing = _json_output(capsys)
    proposal_id = listing["proposals"][0]["id"]
    assert cli.main(["improve", "approve", "--root", str(root), proposal_id, "--reason", "reviewed"]) == 0
    capsys.readouterr()
    assert cli.main(["improve", "apply", "--root", str(root), proposal_id]) == 2
    applied = _json_output(capsys)
    assert applied["status"] == "blocked"
    assert applied["code_write_allowed"] is False

