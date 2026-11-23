# Superpowers: mechanisms and DIRECTOR adoption

Research date: **2026-11-23**. Source: **obra/superpowers**, inspected read-only source snapshot (temporary local clone removed after research), commit **22f0b463e7a5e579904dd6211a520321035526f7**, commit timestamp **2026-11-03T14:17:07-08:00**. Manifest version **7.0.2**. License **MIT**, copyright Jesse Vincent 2025; preserve the notice in copied/substantial adapted portions. [Manifest][manifest], [license][license].

**Recommendation:** use selected Superpowers workflows as DIRECTOR's coding procedures. Keep DIRECTOR core responsible for authorization, budgets, scheduler state, tool execution and durable evidence. Superpowers supplies detailed behavioral instructions and small helpers; it does not implement these platform guarantees. Prefer its native/inline execution lane for routine work and reserve SDD for changes whose independent task review is worth the extra contexts.

## Scope and evidence

All **15 tracked SKILL.md files** were enumerated using git and read in full. All are canonical `skills/<name>/SKILL.md`; there are **0 tracked example/mirror SKILL.md copies**. The corpus contains **3,358 lines, 22,199 whitespace-delimited words, 143,103 working-tree bytes**. References/templates/examples inside a skill directory are support files, not additional skills. [CSV](SUPERPOWERS_SKILLS.csv) and [JSON](SUPERPOWERS_SKILLS.json) give every skill's activation, flow, inputs, outputs, artifacts, approval, costs, failure modes, disposition, exact path, file hash, git blob and pinned source link. They enumerate all tracked support files for each skill.

This is **static source analysis**: no upstream script, hook, test, installer, server or plugin was executed, and no global agent configuration was modified. The snapshot was fetched with ordinary git; gh was unavailable. Package/hook behavior is code-inspected, not proven on a running DIRECTOR or every advertised harness. Current-revision evidence supersedes broad README summaries where they differ. Popularity, upstream anecdotes, numeric performance claims and internal eval descriptions are not independent proof of reliability or savings.

Disposition counts: **adopt 4; adapt 9; optional 1; reject wholesale 1**. “Adopt” means reuse the mechanism with normal integration, not silently install upstream or inherit its authority.

## 1. Activation is prompt routing, not a runtime policy gate

The general hook registers synchronous SessionStart for startup/clear/compact, launches a polyglot cmd/bash wrapper, reads using-superpowers, JSON-escapes it and emits platform-shaped additional context. Only that bootstrap is injected; subsequent full skills are loaded on demand. On Windows the wrapper searches known Git Bash locations and PATH; if no supported shell exists it exits silently, so startup may appear successful without injection. The hook intentionally avoids emitting duplicate context fields. [Hook registration][hookconfig], [injection][hook], [wrapper][wrapper].

The bootstrap instructs the model to load a relevant skill before even exploration/questions at a **1% applicability threshold**, prioritize process skills, create checklist todos, and defer to direct user/project instructions. It exempts assigned subagents. There is no classifier implementation or mandatory tool intercept making these instructions true: the model must comply. Its source is 492 words before wrapper/mapping context; selecting more skills adds their bodies/references. [Bootstrap, lines 6–65][bootstrap].

Harnesses differ. The pinned **Codex manifest has `hooks: {}`**, so the general Claude-style SessionStart path must not be assumed active for Codex. Codex exposes the skill directory/description through its host; DIRECTOR needs its own explicit adapter. OpenCode V1/V2 register native skills, cache the bootstrap, and inject into first-user context; V2 covers context/compaction/generate and skips child sessions using parent identity, but lookup failure treats a session as top-level and injects. Pi injects provider context with a dedup marker and caches the body; Hermes injects only the first non-subagent turn, without a post-compaction recovery path in this adapter. [Codex manifest][manifest], [OpenCode][opencode], [Pi][pi], [Hermes][hermes].

