# Release evidence â€” v0.1-supervised-three-domain

Date: 2026-11-23
Platform: Windows 11, PowerShell 5.1, Python 3.14.4, SQLite 3.50.4,
Node 24.14.1, Chrome 158.0.8127.36, `mcp` SDK 1.29.0, pytest 9.1.1.

Raw files in this directory:
`pytest.txt`, `demo.txt`, `demo-summary.json`, `doctor.txt`.

## 1. Offline test suite

Command:

```powershell
$env:PYTHONPATH="src"; python -m pytest
```

Result: **59 passed in 93.07s**, no failures, no skips. The browser (real
Chromium/CDP) and MCP SDK tests executed; they were not skipped.

Coverage highlights:

- path traversal, symlinks, junctions, hardlinks, oversized reads;
- bounded JSON/frames/output and secret redaction/no-echo;
- fenced leases, stale publish rejection, crash retry cap, concurrent claim;
- atomic budget reservation race (10/20 succeeded against limit 10);
- latest-fail supersession, scan tree/dir invalidation, policy/revision changes;
- owner waiver revision binding, grant expiry/limits, memory re-ingest;
- MCP initialize/tools/list/call, unknown args/methods, oversize-before-parse;
- ML leakage/held-out/reproducibility, fixture threshold tampering, stdlib
  shadowing;
- research NaN/oversized tolerance, missing citations, rendered artifacts;
- detached worker heartbeat/stop and lease recovery.

## 2. Full controlled demo

Command:

```powershell
python -m director demo --root . --domains general,website,ml,research --modes clean,broken
```

Observed (`demo.txt`):

| Domain | Clean | Broken | Broken findings |
|---|---|---|---|
| general | pass | fail | 4 |
| website | pass | fail | 13 |
| ml | pass | fail | 2 |
| research | pass | fail | 8 |

`expectations: met`; `model calls: 0.0`; exit 0.
Run id `20261123T173650Z-729e82`; raw summary copied to
`demo-summary.json`.

Discrimination details:

- Website broken: add-to-cart throws, checkout unreachable, keyboard cannot
  focus the div control, 390px viewport overflows (fixed 1200px), external image
  request, missing alt/label/viewport, AX role is `StaticText` not `button`.
- ML broken: 22 held-out rows duplicate training vectors and `target_enc` is
  target-derived. Held-out accuracy is **1.0**, yet the pilot fails because
  leakage checks fail â€” training accuracy is not accepted as success.
- Research broken: fabricated `s9`, quote mismatch, superseded source used as a
  current fact, wrong calculation, empty conflict note, unresolved citation and
  `TODO`. Clean fixture passes all claim/calculation/conflict/render checks.
- General broken: uppercase `.PY` syntax error, secret-like file, invalid JSON,
  unsupported extension; clean passes.

## 3. Doctor

`python -m director doctor --root var/cli-test` â†’ core checks ok:
Python, SQLite, state dir, DB integrity, FTS5, contract, zero model budget/spend,
external network off, trust boundary checks, MCP SDK, Node, Chrome.

## 4. MCP protocol

- `initialize` â†’ negotiated `2025-11-25`; tools/list exposes `director_*`.
- `tools/call` status/preflight work; unknown arguments â†’ `-32602` without
  echoing a supplied secret; oversized frame â†’ `-32600` before JSON parse and
  the server continues; ping works after the frame error.
- Official SDK `ClientSession` round trip passes (initialize/list/call).
- Native OpenCode/Claude/Codex tool-call paths were **not** exercised; adapters
  are generated examples only.

## 4b. Packaging and benchmark

- `python -m pip wheel . --no-deps --no-build-isolation` built
  `director_supervisor-0.1.0-py3-none-any.whl` (102,915 bytes) successfully.
- `python benchmarks/retrieval_smoke.py --files 500 --queries 100`:
  500 synthetic docs, ingest 0.4176s, recall@1 1.0, p50 0.142ms, p95 0.242ms,
  0 model calls. This is a lexical FTS5 smoke test, **not** semantic memory or
  billion-scale evidence. Raw: `benchmarks/results/retrieval_smoke.json`.

## 5. Independent review

Two review rounds were performed by an independent agent. The first found real
false-completion, false-pilot-pass, policy self-grant, stale-evidence and
fixture-code-execution defects. They were fixed with regressions:

- latest evidence wins regardless of outcome;
- scan evidence binds a recomputable file+directory snapshot;
- ML thresholds from trusted constants; `-I -P` trusted trainer;
- research trusted tolerance/finite checks and mandatory citations;
- enforced `allowed_actions`; owner-side pilot provisioning only; grant limits;
- verify-by-default completion surfaces;
- strict grant expiry; deterministic same-second grant ordering;
- memory re-ingest; waiver revision/hash binding; bounded reads.

The second review independently reproduced the fixes and reported one remaining
medium fail-closed ordering issue (same-second grant tie), which was fixed with
`rowid DESC` ordering and a selection test. Final residual limitations are
recorded in `docs/build/LIMITATIONS.md`.

## 6. What is proven

Proven on this host, with controlled fixtures:

- M0 local substrate works, persists, fences, budgets, verifies freshness and
  reports honestly;
- three domain pilots share the same core and reject seeded broken fixtures
  while accepting clean ones;
- MCP stdio works with the installed SDK and bounds hostile frames/arguments;
- the 24/7 worker runs deterministically with zero model calls;
- self-improvement proposals are generated, deduplicated, owner-approved, and
  cannot apply code.

## 7. What is not proven

- General domain support, production readiness or a security audit.
- Kernel/container isolation; process-level containment only.
- Native host tool-call integration for any agent.
- Live web research freshness, provider routing/spend, A2A, computer-use.
- Billion-token memory scale or semantic memory.
- Autonomous self-coding; `improve apply` is intentionally blocked.

Performance/quality claims are fixture-scoped; no comparative productivity study
or broad benchmark is claimed.

