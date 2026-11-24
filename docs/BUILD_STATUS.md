# DIRECTOR build ledger

Release target: **v1.0.0-local-supervised (M0 + M1 + production hardening)**
Ledger updated: 2026-11-24
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

- State: `<project>/.director/director.db` (SQLite WAL, schema v4). Never committed.
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
- The 24/7 worker is deterministic at idle and cannot spend, merge, push or
  deploy. It may execute explicitly enqueued jobs: scan, proposal generation,
  local-model author/test, and scheduled backups.
- selfdev adds supervised self-modification: validated patch -> isolated git
  worktree -> full tests -> independent review -> owner merge. It never pushes.
  Local Ollama authoring is tested; real cloud authoring remains gated.

## Milestones

- [x] Workspace, runtime and research audit
- [x] M0 substrate: contracts, store, queue/fencing, policy, budgets, evidence,
  context, memory, deterministic scan, CLI, recovery
- [x] CLI / lifecycle / doctor / checkpoints
- [x] Bounded MCP stdio adapter + SDK conformance + host-neutral adapter generation
- [x] M1 website pilot (static + real Chromium CDP journey)
- [x] M1 ML pilot (manifest, leakage, held-out, reproducibility, slices, resources)
- [x] M1 research/document pilot (claims, conflicts, calculation, render)
- [x] Supervised self-improvement proposal engine (24/7 idle = deterministic)
- [x] Supervised self-modification executor (worktree, tests, review, owner merge)
- [x] Local model/provider gateway (stub + owner command) with grant/budget gates
- [x] 24/7 worker can test queued selfdev patches
- [x] Production hardening: verified backups/restore/prune, OS-keychain secrets,
  health/doctor gates, redacted audit log, per-user autostart, native OpenCode
  MCP connection
- [x] OpenAI-compatible HTTP provider with keychain auth/token/cost accounting
  (local mock tested; real cloud not called)
- [x] Local Ollama authoring + 24/7 author/test queue
- [x] Per-user autostart (Startup folder) install/status/remove
- [x] 85-test offline suite incl. historical defect regressions and selfdev
- [x] Independent review rounds + fixes
- [x] Release docs, evidence report, install/uninstall

## Evidence log (exact commands)

1. `python -m pytest -q` with `PYTHONPATH=src` → **70 passed**, no failures, no
   skips. Browser test and MCP SDK round-trip both executed.
2. `python -m director demo --root . --domains general,website,ml,research --modes clean,broken`
   → `expectations: met`, `model calls: 0.0`, exit 0.
   - clean: general/website/ml/research all `pass`, 0 findings.
   - broken: general `fail` (4 findings), website `fail` (13), ML `fail` (2),
     research `fail` (8).
   - Raw summary: `var/demo/20261123T184737Z-4c92c0/summary.json` (gitignored).
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
7. Supervised self-modification executed end-to-end on DIRECTOR itself:
   - patch `patch_cdc28362d02d4f2d998e82324ecc9df9` (version command + test);
   - isolated worktree at base `85d8209`; full suite passed in 99.1s;
   - independent reviewer PASS with patch-integrity verification;
   - owner approval recorded; fast-forward merge commit `f439b16`;
   - merged tree: 85/85 tests, version command works, no push by the pipeline.
8. Local model/provider gateway:
   - default policy denied a local model call with zero spend;
   - owner grant + contract `model_call_local` + model-call budget enabled the
     deterministic stub;
   - an owner-supplied local command ran in the scrubbed runner;
   - secret-like prompts refused; budget cap enforced; cloud providers disabled;
   - worker tested a queued selfdev patch (`selfdev test --queue`).
9. Native OpenCode MCP connection:
   - corrected generated config to current `mcp.servers` + `disabled` shape;
   - OpenCode 1.19.4 read `.opencode/opencode.jsonc` and `opencode mcp list`
     reported `director connected`;
   - native tool-call verified: the run agent emitted a `tool_use` for
     `director_director_status`, received the status JSON, and replied
     `ACCEPTANCE=false`.
