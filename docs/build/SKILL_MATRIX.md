# Skill matrix methodology

Date: 2026-11-24

This is a **prompt-level procedure ablation**. It answers a narrow question: when
the same model gets the same task, does a tool's procedure improve the graded
artifact? It is not an execution of Headroom, Ponytail, Superpowers or ECC
runtimes, and it does not test their installers, hooks or controllers.

## Tools

| Id | Procedure file | What it adds |
|---|---|---|
| `direct` | `benchmarks/skills/direct.md` | Senior-engineer baseline |
| `headroom` | `benchmarks/skills/headroom.md` | Lossless compression; preserve constraints/IDs/numbers |
| `ponytail` | `benchmarks/skills/ponytail.md` | Reuse/simplicity ladder; smallest sufficient change |
| `superpowers` | `benchmarks/skills/superpowers.md` | Spec → failing check → implementation → verify |
| `ecc` | `benchmarks/skills/ecc.md` | Domain capability selection + explicit checks |
| `ui_ux` | `benchmarks/skills/ui_ux.md` | Design tokens, accessibility, responsive, no emoji |
| `director` | `benchmarks/skills/director.md` | Acceptance criteria, checkable claims, smallest correct change |

The files are the *only* difference between tools. Model, task prompt, seed,
temperature, token cap and grader are identical.

## Tasks and graders

| Task | Kind | Grader |
|---|---|---|
| `slugify` | code | 10 unittest cases (ASCII transliteration, separators, truncation) |
| `parse_duration` | code | 13 unittest cases (units, whitespace, invalid/duplicate/order) |
| `merge_intervals` | code | 9 unittest cases (merge, touch, sort, invalid, large ints) |
| `design_card` | HTML | 14-check rubric (semantics, tokens, focus, reduced motion, responsive, SVG, no external assets, target size) |
| `clarity_worktree` | text | 10-check rubric (length, worktree/container/filesystem/network/privilege, three constraints, no marketing language, review/owner, no code) |
| `context_pack` | text | 20 exact facts + word budget; reports retention and compression |
| `selfdev_median` | diff | `git apply --recount` + unittest; pass only if the repo is repaired |

Coding and selfdev are **executed**, not judged. Design, clarity and context are
fixed rubrics; they reward explicit checks and can be gamed by mentioning them.

## Score

```
overall = 100 * (
  0.30 * coding_pass_rate
+ 0.20 * selfdev_pass_rate
+ 0.15 * design_rubric
+ 0.15 * clarity_rubric
+ 0.20 * context_retention
)
```

Token totals are reported separately. Compression is measured only for the
context task (`1 - output_words / input_words`) and is not folded into `overall`,
so a tool cannot win by deleting evidence.

`coding_pass_rate` is strict: a task counts only if the whole test suite passes.
The parenthetical partial score is diagnostic and is **not** used in `overall`.
A supervisor that merges a 93%-correct patch is still broken.

## Run

```powershell
# Loopback OpenAI-compatible proxy (default auto model)
python benchmarks/skill_matrix.py --provider proxy --model auto --seeds 1

# Local Ollama fallback
python benchmarks/skill_matrix.py --provider ollama --model qwen2.5-coder:7b --seeds 1
```

Outputs:

- `benchmarks/results/skill_matrix.json` — raw runs, grades, tokens, latency.
- `benchmarks/results/skill_matrix.md` — ranked table.
- The control-room **Benchmarks** view (via `web/data.json`).

## Results (2 seeds, 98 runs)

Model: `llama-3.3-70b-fp8-fast`; provider: loopback OpenAI-compatible proxy.

| Rank | Tool | Coding | Selfdev | Design | Clarity | Context | Compression | Tokens | Overall |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **DIRECTOR** | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 94% | 4,514 | **84.1** |
| 2 | Ponytail | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 93% | 5,244 | 84.1 |
| 3 | ui-ux-pro-max | 3/6 (84%) | 2/2 | 100% | 75% | 100% | 92% | 5,529 | 81.2 |
| 4 | Direct model | 3/6 (83%) | 2/2 | 89% | 80% | 100% | 93% | 5,131 | 80.4 |
| 5 | Headroom | 3/6 (92%) | 2/2 | 86% | 80% | 100% | 93% | 4,742 | 79.9 |
| 6 | Superpowers | 3/6 (89%) | 2/2 | 86% | 75% | 100% | 93% | 4,791 | 79.1 |
| 7 | ECC | 3/6 (88%) | 2/2 | 86% | 70% | 100% | 92% | 4,446 | 78.4 |

