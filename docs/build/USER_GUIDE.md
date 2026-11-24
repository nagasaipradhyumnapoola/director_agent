# DIRECTOR user guide

## Install

Windows (no admin, no global settings, no network):

```powershell
.\install.ps1
.\.venv\Scripts\Activate.ps1
python -m director doctor
```

`install.ps1` creates a local venv and adds a `director-src.pth` source-path
entry; it does not fetch packages. For a package install instead:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . --no-deps
```

`install.sh` is the equivalent for POSIX shells. The package has no required
runtime dependencies; optional tools: Node + Chromium for the website pilot,
`python-docx` for DOCX render inspection, `pytest` and `mcp` for tests.

## Initialize a project

```powershell
python -m director init --root . --name my-project --domain general
python -m director doctor
python -m director status
```

`init` creates `<project>/.director/director.db` and a default contract for the
selected domain(s). For a custom contract:

```powershell
python -m director init --root . --contract examples/contract.example.json
python -m director contract show
python -m director contract set --file examples/contract.example.json
```

Contracts define intent, deliverables, constraints, non-goals, assumptions,
domains, requirements, mandatory criteria, budgets and permissions. Model calls,
cost and external network default to zero/off.

## Scan and investigate

```powershell
python -m director scan --path .
python -m director investigate --scan
python -m director investigate --run        # claim and run one queued scan
python -m director worker --once            # same, explicit one-shot worker
python -m director findings
python -m director findings --dismiss <id> --reason "..."
```

A clean scan is `pass`; high/critical findings or unsupported formats produce
`fail`/`partial`. Partial/unsupported is never reported as validated.

## Evidence and completion

```powershell
python -m director evidence
python -m director evidence --verify
python -m director verify                   # exit 0 only if all mandatory criteria are current
python -m director status                   # verifies freshness by default
python -m director status --no-verify       # explicit UNVERIFIED view
python -m director waive --criterion <key> --reason "..."
```

The latest evidence per criterion wins. A newer failing/blocked result
supersedes an older pass. Waivers are bound to the current contract revision and
become inactive when the contract changes.

## Pilots

```powershell
python -m director pilot list
python -m director pilot run --domain website  --fixture fixtures/website/clean
python -m director pilot run --domain ml       --fixture fixtures/ml/clean
python -m director pilot run --domain research --fixture fixtures/research/clean
```

Pilots need a contract that declares the domain and its criteria. The CLI
provisions scoped owner grants automatically for the requested fixture; this is
an owner action, not an evaluator self-grant. A pilot is `blocked` if a
prerequisite (Node/Chromium, clean fixture, policy) is missing.

### Website prerequisites

- `node` on PATH
- Chrome/Edge, or `DIRECTOR_BROWSER` pointing to a Chromium-family executable
- The fixture is served from `file://` with DNS resolution disabled and a
  disposable browser profile.

### ML notes

The trainer is a small stdlib logistic regression. It runs with `-I -P` so a
fixture file cannot shadow stdlib imports. Acceptance thresholds are DIRECTOR
constants, not fixture config.

## 24/7 worker

```powershell
python -m director start
python -m director status
python -m director pause
python -m director resume
python -m director stop
python -m director recover
python -m director checkpoint
```

The worker is deterministic: zero model calls, no external network. It processes
the fenced queue, scans, and generates improvement proposals. It requires a
running host; it does not continue after shutdown/sleep.

## Self-improvement

Proposals:

```powershell
python -m director improve propose
python -m director improve queue       # let the 24/7 worker generate proposals
python -m director improve list
python -m director improve show <id>
python -m director improve approve <id> --reason "reviewed"
python -m director improve reject <id> --reason "..."
python -m director improve apply <id>  # blocked; use selfdev
```

Supervised execution (agent/human-authored patch):

