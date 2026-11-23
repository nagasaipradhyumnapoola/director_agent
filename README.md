# DIRECTOR

Local-first, harness-neutral project supervisor. DIRECTOR owns the task
contract, durable state, policy/effect gateway, budgets, evidence and completion
decision; domain evaluators supply domain-specific checks. It is not a model
wrapper and not a coding-only tool.

**Release:** `v1.0.0-local-supervised` (production-hardened local single-user
scope; the original `v0.1-supervised-three-domain` M0+M1 work is included). See
the [v1 release notes](docs/build/V1_RELEASE.md),
[BUILD_STATUS](docs/BUILD_STATUS.md) and [evidence](docs/build/EVIDENCE.md) for
exact checks and limits.

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

- Durable task contracts, acceptance criteria, SQLite WAL state, schema v4.
- Default-deny policy gateway, owner-bound grants, atomic budget reservations.
- Fenced investigation queue (lease token + generation), retry caps, recovery.
- Deterministic artifact scan: secrets redacted, links/hardlinks/junctions
  rejected, case-insensitive syntax checks, unsupported formats never pass.
- Evidence receipts bound to subject hash/check version/params/policy/revision;
  latest outcome wins; freshness re-verified before acceptance.
- Bounded context packets with untrusted-content labeling and unknown headroom.
- FTS5 lexical memory with provenance, taint, deletion and re-ingest.
- Bounded MCP stdio server (newline JSON-RPC 2.0) with strict argument validation,
  plus a verified native OpenCode MCP connection.
- Production operations: verified ZIP backups/restore, OS-keychain secrets,
  health/doctor checks, schema migrations, install/uninstall.
- Model gateway: stub, owner command, loopback Ollama, and OpenAI-compatible
  HTTP with OS-keychain credentials and exact token/cost accounting. Cloud calls
  are default-denied and untested without an owner-supplied key.
- 24/7 deterministic worker: start/stop/pause/resume, heartbeat, zero model calls
  (model calls are explicit CLI/owner actions, not idle work).
- Supervised self-improvement: proposal engine plus `selfdev` execution path
  (patch → isolated git worktree → full tests → independent review → owner merge).
  It has been used to modify DIRECTOR itself; it never auto-pushes.
- Local model authoring: a loopback Ollama model can author a patch into the
  selfdev gates; a proposal→author→test queue is available.
- Autostart: optional per-user Startup-folder entry (no admin) starts the worker
  at logon; still only while the user session runs.
- Optional container runner: Docker-only, read-only source mount, no network,
  unprivileged user, dropped capabilities, memory/CPU/pid/output bounds. It is
  not a hardened microVM.
- Opt-in scheduled maintenance: the worker creates a verified ZIP backup and
  prunes old archives on a configured interval.
- Three controlled pilots:
  - website: static checks + real headless Chromium journey, keyboard, mobile
    overflow, console errors, external requests, accessibility tree;
  - ML: manifest/rights, split leakage, target-derived feature, baseline vs
    held-out accuracy, two-run determinism, slices, resources;
  - research: dated sources, verbatim claim quotes, conflicts, trusted
    calculation tolerance, rendered HTML/DOCX inspection.

## What is deliberately not claimed

- No autonomous model/provider routing or spend; no live web research.
- Process-level supervision by default; the optional Docker runner is bounded
  but not a hardened kernel/microVM sandbox.
- Native OpenCode MCP **connection and tool-call** are tested: `director
  director_status` executed through a loopback OpenAI-compatible proxy and the
  model reported the result. Claude/Codex native paths are not tested.
- No billion-token memory scale, A2A, computer-use or general domain competence.
- No autonomous cloud provider loop or cloud authoring without an owner key,
  grant and budget; local Ollama authoring exists and is gated.

Read [SELF_IMPROVEMENT.md](docs/SELF_IMPROVEMENT.md) for the gated path to
provider-driven self-coding.

## Self-modification (supervised)

DIRECTOR can improve its own code through a gated pipeline:

```powershell
python -m director selfdev propose --file var/selfdev/change.patch --title "Add X"
python -m director selfdev test --patch <id>          # isolated worktree + full offline suite
python -m director selfdev review --patch <id> --verdict pass --reviewer <name> --notes "..."
python -m director selfdev merge --patch <id>         # owner-gated fast-forward; no push

python -m director improve auto --proposal <id> --provider ollama \
  --model qwen2.5-coder:7b [--queue]
python -m director service install                    # logon autostart (Startup folder)
python -m director service status
python -m director service remove

python -m director maintenance enable --interval-hours 24 --keep 14
python -m director maintenance status|run|disable

python -m director container check
python -m director container run --image python:3.12-slim \
  --workdir . --timeout 300 -- python -c "print('isolated')"
```

The patch is validated against a path allowlist, applied in a disposable git
worktree at a recorded base commit, tested, and bound to evidence. Merge requires
a clean tree, unchanged HEAD, an independent review record and owner approval.
Local model authoring is gated; push and deploy remain owner actions.

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
waive memory preflight budget grant secret model improve selfdev backup health
service adapters pilot demo mcp version start stop pause resume recover checkpoint
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
- [v1 release notes](docs/build/V1_RELEASE.md)
- [Benchmarks](docs/build/BENCHMARKS.md)
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