**DIRECTOR action:** one version-pinned skill registry and selector, with controller/worker roles defined structurally. Reject wholesale the “load anything possibly relevant before every action” bootstrap: it competes with the other layers and spends context on weak matches. Keep its useful descriptive metadata, explicit tool mapping and user-priority rule. The core should log the selected procedure/version/reason and recover that state after compaction.

## 2. The complete per-skill mechanics

### brainstorming — ADAPT

Input is the actual request plus existing source/spec/context and decisions. It first distinguishes fully specified trivial tasks from meaningful unknowns; trivial requests can execute directly. Otherwise it investigates before asking, asks only questions changing the result, compares approaches, and writes a short or full design with assumptions and builder choices. A project gets one fresh builder-check agent asking only consequential unanswered questions; small designs skip that agent. It commits the design under `docs/superpowers/specs/`, gets approval, then invokes writing-plans. A user opt-out ends this workflow; an agreed throwaway spike bypasses implementation planning/review until someone requests keeping it. [Skill, lines 17–108, 156–188, 209–283][brainstorm], [builder prompt][builder].

The optional visual companion requires an offer/acceptance. Bash starts a local Node HTTP/WebSocket server; HTML files become screens and choice events become JSON lines. The model reads those on the next chat turn; terminal/chat text remains primary feedback. It is a mockup transport, not an approval system. Project sessions persist screens, port and session key. The server uses a key/cookie, constant-time comparisons, WebSocket origin checks and file-boundary checks. Loopback is default; non-loopback binding is possible. Default branding makes a browser request to the vendor logo URL with version; opt-out flags remove it. Windows process lifetime requires foreground/host background management. [Guide, lines 27–125][visual], [launcher][visualstart], [server auth/branding][visualserver], [stop helper][visualstop].

Cost: human turns, full skill context, optional builder agent/server/browser. Failure: repetitive questions, duplicated approvals, unattended local server, treating clicks as authorization, sensitive mockup/key persistence. Adapt to existing authorization and real uncertainty; make companion optional and never infer consequential consent from browser events.

### writing-plans — ADOPT

Consumes an approved spec and real repository patterns. Maps files/responsibilities, then makes each task an independently testable deliverable deserving a review gate. Steps carry exact interfaces, test assertions and verification command/Expected output; implementation bodies appear only when signatures/tests do not determine the algorithm. The plan includes Spec, Global Constraints, Interfaces and Review Focus, then self-review for coverage/consistency/proportion. Output is `docs/superpowers/plans/YYYY-MM-DD-feature.md`. Planning self-review is inline, with **no mandatory plan-review subagent**. [Skill, lines 10–177][plans].

It links the plan for review and asks for **Subagent-driven or Native**, preserving a method already chosen. Native means executing-plans inside the current harness, not a separate engine. This is a real cost/control choice, not a cosmetic setting. Failure modes are vague steps, transcript-size plans, drifting signatures, redundant method questions. Adopt the structure; bind a plan revision to DIRECTOR task IDs rather than relying only on Markdown headings. [Handoff, lines 179–204][plans].

### executing-plans — ADAPT; recommended routine lane

The current session is the implementer. It creates/verifies isolation, opens the same plan-scoped workspace as SDD, reads ledger/plan/spec, loads TDD and scans shared interfaces. For each task, task-start returns a brief path and BASE; the executor reads the brief, performs RED/GREEN steps, compares every Expected output, commits, then task-done runs the task test command and records completion only on exit zero. There is **no implementer or reviewer subagent per task**. One fresh capable reviewer checks the full branch at the end; absent subagent tools it permits an explicitly disclosed weaker self-review. [Skill, lines 8–64, 108–260][inline].

Critical/Important final findings receive **one inline fix pass**, each with reproduction RED→GREEN plus green suite; no second reviewer is dispatched. Minors are deferred and all rulings must reach the owner. Continuous execution stops only for destructive/irreversible operations, security-sensitive action, consequential outside-worktree effects, or an unusably broken plan. This is a prose rule, not a grant to exceed DIRECTOR budgets. [Final handling, lines 262–306][inline].