```powershell
python -m director selfdev propose --file change.patch --title "Add X"
python -m director selfdev test --patch <id>
python -m director selfdev test --patch <id> --queue   # 24/7 worker tests it
python -m director selfdev review --patch <id> --verdict pass --reviewer "reviewer" --notes "..."
python -m director selfdev merge --patch <id> --reason "owner approved"
python -m director selfdev list
python -m director selfdev cleanup

python -m director improve auto --proposal <id> --provider ollama \
  --model qwen2.5-coder:7b [--queue]
```

`test` applies the patch in a disposable git worktree, runs the full offline
suite and records evidence. `merge` requires a clean tree, the same base commit,
a passing review record and owner approval. It fast-forwards locally and never
pushes.

`improve auto` asks an authorized local Ollama model to author a diff, then runs
the same gates. `--queue` lets the 24/7 worker do the authoring/testing. A model
patch that passes tests can still be held by review for dead code or design
issues; that is intentional.

## Autostart

```powershell
python -m director service install            # at logon, current user
python -m director service status
python -m director service remove
```

This uses the per-user Startup folder when Task Scheduler is unavailable. It is
not a Windows service and runs only while the user is logged in.

## Scheduled backups

```powershell
python -m director maintenance enable --interval-hours 24 --keep 14
python -m director maintenance status
python -m director maintenance run
python -m director maintenance disable
```

When enabled, the running worker checks the interval (about once a minute),
creates a verified ZIP backup and prunes older archives. Maintenance is off by
default.

## Container runner

```powershell
python -m director container check
python -m director container run --image python:3.12-slim --workdir . `
  --timeout 300 -- python -c "print('isolated')"
```

This requires Docker and a project contract created with `init --allow-container`
plus an owner `container_run` grant. The source directory is mounted read-only,
networking is disabled unless `--network` is also allowed by the contract, and
the process runs as uid 65534 with all capabilities dropped and memory/CPU/pid
bounds. It is bounded isolation, not a hardened microVM. `selfdev` itself still
tests in a git worktree.

### Build the DIRECTOR image

```powershell
docker build -t director:local .
docker run --rm director:local --version
docker run --rm -v "${PWD}:/project" director:local status --root /project --json
```

The image runs unprivileged and mounts the project at `/project`. It is tested by
the `docker` CI job (build, version, init, status).

## Recipes and routing

```powershell
python -m director recipe list
python -m director recipe run --name slugify --args-json '["Straße", 80]'
python -m director route --task "Write a Python slugify function"
```

Recipes are deterministic, tested implementations for well-specified shapes
(`slugify`, `parse_duration`, `merge_intervals`). `route` selects the best
measured specialist for a task kind; it does not pretend one prompt wins
everything.

## Local agent loop

```powershell
python -m director grant add --actor director.model --grant-action model_call_local `
  --resource provider:ollama
python -m director grant add --actor director.agent --grant-action run_local_subprocess `
  --resource project
python -m director agent run --goal "Run the tests and propose a fix." `
  --provider ollama --model qwen2.5-coder:7b --steps 8
```

One JSON tool call per turn; bounded steps/time. Tools: list/read, allowlisted
command, browser capture, memory search/remember, propose patch, finish. It
cannot write project files directly, merge, push or self-grant. Patches go to the
normal selfdev gates.

## Control room

```powershell
python -m director ui --port 8765 --root .
```

Serves the landing page and console on loopback. The console calls
`/api/state` and shows the live project summary when `--root` is supplied;
otherwise it uses bundled demo data. Directory listings are blocked.

## Memory and preflight

```powershell
python -m director memory add --path docs/RESEARCH.md --title "research"
python -m director memory add --text "decision: use SQLite WAL" --title "decision"
python -m director memory search "evidence"
python -m director memory list
python -m director memory forget <source-id>

python -m director preflight --query "next action" --max-bytes 16000
```

Memory is lexical (FTS5), project-scoped, tainted and deletable. Retrieved text
is untrusted data in context packets, never instructions.

## Budgets

```powershell
python -m director budget status
python -m director budget set --unit model_calls --limit 0
python -m director budget set --unit wall_seconds --limit 600
```

