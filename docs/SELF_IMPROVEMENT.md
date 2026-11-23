# DIRECTOR self-improvement

Goal: DIRECTOR should get better over time without pretending to be more
autonomous than it is. The v0.1 release implements the safe half of that loop:
a **24/7 deterministic improvement engine** that observes its own evidence,
findings and failures, records prioritised proposals, and requires owner
decisions. It does not write or apply code on its own yet.

## What runs 24/7 in v0.1

`director start` launches a detached local worker. It:

- makes **zero model calls** and no external network requests;
- claims fenced investigations from the durable queue;
- runs deterministic scans;
- generates improvement proposals from findings, stale evidence, unmet criteria,
  blocked pilots and failed investigations;
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
[v0.1 stops here: no code write]
        |
        v  (future M2, gated)
isolated branch/worktree -> scoped provider + budget -> tests -> independent
review -> current evidence -> owner merge decision -> no auto-push/deploy
```

Proposals are stored in SQLite and mirrored as bounded JSON under
`.director/proposals/`. Rejected proposals are not repeated. Approval records
intent only; `director improve apply` deliberately returns `blocked`.

## Commands

```powershell
python -m director improve propose
python -m director improve queue          # let the 24/7 worker generate them
python -m director improve list
python -m director improve show <id>
python -m director improve approve <id> --reason "..."
python -m director improve reject <id> --reason "..."
python -m director improve apply <id>     # blocked in v0.1
python -m director start                  # detached deterministic worker
python -m director pause | resume | stop
python -m director recover
```

## Why autonomous self-coding is gated

Making an agent edit its own code 24/7 safely requires capabilities that are not
part of v0.1:

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

Until those exist and are tested, a "self-coding 24/7" claim would be a fake
demo. v0.1 therefore implements the durable proposal engine, not self-modifying
execution.

## Learning without authority drift

- Observations and proposal outcomes are stored with provenance and confidence.
- Confirmed decisions require owner action; model/retrieved text cannot promote
  itself to a fact or permission.
- Rejected/duplicate proposals are deduplicated by a stable signature.
- Accepted changes must add current evidence; before/after baselines are
  recorded.
- Memory deletion and retention apply to derived indexes as well as sources.
- The worker cannot edit global settings, install hooks, push, deploy or spend.

## Next release gate (M2 self-improvement)

A future `v0.2-self-improving-supervised` target would add:

- opt-in provider/keychain and exact budget ledger;
- container/VM-backed workspace with network disabled by default;
- proposal-to-patch execution on a disposable branch;
- mandatory tests, independent review and a rollback artifact;
- owner merge approval and no automatic publication;
- measured improvement per accepted change (cost, defect reduction, regressions).

Only then can DIRECTOR honestly say it writes code to improve itself day by day.
