from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from director.mcp_server import MAX_FRAME, SUPPORTED_PROTOCOLS
from tests.helpers import new_store


def _server_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _start(db_path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "director", "mcp", "serve", "--db", str(db_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_server_env(),
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def test_mcp_bounded_protocol_and_unknown_arguments(tmp_path):
    store = new_store(tmp_path)
    db = store.path
    store.close()
    process = _start(db)
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "director_status", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "director_status", "arguments": {"password": "sk-abcdefghijklmnopqrstuvwxyz0123456789"}}},
        {"jsonrpc": "2.0", "id": 6, "method": "ping"},
    ]
    payload = b"\n".join(json.dumps(line).encode("utf-8") for line in lines)
    oversized = b'{"pad":"' + b"a" * (MAX_FRAME + 1000) + b'"}\n'
    payload = payload + b"\n" + oversized
    stdout, stderr = process.communicate(payload, timeout=30)
    assert process.returncode == 0
    responses = [json.loads(line) for line in stdout.decode("utf-8").splitlines() if line.strip()]
    by_id = {item.get("id"): item for item in responses if item.get("id") is not None}
    assert by_id[1]["result"]["protocolVersion"] in SUPPORTED_PROTOCOLS
    tools = {tool["name"] for tool in by_id[2]["result"]["tools"]}
    assert {"director_status", "director_preflight", "director_findings", "director_evidence", "director_verify", "director_proposals"} <= tools
    status_payload = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert "project" in status_payload
    assert by_id[4]["error"]["code"] == -32602
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in json.dumps(by_id[4])
    assert by_id[6]["result"] == {}
    frame_errors = [item for item in responses if item.get("id") is None and item.get("error")]
    assert frame_errors
    assert frame_errors[0]["error"]["code"] == -32600


def test_mcp_unknown_method_and_reinitialize_after_frame_error(tmp_path):
    store = new_store(tmp_path)
    db = store.path
    store.close()
    process = _start(db)
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 3, "method": "not/a/method"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
    ]
    payload = b"\n".join(json.dumps(line).encode("utf-8") for line in lines) + b"\n"
    stdout, _ = process.communicate(payload, timeout=30)
    responses = [json.loads(line) for line in stdout.decode("utf-8").splitlines() if line.strip()]
    by_id = {item.get("id"): item for item in responses}
    assert by_id[1]["error"]["code"] == -32002
    assert by_id[2]["result"]["protocolVersion"] == "2025-11-25"
    assert by_id[3]["error"]["code"] == -32601
    assert by_id[4]["error"]["code"] == -32601


def test_mcp_sdk_roundtrip(tmp_path):
    mcp = pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    store = new_store(tmp_path)
    db = store.path
    store.close()

    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "director", "mcp", "serve", "--db", str(db)],
            env=_server_env(),
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion
                tools = await session.list_tools()
                assert any(tool.name == "director_status" for tool in tools.tools)
                result = await session.call_tool("director_status", {})
                text = result.content[0].text
                payload = json.loads(text)
                assert "project" in payload
                with pytest.raises(Exception):
                    await session.call_tool("director_status", {"unexpected": 1})

    asyncio.run(run())
