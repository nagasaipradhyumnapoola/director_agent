# Compatibility matrix

Evidence levels are not interchangeable:

`designed → implemented → statically inspected → unit-tested → integration-tested
→ protocol-tested → native-client tested → domain-validated → operationally supported`

| Surface | Level in v1.0.0-local-supervised | Evidence / limits |
|---|---|---|
| Python core (contracts/store/policy/budget/evidence) | implemented, unit + integration tested | 57 offline tests, Windows 11 + Python 3.14 |
| Fenced queue / recovery | implemented, integration tested | lease expiry, stale publish rejection, retry cap, concurrent claim |
| Policy gateway / grants | implemented, tested | default deny, deny precedence, expiry, payload/revision binding, `allowed_actions` |
| Artifact scanner | implemented, adversarial tested | links/hardlinks/junctions, uppercase extensions, secrets, unsupported formats, partial bounds |
| Context packet / memory | implemented, tested | bounded output, untrusted labels, deletion/re-ingest, project isolation |
| MCP stdio server | **protocol tested** | official Python `mcp` 1.29.0 `ClientSession` round trip; protocol negotiated `2025-11-25`; oversized frame before parse; strict args |
| Generic MCP config (`mcp.json`) | adapter generated | not native-host tested |
| OpenCode adapter | **native connection + tool-call tested** | V1.19.4 connected and invoked `director_director_status` through the loopback OpenAI-compatible proxy; model returned `ACCEPTANCE=false` |
| Claude adapter (`.mcp.json`) | adapter generated | not native-host tested |
| Codex adapter (`codex.config.toml`) | adapter generated | not native-host tested |
| Website pilot | **domain-validated** | real headless Chrome 158 CDP journey on controlled fixtures; Node 24; Edge present but not separately validated |
| ML pilot | **domain-validated** | controlled clean/leaky fixtures; pure-Python CPU; leakage/held-out/repro/slices |
| Research/document pilot | **domain-validated** | controlled conflicting dated sources; HTML render inspected; DOCX optional |
| Self-improvement proposals | implemented, tested | proposal-only, owner approval, zero model calls |
| Supervised selfdev executor | implemented, integration tested | path allowlist, isolated worktree, full tests, independent review record, owner merge; no push; local Ollama authoring tested; cloud authoring NOT tested |
| Model gateway | implemented, tested | stub/command/Ollama; OpenAI-compatible HTTP with keychain and token/cost accounting; cloud path mock-tested, real cloud not called |
| Backups/restore | implemented, tested | consistent SQLite online backup, hashed manifest, integrity verify, non-destructive restore |
| OS keychain | implemented, tested | Windows Credential Locker round trip; no plaintext fallback |
| Health/doctor | implemented, tested | DB/schema/worker/acceptance/backups/keychain/disk checks |
| Autostart | implemented, tested | per-user Startup-folder fallback; requires user logon; not a Windows service |
| Model authoring | implemented, tested | local Ollama authored a patch into selfdev; weak patch rejected by review |
| Scheduled maintenance | implemented, tested | opt-in worker backup + prune on an interval |
| 24/7 patch testing | implemented, integration tested | worker claims queued `selfdev_test` jobs and records evidence |
| 24/7 worker | implemented, integration tested | detached start/heartbeat/pause/resume/stop; requires running host |
| Autonomous provider routing | designed only (M2) | not implemented; zero spend default |
| Native hooks/plugins for hosts | designed only | no host plugin installed; MCP is the tested boundary |
| Billion-token memory | roadmap (M4) | not implemented or measured |
| A2A / computer-use | roadmap | not implemented |
| POSIX | code paths present | not validated in this release |
| Container runner | implemented, tested | Docker 29.6.2; read-only mount, no network, uid 65534, cap-drop ALL; not a hardened microVM |
| Container image | implemented, tested | `director:local` 260MB; build + version/init/status; CI docker job |
| Control room UI | implemented, tested | static `web/`, loopback server, no directory listing, 85+ tests |
| Continuous autonomy | implemented, tested | opt-in proposal → author/test queue; owner merge required |

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
