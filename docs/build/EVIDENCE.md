# Release evidence - v1.0.0-local-supervised

Date: 2026-11-24
Platform: Windows 11, PowerShell 5.1, Python 3.14.4, SQLite 3.50.4,
Node 24.14.1, Chrome 158.0.8127.36, `mcp` SDK 1.29.0, pytest 9.1.1.

Raw files in this directory:
`pytest.txt`, `demo.txt`, `demo-summary.json`, `doctor.txt`.

## 1. Offline test suite

Command:

```powershell
$env:PYTHONPATH="src"; python -m pytest
```

Result: **107 passed in 105.90s**, no failures, no skips. The browser (real
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
- detached worker heartbeat/stop and lease recovery;
- local model default deny, owner grant + budget, command provider, secret prompt;
- selfdev patch allowlist/worktree/test/review/merge and queued patch testing.

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
Run id `20261123T184737Z-4c92c0`; raw summary copied to
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
  `director_supervisor-1.0.0-py3-none-any.whl` (124,713 bytes) successfully.
- `python benchmarks/retrieval_smoke.py --files 500 --queries 100`:
  500 synthetic docs, ingest 0.4176s, recall@1 1.0, p50 0.142ms, p95 0.242ms,
  0 model calls. This is a lexical FTS5 smoke test, **not** semantic memory or
  billion-scale evidence. Raw: `benchmarks/results/retrieval_smoke.json`.

## 4c. Supervised self-modification (tested on DIRECTOR itself)

- Patch patch_cdc28362d02d4f2d998e82324ecc9df9 added a read-only 
ersion
  command and CLI test (author: this agent).
- Isolated git worktree at base commit 85d8209; full offline suite passed in
  99.1s (exit 0). Raw: selfdev-test.txt, diff: selfdev-version.patch.
- Independent reviewer returned **PASS**, verified reverse-apply integrity and
  ran the targeted test; only low non-blocking notes.
- Owner approval recorded; local fast-forward merge commit f439b16.
- Merged tree: 107/107 tests, python -m director version --json works.
- The pipeline did not push; the release push was a separate owner action.

## 4d. Local model/provider gateway and 24/7 patch testing

- Default deny: a local model call failed policy before any budget spend.
- Owner grant + model_call_local contract action + model-call budget enabled
  the deterministic stub provider; usage recorded and the third call hit the
  budget cap.
- The command provider ran an owner-supplied local Python command in the
  scrubbed runner (prompt -> uppercase) with no external provider.
- Secret-like prompts are refused before any call.
- selfdev test --queue enqueues patch testing; the worker claimed it and
  completed the patch test with evidence.
- Cloud providers, provider credentials and external spend remain disabled.

## 4e. Native OpenCode MCP connection

- Current docs use `mcp.servers` and `disabled`; the generated adapter was
  corrected to that schema.
- OpenCode 1.19.4 read `.opencode/opencode.jsonc` and started the local stdio
  server; `opencode mcp list` reported **`✓ director connected`**.
- This is a native transport/connection test, not a native tool-call test; tool
  invocation still needs an authorized model session.

## 4f. Production hardening

- `backup create` produced a ZIP with a consistent SQLite online backup and a
  SHA-256 manifest; `backup verify` passed integrity; `backup restore` restored
  to a **new** project and memory search survived.
- OS keychain (`WinVaultKeyring`) round-tripped a test secret and deleted it.
- `health --json` reported DB quick_check, schema, worker, acceptance, budget,
  backups, keychain and disk; `doctor` includes the same gates.
- Offline installer/uninstaller tested; wheel includes assets and selfdev.

## 4g. Native tool-call attempt and autostart

- OpenCode 1.19.4 V1 loaded the corrected MCP config and showed `director
  connected`. A local Ollama model did not expose the MCP tool, but the loopback
  OpenAI-compatible proxy did: `opencode run --model freellm/auto` emitted a
  `tool_use` for `director_director_status`, included the status JSON, and the
  model replied `ACCEPTANCE=false`. Native connection + tool-call are verified.
- Task Scheduler `ONLOGON` creation was denied (no admin). DIRECTOR fell back to
  a per-user Startup-folder entry; install/status/remove passed. This is logon
  autostart in a user session, not a Windows service.
- `improve auto --queue` can enqueue local-model authoring/testing for the 24/7
  worker; the synchronous path was exercised with a mock model and real
  qwen2.5-coder:7b (patch tested 126.8s, review PASS but rejected after review as dead code).
- OpenAI-compatible HTTP provider: a loopback proxy returned `OK` with exact
  usage; an external endpoint was policy-denied without network permission and a
  grant. The provider key was stored in the OS keychain, not config or logs.
- Redacted JSONL audit log records evidence/model/backup/service/selfdev actions;
  backup prune, scheduled maintenance and per-user Startup-folder autostart
  tested.
- Container runner: Docker 29.6.2 daemon available. `python:3.12-slim` ran as uid
  65534, read a mounted file, failed to write (read-only mount), and could not
  open a network socket (`Network is unreachable`). Source is mounted `:ro`, caps
  dropped, `no-new-privileges`, with memory/CPU/pid/output bounds.
- Production image: `director:local` (260MB) builds, runs `--version` in
  1.66-2.01s, and initializes/inspects a mounted project as uid 65534.
- Opt-in maintenance: first `maybe_run` created a backup, an immediate second run
  was skipped, and disable stopped it.
- UI: `director ui` served the landing page and control room on loopback; the
  server blocked directory listing and sent nosniff/DENY headers. `/api/state`
  returned a live project summary; `tests/test_ui.py` covers assets, server and
  the live endpoint.
- Autonomy: enabling at 60 minutes enqueued one `selfdev_author` job with
  `test=true`; a second sweep was not due; disable stopped it.
- Agent loop: tests exercised read → finish, path-escape rejection, command
  allowlist, model-grant denial and a valid `propose_patch` that entered the
  selfdev patch store. The loop cannot write project files directly.
- Skill matrix (2 seeds, 98 runs, `llama-3.3-70b-fp8-fast`):
  DIRECTOR 84.1 (4,514 output tokens), Ponytail 84.1 (5,244), ui-ux-pro-max 81.2
  with design 100%, Direct 80.4, Headroom 79.9, Superpowers 79.1, ECC 78.4.
  95% bootstrap ranges overlap (DIRECTOR/Ponytail 73.4-94.1), so the rank is
  directional; the token difference is the concrete result. Prompt-level
  procedure ablation; upstream runtimes/hooks not executed.
- Per-tool scorecards: `benchmarks/skill_report.py --verify-only` reports
  **98/98** cells (7 tools x 7 tasks x 2 seeds), no empty outputs, no provider
  errors. Task winners: DIRECTOR merge/parse/context, ui-ux design, Direct
  clarity, selfdev seven-way tie, slugify no strict pass.
- Recipes: `benchmarks/recipe_eval.py` runs `slugify`, `parse_duration` and
  `merge_intervals` against the same official tests: **3/3 pass**, including
  `Straße -> strasse`, `Café -> cafe`, `Æther -> aether`, max-length boundaries
  and separator-only input.
- Portfolio: `benchmarks/router_score.py` composes coding 100% (recipes),
  selfdev 100%, design 100% (ui-ux), clarity 100% (DIRECTOR clarity template),
  context 100% (DIRECTOR) -> **100.0** vs 84.1 best single prompt.

## 4h. Benchmarks

Full methodology and limits: `docs/build/BENCHMARKS.md`. Raw:
`benchmarks/results/director_bench_20261123T195633Z.json`,
`benchmarks/results/director_bench_20261123T222130Z.json`,
`benchmarks/results/retrieval_100000000.json`,
`benchmarks/results/prompt_ablation.json`.

- Domain discrimination: 8/8 (4 clean pass, 4 broken fail), 52.9s including
  real Chromium.
- Lexical retrieval: 1M tokens (1,000 docs) ingest 2.23s, recall@5 1.0, p95
  0.726ms; 10M tokens (10,000 docs) ingest 24.64s, recall@5 1.0, p95 1.727ms,
  181.8MB DB; **100M tokens (100,000 docs) ingest 217.5s in the container,
  recall@5 1.0, p50 1.164ms, p95 7.134ms, 1.78GB DB**; deletion returned 0.
  The same 100M tier in resumable host chunks measured p95 2.001ms. 1B was
  attempted in the same container: after 4h it had written 3.9GB (~22% of the
  projected 17.8GB) at ~95% CPU and 475MB RSS, and was terminated. No 1B
  recall/latency is claimed; FTS5 ingestion degrades at this scale.
- MCP: 20 calls, p95 1.57ms, ping ok.
- Local Ollama: qwen3:1.7b 41.8s/209 output tokens; qwen2.5-coder:7b 17.3s/3.
- Selfdev: mock 1.5s; real local-model patch tested 126.8s after recount; review
  PASS but rejected after review as dead code.
- Prompt ablation (one task/model/run): baseline, Ponytail, ECC, Headroom skill
  passed; Superpowers TDD failed its added edge test; upstream runtimes not run.
- Coverage matrix marks real cloud spend and kernel/microVM sandboxing as not
  measured; native OpenCode tool-call and the bounded Docker runner are verified.

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
- self-improvement proposals are generated, deduplicated and owner-approved;
- the supervised `selfdev` pipeline applied and merged a real DIRECTOR patch
  only after isolated full-suite tests, independent review and owner approval;
- the local model gateway enforces contract/grant/budget gates for stub and
  owner-supplied command providers with zero external spend;
- OpenCode natively loaded the generated MCP config and showed `director
  connected` (connection only, not tool-call);
- verified backups/restore and OS-keychain secrets work on this host, and health
  checks cover DB/schema/worker/acceptance/backups/keychain/disk.

## 7. What is not proven

- General domain support, production readiness or a security audit.
- Kernel/container isolation; process-level containment only.
- Native host tool-call integration for any agent.
- Live web research freshness, cloud provider routing/spend, A2A, computer-use.
- Billion-token memory scale or semantic memory.
- Provider-driven autonomous patch authoring exists for local Ollama; real cloud
  authoring is gated and `improve apply` is blocked. `selfdev` needs an authored
  patch (agent, human or local model).
- Kernel/microVM sandboxing; `selfdev` uses process-level isolation or the
  optional Docker runner, not a hardened VM boundary.

Performance/quality claims are fixture-scoped; no comparative productivity study
or broad benchmark is claimed.

## Release record

- Commits: `e04817d` (benchmarks + local-model authoring) after `eac3c39`
  (v1.0.0 hardening), `1f98389` (Ollama/selfdev), `5606419` (grants), `f439b16`
  (selfdev) and `85d8209` (pipeline), pushed to `origin/main` on 2026-11-24.
- Remote: https://github.com/nagasaipradhyumnapoola/director_agent
- Verified release evidence: 107 tests, full demo, zero model calls, independent
  review fixes, one merged selfdev patch.
