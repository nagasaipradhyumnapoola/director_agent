# Headroom: implementation and skill analysis

Research date: 2026-11-23. Inspected read-only source snapshot; temporary local clone removed after research. Canonical repository: [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom), pinned to **ce0460cfa8598dc939243dbc7aec4b2d35f4e44a**, committed **2026-11-21T17:25:16-08:00**. Root license: Apache-2.0. This is static source analysis; no upstream package, hook, proxy, installer, model, test or benchmark was executed. Dependencies and bundled models have their own licenses and supply-chain requirements.

## Recommendation

Use Headroom as an **optional measured transport/content optimization adapter**, after DIRECTOR has a trustworthy provider boundary and evaluation harness. Do not make a proxy mandatory for the first local source-supervision MVP. DIRECTOR owns task contracts, permission grants, budgets, evidence, memory retention and retrieval policy. Compression cannot replace any of them.

The most suitable first experiment is lossless agent-mode densification with a strict offline configuration, protected system/user instructions and round-trip checks. Compare total task outcomes, latency, retrieval calls and realized cost against the same workflow without it. Do not inherit advertised savings as a DIRECTOR result.

## Every tracked skill

The pin contains exactly **two tracked `SKILL.md` files**. Both full bodies were inspected and mechanically inventoried. Their hashes, bytes, words and pinned links are in HEADROOM_SKILLS.json/CSV. There is one conceptual skill in a canonical source and plugin distribution copy; all other runtime features below are code, not additional skills.

| Skill path | Activation and mechanism | Artifacts/tools | DIRECTOR decision |
|---|---|---|---|
| `skills/headroom/SKILL.md` | Triggered by reducing LLM input cost, oversized logs/JSON/tool results/history, or fitting context. Guides an agent to add `compress(messages, model=...)`, forward `result.messages`, and inspect before/after counts. Provides offline no-provider smoke example. Distinguishes Python in-process, TypeScript proxy and coding-agent wrapping. | May instruct package installation and app source changes; wrapper setup can alter agent transport configuration. No task queue or independent reasoning loop. | Adapt; on-demand provider optimization procedure, gated by owner scope and comparative fidelity tests. |
| `plugins/headroom-skill/skills/headroom/SKILL.md` | Distribution copy of the same procedure; inventory compares exact content hashes. It does not itself implement compression. | Plugin host loads prose; all effective compression happens in installed runtime. | Do not load alongside canonical copy; deduplicate by semantic identity/version. |

The skill says not to claim a savings percentage and discourages unnecessary `[all]`/`[ml]` installs. It preserves user messages by default but points out that data in user messages needs explicit configuration. Its instructions are useful but cannot prove the runtime is offline or output lossless. [Canonical skill](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/skills/headroom/SKILL.md).

## How the runtime actually works

### 1. A convenience API builds a configured pipeline

`headroom/compress.py` defines a user-facing configuration and result rather than merely calling a model to summarize content. Its configuration separates user/system messages, recent code protection, analysis-intent protection, frozen cached-prefix message count, minimum size, optional ML model, compression regime and round-trip verification. The source defaults `compress_system_messages=True`; DIRECTOR should explicitly protect instructions rather than rely on a blanket “tool output only” description.