Failure: compaction drift, false completion from inadequate commands, stale evidence, deletion of audit material, missing independent inspection of the final fix. Adapt by persisting receipts in core and selecting extra review only when the fix risk warrants it.

### subagent-driven-development — ADAPT; optional higher-assurance lane

Consumes plan/spec/global constraints and an isolated checkout. The controller runs preflight, writes task briefs, then dispatches **serial clean-context implementers**. It never runs multiple implementation agents simultaneously. Each writes a detailed report to file, returning a short status/commits/test summary. Worker statuses are DONE, DONE_WITH_CONCERNS, BLOCKED or NEEDS_CONTEXT; concerns/context gaps get handled explicitly. Workers and reviewers are told not to spawn further agents. [Skill, lines 101–138, 198–295][sdd], [implementer][implementer], [report routing][reports].

Current v7 uses **one combined task reviewer returning two verdicts: spec compliance and quality**. It is not two separate reviewer seats, despite historical/two-stage language elsewhere. Reviewer receives brief, report, exact global constraints and packaged BASE..HEAD diff, checks named risks without a repository crawl, and resolves “cannot verify from diff” through the controller. It normally reads existing test evidence instead of rerunning the suite, unless a concrete doubt warrants a focused test. This reduces duplicate tool work; it does not cryptographically validate the implementer's report. [Task reviewer][taskreview], [cannot-verify][cannotverify].

A failed task review allows at most **five fix rounds**, each implementer fix plus scoped re-review. Rounds 1–3 resume the original worker; rounds 4–5 use a fresh, higher-tier worker. At the cap the controller may park even real unresolved findings with explicit rulings and continue; load-bearing defects require a recorded corrective decision. “Task complete” can therefore mean reviewed clean **or findings parked**, which DIRECTOR must keep distinct. One broad final branch review follows all tasks, with one fix agent and one scoped re-review; residual findings surface through rulings. [Fix loop][fixloop], [final review][finalreview].

Cost baseline for N tasks: N implementer starts + N task reviewer starts + 1 final reviewer; fix rounds and final fix wave add work. Model tiers are advised explicitly, but claims that particular tiers/turn counts are cheapest remain unmeasured here. Native baseline adds only one final reviewer to the continuing executor. Do not present these structural counts as measured token savings.

### test-driven-development — ADAPT

Requires behavior test first, an observed intended failure, minimal implementation, passing relevant tests and the project suite, then refactor. Bug fixes get reproductions. The supporting test guide rejects mirror assertions, source-text greps and mocks as substitutes for real behavior; it says trivial code/human prose need no ritual tests. Those useful specifics qualify the main skill's broad “every new function” checklist. [Skill][tdd], [test quality][goodtests].

Inputs are a behavior/spec and real production boundary; outputs are tests, code and RED/GREEN evidence. It has no executable enforcement log. It asks permission for prototype/generated/config exceptions and tells the agent to delete code written before tests. Do **not** adopt blanket deletion/rewrite of valid user work. Require meaningful regressions and proportionate testing; preserve existing code, track evidence and avoid duplicate suite runs on identical state.

### systematic-debugging — ADOPT

Reproduce/read errors/check changes; gather boundary observations and trace bad values backward; compare working patterns; state one hypothesis; run the smallest experiment; write regression; fix the origin and verify. Three failed fixes trigger architectural reconsideration instead of endless patching. Output is an evidence-supported explanation plus a repair or explicit limitation. No mandatory subagent or file format. [Skill, lines 44–210][debug].

References cover backward tracing, defense-in-depth and condition-based waits. The supplied find-polluter.sh is described as bisection but actually runs matching npm test files **linearly**, suppresses their output and ignores command failures while checking pollution; adapt it to the project runner and reliable error handling, never trust its success string as a clean-suite verdict. Boundary instrumentation must redact secrets before logging. [Polluter helper, lines 21–71][polluter].

