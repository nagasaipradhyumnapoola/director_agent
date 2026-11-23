# Ponytail: every skill, adapter flow and adoption decision

Analysis date: **2026-11-23**. Confidence is high for the source descriptions below; effectiveness and native-host compatibility were not independently tested.

## Snapshot and method

Repository: `DietrichGebert/ponytail`, inspected in a shallow read-only source snapshot; the temporary local clone was removed after research. Exact commit: **`ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10`**, committed **2026-11-22T03:31:58+01:00**, subject “fix(hooks): decode stdin across UTF-8 chunk boundaries (#1495)”. Package version **5.3.3**. The repository is **MIT**, copyright 2026 DietrichGebert; substantial copied material requires preservation of its copyright and permission notice. [Package][package], [license][license].

This is static source research. Git retrieved the snapshot; our own inspection code read tracked files and compared copies. **No upstream script, installer, hook, test, benchmark, or generated code was executed. No upstream plugin was installed.** A browser fetch of the pinned GitHub tree failed; evidence comes from the successfully cloned Git objects, linked below at the exact SHA. No provider/pricing/host-version claim is independently verified by this report.

Inventory: **12 tracked files named `SKILL.md`: six canonical skills and six generated OpenClaw variants, representing six distinct behaviors.** Every canonical skill was read completely. Each generated body was compared with its canonical body and all six match exactly after newline normalization; only frontmatter differs. `benchmarks/arms/caveman-SKILL.md` is an additional vendored comparison prompt, not a seventh Ponytail runtime skill. The companion JSON/CSV inventory contains every tracked `SKILL.md`, byte/word/line counts, content hashes, source links, activation, mechanics, outputs, state/approval implications, tests, failure modes and DIRECTOR decisions.

DIRECTOR remains original code. **Adopt** means use a principle, **adapt** means implement a narrower original version, **optional** means expose only on demand, and **reject** means do not import that behavior into DIRECTOR by default. None means integration is already implemented.

## How every canonical skill works

| Skill | Actual mechanism and artifact flow | DIRECTOR decision |
|---|---|---|
| `ponytail` | A persistent instruction prompt, not a simplifier algorithm. Read the task and affected code; enumerate callers, tests, fixtures, config and exports before selecting the first sufficient solution: omit unrequested work → reuse house code → stdlib/platform → installed dependency → readable one line → minimum implementation. Finish all required callers/tests/fixtures. Preserve trust-boundary validation, data-loss handling, security, accessibility, hardware calibration and everything requested. Nontrivial logic leaves a small test or self-check; known shortcuts get a limit and upgrade trigger. End with unchecked work and material risk. `lite` offers a smaller option, `full` applies the rubric, `ultra` challenges unjustified scope. It does **not** require test-first or enforce compliance. [Core, L15–52][core] | **Adapt** as a bounded pre-decomposition rubric. Acceptance criteria and risk determine completeness; minimum line count is not the objective. Superpowers owns the TDD sequence. |
| `ponytail-review` | Resolve the target: explicit files/PR/branch/staged scope, otherwise uncommitted diff or last commit. Read connected callers/callees and tests; trace inputs, storage and outputs; infer expected load. Check correctness, safety/data loss, concurrency/scale, missing meaningful tests, speed, then unnecessary structure. Re-read suspected defects and require concrete cases. Produce numbered severity groups and four-part findings: what it is, problem, smallest fix, consequence. It is report-only and changes no code. Its `Ship` verdict is advice, not verified execution. [Review, L16–101][review] | **Adapt** its connected-code coverage and explanation format into DIRECTOR's existing review job, with source hashes and reproducible evidence. Do not launch a second review ceremony. |
| `ponytail-audit` | Map README/build/deploy/dependencies/entry points/tests and high-consequence flows before judging. In a large repo, prioritize consequential paths and disclose unread areas. Apply the same quality order as review, including string/dynamic references before dead-code claims. Report at most 20 findings, most important first, plus load assumptions, verdict, potential removals and unchecked scope. It is a one-shot report, not an automatic repairer. [Audit, L16–103][audit] | **Adapt** the risk-based map and ranked backlog. The 20-item cap may limit presentation; it must not discard persistent findings. “Healthy” must never imply tests passed. |
| `ponytail-debt` | Search nonignored files for `shortcut:` and legacy `ponytail:` comment markers; optionally use a custom marker and blame for ownership. Remove prose/nondeferral hits. Produce file/line, simplification, stated ceiling and revisit trigger; tag missing triggers `no-trigger`; summarize counts. No matches means no matching marked debt. The canonical skill asks before writing a persistent ledger. [Debt, L9–44][debt] | **Adapt** into typed deferral records tied to source hash and owner-confirmed decisions. Respect already-authorized file output; do not ask again. Escape custom marker inputs and apply DIRECTOR privacy policy in addition to ignore rules. |
| `ponytail-gain` | Display hardcoded author benchmark figures as bars. It does not measure the current repository or compute savings. Its valuable boundary forbids inventing per-repo counterfactual savings and points to counted debt instead. It changes neither state nor mode. [Gain, L11–52][gain] | **Reject** the imported scoreboard as DIRECTOR telemetry; **adopt** its honesty rule. Historical figures can appear only as attributed research with model, version, date and limits. |
| `ponytail-help` | Display static mode/command/configuration/host/update instructions. It includes band toggles and historical-session import. It is one-shot, with no flag/config/mode writes of its own. Following its installation instructions would have separate effects. [Help, L10–76][help] | **Optional** reference generated from DIRECTOR's installed capability registry. A help request does not authorize updates, global settings changes, or transcript import. |

These skills contain natural-language instructions executed by a host agent using that host's tools. None grants permissions, creates an isolation boundary, schedules an autonomous worker pool, validates a source-state receipt, or proves correctness. Review/audit/debt are read-only by instruction; the host's actual tool boundary remains necessary.

## Canonical, generated and mirrored forms

OpenClaw copies are generated by `scripts/build-openclaw-skills.js`: a short single-line description, homepage and MIT field replace frontmatter; the body is copied verbatim. Source tests explicitly compare generated bodies with canonical content. This is six distributions of the same behavior, not six additional skills. [Generator, L19–58][generator], [copy tests, L10–25][copies].

There are also **six TOML commands** under `commands/` and **six compressed OpenCode command mirrors** under `.opencode/command/`. These are summaries, not byte-identical canonical skills. OpenCode audit/gain/help/review bodies match their TOML prompt strings; debt differs in punctuation, and the base command uses `$ARGUMENTS` instead of `{{args}}`. Seven compact host rules copy the `AGENTS.md` body; `check-rule-copies.js` compares those bodies but only uses phrase canaries between `AGENTS.md` and the longer skill. [Rule checker, L15–65][rulecheck].

**Observed drift matters:** the canonical review/audit exemption for a documented shortcut ends when expected load crosses its limit; compressed review/audit commands omit that exception. Compressed help still describes an older ladder that omits house-code reuse and calls review/audit chiefly over-engineering checks. The base command also omits the newer explicit change-scope and test rules; some hosts obtain them separately from always-on context. Therefore host behavior cannot be inferred from `SKILL.md` alone. DIRECTOR should generate adapters from one structured contract and test semantic invariants, not maintain hand-compressed parallel rulebooks. [Review L63–64][review], [audit L63–64][audit], [command review][cmdreview], [command audit][cmdaudit], [command help][cmdhelp], [base command][cmdbase].

## Activation, state, hooks and artifacts

**Claude/Codex lifecycle.** The shared configuration registers SessionStart (`startup|resume|clear|compact`), SubagentStart and UserPromptSubmit. Default resolution is environment override → config → `full`. Activation writes mode flags, strips frontmatter, filters the levels table, injects the core body and optionally a source-symbol map. Compaction preserves the live mode; other starts resolve the default. Ordinary prompt submissions are normally silent, while recognized commands update mode or configuration. Reads of split UTF-8 input use Node's streaming decoder; fallback timers prevent waiting indefinitely for stdin. These are best-effort adapters: broad catches usually continue silently. [Hook config][hookconfig], [config L80–104][config], [activation L31–71, L176–202][activate], [instruction builder][instructions], [tracker L47–76, L105–217][tracker].

**State scope and off semantics.** Claude project mode files use a hash of the project directory; the shared compatibility/statusline flag is also written. Sessions in the same repo still share the mode, and hosts without the project variable use shared state. Turning off sends a mode notice; it does not erase earlier conversation instructions. The Cursor rule fallback cannot be turned off by a hook: detection suppresses duplicate injection and explains removal of the always-on rule. Multi-root Cursor detection covers only the first root. This is a useful deduplication pattern, not a permissions system. [Runtime L44–101][runtime].

**Subagents.** Active mode normally injects the core rules into every subagent. An optional type matcher limits it; invalid/missing matcher/input and matcher timeouts fall back to injection. Regex evaluation uses a 100 ms VM timeout and stdin has a 1 s fallback. That protects responsiveness but means uncertain scoping broadens injection. DIRECTOR should instead select explicit role profiles and count their context overhead; a review agent need not inherit the builder's brevity bias. [Subagent L17–95][subagent].

**Source map.** Startup runs a shipped Node mapper, with a 3 s parent timeout and 64 KiB output buffer. It obtains tracked paths with `git ls-files` or a bounded-depth fallback walk, selects at most 4,000 source files, skips tests/generated/vendor patterns, regex-extracts top-level symbols and prioritizes shared folders. The default data budget is 2,000 characters, plus headings/omission text. It is not an AST, dependency graph, source-versioned index or token budget. `readFileSync(...).slice(0,65536)` reads a whole file before truncation. The fallback walk does not implement full gitignore semantics, and the mapper has no DIRECTOR secret/scope policy. **Adapt** the reuse-discovery idea onto DIRECTOR's bounded, policy-filtered source index; do not install a second scanner. [Mapper L16–106][map].

**Other hosts.** OpenCode V1/V2 registers six commands and six skills, injects core rules each request/compaction, and uses a shared persisted mode file. Pi writes mode entries into host session history, restores branch/session modes, and uses a structured prompt section where supported. Hermes registers skills/commands, injects context only when the recorded mode changes or compaction removed it, and checks gateway slash-command access before rewriting commands. Qoder reinjects rules per prompt because it lacks the same SessionStart lifecycle. These are inspected implementations; upstream portability tables' native-client verification claims were not independently repeated. [OpenCode][opencode], [Pi][pi], [Hermes][hermes], [Qoder tracker L168–190][tracker], [portability][portability].

**Band and board are separate from the six skills.** Claude's band reads session usage, observes Edit/Write/Bash events, regex-counts reuse/new symbols, marks a recorded test result stale after observed code edits, writes project CSV ledgers and rebuilds a local HTML board. It derives task names from sidebar titles or the first prompt. An optional webhook sends snapshot JSON after turns; HTTPS is required except loopback HTTP, and names are sent by default unless disabled. The manifest labels the token sensitive and describes host-keychain handling; that host guarantee is not proven by this code inspection. [Manifest][claudemanifest], [band L154–214, L244–349][band], [metrics L63–99, L292–310][metrics].

`/ponytail band import` spawns a detached shipped script which reads historical Claude transcripts and subagent records, derives name/model/tokens/time, estimates some costs from a hardcoded price table, and writes CSV rows. It reads historical conversation data even though it does not retain whole transcripts. The code admits estimates can miss side calls and excludes long within-turn pauses. **Observed presentation conflict:** the board footer says nothing is estimated while the importer can populate estimated costs. Keep measured and estimated values separate. [Tracker L81–88][tracker], [import L16–55, L103–175, L216–270][import], [board L555][board].

For DIRECTOR, the band/board is **optional future telemetry**, and historical import plus webhooks are **disabled/rejected in MVP**: they exceed project-bound source supervision and its no-network/no-transcript-ingestion boundary. Reuse percentage is a name-matching heuristic, not semantic reuse or saved engineering cost. Test badges observe recognized commands and selected edit tools, not all changes or a source-hash-bound successful suite. CSV read/modify/write is not DIRECTOR's transactional evidence store. Installation helpers and cleanup also touch global host settings/state; do not execute them as part of an ideas-only composition.

## Context overhead and evidence quality

Exact tracked UTF-8 blob sizes, including frontmatter, are:

| Canonical skill | Bytes | Whitespace words |
|---|---:|---:|
| ponytail | 3,496 | 592 |
| ponytail-review | 5,143 | 860 |
| ponytail-audit | 5,417 | 900 |
| ponytail-debt | 1,769 | 269 |
| ponytail-gain | 2,164 | 286 |
| ponytail-help | 3,188 | 460 |
| All six | 21,177 | 3,367 |

These are file measurements, **not provider token counts**. Runtime stripping/filtering reduces the core body; maps, mode headers, setup nudges, activated command bodies and host wrappers add context. SessionStart/subagent injection multiplies with sessions, compactions and agents. OpenCode/Pi reconstruct an active prefix each turn, which may benefit from provider caching but still occupies attention. Qoder explicitly sends the body each prompt. Load only the core invariant summary by default; fetch review/audit/debt profiles on demand; account final serialized text and each worker separately. Do not install both compact rules and lifecycle injection indiscriminately.

## Benchmarks: what was measured and what remains unverified

The **author's 2026-10-07 report**, not this audit, reports Claude Code 2.1.288 / Opus 5.5 default effort, 39 tasks × 5 runs × 3 arms = 585 sessions. It compares no-skill, v4.13 and Ponytail 5, reporting geometric means of per-task median ratios: 53% less source LOC, 45% fewer **output** tokens, 26% lower list-price cost and 41% less time. Only 18 tasks have hidden executed correctness/safety checks: 87/90 Ponytail 5 versus 86/90 baseline. All arms pass the six selected security tasks; the privacy task passes only 2/5 in every arm. This supports investigating smaller implementations, not security superiority. [Report L10–76][results].

The harness makes a fairer baseline than a bare one-shot model: fresh workspaces, global plugin/memory exclusion, one selected plugin, same task, source/diff counting with tests separate, retained per-cell workspaces and instrument self-tests. It uses a 300 s cell timeout, process-tree termination, a warm-up call and parallel cells. **Bash and MCP execution are disabled; agents write code/tests but cannot run/debug them.** Scoring later executes generated functions outside an OS sandbox. Temporary directories and `bypassPermissions` are not isolation boundaries suitable for DIRECTOR. [Harness L50–77, L319–392, L492–519][run].

Limitations and source mismatches:

1. This is author-run, task-specific historical evidence. It is not an independent DIRECTOR trial, a current 5.3.3 rerun, native-host coverage, production correctness or long-session performance. Twenty-one tasks primarily measure size and receive LLM completeness judgments rather than hidden executable acceptance checks.
2. Completeness judging uses a 0–3 rubric, only two simple complete/stub reference pairs, and fixture diffs rather than whole repos. Timeout cells are excluded from judging and counted separately. The report manually corrects one judge error about an import outside the diff. A ceiling score therefore cannot establish functional completeness. [Complete L40–91, L108–143][complete], [report L78–88][results].
3. The report claims 98% test presence and 66% injected-bug capture, and says mutation tools ship. **No mutation runner was located in the tracked benchmark files**; text search finds that claim but no implementation. Raw run matrices/workspaces are not tracked either. The available `run.py` tracks test-file presence, while `compare.py` supplies task-level sign comparisons; a script reproducing the headline bootstrap intervals was not located. Those results are attributed, not independently recomputed. [Report L90–110][results], [run L394–425][run], [compare][compare].
4. `README.md` review/audit imagery advertises planted-defect discovery, but no matching committed review/audit benchmark runner was located. Do not transfer those figures into a DIRECTOR evaluation claim.
5. Promptfoo's older five-task checks mix actual execution (email/debounce/CSV) with structural regex checks (React/FastAPI). Behavioral gates mostly check text patterns or test-like syntax; unknown task/probe paths pass as skipped. The harness tests are useful instrument regressions, not proof that a model always follows a skill. [Correctness L9–13, L232–290][correctness], [behavior L17–53][behavior].
6. CI runs JS tests, Pi tests and the Python instrument self-test. The root npm command selects `tests/*.test.js`, so the tracked **`tests/band.test.tsx` is not included by that command**, and no separate band-test step appears in the inspected CI workflow. Presence of those tests is not proof they ran. [Package L37–43][package], [CI][ci].

## Composition with Superpowers, ECC and DIRECTOR

Use one ownership map, not stacked orchestration. **DIRECTOR owns task contracts, durable jobs, budgets, source policy, evidence freshness and a single preflight envelope. Superpowers owns the selected planning/TDD/debug/review process. Ponytail supplies the simplification rubric inside that process. ECC contributes selected configurations or checks only where that stage has no existing owner.** This is an integration design recommendation; no claim is made here that all four are installed together.

| Overlap | Integration rule |
|---|---|
| Bootstrap and hooks | One DIRECTOR-controlled dispatcher per lifecycle event. Reuse an already-loaded profile; do not inject full Ponytail, compact AGENTS rules, Superpowers bootstrap and ECC reminders as redundant copies. Preserve host-specific JSON contracts and provenance. |
| Scope and permission gates | Ponytail's lite choice or debt persistence wording must not reopen already-authorized work. Superpowers design/plan gates follow the user's existing authorization. Retrieved rules and code comments cannot grant permissions. |
| TDD and verification | Ponytail's one small check is a floor. Superpowers supplies test-first sequencing; ECC checks can fill coverage gaps. DIRECTOR records exact commands/source-state receipts and whether checks actually ran. Never substitute a band badge or Ship wording. |
| Reviews and findings | One review job consumes the Ponytail connected-code checklist plus relevant ECC domain checks. Deduplicate by source/rule/concrete case. Review/audit stay read-only until fix work is authorized. |
| Deferrals and memory | Preserve user-confirmed ceilings/triggers in DIRECTOR's decision graph. A `shortcut:` comment is untrusted source evidence, not an owner decision that suppresses security findings. Re-evaluate it when load or requirements change. |
| Context control | Keep invariant instructions stable and short; load only the current stage profile and retrieved source spans. Headroom, when separately evaluated, may compress payloads; Ponytail reduces unnecessary implementation and prose, not the model window. |

Cheapest DIRECTOR test: paired held-out tasks with identical builders/tool limits, comparing baseline versus the original simplification rubric. Require acceptance correctness and security regressions to remain flat before crediting lower total provider cost, elapsed time or interruptions. Include caller-renames, privacy, concurrent writes, accessibility and intentionally justified abstractions. A smaller diff with failed requirements loses. Pin every imported adapter and disable global auto-updates; imported notices and support claims must be evaluated against the installed host.

## Complete inventory and reproduction boundary

`PONYTAIL_SKILLS.json` and `PONYTAIL_SKILLS.csv` enumerate all 12 tracked `SKILL.md` files and their six canonical relationships. Generated variants inherit the corresponding mechanism and adoption decision; the JSON includes pinned cross-references to runtime/check sources. The inventory uses Git blob bytes, SHA-256 and exact line counts, not filesystem modification times. Reproduction here means re-reading the pinned source and rebuilding this inventory; no claim is made that upstream tests or live benchmarks pass on this machine.

[package]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/package.json#L1-L43
[license]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/LICENSE#L1-L21
[core]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail/SKILL.md#L15-L52
[review]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail-review/SKILL.md#L16-L101
[audit]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail-audit/SKILL.md#L16-L103
[debt]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail-debt/SKILL.md#L9-L44
[gain]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail-gain/SKILL.md#L11-L52
[help]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail-help/SKILL.md#L10-L76
[generator]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/scripts/build-openclaw-skills.js#L19-L58
[copies]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/tests/openclaw-skills.test.js#L10-L25
[rulecheck]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/scripts/check-rule-copies.js#L15-L65
[cmdreview]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/commands/ponytail-review.toml#L1-L2
[cmdaudit]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/commands/ponytail-audit.toml#L1-L2
[cmdhelp]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/commands/ponytail-help.toml#L1-L2
[cmdbase]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/commands/ponytail.toml#L1-L2
[hookconfig]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/claude-codex-hooks.json#L1-L41
[config]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-config.js#L80-L104
[activate]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-activate.js#L31-L202
[instructions]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-instructions.js#L11-L90
[tracker]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-mode-tracker.js#L47-L217
[runtime]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-runtime.js#L44-L101
[subagent]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-subagent.js#L17-L95
[map]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-map.js#L16-L106
[opencode]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/.opencode/plugins/ponytail.mjs#L29-L206
[pi]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/pi-extension/index.js#L101-L253
[hermes]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/__init__.py#L102-L228
[portability]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/docs/agent-portability.md#L9-L46
[claudemanifest]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/.claude-plugin/plugin.json#L13-L40
[band]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/band/register.tsx#L154-L349
[metrics]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/band/metrics.ts#L63-L310
[import]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/ponytail-band-import.js#L16-L270
[board]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/hooks/band/board.ts#L555
[results]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/results/2026-10-07-agentic.md#L10-L126
[run]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/agentic/run.py#L50-L519
[complete]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/agentic/complete.py#L40-L143
[compare]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/agentic/compare.py#L18-L90
[correctness]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/correctness.js#L9-L290
[behavior]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/benchmarks/behavior.js#L17-L53
[ci]: https://github.com/DietrichGebert/ponytail/blob/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/.github/workflows/test.yml#L1-L40
