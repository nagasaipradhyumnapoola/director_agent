# DIRECTOR benchmarks

Date: 2026-11-24 (run timestamps 2026-11-23 UTC)
Host: Windows 11, Python 3.14.4, SQLite 3.50.4, Node 24.14.1,
Chrome 158, Ollama 0.40.11. Container runs: Linux/Python 3.12.16,
Docker 29.6.2, 5GB memory cap.

Raw results:

- `benchmarks/results/director_bench_20261123T195633Z.json` — core/domain/retrieval/MCP/local-model/selfdev
- `benchmarks/results/director_bench_20261123T222130Z.json` — container 100M retrieval
- `benchmarks/results/retrieval_100000000.json` — host chunked 100M retrieval
- `benchmarks/results/skill_matrix.json` — 7-tool prompt-level matrix (2 seeds)
- `benchmarks/results/skill_individual.md` — per-tool task scorecards and winners
- `benchmarks/results/prompt_ablation.json` — upstream skill-prompt ablation
- `benchmarks/results/retrieval_smoke.json` — earlier 500-doc smoke

These are small, reproducible measurements on one machine. They are **not** a
leaderboard, not statistical significance, and not evidence of general
competence or "best in everything".

## 1. Domain detection

Command: `python benchmarks/run_benchmarks.py --tiers 1000000,10000000`

| Fixture set | Clean | Broken | Correct | Accuracy |
|---|---|---|---|---|
| general/website/ml/research | 4 pass | 4 fail | 8/8 | 1.0 |

Wall: 52.9s (includes real Chromium website journey). Zero model calls.
This is controlled-fixture discrimination, not real-project accuracy.

## 2. Lexical retrieval tiers

Synthetic exact-marker corpus, FTS5, 100 queries per tier.

| Tier | Docs | Ingest | Recall@5 | p50 | p95 | DB size | Deleted search |
|---|---|---|---|---|---|---|---|
| 1M tokens | 1,000 | 2.23s | 1.0 | 0.433ms | 0.726ms | 22.0MB | 0 results |
| 10M tokens | 10,000 | 24.64s | 1.0 | 0.920ms | 1.727ms | 181.8MB | 0 results |
| 100M tokens | 100,000 | 217.5s | 1.0 | 1.164ms | 7.134ms | 1.78GB | 0 results |

The 100M tier was also completed in resumable host chunks (the host process
limit killed single-process ingestion): p50 1.383ms, p95 2.001ms, max 6.725ms,
recall 1.0. The container run above is the single-process reference.

**1B was attempted and not completed.** In the same 5GB container it ran for
4h at ~95% CPU and 475MB RSS, writing 3.9GB (about 22% of the projected 17.8GB
index) before it was terminated. FTS5 ingestion degrades sharply at this scale;
no 1B recall or latency number is claimed. Reaching 1B needs a different index
strategy (sharding, bulk transactions, or external/compressed storage).

Exact lexical markers are necessary smoke evidence, not semantic/temporal/ACL
proof.

## 3. MCP stdio

Protocol `2025-11-25`, 9 tools, 20 `director_status` calls.

| Metric | Value |
|---|---|
| mean | 0.591ms |
| p50 | 0.451ms |
| p95 | 1.570ms |
| ping | ok |

Local stdio only. Remote/OAuth/native tool-call not measured. Native OpenCode
`director_director_status` tool-call was verified separately (loopback proxy),
not as a latency benchmark.

## 4. Local Ollama models

Single prompt ("Reply with exactly OK"), loopback only, zero cloud cost.

| Model | Wall | Input tokens | Output tokens | Result |
|---|---|---|---|---|
| qwen3:1.7b | 41.80s | 15 | 209 | OK (thinking overhead) |
| qwen2.5-coder:7b | 17.30s | 34 | 3 | OK. |

This measures gateway latency/accounting, not coding quality. Local energy/RAM
were not measured.

## 5. Self-development pipeline

| Run | Result |
|---|---|
| Mock apply/test/review/merge | 1.518s, merged |
| Real local-model patch `patch_32e0763…` | qwen2.5-coder:7b authored `format_bytes`; first apply failed (bad hunk count, exit 2); `git apply --recount` retest passed full suite in 126.8s |
| Independent review | PASS on correctness/safety; **rejected** because the helper has no production caller (dead code) and uses MB vs existing MiB convention |

The gate rejected the weak patch rather than merging it. The proposal remains
available for an integration patch.

## 6. Upstream skill-prompt ablation (prompt-level only)

Same task, same local model (`qwen2.5-coder:7b`), one run per variant. Skill
bodies fetched from pinned upstream revisions and used as prompt instructions;
runtimes/hooks/installers were not executed.