### verification-before-completion — ADOPT

Before a success claim, identify a command proving that exact claim, run fully, inspect output/exit and report supported status; requirements need a checklist, regression claims need RED/GREEN, and delegated success needs independent source/evidence inspection. Inputs are a claim, current state and suitable verifier; output is scoped status with evidence. [Skill, lines 14–48, 74–120][verify].

Its “this message” freshness rule can duplicate expensive unchanged-tree checks, and its full-output rule conflicts operationally with execution skills' tail-to-file advice. DIRECTOR receipts should bind command/arguments, environment, code hash, output artifact, exit and claim scope: bounded visible summaries plus inspectable full output. Freshness means relevant state has not changed, not a ritual rerun for each sentence.

### requesting-code-review — ADAPT

Dispatches a fresh read-only reviewer with requirements and BASE/HEAD. Reviewer checks alignment/quality/architecture/testing, provides file:line findings graded Critical/Important/Minor, and an explicit readiness verdict. The broader template judges plausible user failures even when the spec omitted them and lists what it declined to judge. Reviewers cannot recursively dispatch. [Skill][requestreview], [review template, lines 23–61, 95–151][broadreview].

The standalone example uses HEAD~1, which can omit earlier commits of a multi-commit task; execution workflows explicitly record BASE and package the whole range. Use that stronger path. One review owner/range prevents this skill, SDD and ECC from buying the same reviewer repeatedly. Read-only must be a tool permission, not only a prompt.

### receiving-code-review — ADOPT

Read/understand/verify/evaluate before implementation. Challenge technically wrong feedback, check actual use before adding “professional” features, and fix proven issues one at a time with tests. Conflicts with owner decisions are raised explicitly. It has no mandatory agents/artifacts. [Skill, lines 14–127][receivereview].

The rule to stop all work on any unclear item is too broad for independent findings; DIRECTOR should isolate dependencies and keep authorized clear work moving. Forge replies belong to their exact review thread, but a reference showing how to send them is not permission to communicate externally.

### dispatching-parallel-agents — ADAPT

For genuinely independent problem domains, construct self-contained prompts with scope/constraints/report contract, dispatch concurrently, inspect all reports and conflicts, then test integration. It has no durable scheduler, DAG, lock service or process budget. [Skill, lines 8–85, 129–167][parallel].

False independence is the main failure: nonoverlapping files may still share schema, tests, port, database or checkout state. Core must own dependency/ownership locks and concurrency caps. This workflow is distinct from SDD's deliberately serial implementers.

### using-git-worktrees — ADAPT

Checks git-dir/common-dir/branch plus a submodule guard before creating anything; respects existing preference or asks consent; prefers native host worktree tools; otherwise uses ignored .worktrees/worktrees paths. It then installs/builds detected dependencies and runs a baseline suite, asking about failures. Declined consent or permission failures permit explicit in-place work. [Skill, lines 16–132][worktrees].

Default setup may execute npm/pip/Poetry/build scripts and downloads. Treat setup as policy-controlled execution, not harmless isolation bookkeeping. DIRECTORY naming is not provenance. Core should record actual creator/base/allowed roots and cached setup recipe, including degraded in-place isolation.

### finishing-a-development-branch — ADAPT

Fresh suite → detect normal/named/detached workspace → resolve real base → owner chooses merge, PR or keep. Re-test merged result, preserve PR worktrees, and remove only owned workspace after authorized merge. Destruction is only an explicit user request with exact discard confirmation; never force-remove unique files automatically. [Skill, lines 14–201][finish].

Reuse already granted integration authorization and respect host semantics. Upstream cleanup infers ownership from .worktrees/worktrees path and runs git pull before merging; neither replaces core provenance or a known base revision. Keep evidence until audit retention policy allows removal.