`mode='agent'` chooses lossless densification with verification forced on, no CCR/removal and no ML text compression. A transform that cannot establish round-trip equivalence falls back to the original. Default mode can use compressed representations and retrieval markers. Those are different fidelity contracts. `protect_recent` applies to detected code, not every recent JSON/log/text payload. `target_ratio` targets one compressor, not an enforced whole-request budget. [Configuration, lines 83–182](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/compress.py#L83).

### 2. Routing chooses transforms by content and policy

The pipeline optionally applies tool-result interceptors, then cache alignment, then a content router. It no longer includes the former rolling-window history-dropping stage. The router dispatches structured arrays, code, logs, search output, configuration, HTML, text and images through distinct adapters. It has per-stage deadlines and configurable worker limits. A circuit breaker returns original messages after repeated transformation failures instead of repeatedly failing on the request hot path. Passing originals preserves data but may exceed an upstream context/budget limit: DIRECTOR must still enforce its final dispatch budget. [Pipeline](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/transforms/pipeline.py#L107), [router adapters](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/transforms/content_router.py#L270).

The Rust pipeline configuration distinguishes cheap structural reformatting from optional offloading. It uses bloat estimates and thresholds to avoid retrieval-marker overhead on small inputs: log density/repetition, diff context ratio, search clustering and array shape are separate signals. Reformatting can pack repeated structures densely; offloading may omit material from the immediate request and requires recoverable originals. Its lockfile/whitespace noise policy is a tradeoff, not proof that those changes have no security significance. Dependency and supply-chain investigations must be able to retrieve lockfile details. [Embedded configuration](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/crates/headroom-core/config/pipeline.toml).

### 3. Reversibility is a storage and retrieval protocol

CCR associates a compressed representation with stored originals and exposes `headroom_retrieve`. The MCP path caches file content by hash and uses TTL-managed originals; retrieval can fail because an original expired or its owning runtime is unavailable. A marker is not permanent archival memory. DIRECTOR must bind recovery to project/session identity and retain its own durable source provenance and deletion policy.

The implementation explicitly exempts retrieval-tool results from recompression, including aliases and nested orchestration payloads. Otherwise the supposedly complete original can be replaced by another marker, producing a recovery loop. This is a concrete integration invariant for DIRECTOR: **recovery data must remain recoverable without recursively invoking the same lossy transformation**. [Tool exemptions and wrapper detection](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/config.py#L239), [MCP retrieval and expiry](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/ccr/mcp_server.py#L603).

Batch context is a separate bounded TTL store retaining messages, tool definitions, model/provider continuation metadata and optional credentials in memory. Its 24-hour default TTL and 10,000-context cap are operational limits, not a billion-token durable knowledge index. Do not serialize provider credentials or copy this store wholesale into DIRECTOR receipts. [Batch store, lines 1–90](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/ccr/batch_store.py#L1).

### 4. Fewer tokens can still cost more

`CompressionPolicy.net_mutation_gain` models saved tokens against the cost of rewriting a warm cached suffix. It takes delta tokens, suffix length, expected future reads and cache survival probability. The source computes a mutation only when projected gain is positive; mode policy differs between PAYG/OAuth and subscription. This is a better lesson than “compress everything.” DIRECTOR must use current provider tariffs and actual usage, not copy these policy constants as universal prices. Prefix stability, latency, fidelity and possible retrieval calls belong in the comparison. [Policy, lines 147–273](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/transforms/compression_policy.py#L147).

Its tokenizer path may be exact for a supported tokenizer, calibrated for another provider, or a character-based fallback. “Tokens saved” can therefore be an estimate depending on configuration. DIRECTOR's accounting must preserve measured/estimated distinction and reconcile actual provider usage. [Tokenizer selection](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/transforms/pipeline.py#L213).

### 5. Hooks ensure runtime availability, not task quality

The agent-hooks plugin registers SessionStart startup/resume and PreToolUse Bash/PowerShell handlers calling `headroom init hook ensure`. Its launcher searches configured binaries, PATH and common installation locations, then tries installed Python module execution with `-P` to avoid importing an attacker-controlled same-name module from the project. Missing runtime prints a diagnostic and exits successfully. A hook's exit success is therefore not proof compression is active. The skills plugin and runtime hooks serve distinct roles. [Hook definitions](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/plugins/headroom-agent-hooks/hooks/hooks.json), [launcher](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/plugins/headroom-agent-hooks/bin/headroom-hook.sh).

### 6. Local compression does not imply zero network

Source comments and beacon gating show anonymous session telemetry enabled by default, with offline/telemetry opt-out controls. The skill documents `HEADROOM_OFFLINE=1` to suppress update checks, model/pricing downloads and beacon activity. DIRECTOR's proposed adapter must configure offline behavior before import, keep external calls opt-in and verify it at the process/network boundary. This finding concerns default network behavior, not a claim that file contents are uploaded. [Session telemetry](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/telemetry/session.py#L1), [beacon gate](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/telemetry/beacon.py).

## DIRECTOR integration contract and failure tests

1. Pin runtime and model/transform versions; record license and dependency provenance. Do not run upstream installers merely to reuse an idea.
2. Preserve original user/system instructions, source hashes and source ACLs. Compressed content remains untrusted data.
3. Start with lossless/offline densification. Add lossy modes only after adversarial fidelity evaluations, including buried errors, rare outliers, code review, dependency lockfile changes and multilingual text.
4. Include all recovery calls and cache writes/reads in cost accounting. Protect recovered originals against recompression.
5. Validate final provider payload, not only transform output. Fallback originals must not bypass limits.
6. Test expired/missing markers, runtime absence, malformed tool pairing, prefix-cache churn, mixed model usage, secrets in tool output and concurrent workspace isolation.

## Evidence limits

README savings and answer-equivalence results are author-reported, scenario-dependent evidence. This analysis inspected mechanisms and relevant test paths but did not reproduce upstream experiments. The static presence of tests does not establish they pass. DIRECTOR currently contains no Headroom runtime adapter and claims no upstream compression savings. Its original bounded lexical packet builder is narrower, measurable and explicitly documented.
