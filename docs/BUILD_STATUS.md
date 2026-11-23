# DIRECTOR build ledger

Release target: **v0.1-supervised-three-domain (M0 + M1)**
Ledger updated: 2026-11-23
Authoritative contract: `OPENCODE_BUILD_PROMPT.md`; invariants: `AGENTS.md`.

## Host audit (observed this session)

| Item | Observation |
|---|---|
| OS/shell | Windows 11, PowerShell 5.1, win32 |
| Python | 3.14.4 |
| OpenCode | 1.19.4 |
| SQLite | 3.50.4, FTS5 available |
| pytest | 9.1.1 |
| MCP SDK | `mcp` 1.29.0, latest protocol `2025-11-25` |
| Browser | Chrome 158 + Edge installed; no Playwright |
| Node | v24.14.1 (global WebSocket) |
| Git | `origin/main` history preserved; local commits on main |

## Contract decisions

- State: `<project>/.director/director.db` (SQLite WAL, schema v3). Never committed.
- Model calls = 0, cost = 0, external network off by default.
- Evidence is bound to subject SHA-256, check name/version, params, environment,
  policy hash, contract revision and time. A newer failing/blocked result
  supersedes an older pass. Acceptance re-verifies freshness.
- Mandatory criteria require current passing evidence or an owner waiver bound
  to the current contract revision/hash.
- Policy is default-deny. `allowed_actions` is enforced. Pilots do not mint
  their own grants; owner-side `provision_pilot_grants` is called by the CLI/demo
  and grants are bound to actor/action/resource/revision/payload/expiry/timeout.
- The website pilot uses a real headless Chromium journey over CDP. Node/browser
  absence makes that pilot `blocked`, never pass.
- ML trainer runs with `-I -P` and an absolute trusted script path. Thresholds
  come from DIRECTOR constants, not fixture config.
- Research uses a trusted calculation tolerance, requires source quotes,
  conflict/date handling and resolved citations in the rendered document.
- The 24/7 worker is deterministic and proposal-only. It cannot model-call,
  spend, edit source, push or deploy. Autonomous self-coding remains gated.

## Milestones

- [x] Workspace, runtime and research audit
- [x] M0 substrate: contracts, store, queue/fencing, policy, budgets, evidence,
  context, memory, deterministic scan, CLI, recovery
- [x] CLI / lifecycle / doctor / checkpoints
- [x] Bounded MCP stdio adapter + SDK conformance + host-neutral adapter generation
- [x] M1 website pilot (static + real Chromium CDP journey)
- [x] M1 ML pilot (manifest, leakage, held-out, reproducibility, slices, resources)
- [x] M1 research/document pilot (claims, conflicts, calculation, render)
- [x] Supervised self-improvement proposal engine (24/7, proposal-only)
- [x] 59-test offline suite incl. historical defect regressions
- [x] Independent review rounds + fixes
- [x] Release docs, evidence report, install/uninstall

## Evidence log (exact commands)

1. `python -m pytest -q` with `PYTHONPATH=src` → **59 passed**, no failures, no
   skips. Browser test and MCP SDK round-trip both executed.
2. `python -m director demo --root . --domains general,website,ml,research --modes clean,broken`
   → `expectations: met`, `model calls: 0.0`, exit 0.
   - clean: general/website/ml/research all `pass`, 0 findings.
   - broken: general `fail` (4 findings), website `fail` (13), ML `fail` (2),
     research `fail` (8).
   - Raw summary: `var/demo/20261123T173650Z-729e82/summary.json` (gitignored).
3. `python -m director doctor --root var/cli-test` → all core checks ok.
4. MCP: initialize/tools/list/tools/call over stdio + official SDK
   `ClientSession` round trip; oversized frame rejected before JSON parsing;
   unknown args rejected; no secret echo.
5. Lifecycle: detached worker start/heartbeat/pause/resume/stop tested; expired
   lease reclaimed; zero model calls.
6. Independent reviews (2 rounds) found and reproduced real false-completion
   and policy defects; all high/critical findings were fixed and re-verified:
   - latest-fail supersession, scan tree snapshot (files+dirs), trusted ML
     thresholds, finite/trusted research calculation, `allowed_actions` +
     owner-only provisioning, verify=True completion surfaces, strict grant
     expiry, memory re-ingest, revision-bound waivers, ML `-I -P`, required
     citations, bounded reads, grant timeout enforcement, deterministic
     same-second grant ordering.

## Evidence levels (per surface)

| Surface | Level |
|---|---|
| Core store/queue/policy/budget/evidence | implemented, unit + integration tested |
| Scanner/regressions | implemented, adversarial tests |
| MCP stdio | implemented, protocol tested with official SDK |
| OpenCode/Claude/Codex adapters | generated examples; native tool paths NOT tested |
| Website pilot | domain-validated on controlled fixture with real Chrome |
| ML pilot | domain-validated on controlled clean/leaky fixtures |
| Research pilot | domain-validated on controlled conflicting-source fixture |
| Self-improvement | proposal engine tested; autonomous code application NOT implemented |
| 24/7 worker | detached lifecycle tested; requires running host |

## Known limitations

- Process-level supervision only; not a kernel/container sandbox. Fixtures are
  controlled/trusted. Do not run untrusted repositories or training code.
- Browser/ML/research pilots are fixture-scoped, not general domain claims.
- No live web freshness, no provider/model routing (M2), no native host tool-call
  test, no A2A, no billion-token scale.
- ML leakage/slice checks are heuristic; `low_support` slices are skipped.
- `verify` scans re-walk the tree; cached within one verify pass only.
- A pre-evaluator budget block records blocked evidence but may leave older
  fresh passes; acceptance still means "latest criterion evidence", not "whole
  project unchanged".

## Next action

M2: opt-in providers/keychain/budget routing, real sandbox, native host tests,
and the gated self-coding pipeline described in `docs/SELF_IMPROVEMENT.md`.

## Release record

- Commit: 867bd2 (pushed to origin/main on 2026-11-23).
- Remote: https://github.com/nagasaipradhyumnapoola/director_agent
- Verified release evidence: docs/build/EVIDENCE.md (59 tests, full demo,
  zero model calls, independent review fixes).
