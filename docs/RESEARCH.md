# DIRECTOR research — mechanisms, standards and decisions

**As of 2026-11-23.** Primary sources were opened on this date; four upstream repositories were cloned read-only and pinned. This report separates source-observed behavior, author-reported experiments, research findings and DIRECTOR design recommendations. No upstream installers, hooks, models, tests or benchmarks were run. No claim of market completeness, runtime certification or guaranteed future compatibility is made.

## 1. The requested upstream stack, inspected beyond READMEs

| Project | Exact inspected revision | What it implements | Skill coverage | DIRECTOR decision |
|---|---|---|---|---|
| [Headroom](https://github.com/headroomlabs-ai/headroom/tree/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a) | ce0460cfa8598dc939243dbc7aec4b2d35f4e44a | Compression/densification runtime, proxy, recovery store/MCP, lifecycle integration | 2 tracked files; 1 conceptual skill and distribution copy | Optional measured adapter; preserve instruction/source fidelity and offline defaults |
| [Ponytail](https://github.com/DietrichGebert/ponytail/tree/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10) | ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10 | Six prompt behaviors, host adapters, source map, metrics/import/webhook components | 12 tracked; 6 canonical +6 generated variants | Adapt reuse/minimum-change rubric; keep telemetry/import optional and evidence-qualified |
| [Superpowers](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7) | 22f0b463e7a5e579904dd6211a520321035526f7 | Composable development procedures and execution/review helpers | 15 tracked, all canonical | Select one development lane; retain durable evidence outside scratch ledgers |
| [ECC](https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53) | 4adeee6732a12d1540f49a4d50a38ce8c97f9a53 | Large skill library, executable hooks, memory/learning/coordination components | 1,089 tracked; 328 primary skills;331 directory identities | On-demand catalog; reject competing default controllers; review nested licenses |

Total: **1,118 tracked SKILL.md files**, representing **350 primary/canonical skill entries** under the definitions above. ECC adds three side-only identities; these totals do not assert semantic uniqueness across repositories or translations.

The detailed [Headroom](research/HEADROOM_ANALYSIS.md), [Ponytail](research/PONYTAIL_ANALYSIS.md), [Superpowers](research/SUPERPOWERS_ANALYSIS.md) and [ECC](research/ECC_ANALYSIS.md) reports explain actual flows and link pinned source lines. CSV inventories support browsing; JSON inventories preserve additional per-variant evidence. ECC's JSON is approximately 26 MB: retrieve selectively rather than putting it in one prompt.

**Coverage limits:** Headroom's two full skill bodies plus selected runtime paths were inspected. Ponytail's six canonical skills, generated variants, adapters and key supporting code were examined. Superpowers' fifteen canonical bodies and relevant helpers/prompts were read. ECC's every skill body received a complete programmatic read; 233 mechanism summaries are curated, 98 cookbook summaries body-derived, and 16 focus packages plus selected runtime paths received deeper semantic tracing. A parser reading all text is not a line-by-line expert audit or proof every recipe works.

## 2. Important implementation lessons

- **Compression and attention are different.** Headroom can transform content or offload recoverable originals; it does not give a model unlimited attention. Its library has lossless agent mode and other modes with different fidelity contracts. Its cache mutation model accounts for warm-prefix rewrites, so fewer visible tokens need not mean lower realized cost. See the Headroom report's pinned configuration/policy sources.
- **Local computation and zero-network defaults are different.** Headroom's upload beacon is enabled by default in the pin; explicit offline controls are necessary for DIRECTOR's no-external-call default. This is a source-observed network-default issue, not evidence that prompt contents are uploaded. [Beacon gate](https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/telemetry/beacon.py).
- **Prompt discipline and enforcement are different.** Ponytail and Superpowers largely guide model behavior. Their hooks and helper scripts have real effects, but neither should become DIRECTOR's permission/budget/completion authority. Per-host compressed copies can differ from canonical instructions; compare semantic invariants, not only file presence.
- **A quality notification is not a release gate.** ECC includes pass-through quality reporting and coordination validation whose semantics differ from independent product acceptance. Its GateGuard retry friction must not be interpreted as action-bound consent. These source traces are in ECC_ANALYSIS.md; no runtime exploit claim is inferred from static analysis alone.
- **Memory and learned instructions need separate authority.** ECC's learning system can capture scrubbed observations and later inject learned instincts. DIRECTOR should store observations with provenance and require an explicit promotion policy before they influence instructions. “Unreviewed memory” cannot expand permissions.
- **Benchmark headlines are not portable guarantees.** Ponytail's reported evaluation constraints and missing raw artifacts limit independent reproduction. Headroom savings depend on content and mode. DIRECTOR needs its own paired ablations across project domains, including the cost of reviews, observers, compaction, recovery and failures.

## 3. Current interoperability and integration research

| Topic | Verified primary evidence | Design consequence | Confidence/limit |
|---|---|---|---|
| Claude Code hooks | Lifecycle event JSON, shell/exec forms and output conventions are documented. [Hooks reference](https://code.claude.com/docs/en/hooks) | Keep synchronous prompt work very small; validate events; enqueue investigations; test Windows shell selection | High for documented interface; installed-client integration still requires actual tests |
| Claude plugins | Plugins package skills/hooks and other components through a manifest. [Plugin reference](https://code.claude.com/docs/en/plugins-reference) | Package one selected DIRECTOR interface, do not duplicate manually installed hooks | High for docs; signing/distribution/review are deployment work |
| Codex hooks | Current guide describes trusted project/user/plugin hook layers, UserPromptSubmit context and duplicate commands running twice. [Hooks](https://learn.chatgpt.com/docs/hooks) | Feature-detect; register once; do not infer identical Claude/Codex event/tool payloads | High for current docs; older releases differ |
| Codex skills/plugins | Skills are workflow instructions/resources; plugins can bundle skills, MCP and hooks. [Skills](https://learn.chatgpt.com/docs/build-skills), [plugin architecture](https://developers.openai.com/plugins/concepts/plugins) | Use small descriptions and progressive loading; separate package capability from actual runtime availability | High for current docs |
| Codex programmatic integration | App Server provides a richer integration surface than text scraping. [App Server](https://learn.chatgpt.com/docs/app-server) | Consider host events/turn control behind a versioned adapter; avoid unstable transcript parsing | High for interface, untested for DIRECTOR |
| MCP | Latest specification opened resolves to **2026-07-28**. [Specification](https://modelcontextprotocol.io/specification/2026-07-28) | Pin/negotiate protocol; avoid assuming older lifecycle rules remain universal | High as of access date |
| MCP Python SDK | Official v2 docs rename FastMCP to MCPServer and describe lifecycle/protocol changes. [What's new](https://py.sdk.modelcontextprotocol.io/whats-new/) | Use official SDK and real client conformance tests; do not copy old v1 snippets uncritically | High; PyPI metadata observed mcp2.3.0, not a future pin guarantee |
| MCP security | Covers local-server compromise, token passthrough, SSRF and related risks. [Security](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices) | Stdio first; no arbitrary execution tool; input caps before parse, output caps, least privilege and sanitized errors | High for threat classes; controls need adversarial validation |
| Agent Skills | Defines SKILL.md metadata/body and optional support resources. [Specification](https://agentskills.io/specification) | A skill is an instruction package, not a worker, scheduler, sandbox or memory engine | High |
| A2A | Current specification distinguishes versioned agent interfaces/tasks, including version negotiation. [Specification](https://a2a-protocol.org/latest/specification/) | Use later for authenticated delegation, not internal queue replacement or automatic trust | High for interface; no DIRECTOR A2A implementation |

Documentation compatibility is surface-specific. Both MCP and native host adapters need tests; the presence of a hook/plugin schema is insufficient proof of end-to-end behavior.

## 4. Context, memory and long-horizon research

| Source | What it supports | DIRECTOR inference, not a source guarantee |
|---|---|---|
| [Anthropic context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents), 2025-09-29 | Treat context selection as a constrained engineering problem; retrieval and state management matter | Keep focused contexts, retrieve progressively and evaluate loss from summaries |
| [Advanced tool use](https://www.anthropic.com/research/advanced-tool-use), 2025-11-24 | Tool search and programmatic calling can change how tool information is supplied | Load tools on demand, filter deterministic output before it enters model context |
| [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) and [prefix preservation](https://developers.openai.com/api/docs/guides/keep-prefix-unchanged), live docs | Cache economics/settings and prefix behavior vary by model | Stable prefixes and actual cache-write/read accounting are part of routing; no fixed savings promise |
| [OpenAI compaction](https://developers.openai.com/api/docs/guides/compaction), live docs | Long-running state can be compacted, with provider-specific opaque items and replay rules | Preserve source/evidence/authority externally; follow supported compaction protocol rather than hand-editing opaque state |
| [SQLite FTS5](https://sqlite.org/fts5.html) | Full-text indexes and relevance-ranked retrieval | Good low-operating-cost lexical baseline; not semantic memory or billion-scale proof |
| [Qdrant quantization](https://qdrant.tech/documentation/manage-data/quantization/) | Vector storage optimization with quality/performance tradeoffs | Evaluate dense/hybrid memory as corpus grows; measure recall loss and memory overhead |
| [Letta](https://github.com/letta-ai/letta) | Stateful-agent platform and memory-oriented prior art | Compare before implementing a second full memory runtime; platform integration has operational cost |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal graph memory prior art | Evaluate time/version/relationship retrieval; keep extraction confidence distinct from truth |
| [RULER](https://arxiv.org/abs/2404.06654), 2024 | Tests long-context behavior beyond one simple retrieval task | Advertised window size cannot substitute for tested effective use |
| [LongMemEval](https://github.com/xiaowu0162/longmemeval) and [LongMemEval-V2](https://arxiv.org/abs/2605.12493), 2026-05-12 | Evaluate longer-term and environment-specific memory abilities | Include updates, temporal state, workflows, false premises and abstention; factual lookup alone is insufficient |
| [Recursive Language Models](https://arxiv.org/abs/2512.24601), revised2026-05-11 | Explores prompts as an external environment with recursive bounded-context exploration | Candidate experimental retrieval/reasoning lane; bound recursion/tool execution/cost and reproduce relevant tasks |
| [ReContext](https://arxiv.org/abs/2607.02509), 2026-07-02 | Studies evidence organization/replay while retaining original context | Evidence availability and evidence use are distinct; proposed replay need not be implementable through every hosted API |

Research-paper results belong to their tested settings. Neither recursive exploration nor graph memory establishes arbitrary-domain correctness or one-billion-token simultaneous attention. Large-corpus architecture and sizing assumptions are in DIRECTOR_BLUEPRINT.md; an actual scale benchmark remains future work.

## 5. Orchestration, evaluation, security and computer-use

- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) provides checkpoint/state concepts; [Temporal durable execution](https://docs.temporal.io/durable-execution) provides durable workflow/activity semantics. Compare their operational costs to a small local SQLite queue before adopting either. Persistence still requires idempotent effects, explicit retries and correct state/version handling.
- [OpenHands](https://docs.openhands.dev/overview/introduction) supplies software-agent SDK/server/client prior art. It is a potential execution adapter or competitor in engineering workflows, not a universal project evaluator. Do not duplicate its entire runtime merely to supervise it.
- [Anthropic agent evals](https://www.anthropic.com/research/demystifying-evals-for-ai-agents), 2026-01-09, and [MLflow evaluation](https://www.mlflow.org/docs/latest/genai/eval-monitor/) support systematic evaluation rather than one-off demonstrations. DIRECTOR should combine deterministic/domain checks, independent judgments and calibrated human review. Judges can be wrong and must not control permissions.
- [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) provide an observability reference. Version-pin evolving attributes and collect privacy-safe usage/timing metadata by default; full prompts are sensitive optional data.
- [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) explains why retrieval does not eliminate injection. Combine source taint with an external policy boundary; “ignore malicious instructions” is not sufficient isolation.
- [Claude computer-use guidance](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) is a capability interface, not a guarantee of safe external actions. Use isolated accounts/environments and action-bound approval. Prefer structured APIs and [Playwright](https://playwright.dev/docs/intro) for supported web checks before pixel control.
- [PyTorch reproducibility](https://docs.pytorch.org/docs/2.15/notes/randomness.html) is a relevant ML-domain reference. Pin environment, data and checkpoint lineage, and record nondeterminism limits rather than assuming seeds prove reproducibility across releases/platforms.

## 6. 2026 direction: supported observations versus bets

**Observed in the sources:** host-native extension surfaces are converging around skills/plugins/hooks/MCP; protocol and SDK semantics are still evolving; context transformation must account for caching and fidelity; agent systems are adding durable state, evaluation and memory; long-context research increasingly examines external exploration and evidence selection rather than window length alone.

**Design bets:** DIRECTOR's useful differentiator could be one transparent supervisor connecting domain-specific evidence, project knowledge and resource constraints across existing agents. A universal workflow core with selected domain capabilities is more plausible than a giant instruction bundle. These are product judgments, not established market facts.

**Do not bet on:** a permanent single model/provider, a literal billion-token attention window, unbounded autonomous self-improvement, always-correct learned memories, a tool succeeding implying a goal succeeded, or raw skill count implying competence.

## 7. Licensing and reuse

Root licenses observed: Headroom Apache-2.0; Ponytail/Superpowers/ECC MIT. Root licensing does not cover every nested contribution uniformly: ECC includes an osint-investigation CC BY-SA4.0 notice and other retained notices. This is a source inventory observation, not legal advice. Inspect each copied component/model/asset license, preserve notices, and keep optional integrations external when obligations or maintenance make vendoring unattractive. Do not copy upstream code into DIRECTOR merely because its conceptual technique is useful.

## 8. Remaining unknowns

No comparative DIRECTOR productivity result; no real user study; no independent upstream benchmark reproduction; no billion-token index; no validated domain-general autonomous completion; no production security audit; no live provider cost/routing experiment; no full native Claude/Codex/A2A integration matrix. The interrupted original prototype has known defects and is not evidence for these claims. These gaps are explicit build/evaluation gates, not hidden assumptions.
