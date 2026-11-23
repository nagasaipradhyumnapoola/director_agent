# Integration examples

These are reviewable examples with placeholders; they are **not enabled** and
were not installed automatically. Prefer generating them for your actual paths:

```powershell
python -m director adapters generate --host generic  --out .mcp
python -m director adapters generate --host opencode --out .opencode
python -m director adapters generate --host claude   --out .claude
python -m director adapters generate --host codex    --out .codex
```

Replace `<PYTHON>`, `<PROJECT>` and `<REPO>` before use. The universal boundary
is the local MCP stdio server:

```
<PYTHON> -m director mcp serve --db <PROJECT>/.director/director.db
```

Evidence levels: generated (yes), MCP protocol tested with the installed SDK
(yes), native host tool-call tested (no). Tools never grant permission or spend
money. See `docs/HARNESS_INTEGRATION.md`.
