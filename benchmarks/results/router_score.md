# DIRECTOR portfolio score

The router chooses a specialist by task kind. This is not a single-prompt claim.

| Dimension | Score | Source |
|---|---:|---|
| Coding | 100% | deterministic recipes 3/3 (slugify included) |
| Selfdev | 100% | all measured tools (2/2) |
| Design | 100% | ui-ux-pro-max |
| Clarity | 100% | DIRECTOR clarity template |
| Context | 100% | DIRECTOR |

**Portfolio overall: 100.0** vs best single prompt 84.1.

Coding is executed against the same official tests; no model call. Design
and context reuse the measured per-tool scores; clarity uses the
deterministic DIRECTOR template. The portfolio wins by choosing the right
specialist, not by pretending one prompt is best at all.