### diagnosing-superpowers — ADAPT

Consumes a scoped complaint and verified transcripts. Records source/field provenance, then always fans out **seven** analysts: skill timeline, plan adherence, repeated work, stumbles, quality evidence, request conflicts, cost/time. Every finding needs path:line. It reports involvement but explicitly bars proposing a Superpowers fix. Optional issue search/export/similar-session scan are separate paths; export runs scrubber then independent scrub-audit until CLEAN. Exact issue/comment text and archive require approval. [Skill, lines 19–109][diagnose], [analyst contract][analyst], [redaction][redaction].

The strongest reusable mechanism is measure-first, field-level transcript extraction: one record can be huge, so never dump raw histories. Counter meanings must be established before adding usage. Seven mandatory agents and an uncapped scrub repeat are disproportionate for a tiny issue; select relevant dimensions/cap work. An LLM CLEAN verdict is not exhaustive privacy certification; preserve evidence and add deterministic scanning before approved exports.

### writing-skills — OPTIONAL

Treat skill writing as behavioral TDD: observe baseline failure without guidance, author minimal guidance, rerun scenarios, refactor. Shape instructions according to failure type; wording micro-tests use a no-guidance control and 5+ fresh samples per variant before full pressure scenarios. Metadata describes triggers rather than summarizing workflows; heavy references load separately. Each skill gets its own deployment checklist. [Skill, lines 8–59, 248–305, 347–399][writeskills].

Inputs are reusable observed failures and realistic test contexts; outputs are versioned guides/eval evidence. This can be expensive and prompt/model-specific; five samples are not robust proof. Optional render-graphs.js invokes installed Graphviz through Node and writes diagrams in the skill tree. Keep authoring/evaluation separate from runtime skill selection and installation; no self-push/self-promotion based only on model compliance.

### using-superpowers — REJECT wholesale

Mechanics and rationale are in section 1. Its global imperative competes with DIRECTOR's single procedure selector. Reuse descriptions/cross-references, not a second controlling policy.

## 3. Helpers, native ledger and recovery: useful but incomplete

The six plan helpers form a concrete file protocol:

| Helper | Input → actual operation/output |
|---|---|
| sdd-repo | Current directory (or caller's -C) → actual git root; optional committed-HEAD requirement. Plan location never selects the repository. |
| sdd-workspace | Plan path → .superpowers/sdd/<basename>/; plan-path marker resolves basename collisions; self-ignoring base .gitignore; returns host-readable absolute path. |
| task-brief | Plan and task ID → full task body file; parses literal English Task headings, skips fences, supports dotted/alphanumeric IDs, warns/errors on malformed hidden headings. |
| review-package | Plan, BASE, HEAD → commit list/stat/full -U10 diff file; requires valid commits, ancestry and nonempty range. |
| task-start | Plan/task → brief extraction plus current HEAD BASE. |
| task-done | Plan/task/BASE and test argv → execute command, save full log, print five-line tail; exit zero appends completion with BASE..HEAD/command/last line. |

[Repository resolver][sddrepo], [workspace][workspace], [brief parser][brief], [review package][package], [task-start][start], [task-done][done].

This ledger survives model compaction and supports switching inline↔SDD. It does **not** equal DIRECTOR's billion-token external memory. It is git-ignored scratch; upstream instructions later delete it, and git clean -fdx destroys it. Git commits cannot recreate all rejected findings, reports, transient logs and owner rulings.

Important static boundaries, **not runtime-verified defects**:

- A plan-path marker identifies a path, not a content hash. Editing a plan in place can leave old Task N complete records semantically stale.
- task-done checks command exit status and BASE existence, not RED evidence, requirement coverage, ledger identity, commit ancestry, clean working tree or meaningful tests. The surrounding skill asks the model to supply those guarantees.
- Same-plan/same-worktree concurrent runs share filenames; there is no locking/transactional append protocol. DIRECTOR must prevent them or add task/run IDs.
- Some cross-helper calls execute bare script paths despite documentation advising interpreter invocation for packages stripping executable bits. Installed-archive compatibility is unverified.
- Cap/ruling logic can label a task complete with serious parked findings. A platform must separate implemented, tested, reviewed, deferred and accepted-risk states.

DIRECTOR should ingest append-only typed events and content-addressed artifacts before scratch cleanup: plan/spec hash, task/run IDs, source revision, scoped authorization, assigned role, commands/exits/output hashes, findings/verdicts, fix attempts, rulings, acceptance and retrieval lineage. Retrieve the small relevant slices into working context. Retrieved history is evidence/data; it cannot silently alter authorization or override newer source.

## 4. Composition with Headroom, Ponytail and ECC

The following are design recommendations, not claims that an integrated stack was executed.

| Overlap | Source-grounded mechanism | DIRECTOR resolution |
|---|---|---|
| Multiple startup instructions | Superpowers bootstrap; Ponytail session/user/subagent injection; ECC session/observation hooks | One core-owned event order and composition manifest; inject one controller workflow and bounded role rubrics. No recursive independent process selection. |
| Competing plans/gates | Superpowers design→plan→native/SDD; ECC orch-pipeline size→plan→implement→test→review→commit with plan/precommit gates | Select one workflow owner per task. Map ECC specialist checks into Superpowers stages; do not rerun two planners or ask twice for the same approval. |
| Test/style loop collisions | Superpowers RED/GREEN commits; ECC PostToolUse/Stop quality actions and formatting/typecheck; Ponytail nontrivial self-check | Check mutation order and owner. No unexpected formatter mutation after evidence was recorded; invalidate evidence when content changes. |
| Review duplication | SDD task+final seats; ECC review pipeline; Ponytail review/audit are report-only | Single review seat per declared purpose/range; Ponytail simplifies the rubric, ECC supplies specialized checks, core schedules and caps them. |
| Memory/rule authority | Ignored Superpowers ledger; ECC instincts auto-injected by confidence; external memory retrieval; Headroom transforms tool payloads | One versioned provenance/promotion authority. Evidence is retained separately from compressed prompt views; observations never become permissions. |
| Budget/context | SDD workers/reviewers; seven-agent diagnosis; Headroom proxy transformations | Enforce budgets before dispatch and report measured usage. Compression may add retrieval latency/cache effects; do not multiply upstream savings claims. |

Peer research source pins: Ponytail **ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10**, [hook registrations][ponyh], [activation][ponya], [subagent injection][ponys], [core rubric][ponyc]. ECC **4adeee6732a12d1540f49a4d50a38ce8c97f9a53**, [orchestration][ecco], [verification workflow][eccv], [dispatcher][eccd], [Stop formatter][eccf], [warning-only quality gate][eccq], [instinct injection][ecci]. Headroom **ce0460cfa8598dc939243dbc7aec4b2d35f4e44a**, [retrieval exclusions/cache transforms][headroom]. These integration facts were supplied by the sibling source audits; this report's direct full-skill reading covers Superpowers only.

## 5. Cheapest validation before adoption

1. Run no-op/simple-change/bug/design scenarios through a disposable DIRECTOR adapter; verify correct selector, preserved prior authorization and no unexpected question/install/spawn.
2. Execute the same short plan through inline and SDD with recorded model/tool usage. Compare accepted behavior, total cost, elapsed time and review coverage; include one multi-commit task and injected false-positive finding.
3. Interrupt after a committed task, compact/resume, and modify the plan at the same path. Verify no repeat/skip, stale plan rejection, surviving evidence and bounded retries.
4. Inject exit-zero/no-op tests, failed suite, unauthorized push, concurrent same-plan run and malicious retrieved instructions. Core should reject invalid transitions regardless of prose.
5. Only then enable optional companion/evaluation authoring paths in isolation. Validate key retention, network policy and process cleanup separately.

Until these pass, confidence is **high in the described static mechanisms**, **medium in the proposed adaptation**, and **unverified for integrated runtime quality, autonomy or savings**.

[manifest]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.codex-plugin/plugin.json#L1-L25
[license]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/LICENSE#L1-L21
[hookconfig]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/hooks/hooks.json#L1-L18
[hook]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/hooks/session-start#L22-L88
[wrapper]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/hooks/run-hook.cmd#L13-L79
[bootstrap]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/using-superpowers/SKILL.md#L6-L65
[opencode]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.opencode/plugins/superpowers.js#L110-L214
[pi]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.pi/extensions/superpowers.ts#L16-L92
[hermes]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.hermes-plugin/__init__.py#L93-L127
[brainstorm]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/SKILL.md#L17-L283
[builder]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/builder-check-prompt.md#L1-L23
[visual]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/visual-companion.md#L27-L125
[visualstart]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/scripts/start-server.sh#L97-L187
[visualserver]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/scripts/server.cjs#L100-L151
[visualstop]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/scripts/stop-server.sh#L63-L120
[plans]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-plans/SKILL.md#L10-L204
[inline]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans/SKILL.md#L8-L306
[sdd]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/SKILL.md#L101-L339
[implementer]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/implementer-prompt.md#L32-L153
[reports]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/handling-reports.md#L1-L15
[taskreview]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/task-reviewer-prompt.md#L15-L187
[cannotverify]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/cannot-verify.md#L1-L10
[fixloop]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/fix-loop.md#L7-L77
[finalreview]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/final-review.md#L6-L49
[tdd]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development/SKILL.md#L16-L216
[goodtests]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development/writing-good-tests.md#L20-L184
[debug]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/SKILL.md#L44-L210
[polluter]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/find-polluter.sh#L21-L71
[verify]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion/SKILL.md#L14-L120
[requestreview]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/requesting-code-review/SKILL.md#L8-L95
[broadreview]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/requesting-code-review/code-reviewer.md#L23-L151
[receivereview]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/receiving-code-review/SKILL.md#L14-L127
[parallel]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/dispatching-parallel-agents/SKILL.md#L8-L167
[worktrees]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/using-git-worktrees/SKILL.md#L16-L132
[finish]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/finishing-a-development-branch/SKILL.md#L14-L201
[diagnose]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/diagnosing-superpowers/SKILL.md#L19-L109
[analyst]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/diagnosing-superpowers/prompts/analyst-common.md#L1-L38
[redaction]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/diagnosing-superpowers/references/redaction-policy.md#L6-L34
[writeskills]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-skills/SKILL.md#L8-L399
[sddrepo]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/scripts/sdd-repo#L1-L54
[workspace]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/scripts/sdd-workspace#L50-L110
[brief]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/scripts/task-brief#L37-L108
[package]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/scripts/review-package#L26-L64
[start]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans/scripts/task-start#L19-L32
[done]: https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans/scripts/task-done#L17-L55
[ponyh]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/claude-codex-hooks.json#L3-L39
[ponya]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-activate.js#L60-L71
[ponys]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-subagent.js#L17-L53
[ponyc]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail/SKILL.md#L21-L50
[ecco]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/orch-pipeline/SKILL.md#L24-L95
[eccv]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/verification-loop/SKILL.md#L21-L105
[eccd]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/scripts/hooks/posttooluse-dispatcher.js#L35-L69
[eccf]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/scripts/hooks/stop-format-typecheck.js#L228-L251
[eccq]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/scripts/hooks/quality-gate.js#L88-L153
[ecci]: https://github.com/affaan-m/ECC/blob/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/scripts/hooks/session-start.js#L492-L532
[headroom]: https://github.com/headroomlabs-ai/headroom/blob/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/headroom/config.py#L239-L312