Reservations are atomic. Exhaustion blocks work rather than over-spending.

## Owner grants and local models

Local model calls are default-denied. The contract must enable
`model_call_local`, an owner grant must match, and a model-call budget must be
available:

```powershell
python -m director grant add --actor director.model --grant-action model_call_local --resource provider:stub
python -m director model providers
python -m director model call --prompt "Summarize the current status" --provider stub
```

For an owner-supplied local command (no cloud provider):

```powershell
python -m director grant add --actor director.model --grant-action model_call_local --resource provider:command
python -m director model call --prompt "hello" --provider command --command-json '["python","-c","import sys; print(sys.argv[-1].upper())"]'
```

Prompts containing secret-like values are refused. The command runs in the
scrubbed runner with output/time caps; it is not a sandbox.

OpenAI-compatible endpoints use the same gate plus OS-keychain credentials:

```powershell
# store the key in the OS keychain (not config/stdin history)
python -m director secret set --name provider/openai
python -m director grant add --actor director.model --grant-action model_call `
  --resource provider:openai_compatible
python -m director model call --provider openai_compatible `
  --base-url https://api.example.com/v1 --model my-model `
  --api-key-secret provider/openai --price-input-per-million 1.0 `
  --price-output-per-million 2.0 --prompt "hello"
```

An external endpoint requires the contract to enable network and `model_call`;
a loopback endpoint uses `model_call_local`. The path is tested with a local
OpenAI-compatible mock; a real cloud provider has **not** been called because no
credentials/budget were supplied.

## Backups, secrets and health

```powershell
python -m director backup create
python -m director backup list
python -m director backup verify --file .director/backups/<file>.zip
python -m director backup restore --file <zip> --to ..\project-restored

python -m director secret set --name provider/openai   # value read from stdin
python -m director secret status --name provider/openai
python -m director secret delete --name provider/openai

python -m director health --json
```

Backups are ZIP archives with a consistent SQLite online backup and a SHA-256
manifest. Restore only writes to a new/empty directory. Secrets go to the OS
keychain (Windows Credential Locker), never project config or SQLite.

## MCP and host adapters

```powershell
python -m director mcp serve --db .director/director.db
python -m director adapters generate --host generic  --out .mcp
python -m director adapters generate --host opencode --out .opencode
python -m director adapters generate --host claude   --out .claude
python -m director adapters generate --host codex    --out .codex
```

Generated configs are disabled/for-review by default. Review paths and merge
into the host's project-scoped configuration. See
`docs/HARNESS_INTEGRATION.md`.

OpenCode 1.19.4 V1 loads the config, reports `director connected`, and successfully
invoked `director_director_status` through a loopback OpenAI-compatible proxy in
testing. The model returned the tool result. Claude/Codex native paths remain
untested; the CLI/MCP SDK path is the portable fallback.

## Demo (release evidence)

```powershell
python -m director demo --domains general,website,ml,research --modes clean,broken
```

Outcome: every clean fixture passes, every broken fixture fails, zero model
calls, exit 0. Raw summary is written under `var/demo/<run-id>/summary.json`.

## Troubleshooting

- `error: project not initialized` → run `init`.
- `doctor` fails `database_integrity` → restore a backup; do not edit the DB.
- Website pilot `blocked` → install Node/Chromium or set `DIRECTOR_BROWSER`.
- `verify` exit 2 → inspect `status`/`evidence`; re-run the affected check.
- `adapters generate` refuses → review the existing files and use `--force`.

## Uninstall

```powershell
.\uninstall.ps1
```

Removes the local venv/package entry. It does **not** delete project
`.director/` state, research files or generated adapters; remove those explicitly
after backup. No global settings, service or credentials were installed.

## Supported platforms

Windows 11 is the tested platform (Python 3.11+). POSIX code paths exist but the
full pilot matrix has not been validated there. Browser and Node are optional
for the website pilot; ML/research/core work without them.
