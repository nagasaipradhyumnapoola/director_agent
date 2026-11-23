# DIRECTOR

Local-first, harness-neutral project supervisor. DIRECTOR owns the task
contract, durable state, policy/effect gateway, budgets, evidence and completion
decision; domain evaluators supply domain-specific checks. It is not a model
wrapper and not a coding-only tool.

**Release:** `v0.1-supervised-three-domain` (M0 substrate + M1 website, ML and
research/document pilots on controlled fixtures). See
[BUILD_STATUS](docs/BUILD_STATUS.md) for exact evidence and limits.

## Quick start (Windows PowerShell)

```powershell
.\install.ps1
.\.venv\Scripts\Activate.ps1
python -m director --help

# Initialize a project, then inspect it
python -m director init --root . --name my-project --domain general
python -m director doctor
python -m director status

# Controlled release demo: clean must pass, broken must fail
python -m director demo --domains general,website,ml,research --modes clean,broken
```

No global settings are changed, no service is installed and no provider is
contacted. `install.ps1` / `install.sh` create a local venv and add an offline
source-path entry (no network, no global package install); `uninstall.ps1` /
`uninstall.sh` remove it without touching project state. If you prefer a package
install, use `python -m pip install -e . --no-deps` (build tooling may be needed).

## What works now

- Durable task contracts, acceptance criteria, SQLite WAL state, schema v3.
- Default-deny policy gateway, owner-bound grants, atomic budget reservations.
- Fenced investigation queue (lease token + generation), retry caps, recovery.
- Deterministic artifact scan: secrets redacted, links/hardlinks/junctions
  rejected, case-insensitive syntax checks, unsupported formats never pass.
- Evidence receipts bound to subject hash/check version/params/policy/revision;
  latest outcome wins; freshness re-verified before acceptance.
- Bounded context packets with untrusted-content labeling and unknown headroom.
- FTS5 lexical memory with provenance, taint, deletion and re-ingest.
- Bounded MCP stdio server (newline JSON-RPC 2.0) with strict argument validation.
- 24/7 deterministic worker: start/stop/pause/resume, heartbeat, zero model calls.
- Supervised self-improvement proposal engine with owner approvals; no autonomous
  code writes.
- Three controlled pilots:
  - website: static checks + real headless Chromium journey, keyboard, mobile
    overflow, console errors, external requests, accessibility tree;
  - ML: manifest/rights, split leakage, target-derived feature, baseline vs
    held-out accuracy, two-run determinism, slices, resources;
  - research: dated sources, verbatim claim quotes, conflicts, trusted
    calculation tolerance, rendered HTML/DOCX inspection.

## What is deliberately not claimed

- No autonomous model/provider routing or spend; no live web research.
- No kernel/container sandbox; process-level supervision only.
- No native OpenCode/Claude/Codex tool-call test; MCP protocol/SDK is tested and
  adapters are generated for review.
- No billion-token memory scale, A2A, computer-use or general domain competence.
- No self-modifying code yet; the 24/7 engine produces proposals only.

Read [SELF_IMPROVEMENT.md](docs/SELF_IMPROVEMENT.md) for the gated path to
autonomous self-coding.

## Harness integration

The stable boundary is local MCP:

```powershell
python -m director mcp serve --db <project>/.director/director.db
```

Generate a reviewable adapter (nothing auto-enabled):

```powershell
python -m director adapters generate --host generic  --out .mcp
python -m director adapters generate --host opencode --out .opencode
python -m director adapters generate --host claude   --out .claude
python -m director adapters generate --host codex    --out .codex
```

See [HARNESS_INTEGRATION.md](docs/HARNESS_INTEGRATION.md).

## Commands

```text
init doctor status contract scan investigate worker findings evidence verify
waive memory preflight budget improve adapters pilot demo mcp
start stop pause resume recover checkpoint
```

Run `python -m director <command> --help` for options.

## Repository layout

```text
src/director/        core, CLI, MCP, domains, assets
fixtures/            controlled clean/broken pilots
tests/               offline suite (browser and MCP SDK tests included)
benchmarks/          measured smoke/ablation helpers
integrations/        generated adapter examples (none enabled)
docs/                research handoff + build docs + ledger
```

## Documentation

- [CONTEXT.md](CONTEXT.md) — low-token context for a new session.
- [Build status / evidence](docs/BUILD_STATUS.md)
- [Architecture](docs/build/ARCHITECTURE.md)
- [Security and threat model](docs/build/SECURITY.md)
- [User guide](docs/build/USER_GUIDE.md)
- [Compatibility matrix](docs/build/COMPATIBILITY.md)
- [Limitations](docs/build/LIMITATIONS.md)
- [Roadmap](docs/build/ROADMAP.md)
- [Self-improvement design](docs/SELF_IMPROVEMENT.md)
- [Original research handoff](docs/DIRECTOR_BLUEPRINT.md) and
  [research synthesis](docs/RESEARCH.md)

## License

MIT for the DIRECTOR application. Research-derived notices and upstream
attribution are preserved in [NOTICE](NOTICE) and `docs/research/licenses/`.
