# Compatibility matrix

Evidence levels are not interchangeable:

`designed → implemented → statically inspected → unit-tested → integration-tested
→ protocol-tested → native-client tested → domain-validated → operationally supported`

| Surface | Level in v0.1 | Evidence / limits |
|---|---|---|
| Python core (contracts/store/policy/budget/evidence) | implemented, unit + integration tested | 57 offline tests, Windows 11 + Python 3.14 |
| Fenced queue / recovery | implemented, integration tested | lease expiry, stale publish rejection, retry cap, concurrent claim |
| Policy gateway / grants | implemented, tested | default deny, deny precedence, expiry, payload/revision binding, `allowed_actions` |
| Artifact scanner | implemented, adversarial tested | links/hardlinks/junctions, uppercase extensions, secrets, unsupported formats, partial bounds |
| Context packet / memory | implemented, tested | bounded output, untrusted labels, deletion/re-ingest, project isolation |
| MCP stdio server | **protocol tested** | official Python `mcp` 1.29.0 `ClientSession` round trip; protocol negotiated `2025-11-25`; oversized frame before parse; strict args |
| Generic MCP config (`mcp.json`) | adapter generated | not native-host tested |
| OpenCode adapter | adapter generated | `opencode.jsonc` disabled by default; native `director_*` tool call **not tested** (no authorized model session) |
| Claude adapter (`.mcp.json`) | adapter generated | not native-host tested |
| Codex adapter (`codex.config.toml`) | adapter generated | not native-host tested |
| Website pilot | **domain-validated** | real headless Chrome 158 CDP journey on controlled fixtures; Node 24; Edge present but not separately validated |
| ML pilot | **domain-validated** | controlled clean/leaky fixtures; pure-Python CPU; leakage/held-out/repro/slices |
| Research/document pilot | **domain-validated** | controlled conflicting dated sources; HTML render inspected; DOCX optional |
| Self-improvement proposals | implemented, tested | proposal-only, owner approval, zero model calls |
| Supervised selfdev executor | implemented, integration tested | path allowlist, isolated worktree, full tests, independent review record, owner merge; no push; provider authoring NOT implemented |
| 24/7 worker | implemented, integration tested | detached start/heartbeat/pause/resume/stop; requires running host |
| Autonomous provider routing | designed only (M2) | not implemented; zero spend default |
| Native hooks/plugins for hosts | designed only | no host plugin installed; MCP is the tested boundary |
| Billion-token memory | roadmap (M4) | not implemented or measured |
| A2A / computer-use | roadmap | not implemented |
| POSIX | code paths present | not validated in this release |
| Container/VM sandbox | not implemented | process-level containment only |

## MCP protocol note

Research observed spec `2026-07-28`; the installed SDK is `mcp` 1.29.0 with
`LATEST_PROTOCOL_VERSION=2025-11-25`. The server advertises supported versions
`2025-11-25`, `2025-06-18`, `2024-11-05`, echoes a requested supported version,
and falls back to `2025-11-25`. Compatibility is claimed only for the tested
installed pairing.

## Host configuration shapes generated

- **generic / Claude-style**: `{"mcpServers": {"director": {"command", "args", "env"}}}`
- **OpenCode**: `{"mcp": {"director": {"type": "local", "command": [...], "environment": {...}, "enabled": false}}}`
- **Codex**: `[mcp_servers.director]` TOML with `command`, `args`, `[mcp_servers.director.env]`

All generated with the local database path and a local interpreter. Nothing is
enabled globally or installed automatically.

## Enforcement coverage (separate axis)

| Path | Coverage |
|---|---|
| DIRECTOR scanner/queue/runner/budget/grant | gateway mediated |
| MCP tools | gateway mediated for read/enqueue; no permission/spend/code-apply |
| External host actions outside DIRECTOR | not covered; host permissions remain authoritative |
| Adapter/skill instructions | advisory only |

## Not claimed

General domain competence, production readiness, a security certification,
perfect retrieval, 24/7 operation across host shutdown, autonomous self-coding,
or compatibility with every MCP/host version.
