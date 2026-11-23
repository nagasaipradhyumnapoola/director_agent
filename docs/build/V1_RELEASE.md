# v1.0.0-local-supervised release

Date: 2026-11-24
Target: **local, single-user, supervised project supervision** on Windows.

This is the first production-hardened local release. "Production-ready" here
means a durable local tool with verified backups, OS-keychain secrets, health
checks, migrations, bounded I/O, evidence-gated completion and native MCP host
connection. It does **not** mean enterprise/multi-user/SaaS readiness, a kernel
sandbox, cloud autonomy or universal domain competence.

## Release gates met

| Gate | Evidence |
|---|---|
| Durable schema + additive migrations (v4) | unit/integration tests, fresh + migrated DBs |
| Default-deny actions, grants, budgets | policy/budget tests, owner grant CLI |
| State-bound evidence + latest-fail supersession | freshness and false-completion regressions |
| Verified backups + non-destructive restore | SQLite online backup, ZIP manifest hashes, integrity check, restore test |
| OS-keychain secrets | Windows Credential Locker round trip test |
| Health/doctor checks | DB integrity, schema, worker, acceptance, backups, keychain, disk |
| Local model gateway | stub + owner command, contract/grant/budget/secret gates |
| Supervised self-modification | isolated worktree, full suite, independent review, owner merge |
| Native OpenCode MCP connection | `opencode mcp list` shows `director connected` (1.19.4) |
| MCP protocol | official SDK round trip, bounded frames/args/results |
| Three domain pilots | clean fixtures pass; seeded broken fixtures fail |
| Packaging/install | wheel builds; offline source-path installer; uninstall |
| Test suite | 74 offline tests, browser and MCP SDK included |

## Explicit non-claims

- Not a kernel/container sandbox; process-level containment only.
- No cloud provider, provider credential, API spend or autonomous model loop.
- Native host **tool-call** behavior is not tested; only OpenCode connection.
- No multi-user auth, remote service, A2A, computer-use beyond the browser pilot.
- No billion-token memory scale or general domain certification.
- Python child processes and the owner command provider run with user privileges.

## Operator runbook

```powershell
.\install.ps1
.\.venv\Scripts\Activate.ps1

python -m director init --root . --name my-project --domain general
python -m director doctor
python -m director backup create
python -m director health --json

python -m director start        # optional 24/7 deterministic worker
python -m director status
python -m director backup verify --file .director/backups/<file>.zip
python -m director backup restore --file <zip> --to ..\project-restored

python -m director stop
```

Upgrade: keep a verified backup, replace the checkout/install, run
`python -m director doctor`; schema migrations are additive. Roll back the code
to the prior commit and restore a backup to a new directory if needed.

Uninstall: `.\uninstall.ps1` removes the local source entry/venv; project state
and backups are preserved. Delete them explicitly only after verifying a backup.

## Release evidence

`docs/build/EVIDENCE.md`, `docs/BUILD_STATUS.md`, `docs/build/evidence/`.
