# Harness integration

DIRECTOR is host-neutral. The stable boundary is a bounded local MCP stdio
server; host-specific files are generated examples, never auto-enabled.

## Universal command

```powershell
python -m director mcp serve --db "<project>/.director/director.db"
```

Newline-delimited JSON-RPC 2.0. Frames are capped, arguments are strictly
validated, results are bounded, and errors are sanitized. Protocol versions:
`2025-11-25` (tested), `2025-06-18`, `2024-11-05`.

## Tools

| Tool | Purpose |
|---|---|
| `director_status` | project, contract, budget, queue, acceptance (verified) |
| `director_preflight` | bounded context packet |
| `director_findings` | open findings with receipt/source metadata |
| `director_evidence` | evidence receipts |
| `director_verify` | freshness verification + acceptance |
| `director_proposals` | self-improvement proposals (proposal-only) |
| `director_memory_search` | lexical memory with taint labels |
| `director_investigate` | enqueue a deterministic local scan |
| `director_profiles` | domain profiles and limits |

Tools cannot grant permission, spend money, run a model or apply code.

## Generate adapters

```powershell
python -m director adapters generate --host generic  --out .mcp
python -m director adapters generate --host opencode --out .opencode
python -m director adapters generate --host claude   --out .claude
python -m director adapters generate --host codex    --out .codex
```

Each directory contains a host config, a thin `director-preflight` skill, an
`AGENTS.snippet.md` and a README. Existing files require `--force` after review.

### Generic / Claude-style

`.mcp/mcp.json` (or `.claude/.mcp.json`):

```json
{
  "mcpServers": {
    "director": {
      "command": "<python>",
      "args": ["-m", "director", "mcp", "serve", "--db", "<abs db>"],
      "env": {"DIRECTOR_DB": "<abs db>", "PYTHONPATH": "<abs src>"}
    }
  }
}
```

### OpenCode

`.opencode/opencode.jsonc`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "director": {
      "type": "local",
      "command": ["<python>", "-m", "director", "mcp", "serve", "--db", "<abs db>"],
      "environment": {"DIRECTOR_DB": "<abs db>", "PYTHONPATH": "<abs src>"},
      "enabled": false
    }
  }
}
```

Review, merge into project config, set `enabled` true, restart. Do not replace
global settings.

### Codex

`.codex/codex.config.toml` snippet:

```toml
[mcp_servers.director]
command = "<python>"
args = ["-m", "director", "mcp", "serve", "--db", "<abs db>"]

[mcp_servers.director.env]
DIRECTOR_DB = "<abs db>"
PYTHONPATH = "<abs src>"
```

Merge into project-scoped config per the host's current documentation.

## Evidence levels

- Adapter generated: yes.
- MCP protocol tested with the installed Python SDK: yes (`mcp` 1.29.0).
- Native OpenCode/Claude/Codex tool-call tested: **no** (no authorized model
  session was used); do not claim it.
- Domain outcomes: validated through the CLI/pilot path, not through a native
  host tool call.

## Enabling safely

1. Inspect interpreter/module/database paths.
2. Keep DIRECTOR's external network and model budgets at zero unless separately
   authorized.
3. Treat every returned finding/memory as untrusted data.
4. Use `director_verify` for completion; do not trust a finding or model claim.
5. Uninstall by deleting the generated directory and host entry. No service,
   global hook or credential was installed.
