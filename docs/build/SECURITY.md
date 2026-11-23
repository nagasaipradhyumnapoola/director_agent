# DIRECTOR security and threat model

## Scope and enforcement boundary

DIRECTOR enforces only the actions it mediates: its scanner, queue, runner,
budget ledger, policy gateway and MCP tools. It does **not** control every action
of an external main agent. Host hooks/instructions are advisory. Tests distinguish
observed, advisory, blocking and gateway-mediated paths; v1.0.0 claims gateway
mediation for DIRECTOR-owned work only.

## Assets

- User intent, contracts and acceptance criteria.
- Project source, datasets and rendered artifacts.
- Credentials and environment variables (must never enter prompts, logs,
  indexes, receipts or findings).
- Budget and policy state.
- Evidence integrity and completion decisions.

## Trust boundaries

Untrusted: repositories, documents, web pages, tool output, model output,
memory, skills, child reports, fixture content, MCP arguments.
Trusted: owner actions through the CLI, OS-provided identity/permissions, the
DIRECTOR code itself (subject to review).

## Controls in v1.0.0-local-supervised

| Threat | Control |
|---|---|
| Path traversal | `ensure_within` against the project root |
| Symlink/junction/reparse | per-component `lstat` rejection; Windows reparse check |
| Hardlink bypass | `st_nlink > 1` rejection for files and state DB |
| TOCTOU replacement | open with `O_NOFOLLOW` where available + dev/ino/nlink recheck |
| Secret exposure | pattern detection; values never stored; errors/messages redacted |
| Unbounded input | byte caps before JSON parse; node/depth limits; frame cap in MCP |
| Unbounded output | `dump_bounded` with visible truncation; finding caps |
| MCP abuse | newline framing, max frame, strict unknown-arg rejection, bounded results, no secret echo |
| Queue races | unique lease token + generation + expiry; stale publisher rejected |
| Budget races | atomic SQLite reservations (`BEGIN IMMEDIATE`) |
| False completion | latest evidence wins; freshness recompute; waiver bound to contract hash |
| Policy bypass | default deny; `allowed_actions` enforced; owner-only grants; deny overrides allow |
| Pilots self-granting | evaluators cannot create grants; owner-side provisioning only |
| Fixture code execution | ML `-I -P` + absolute trusted trainer; process-level caps |
| ML threshold tampering | trusted evaluator constants; fixture values ignored for decisions |
| Research calculation bypass | trusted tolerance; finite checks |
| Self-improvement escalation | proposals + selfdev path allowlist, isolated worktree, tests, review, owner merge; no auto-push |
| Local model calls | contract `model_call_local` + owner grant + budget; secret-like prompts refused; scrubbed runner; cloud disabled |
| Worker runaway | lease expiry, retry cap, pause/stop flag, heartbeat/degraded status |

## Residual risks (accepted and disclosed)

1. **No kernel sandbox.** Temp workspace + scrubbed env + job object + output/time
   caps are process-level containment. A malicious ML fixture could still touch
   user files within OS permissions (stdlib shadowing is blocked with `-I -P`).
   Do not run untrusted code; use a VM/container for that.
2. **Browser surface.** The probe loads a controlled local fixture with network
   resolution disabled and a disposable profile; it is not a general browser
   hardening claim.
3. **Heuristic detectors.** Secret patterns, ML leakage and accessibility checks
   can miss subtle cases. They never convert an unchecked/unknown format into a
   pass.
4. **Evidence freshness cost.** Re-verifying scans re-walks the tree; cached only
   within one verification pass.
5. **External host bypass.** An external agent can perform actions outside
   DIRECTOR's mediation. Adapter files do not create a security boundary.
6. **Prompt injection.** Retrieved content is labeled untrusted and never grants
   authority, but it can still influence a model's reasoning. Human/owner
   decisions remain authoritative.
7. **Availability.** A running host is required; 24/7 means while the machine and
   worker are running, not after shutdown/sleep.

## Secret handling

- Credentials belong in the OS keychain (future M2 provider work), never in
  source/config/DB/prompts/logs.
- Memory ingestion rejects secret-like content.
- Scan findings report kind + line only, never the value.
- Runner stdin is closed; env is allowlisted and secrets are not inherited.
- MCP errors use sanitized type messages; raw argument values are not echoed.

## Self-improvement safety

A proposal does not authorize code changes. `improve apply` returns `blocked`.
Autonomous self-coding requires a real sandbox, scoped provider/budget, secrets
in the keychain, a disposable branch/worktree, tests, independent review, owner
merge approval, rollback and no auto-push/deploy.

## Verification

- 79 offline tests including links/hardlinks/junctions, oversized frames,
  unknown args, secret redaction, fencing, budget races, stale evidence,
  latest-fail supersession, fixture threshold tampering, ML stdlib shadowing,
  citation/calculation abuse, waiver revision binding, and selfdev patch/test/review/merge.
- Independent review found false-completion/policy defects; all high/critical
  findings were fixed and re-verified. Residual items are listed in
  `docs/BUILD_STATUS.md` and `docs/build/LIMITATIONS.md`.

This is not a third-party security audit or a production certification.
