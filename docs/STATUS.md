# DIRECTOR status â€” research-only handoff

Updated: **2026-11-23**.

## Current owner instruction

**Put the complete research handoff in D:\directer agent and prepare an end-to-end prompt for OpenCode.** This session prepares files and instructions; it does not implement the application or start OpenCode model work. The earlier research-session no-code instruction remains the historical boundary of preparation, not a prohibition on a later explicit OpenCode build request. The chat remains outside the lana bot project. Product scope is universal project supervision, not coding-only.

Primary entry point: ../OPENCODE_BUILD_PROMPT.md, supported by ../AGENTS.md and OPENCODE_HANDOFF.md. The generic MASTER_BUILD_PROMPT.md, blueprint, research, project analysis, evaluation plan and complete upstream inventories/reports are preserved. Existing destination Git metadata is preserved; no commit, remote push or publication was performed during preparation.

## Historical prototype review â€” no implementation retained here

Before the owner narrowed scope, an original Python prototype was briefly started. Its source, tests, scripts, environment and installer are not retained in this research workspace. After the research copies were verified, the old project and upstream-clone folders were sent to the Recycle Bin at the owner's request. The prototype was unfinished with known defects and is not a product deliverable. No provider credentials, global agent hooks, startup service, production deployment, push or publication were configured.

An earlier 28-test run reported OK with one privilege-dependent symlink test skipped. Subsequent independent review found material defects; five newly added regression tests all failed. Consequently **the prototype is not green and no completion/production-readiness claim is justified**. No fixes were applied after the owner's stop-coding instruction.

Known blockers for any future reuse:

1. Hardlinked source/state files bypass the link boundary; a linked external SQLite file can be modified.
2. Receipt/findings output lacks a total byte/allocation bound; repeated paths multiply large results.
3. Uppercase Python/JSON suffixes skip syntax checks.
4. MCP stdio frames are unbounded before parsing; unknown arguments may be ignored; validation may echo sensitive invalid values.
5. Returned bare findings omit their parent source hash/check version/receipt timestamp.
6. Non-Python/JSON files can receive static_pass even though their language was not checked.

These are recorded to inform the future builder and evaluation plan, not to continue coding now. A small synthetic lexical benchmark was run before the scope change; it is not semantic, domain-general or billion-scale evidence. See research/benchmark.json. No upstream repositories were executed or installed.

## Source provenance

Temporary local clones were removed from their active location. The reports and inventories retain exact revisions, source hashes, pinned public source links and original license notices, so the research remains traceable without keeping repository code here. LANA's existing files were preserved.

