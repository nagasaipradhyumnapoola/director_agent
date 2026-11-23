# DIRECTOR self-improvement

Goal: DIRECTOR should get better over time without pretending to be more
autonomous than it is. v0.1 now has two layers:

1. a **24/7 deterministic improvement engine** that observes evidence, findings
   and failures and records prioritised proposals;
2. a **supervised self-modification executor** (`director selfdev`) that accepts
   an agent/human-authored patch, tests it in an isolated git worktree, records
   independent review and requires owner approval before a local merge.

Provider-driven autonomous patch authoring and push/deploy are still gated.

## What runs 24/7 in v0.1

`director start` launches a detached local worker. It:

- makes **zero model calls** and no external network requests;
- claims fenced investigations from the durable queue;
- runs deterministic scans;
- generates improvement proposals from findings, stale evidence, unmet criteria,
  blocked pilots and failed investigations;
- tests queued `selfdev` patches in isolated worktrees (`selfdev test --queue`);
- writes a heartbeat, honours `pause`/`resume`/`stop`, and records checkpoints;
- survives restarts and reconciles expired leases.

This is real background supervision while the host is running. It is not a
promise of work after the machine sleeps, the process is killed or the budget is
exhausted.

## The improvement loop

```
events / findings / evidence freshness / pilot blocks
        |
        v
deterministic analysis (no model)
        |
        v
proposal queue  (category, risk, files, required checks, zero budget)
        |
        v
owner approve / reject  (durable approval record)
        |
        v
[v0.1 supervised execution]
validated patch -> isolated git worktree at base commit -> full offline tests
        -> independent review -> owner merge approval -> local fast-forward
        -> evidence receipts -> no auto-push/deploy
        |
        v  (future M2, gated)
provider/keychain -> autonomous patch authoring -> container/VM sandbox
```

Proposals are stored in SQLite and mirrored as bounded JSON under
`.director/proposals/`. Rejected proposals are not repeated. `director improve
apply` remains blocked because it would bypass the selfdev gates; use
`director selfdev` for reviewed execution.

## Commands

```powershell
python -m director improve propose
python -m director improve queue          # let the 24/7 worker generate them
python -m director improve list
python -m director improve show <id>
python -m director improve approve <id> --reason "..."
python -m director improve reject <id> --reason "..."
python -m director improve apply <id>     # blocked; use selfdev instead
python -m director selfdev propose --file patch.diff --title "..."
python -m director selfdev test --patch <id>
python -m director selfdev review --patch <id> --verdict pass --reviewer "..."
python -m director selfdev merge --patch <id>
python -m director start                  # detached deterministic worker
python -m director pause | resume | stop
python -m director recover
```

## Executed self-improvement (evidence)

The pipeline was used to modify DIRECTOR itself:

- patch `patch_cdc28362d02d4f2d998e82324ecc9df9` added a read-only `version`
  command and its test;
- the full offline suite passed in an isolated worktree at base commit
  `85d8209` (exit 0, ~99s);
- an independent reviewer returned PASS and verified patch integrity;
- owner approval was recorded, the change fast-forwarded as commit `f439b16`;
- the merged tree then passed **63/63** tests and the four-domain demo.

The author was this agent; no provider spend or automatic push occurred. This
is real supervised self-modification, not autonomous provider-driven coding.

The local model gateway (stub + owner command) is the next building block for
provider-driven authoring, but cloud providers/credentials remain disabled and
default-denied by policy and budget.

## Why provider-driven autonomous self-coding is still gated

The supervised executor exists, but making a model author and apply patches 24/7
without a human/agent-authored diff requires capabilities that are not part of
v0.1:

1. **A real isolation boundary.** A temp directory, worktree, command allowlist
   or scrubbed environment is not a security boundary. Self-modifying code needs
   an OS/container/VM sandbox with narrow mounts, network policy, non-privileged
   identity, process-tree termination and CPU/RAM/time/output caps.
2. **Authorized providers and budgets.** Autonomous improvement implies model
   calls. DIRECTOR starts with zero model calls and zero cloud spend. Enabling
   them needs an explicit release target, scoped budget, OS-keychain credentials
   and pause/resume on exhaustion.
3. **Independent verification.** A model saying "the fix works" is not evidence.
   The change needs tests, domain evaluation, current state-bound receipts and
   an independent review that is not the author.
4. **Change-control.** Work must happen on a branch/worktree, with a reviewable
   diff, rollback, no automatic merge, no automatic push/deploy, and an owner
   decision for consequential effects.
5. **Injection resistance.** Retrieved text, memories, issue comments and child
   reports cannot become instructions or permission grants. Self-improvement
   must not let the agent expand its own scope.

The v0.1 executor enforces change-control (allowlisted paths, isolated worktree,
full tests, independent review, owner merge, no push) but it is not a kernel
sandbox and does not authorize provider spend. A fully autonomous "self-coding
24/7" claim still requires the remaining gates.

## Learning without authority drift

- Observations and proposal outcomes are stored with provenance and confidence.
- Confirmed decisions require owner action; model/retrieved text cannot promote
  itself to a fact or permission.
- Rejected/duplicate proposals are deduplicated by a stable signature.
- Accepted changes must add current evidence; before/after baselines are
  recorded.
- Memory deletion and retention apply to derived indexes as well as sources.
- The worker cannot edit global settings, install hooks, push, deploy or spend.

## Next release gate (M2 provider-driven improvement)

Already present: worktree execution, tests, review, owner merge, evidence, no
push. Still required:

- opt-in provider/keychain and exact budget ledger;
- container/VM-backed workspace with network disabled by default;
- autonomous proposal-to-patch authoring by an authorized model;
- rollback artifact and measured improvement per accepted change;
- broader native host tests.

Only then can DIRECTOR honestly claim it writes code to improve itself 24/7
without an agent/human author in the loop.
