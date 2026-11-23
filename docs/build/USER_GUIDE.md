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
```

`test` applies the patch in a disposable git worktree, runs the full offline
suite and records evidence. `merge` requires a clean tree, the same base commit,
a passing review record and owner approval. It fast-forwards locally and never
pushes. Provider-driven autonomous authoring remains M2 work.

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
scrubbed runner with output/time caps; it is not a sandbox. Cloud providers,
credentials and external spend are not implemented.

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