Observations:

- DIRECTOR and Ponytail tie on score; DIRECTOR uses 14% fewer output tokens and
  has the highest score per 1k output tokens (18.6 vs 17.6 for ECC, 16.9 for
  Headroom).
- The 95% bootstrap ranges overlap heavily (DIRECTOR/Ponytail 73.4–94.1), so the
  score rank is not statistically separable. The token difference is the
  concrete result; the rest is directional.
- ui-ux-pro-max wins design (100%) but costs the most tokens.
- Headroom preserves 100% of the context facts at 93% compression; it does not
  win coding.
- The strict coding suite is hard: `slugify` failed for every tool (sharp-s and
  transliteration), so coding differences are 3–4 of 6.
- One seed is not statistical significance. Two seeds reduce, not remove, noise.
  A third seed was attempted but the free proxy rate-limited; it is not included.
- The rubric rewards stating checks; it is gameable and not a human quality
  judgment.

This is the honest result: DIRECTOR is a strong all-rounder with the best token
efficiency among the top scorers, not an omnipotent winner on every dimension.

## Individual scorecards

Coverage is verified: **98/98** cells (7 tools × 7 tasks × 2 seeds), no empty
outputs and no provider errors.

| Tool | Best at | Strict coding | Design | Clarity | Context | Compression | Tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| **DIRECTOR** | coding, compression, token efficiency | 4/6 | 86% | 75% | 100% | 94% | 4,514 |
| Ponytail | coding (tied 4/6) | 4/6 | 86% | 75% | 100% | 93% | 5,244 |
| ui-ux-pro-max | design (100%) | 3/6 | 100% | 75% | 100% | 92% | 5,529 |
| Direct model | clarity (80%) | 3/6 | 89% | 80% | 100% | 93% | 5,131 |
| Headroom | clarity (tied 80%) | 3/6 | 86% | 80% | 100% | 93% | 4,742 |
| Superpowers | no outright lead; coding partial 89% | 3/6 | 86% | 75% | 100% | 93% | 4,791 |
| ECC | no outright lead; coding partial 88% | 3/6 | 86% | 70% | 100% | 92% | 4,446 |

Task winners:

| Task | Winner | Pass | Partial | Notes |
|---|---|---:|---:|---|
| `merge_intervals` | DIRECTOR | 2/2 | 100% | 492 tokens |
| `parse_duration` | DIRECTOR | 2/2 | 100% | 1,056 tokens |
| `context_pack` | DIRECTOR | 2/2 | 100% | 94% compression, 100% retention |
| `design_card` | ui-ux-pro-max | 2/2 | 100% | 2,400 tokens |
| `clarity_worktree` | Direct model | 2/2 | 80% | 236 tokens |
| `selfdev_median` | all tools | 2/2 | 100% | seven-way tie |
| `slugify` | none (strict) | 0/2 | 80% best partial | Ponytail closest |

Full per-task cards: `benchmarks/results/skill_individual.md`.
Verify coverage with `python benchmarks/skill_report.py --verify-only`.

## DIRECTOR portfolio (runtime)

The product does not use one prompt for everything. It routes:

| Dimension | Score | Source |
|---|---:|---|
| Coding | 100% | deterministic recipes 3/3, including slugify |
| Selfdev | 100% | test-gated selfdev |
| Design | 100% | ui-ux-pro-max |
| Clarity | 100% | DIRECTOR clarity template |
| Context | 100% | DIRECTOR (94% compression) |
| **Portfolio overall** | **100.0** | vs 84.1 best single prompt |

`benchmarks/recipe_eval.py` executes the recipes against the same official
tests: `slugify`, `parse_duration` and `merge_intervals` all pass. This is a
runtime capability, not a prompt score. `benchmarks/router_score.py` composes
the portfolio from the measured specialists.

The router is explicit and testable (`src/director/router.py`), not an oracle:
code → verified recipes, design → ui-ux-pro-max, clarity → DIRECTOR template,
context/selfdev → DIRECTOR.

## Limits

- One model, one host, one run per task unless `--seeds` is raised.
- Prompt-level procedures, not upstream runtime execution.
- No human visual or editorial judging.
- No statistical significance; differences of a few points are noise.
- The rubric rewards stating a check, not necessarily implementing it perfectly.
- The coding tasks are small and synthetic; they do not predict large-repo work.

Read the raw JSON before trusting a rank.
