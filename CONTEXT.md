# DIRECTOR â€” agent context file

Read this first in a new session. It is the durable, low-token context for the
DIRECTOR build. Deeper evidence lives in `docs/BUILD_STATUS.md` and
`docs/build/`.

## Product

DIRECTOR is a local-first, persistent project supervisor. It owns the task
contract, durable state, policy/effect gateway, budget ledger, evidence and
completion decision. Domain evaluators supply domain-specific checks. It is
not a model wrapper, not a coding-only tool, and not an autonomous spender.

Release target: **v0.1-supervised-three-domain = M0 + M1**.

- M0: trustworthy local substrate (contracts, SQLite store, fenced queue,
  deterministic analysis, bounded context, evidence freshness, budgets,
  policy gateway, CLI/lifecycle/doctor/recovery).
- M1: website, small CPU-ML and research/document pilots sharing that core,
  using a narrow supervised runner with scoped grants and resource limits.
- M2â€“M4 (autonomous providers, measured upstream host composition, scale) are
  designed roadmap work, not shipped in v0.1.

## Non-negotiable invariants

1. Idle monitoring makes zero model calls; external network and cloud spend
   default off.
2. A model, retrieved document, imported finding, skill or child report can
   never grant permission or self-certify completion.
3. Every acceptance decision needs current, state-bound evidence; stale
   evidence is invalid.
4. Bound input frames before parsing, bound outputs before allocating, reject
   unknown arguments, redact secrets from errors/logs/receipts.
5. Symlinks, junctions, hardlinks, traversal, state files and oversized input
   are hostile until proven otherwise.
6. Queue claims use unique lease tokens + generations; expired/superseded
   workers cannot publish.
7. External-agent hooks are advisory unless a tested mediation path exists.
   DIRECTOR enforces only what it actually mediates.
8. Report blocked/failed/unknown honestly. A green tool exit is not a user
   outcome.

## Layout

```
src/director/
  security.py      bounds, paths, links, redaction, safe JSON
  models.py        task contract / criteria / budget dataclasses
  store.py         SQLite schema + repository + fenced queue + budgets
  policy.py        capability grants and effect gateway
  evidence.py      receipts, freshness, criterion acceptance
  context.py       bounded context packet
  memory.py        lexical memory with provenance/taint/deletion
  analysis.py      deterministic artifact scan
  runner.py        supervised subprocess runner (scoped env/time/output)
  cli.py           operator CLI
  mcp_server.py    bounded stdio MCP server
  adapter.py       host-neutral adapter generation (generic/OpenCode/Claude/Codex)
  opencode_adapter.py  compatibility wrapper
  lifecycle.py     detached worker, heartbeat, recovery
  improve.py       proposal-only self-improvement engine
  selfdev.py       patch -> isolated worktree -> tests -> review -> owner merge
  providers.py     local stub/command model gateway (gated, no cloud)
  domains/         base, website, ml, research pilots
fixtures/          controlled broken/clean pilot fixtures
tests/             offline tests (browser/MCP opt-in markers)
benchmarks/        measured smoke/ablation evidence
integrations/      reviewable host adapters (not auto-installed)
docs/build/        architecture, security, compatibility, limitations
```

State lives in `<project>/.director/director.db` (WAL). Never commit it.

## Commands

```
python -m director init --root . --name demo
python -m director doctor
python -m director status
python -m director contract set --file contract.json
python -m director scan
python -m director investigate --scan
python -m director findings
python -m director evidence
python -m director verify --all
python -m director budget set --unit model_calls --limit 0
python -m director memory add --path docs/RESEARCH.md
python -m director memory search "evidence"
python -m director preflight --query "next action"
python -m director adapters generate --host opencode --out .opencode
python -m director pilot run --domain website|ml|research --fixture <dir>
python -m director improve propose
python -m director improve list
python -m director grant add --actor director.model --grant-action model_call_local --resource provider:stub
python -m director model call --prompt "..." --provider stub
python -m director start          # 24/7 deterministic worker
python -m director stop
python -m director selfdev propose --file patch.diff --title "..."
python -m director selfdev test --patch <id> [--queue]
python -m director selfdev review --patch <id> --verdict pass --reviewer <name>
python -m director selfdev merge --patch <id>
python -m director version
python -m director mcp serve --db <path>
python -m director demo --domains general,website,ml,research --modes clean,broken
```

Run `python -m director --help` for the authoritative list.

## Self-improvement (current boundary)

The 24/7 worker is deterministic: it generates prioritized proposals, tests
queued selfdev patches, writes heartbeats and never makes idle model calls.

A supervised execution path exists: `director selfdev` accepts an
agent/human-authored patch, applies it in an isolated git worktree, runs the
full offline suite, requires an independent review record and owner approval,
then fast-forwards the merge. It never pushes/deploys.

`providers.py` adds a local model gateway (deterministic stub + owner-supplied
command) gated by contract `model_call_local`, an owner grant, budget and
secret-prompt refusal. Cloud providers/credentials/spend remain disabled.
Provider-driven autonomous authoring is not claimed; `improve apply` is blocked.

## Release commit

`e58dcb6` on `origin/main` (2026-11-24); code `5606419` (model gateway/grants),
`f439b16` (selfdev), `f867bd2` (v0.1).

## Evidence status

v0.1 is implemented and tested on this host for its controlled scope:
- 70 offline tests pass (including a real Chromium/CDP website journey, the
  official MCP SDK round trip, and the selfdev worktree pipeline).
- `python -m director demo ... --modes clean,broken`: all clean fixtures pass,
  all broken fixtures fail, zero model calls.
- Independent review found false-completion/policy defects; all high/critical
  findings were fixed and re-verified. Residual limitations are in
  `docs/build/LIMITATIONS.md`.

Exact commands, raw results, run ids and open limitations are in
`docs/BUILD_STATUS.md` and `docs/build/EVIDENCE.md`. That evidence, not this
summary, is the release ledger. Never claim a milestone from this file alone.

