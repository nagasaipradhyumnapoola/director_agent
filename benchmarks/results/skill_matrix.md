# DIRECTOR skill matrix

Model: `llama-3.3-70b-fp8-fast` · provider: `proxy` · seeds: 2 · tasks: 7

Prompt-level ablation. Upstream runtimes/hooks were not executed. Coding/selfdev are test-graded; design/clarity/context are rubric-graded.

| Rank | Tool | Coding | Selfdev | Design | Clarity | Context | Compression | Tokens | Overall | 95% CI |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **DIRECTOR** | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 94% | 4,514 | **84.1** | 73.4–94.1 |
| 2 | **Ponytail** | 4/6 (93%) | 2/2 | 86% | 75% | 100% | 93% | 5,244 | **84.1** | 73.4–94.1 |
| 3 | **ui-ux-pro-max** | 3/6 (84%) | 2/2 | 100% | 75% | 100% | 92% | 5,529 | **81.2** | 70.5–92.0 |
| 4 | **Direct model** | 3/6 (83%) | 2/2 | 89% | 80% | 100% | 93% | 5,131 | **80.4** | 69.9–90.9 |
| 5 | **Headroom** | 3/6 (92%) | 2/2 | 86% | 80% | 100% | 93% | 4,742 | **79.9** | 69.9–89.9 |
| 6 | **Superpowers** | 3/6 (89%) | 2/2 | 86% | 75% | 100% | 93% | 4,791 | **79.1** | 68.4–89.9 |
| 7 | **ECC** | 3/6 (88%) | 2/2 | 86% | 70% | 100% | 92% | 4,446 | **78.4** | 68.4–88.4 |

Overall = 30% coding + 20% selfdev + 15% design + 15% clarity + 20% context retention.

Limits: one model, one host, prompt-level procedures, no upstream runtime/hook execution, no human visual judging. The matrix is a directional ablation, not a universal leaderboard.
