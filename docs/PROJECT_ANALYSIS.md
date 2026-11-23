# DIRECTOR — project analysis and decisive tradeoffs

Date: 2026-11-23. Recommendation: **a small universal supervision core, selected workflows, and evidence-based domain adapters**. Scope is research/preparation only in this session.

## The product thesis

The exact customer is a person who delegates substantial project work to an agent and spends time correcting weak plans, restoring context, chasing incomplete work and checking unsupported success. The first practical user can be an individual builder using existing coding/research tools; broader domain support follows demonstrated demand and evaluators.

Today's alternatives include the host agent's own planning/tools, manually selected skills, Headroom's context optimization, Ponytail's simplicity guidance, Superpowers' development procedures, ECC's extensive capability library, stateful/memory platforms such as Letta/Graphiti, and execution/orchestration frameworks such as OpenHands/LangGraph/Temporal. None of the research here proves DIRECTOR is better than these alternatives. Its reason to exist must be fewer corrections and lower total cost per verified outcome across tools.

The architecture is feasible as a staged system. The claim of perfect end-to-end performance on anything is not. Universal input handling is cheap; universal competence and reliable domain evaluation are hard. The project should say exactly which task/domain/tool combinations are supported and what evidence establishes completion.

## Options

| Approach | Benefit | Main cost/failure mode | Decision |
|---|---|---|---|
| Skill-only bundle | Fast installation, low service complexity | No independent lifecycle, scheduler, policy or durable evidence; host compliance required | Useful interface, insufficient core |
| Mandatory all-in-one provider proxy | Can observe/transform model traffic centrally | Sensitive traffic boundary, cache/signature/protocol complexity, provider maintenance, hidden failures | Optional measured adapter only |
| Standalone local supervisor + thin adapters | Durable independent work, common policy/evidence, provider/host portability | Must implement and operate service boundaries correctly | Recommended |
| Full replacement general agent/runtime immediately | Maximum theoretical control | Rebuilds existing tools; expensive and delays user evidence | Reject as first milestone |
| Distributed multi-agent memory platform from day one | Scale and concurrency | Operational burden before local usefulness is proven | Defer until measured bottleneck |

## What should own each responsibility

| Responsibility | Accountable owner | Contributors |
|---|---|---|
| User intent, scope and priority | DIRECTOR task contract, revised by owner | Main agent/domain specialist proposes clarifications |
| Permission and spending | Core policy/effect gateway plus owner | Host restrictions provide additional boundaries |
| Durable work and recovery | Core scheduler and transactional store | Native events, host adapters, later workflow backend |
| Working-context selection | Context controller, with host/provider measurements where available | Headroom optional transforms; indexed capabilities/evidence |
| Domain procedure | One selected workflow per task/stage | Superpowers, Ponytail and ECC ideas/capabilities |
| Memory truth/promotion | Core source/provenance model and owner policy | Extractors/model suggestions remain untrusted until qualified |
| Verification/completion | Independent evaluator and core acceptance ledger | Main agent supplies artifacts/check results |
| Communication | Core priority/batching policy | Workers submit findings; no direct notification storm |

The supervisor should not micromanage every action. A compact task packet, correct capability selection and useful evidence often beat continuous commentary. A second full agent reading every token of the first is a cost multiplier unless experiments prove value.

Authority claims have a boundary: the DIRECTOR gateway controls its own mediated workers/actions. External builders remain subject to their host's permissions; advisory hooks cannot guarantee interception of every action. Compatibility reports must distinguish observing, advising, blocking a supported tool path and actually mediating all effects within a declared scope.

## The composition plan

