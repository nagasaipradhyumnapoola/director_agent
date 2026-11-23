# DIRECTOR evaluation and acceptance plan

Research date: 2026-11-23. This is a **future build/test contract**, not results. Use it together with the blueprint, research and master prompt. The earlier interrupted prototype has known failures in STATUS.md.

## Evaluation ladder

| Layer | Question | Required evidence |
|---|---|---|
| Deterministic contracts | Do boundaries hold for every supported input? | Unit/property/adversarial tests for schema, scope, budgets, queue and evidence |
| Component correctness | Do index, adapters, evaluators and recovery work? | Real local integration tests, process crashes, corrupted/stale state, protocol tests |
| Domain task success | Does the final artifact meet the actual brief? | Held-out website, ML and research/document cases with independent acceptance |
| System value | Does supervision improve outcomes at acceptable cost? | Paired baseline/ablations with matched models/tools/resources and raw traces |
| Long horizon/scale | Do memory and recovery remain useful? | Replay/soak/scale tests with temporal updates, deletion, failures and realistic queries |
| User value | Do people act on findings and keep the tool? | Consented real-work trials, accepted/rejected findings and interruption feedback |

## Invariants that must have adversarial tests

1. No model calls at idle; no automatic external calls with external access disabled.
2. A capability/task/plugin/retrieved document cannot expand its own permissions or budget.
3. Exact request/body/account/destination/action/risk/task-revision binding for consequential effects; unknown dispatch outcomes are held for state reconciliation, not blindly retried.
4. Atomic reservations across processes; usage includes retries, cached reads/writes, outputs and recovery calls. Pause on exhausted quota or configured allowance.
5. Queue claims have unique fencing tokens and generations; expired/superseded workers cannot publish index, findings, graph or receipts. Edits during work leave successor work queued. Retry caps apply to crashes as well as explicit failures.
6. Static links, hardlinks, Windows junctions, traversal, state sidecars and archive escapes cannot cross declared boundaries. TOCTOU threat assumptions must be explicit; isolate hostile sources rather than hand-wave races away.
7. Secret fixtures never enter prompts/indexes/logs/receipts/notifications. Test credential-like file content, names, invalid schema values and exception messages. Redaction is defense in depth, not a guarantee.
8. Bound transport frames before parsing; reject unknown arguments; bound per-file findings, intermediate memory, total serialized response and actual provider payload. Deduplicate requested artifacts. Report truncation explicitly; never turn an incomplete check into success.
9. Context accounting includes final serialization/provenance/tool envelope and existing conversation when known. Unknown host headroom stays unknown. No silent truncation of user goal or policy.
10. Evidence hashes match the exact source/dataset/artifact/environment/check version actually evaluated. Verify current state synchronously before presenting acceptance. Policy, source or evaluator changes invalidate relevant evidence.
11. Unsupported languages/formats/domains are indexed/unknown as appropriate, never labeled validated. Include case-insensitive extension dispatch and disguised/binary/oversized input fixtures.
12. Findings carry source hash, evaluator version, receipt ID, time, confidence and limitations. Source relevance or issue closure cannot satisfy an acceptance criterion.
13. Watcher starts before reconciliation, handles rename/subtree/policy changes and queue overflow, ignores its own state, and exposes stale/degraded monitoring. Simulate shutdown during startup and process death.
14. Checkpoints/handoffs retain current intent, authority, budgets, evidence, open hypotheses and next action. Compaction must not silently turn a hypothesis into a confirmed fact.
15. No placeholder production capability passes tests through canned output, mocks alone, test deletion or swallowed errors. External-provider tests are opt-in and separate from default offline tests.

16. Adapter coverage explicitly separates advisory observation, supported blocking hooks and gateway-mediated effects. Test bypass paths; never claim DIRECTOR enforces an external builder's every action unless the declared scope is actually mediated.

## Three first domain pilots

**Website pilot:** an existing small site with a broken primary journey, keyboard issue and mobile overflow, plus clean controls. Acceptance includes actual user journey, defined viewport/keyboard states, error/loading states and data correctness. A successful build is only one check. Include human visual review for subjective design and accessible-text quality.

**ML pilot:** a small CPU-runnable dataset/model task with a known split leak, baseline and hidden evaluation. Acceptance includes data/source manifest, split/checkpoint lineage, held-out metric, slice analysis, reproducible environment/run and resource report. Do not reward memorization, leaked test labels or a high training score. Record nondeterminism limits.

**Research/document pilot:** a current question with conflicting primary sources and an output document. Acceptance includes claim-source mapping, date sensitivity, transparent inference, correct calculation and rendered artifact inspection. A confident fabricated citation is a failure even if prose is polished.

Keep budgets low and dataset sizes small. These pilots establish a reusable substrate across domains; they do not prove support for every kind of project.

## Baseline and ablations

Compare: builder alone; core contract/evidence layer; optional Headroom; optional Ponytail rubric; selected Superpowers procedures; selected ECC capabilities; selected combination. Match model version/effort, tools, task inputs, time/token/cost ceilings and starting artifact state. Randomize order and repeat stochastic runs. Keep evaluator data hidden from builder/strategy tuning; maintain a separate development set.

Primary metric: **total resource cost per independently accepted outcome**. Also record acceptance rate, error severity, useful/false findings, missed seeded defects, recovery quality, p50/p95 latency, model/input/output/cached tokens, dollar cost using dated actual tariffs, local CPU/RAM/GPU energy proxy, tool calls, interruptions and human correction time. Wall time and cost can improve in opposite directions; report both.

LLM judges should be calibrated against human decisions, use task rubrics and report disagreements. Use different evidence/roles, not merely a second copy of the builder's success narrative. Do not publish relative gains without sample counts, uncertainty, raw artifact/trace references and limitations.

## Memory and billion-scale validation

| Tier | Corpus/evaluation requirement | Cannot claim yet |
|---|---|---|
| Tiny smoke | Reproducible lexical fixture, exact queries, no secret/cross-project leaks | Semantic usefulness or long-horizon memory |
| 1M/10M tokens | Diverse code/docs/history, updates, deletion, multi-hop/temporal/abstention queries | 100M/1B capacity or equivalent quality |
| 100M tokens | Incremental ingest, restart/backup, concurrency, index/disk/RAM accounting | 1B performance based on linear extrapolation alone |
| 1B tokens | Actual indexed tokenizer count, resource requirements, realistic held-out queries, ACL/deletion/contradiction tests | Billion-token attention or complete retrieval |

Measure recall@k, MRR, grounded-answer correctness, citation validity, source freshness, temporal updates, false-premise handling, deletion/forgetting, index size, ingestion/reindex rate and p50/p95 retrieval/end-to-end latency. Evaluate recursive exploration and compression as separate ablations with depth/call/cost caps. Needle retrieval is necessary smoke evidence but insufficient for project understanding.

## Reporting format

Each result record includes objective/criterion, input snapshot, implementation/evaluator versions, environment, resources, expected outcome, observed evidence, pass/fail/unknown, confidence and limits. Publish an explicit compatibility matrix: capability metadata known; source inspected; adapter generated; protocol tested; native client tested; domain outcome validated; production supported. Never collapse these into a single “supported” badge.
