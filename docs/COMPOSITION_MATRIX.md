# DIRECTOR composition and support matrix

Date: 2026-11-23. This is a research/design handoff. **No row below establishes a completed DIRECTOR integration.**

| Capability/layer | What is established now | What a future builder must prove | Default decision |
|---|---|---|---|
| Universal DIRECTOR core | Product/architecture/acceptance specified; interrupted prototype is unready | Durable contracts, queue, policy, budget, context and evidence tests plus real domain outcomes | Build small shared substrate |
| Headroom | Full skill inspection, selected runtime traces, mode/cache/recovery/network behavior documented | Pinned optional adapter; offline behavior; fidelity/recovery/cache/cost ablations | Optional; lossless experiment first |
| Ponytail | All six canonical skills and generated copies inspected; key adapters/metrics/benchmarks traced | Selected rubric improves outcomes without deleting necessary work; host variants preserve intent | Adapt principles; no global install |
| Superpowers | All fifteen skills and relevant helpers/prompts inspected | One selected lane; no duplicate gates; durable typed evidence; real host activation | Adapt relevant engineering procedures |
| ECC | All tracked skills inventoried; depth-qualified mechanism summaries and critical runtime traces | Narrow capability selection, reviewed executable tools, authority separation, per-component licenses | On-demand catalog; no competing default controller |
| Claude Code hooks/plugin | Current docs checked; source adapter patterns compared | Real installation, trust, prompt/edit lifecycle, shell behavior, bounded output, dedupe, uninstall | Generated opt-in integration after core tests |
| Codex hooks/plugin | Current docs checked; current source variants compared | Version-specific native integration with actual tools/events; no assumptions from Claude | Separate tested adapter |
| MCP | Official spec/SDK docs checked; earlier prototype SDK round trip is narrow evidence only | Bounded frames/arguments/errors/results, compatible lifecycle, real client tests and policy boundaries | Stdio/local-only first |
| A2A | Current specification reviewed | Auth, versioning, delegation, cancellation, budgets and untrusted agent-output boundary | Later optional interface |
| Website/app domain | Profile and real-journey evidence defined | Browser/accessibility/visual/data tests on held-out tasks | First pilot |
| ML/model domain | Data/evaluation/reproducibility evidence defined | Small genuine experiment with leakage controls, held-out metrics and resource limits | First pilot |
| Research/document domain | Claim-source/date/render evidence defined | Current-source task and real rendered artifact with independent checks | First pilot |
| Other domains | Extensible profile/evaluator contract specified | Working adapter plus domain-appropriate evaluated outcomes | Unsupported until validated |
| Computer-use | Isolation/authorization architecture specified; official interface reviewed | Isolated runtime and verified external states; no duplicate side effects | Later, prefer supported API/DOM tools |
| Billion-token virtual memory | Architecture, arithmetic assumptions and benchmark tiers defined | Actual large corpus, tokenizer/resource measures, retrieval/update/deletion/ACL evaluations | Scale target; no capacity claim |
| 24/7 service operation | Lifecycle and recovery requirements specified | Native service start/stop/health/updates/uninstall; host/budget failures tested | Explicit opt-in, not enabled now |

Use separate evidence levels in future reports: **designed → source inspected → implemented → unit-tested → protocol/integration-tested → native-client tested → domain-validated → operationally supported**. Levels are not interchangeable, and one component's success cannot certify another.

Enforcement coverage is separate again: **observed / advisory / supported blocking hook / gateway mediated**. DIRECTOR can enforce only the workers/actions actually covered by a tested mediation path; external host restrictions remain independently authoritative, and bypass paths must be disclosed.
