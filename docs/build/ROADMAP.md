# Roadmap

v0.1 shipped the trustworthy local substrate and three controlled pilots. Later
milestones are designed, not shipped.

## M2 — supervised reasoning

- Opt-in local/cloud providers; credentials in the OS keychain.
- Exact or qualified token/cost accounting; reservation, settlement, backoff.
- Routing by complexity/risk/uncertainty; bounded investigation.
- Pause/recover on quota, rate, context or cost exhaustion.
- Model proposals remain untrusted; deterministic checks and owner decisions
  stay authoritative.
- Gate: keychain + budget + provider tests; no hidden fallback spend.

## M2.5 - self-improvement execution

Shipped in v0.1: patch allowlist, isolated git worktree, full offline tests,
independent review record, owner merge, evidence receipts, no push/deploy.

Still gated: provider/keychain-driven autonomous patch authoring, container/VM
sandbox, rollback artifact, measured improvement per accepted change. See
docs/SELF_IMPROVEMENT.md.

## M3 — measured host/upstream composition

- Native OpenCode/Claude/Codex lifecycle tests (not just MCP).
- One selected procedure per stage; no duplicate approval loops.
- Optional Headroom adapter with offline/no-beacon mode, fidelity and cache
  economics measured.
- Ponytail/Superpowers/ECC selected capabilities, licenses reviewed, executable
  hooks inspected.
- Paired ablations: builder alone, core, component, selected stack.

## M4 — scale and domains

- Hybrid/temporal graph memory with deletion/ACL/contradiction tests.
- 1M → 10M → 100M → 1B indexed-token tiers with measured recall/latency/storage.
- Additional validated domains (data, spreadsheets, presentations, media,
  operations) with real evaluators.
- Authenticated A2A and isolated computer-use only after real-task justification.

## Explicit non-goals

- A literal billion-token attention window.
- Perfect retrieval or universal domain correctness.
- Autonomous self-modification without sandbox, budgets, tests and owner gates.
- Unbounded autonomous spend, push or deploy.