1. Import capability metadata and maintain exact upstream revisions. Load only selected skill bodies and necessary references. Separate canonical skills, host variants and translated copies.
2. Compile an explicit task profile: domain evaluator + minimal procedure + permitted tools + budget. A workflow's proposal is never authority to execute or spend.
3. Put Ponytail's reuse/simplicity decision before a selected engineering plan; apply Superpowers' relevant testing/debugging/review procedures to material code changes. Do not impose programming TDD literally on a literature review or visual artwork.
4. Select ECC specialist procedures for domain work; review executable scripts and external requirements before enabling them. Do not activate its alternate controllers, learned-instruction injection or approval substitutes by default.
5. Introduce Headroom at the outbound content boundary only after there is a provider adapter, exact/qualified accounting and fidelity tests. Preserve instructions, originals, recovery and cache economics.
6. Test the composition with ablations: core only, each addition separately, selected combination. Remove components that increase total cost or regress outcomes.

## Lean technology recommendation

Python + SQLite is a proposed low-complexity first research implementation because native watchers, official MCP tooling and ML/evaluation integrations are accessible in one runtime. This is a builder recommendation, not an owner-mandated language. A Rust/Go service could later be justified by measured startup, RAM, throughput, packaging or isolation requirements. Do not build a multilingual microservice architecture for a single-user prototype.

Keep model, memory, queue, evaluator, sandbox and host interfaces replaceable. This does not require a generic plugin framework before the first three pilots. Use explicit small interfaces and typed evidence; generalize only where multiple real domains exercise the same behavior.

## End-to-end analysis the product must perform

DIRECTOR should maintain one living assessment with:

- Intended outcome and user's constraints, with original source and current revision.
- Existing artifacts, architecture/workflow, dependencies and environments.
- Requirements coverage mapped to current evidence and missing checks.
- Highest-impact risks and the cheapest checks that resolve uncertainty.
- Domain-specific quality criteria, including UX/accessibility or ML/data/research validity where relevant.
- Resource model: latency, tokens, API cost, local compute, storage and owner time.
- Proposed changes, expected benefit, side effects, reversibility and stopping rule.
- Final artifacts and reproducible acceptance evidence; unresolved issues and next action.

This assessment must be incremental. It should update affected relationships after a change, not regenerate a massive report after every edit.

## Failure reasons and cheapest tests

| Ranked risk | Why it can kill the product | Cheapest test and proposed decision rule |
|---|---|---|
| 1. Extra supervisor costs more than it saves | Duplicate reasoning, context and review can overwhelm small projects | Paired held-out tasks using the same builder/resources; continue only if accepted outcomes improve without unacceptable total cost/time |
| 2. Generic/false findings | Users stop trusting interruptions and evidence claims | Blind precision/actionability review on seeded defects plus clean decoys; keep low-confidence hypotheses in digest, not interrupts |
| 3. Domain-general scope becomes vague promises | Many skills do not equal end-to-end competence | Three distinct vertical pilots sharing the core; only claim the combinations with real evaluators and results |
| 4. Integration/state bugs undermine safety | Duplicated hooks, stale evidence and repeated effects can corrupt projects or spend money | Fault injection, scope/secret fixtures, malformed I/O and interrupted external effects before autonomy |
| 5. Massive memory gives irrelevant or stale context | More storage can lower decision quality | Retrieval/update/contradiction/abstention tasks at increasing scales, fixed packet budget and explicit miss analysis |

## Seven-day cheapest research validation, before broad implementation

1. Interview five people who already use agents; ask for their last concrete failed/unfinished task and time spent correcting it. Avoid hypothetical feature voting.
2. Collect ten consented, scrubbed examples across websites, small ML experiments and research/documents; define acceptance before viewing agent results.
3. Run the existing builder baseline and record actual corrections, tool/model usage and elapsed time.
4. Manually simulate DIRECTOR with a compact contract, focused context and independent checks; do not build a daemon to test whether guidance helps.
5. Blind-score outcomes and findings; identify which intervention produced value.
6. Compare total cost/time, interruption burden and acceptance rate; interview users about whether they'd keep the added layer.
7. Freeze the smallest justified MVP and its evaluation set. If value is weak, narrow the domain or intervention rather than adding more agents.

These are proposed validation steps; no interviews, payment evidence or market-size estimates were fabricated. Pricing and monetization can be researched after a concrete usage/value pattern exists.