| Variant | Pass | Wall | Output tokens | Note |
|---|---|---|---|---|
| baseline | yes | 107.0s | 334 | correct |
| Ponytail skill | yes | 51.0s | 340 | correct |
| Superpowers TDD skill | no | 71.7s | 393 | added GB test, implementation lacked GB |
| ECC ai-regression-testing skill | yes | 85.3s | 440 | correct |
| Headroom skill | yes | 45.9s | 321 | correct |

These are noisy single-run prompt effects, not upstream runtime quality.
Headroom compression/proxy/caching behavior was **not** measured. Ponytail/
Superpowers/ECC hooks/controllers were **not** activated.

## 7. Coverage matrix

| Tool/surface | Status | Evidence/limit |
|---|---|---|
| DIRECTOR core | measured | domain/retrieval/MCP/selfdev |
| OpenCode | partially measured | native MCP connection + `director_status` tool-call via loopback proxy; Claude/Codex paths and tool-call latency not measured |
| MCP | measured | stdio latency/protocol |
| Ollama local models | measured | latency/token accounting |
| Headroom | prompt skill only | compression runtime not run |
| Ponytail | prompt skill only | runtime/hooks not run |
| Superpowers | prompt skill only | runtime/hooks not run |
| ECC | prompt skill only | selected skill; catalog/controllers not activated |
| Cloud providers | partially measured | loopback OpenAI-compatible proxy with keychain/cost; no real cloud key/spend |
| Container runner | measured | Docker 29.6.2; uid 65534, read-only mount, no network, write denied |
| Kernel/microVM sandbox | not measured | container runner is not a hardened microVM |
| 1B lexical retrieval | attempted, not completed | stopped after 4h at 3.9GB/~22% at 95% CPU; 100M measured |

## 8. Container runner and image

| Check | Result |
|---|---|
| Image build | `director:local`, 260MB |
| Cold CLI (`docker run --rm ... --version`) | 2.007s / 1.662s / 1.721s (3 runs) |
| Project init/status in a mounted volume | passed as uid 65534 |
| Read-only source mount | write denied (`Read-only file system`) |
| Network | disabled (`Network is unreachable`) |
| Container 100M retrieval | 217.5s ingest, 100 queries, recall 1.0, p50 1.164ms, p95 7.134ms, 1.78GB |

The image is `python:3.12-slim` plus DIRECTOR and its MCP/DOCX dependencies; it
does not include Chrome, Node or the browser/ML fixtures. The CI `docker` job
builds it and runs version/init/status.

## 9. Skill matrix (prompt-level)

Model: `llama-3.3-70b-fp8-fast`; 2 seeds; 98 runs; same tasks and graders.
Full method and raw data: `docs/build/SKILL_MATRIX.md` and
`benchmarks/results/skill_matrix.json`.

| Rank | Tool | Coding | Selfdev | Design | Clarity | Context | Tokens | Overall |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | **DIRECTOR** | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 4,514 | **84.1** |
| 2 | Ponytail | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 5,244 | 84.1 |
| 3 | ui-ux-pro-max | 3/6 (84%) | 2/2 | 100% | 75% | 100% | 5,529 | 81.2 |
| 4 | Direct model | 3/6 (83%) | 2/2 | 89% | 80% | 100% | 5,131 | 80.4 |
| 5 | Headroom | 3/6 (92%) | 2/2 | 86% | 80% | 100% | 4,742 | 79.9 |
| 6 | Superpowers | 3/6 (89%) | 2/2 | 86% | 75% | 100% | 4,791 | 79.1 |
| 7 | ECC | 3/6 (88%) | 2/2 | 86% | 70% | 100% | 4,446 | 78.4 |

This is a prompt-level ablation, not an upstream runtime/hook benchmark. DIRECTOR
ties Ponytail on score with 14% fewer output tokens; ui-ux-pro-max wins design.
The 95% bootstrap ranges overlap heavily (DIRECTOR/Ponytail 73.4–94.1), so the
score rank is directional, not statistically separable. Coding/selfdev are
test-graded; design/clarity/context use fixed rubrics. One model, one host, two
seeds.

The runtime portfolio (`benchmarks/router_score.py`) routes coding to verified
recipes (3/3, including slugify), design to ui-ux-pro-max, clarity to the
DIRECTOR template, and context/selfdev to DIRECTOR: **100.0** on the same
dimensions, versus 84.1 for the best single prompt. It is a portfolio, not a
single-prompt claim.

## Honest conclusion

DIRECTOR is fast on the measured local paths and its gates correctly reject a
weak model-authored patch. The benchmark set does **not** establish superiority
over Headroom, Ponytail, Superpowers or ECC, does not test cloud models, and
does not establish 1B retrieval or general domain accuracy.

To claim more, run:
1. multi-task, multi-seed, held-out coding tasks with human/LLM-judge calibration;
2. actual upstream runtime/hook integration and paired ablations;
3. 1B retrieval and temporal/ACL/contradiction queries (100M exact-marker is measured);
4. cloud-provider runs with authorized keys/budgets;
5. hardened microVM/kernel sandbox runs (the Docker runner is measured).
