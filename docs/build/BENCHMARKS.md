# DIRECTOR benchmarks

Date: 2026-11-24 (run timestamps 2026-11-23 UTC)
Host: Windows 11, Python 3.14.4, SQLite 3.50.4, Node 24.14.1,
Chrome 158, Ollama 0.40.11.

Raw results:

- `benchmarks/results/director_bench_20261123T195633Z.json` — core/domain/retrieval/MCP/local-model/selfdev
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

100M and 1B were **not run**. Exact lexical markers are necessary smoke
evidence, not semantic/temporal/ACL/billion-scale proof.

## 3. MCP stdio

Protocol `2025-11-25`, 9 tools, 20 `director_status` calls.

| Metric | Value |
|---|---|
| mean | 0.591ms |
| p50 | 0.451ms |
| p95 | 1.570ms |
| ping | ok |

Local stdio only. Remote/OAuth/native tool-call not measured.

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
| OpenCode | partially measured | native MCP connection connected; tool-call not |
| MCP | measured | stdio latency/protocol |
| Ollama local models | measured | latency/token accounting |
| Headroom | prompt skill only | compression runtime not run |
| Ponytail | prompt skill only | runtime/hooks not run |
| Superpowers | prompt skill only | runtime/hooks not run |
| ECC | prompt skill only | selected skill; catalog/controllers not activated |
| Cloud providers | blocked | no credentials/spend |
| Kernel/container sandbox | blocked | Docker daemon not running |

## Honest conclusion

DIRECTOR is fast on the measured local paths and its gates correctly reject a
weak model-authored patch. The benchmark set does **not** establish superiority
over Headroom, Ponytail, Superpowers or ECC, does not test cloud models, and
does not establish 100M/1B retrieval or general domain accuracy.

To claim more, run:
1. multi-task, multi-seed, held-out coding tasks with human/LLM-judge calibration;
2. actual upstream runtime/hook integration and paired ablations;
3. 100M/1B retrieval with temporal/ACL/contradiction queries;
4. cloud-provider runs with authorized keys/budgets;
5. container/VM sandbox runs.