10. Benchmarks (`docs/build/BENCHMARKS.md`):
   - domain discrimination 8/8; 1M/10M/100M lexical tiers (recall@5 1.0, p95
     0.726ms/1.727ms/7.134ms container, deletion 0 results);
   - 100M: 100,000 docs, 217.5s ingest, 1.78GB index; host chunked p95 2.001ms;
   - 1B attempted in-container: stopped after 4h at 3.9GB/~22% (95% CPU,
     475MB RSS); no 1B result claimed — FTS5 ingest degrades at this scale;
   - MCP 20 calls p95 1.57ms; local qwen3/qwen2.5 gateway calls 41.8s/17.3s;
   - mock selfdev 1.5s; real local-model patch tested 126.8s, review PASS but
     rejected after review as dead code;
   - prompt ablation baseline/Ponytail/ECC/Headroom pass, TDD variant fail;
     upstream runtimes not executed; container runner verified separately.
11. Provider/ops extensions:
   - OpenAI-compatible HTTP provider: loopback mock returned exact usage/cost;
     external endpoint denied without network permission/grant; keychain secret
     path implemented;
   - redacted JSONL audit log for evidence/model/backup/service/selfdev actions;
   - backup prune, opt-in scheduled maintenance and per-user Startup-folder
     autostart tested;
   - bounded Docker runner: read-only mount, no network, uid 65534, cap-drop ALL,
     resource limits; verified read/deny-write/deny-network.
12. Production hardening:
   - SQLite online backup -> hashed ZIP manifest -> `verify_backup` integrity
     check -> non-destructive restore to a new project; memory survived restore;
   - OS keychain (Windows Credential Locker) secret set/status/delete round trip;
   - `health` and `doctor` report DB/schema/worker/acceptance/backup/keychain/disk;
   - offline installer and uninstaller tested; wheel build includes assets.

## Evidence levels (per surface)

| Surface | Level |
|---|---|
| Core store/queue/policy/budget/evidence | implemented, unit + integration tested |
| Scanner/regressions | implemented, adversarial tests |
| MCP stdio | implemented, protocol tested with official SDK |
| OpenCode adapter | native connection + `director_director_status` tool-call tested through a loopback OpenAI-compatible proxy |
| Claude/Codex adapters | generated examples; native paths NOT tested |
| Website pilot | domain-validated on controlled fixture with real Chrome |
| ML pilot | domain-validated on controlled clean/leaky fixtures |
| Research pilot | domain-validated on controlled conflicting-source fixture |
| Self-improvement | proposals + supervised selfdev execution tested; local Ollama authoring tested; cloud authoring NOT tested |
| Local model gateway | implemented/tested (stub + command + Ollama + OpenAI-compatible); keychain secrets, owner grant, exact token/cost budget; real cloud NOT called |
| 24/7 worker | detached lifecycle tested; deterministic jobs, queued author/test, scheduled backups |
| Container runner | implemented, integration tested on Docker 29.6.2; not a hardened microVM |

## Known limitations

- Process-level supervision by default. The optional Docker runner is bounded
  (read-only, no network, unprivileged) but not a hardened microVM. Fixtures are
  controlled/trusted. Do not run untrusted repositories or training code without
  the container runner and a deliberate policy grant.
- Browser/ML/research pilots are fixture-scoped, not general domain claims.
- Live web freshness, autonomous cloud provider routing, A2A and billion-token
  scale are not shipped. Native OpenCode tool-call is verified; Claude/Codex
  native paths are not. The Docker runner is bounded but not a hardened microVM.
- ML leakage/slice checks are heuristic; `low_support` slices are skipped.
- `verify` scans re-walk the tree; cached within one verify pass only.
- A pre-evaluator budget block records blocked evidence but may leave older
  fresh passes; acceptance still means "latest criterion evidence", not "whole
  project unchanged".
- `selfdev` is not a kernel sandbox and does not author patches by itself;
  provider-driven autonomous authoring, push and deploy remain gated.
- The local model gateway has no cloud provider, credential/keychain path or
  external spend; the command provider is not a sandbox.

## Next action

M2: opt-in providers/keychain/budget routing, real sandbox, native host tests,
and provider-driven autonomous patch authoring on top of the existing selfdev
worktree/test/review/owner-merge pipeline.

## Release record

- Commit: `4f011e5` (Docker runner, scheduled backups, native tool-call) after
  `2384476` (ops/provider/audit), `e04817d` (benchmarks + local-model authoring),
  `eac3c39` (v1.0.0 hardening), `1f98389` (Ollama/selfdev), `5606419` (grants),
  `f439b16` (selfdev) and `85d8209` (pipeline), pushed to `origin/main` on
  2026-11-24.
- Remote: https://github.com/nagasaipradhyumnapoola/director_agent
- Verified release evidence: docs/build/EVIDENCE.md (85 tests, full demo,
  zero model calls, independent review fixes).
