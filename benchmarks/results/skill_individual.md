# Individual skill scorecards

Model: `llama-3.3-70b-fp8-fast` · 2 seeds · 98 runs.

Every cell below is present and succeeded. Scores are prompt-level, not
upstream runtime execution. Coding is strict pass count; partial score is
diagnostic. 95% bootstrap CIs overlap, so rank is directional.

## Dimension leaders

| Dimension | Leader | Value |
|---|---|---|
| Coding | **DIRECTOR** | 4/6 |
| Selfdev | **All tools** | 2/2 |
| Design | **ui-ux-pro-max** | 100% |
| Clarity | **Direct model** | 80% |
| Context | **All tools** | 100% |
| Compression | **DIRECTOR** | 94% |
| Token Efficiency | **DIRECTOR** | 18.6 score/1k tokens |

## Task winners

| Task | Winner | Pass | Score | Tokens | Retention | Compression |
|---|---|---:|---:|---:|---:|---:|
| clarity_worktree | **Direct model** | 2/2 | 80% | 236 | — | — |
| context_pack | **DIRECTOR** | 2/2 | 100% | 437 | 100% | 94% |
| design_card | **ui-ux-pro-max** | 2/2 | 100% | 2,400 | — | — |
| merge_intervals | **DIRECTOR** | 2/2 | 100% | 492 | — | — |
| parse_duration | **DIRECTOR** | 2/2 | 100% | 1,056 | — | — |
| selfdev_median | **All tools** | 2/2 | 100% | 226 | — | — |
| slugify | **Ponytail** | 0/2 | 80% | 462 | — | — |

## Individual scorecards

### DIRECTOR

**Best at:** coding, compression, token efficiency.

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 1/2 | 75% | 240 | 5.45s | — | — |
| context_pack | 2/2 | 100% | 437 | 6.37s | 100% | 94% |
| design_card | 2/2 | 86% | 1579 | 23.63s | — | — |
| merge_intervals | 2/2 | 100% | 492 | 6.1s | — | — |
| parse_duration | 2/2 | 100% | 1056 | 14.14s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.71s | — | — |
| slugify | 0/2 | 80% | 480 | 6.07s | — | — |

**Read:** 4/6 strict coding, 2/2 selfdev, 86% design, 75% clarity, 100% context retention, 94% compression, 4,514 output tokens.

### Ponytail

**Best at:** coding (tied 4/6).

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 1/2 | 75% | 270 | 5.46s | — | — |
| context_pack | 2/2 | 100% | 440 | 6.19s | 100% | 93% |
| design_card | 2/2 | 86% | 2182 | 24.57s | — | — |
| merge_intervals | 2/2 | 100% | 596 | 7.21s | — | — |
| parse_duration | 2/2 | 100% | 1064 | 12.85s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.39s | — | — |
| slugify | 0/2 | 80% | 462 | 6.0s | — | — |

**Read:** 4/6 strict coding, 2/2 selfdev, 86% design, 75% clarity, 100% context retention, 93% compression, 5,244 output tokens.

### ui-ux-pro-max

**Best at:** design.

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 1/2 | 75% | 239 | 5.13s | — | — |
| context_pack | 2/2 | 100% | 508 | 7.62s | 100% | 92% |
| design_card | 2/2 | 100% | 2400 | 28.3s | — | — |
| merge_intervals | 2/2 | 100% | 627 | 7.35s | — | — |
| parse_duration | 1/2 | 73% | 1047 | 14.32s | — | — |
| selfdev_median | 2/2 | 100% | 226 | 3.46s | — | — |
| slugify | 0/2 | 80% | 482 | 5.75s | — | — |

**Read:** 3/6 strict coding, 2/2 selfdev, 100% design, 75% clarity, 100% context retention, 92% compression, 5,529 output tokens.

### Direct model

**Best at:** clarity.

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 2/2 | 80% | 236 | 4.45s | — | — |
| context_pack | 2/2 | 100% | 448 | 6.76s | 100% | 93% |
| design_card | 2/2 | 89% | 1949 | 23.01s | — | — |
| merge_intervals | 2/2 | 100% | 592 | 6.91s | — | — |
| parse_duration | 1/2 | 69% | 1178 | 13.78s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.27s | — | — |
| slugify | 0/2 | 80% | 498 | 7.79s | — | — |

**Read:** 3/6 strict coding, 2/2 selfdev, 89% design, 80% clarity, 100% context retention, 93% compression, 5,131 output tokens.

### Headroom

**Best at:** clarity (tied 80%).

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 2/2 | 80% | 278 | 5.33s | — | — |
| context_pack | 2/2 | 100% | 452 | 7.13s | 100% | 93% |
| design_card | 2/2 | 86% | 1729 | 19.7s | — | — |
| merge_intervals | 2/2 | 100% | 586 | 7.16s | — | — |
| parse_duration | 1/2 | 96% | 967 | 13.85s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.36s | — | — |
| slugify | 0/2 | 80% | 500 | 6.37s | — | — |

**Read:** 3/6 strict coding, 2/2 selfdev, 86% design, 80% clarity, 100% context retention, 93% compression, 4,742 output tokens.

### Superpowers

**Best at:** no outright lead; strongest is design (86%).

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 1/2 | 75% | 245 | 4.64s | — | — |
| context_pack | 2/2 | 100% | 543 | 7.3s | 100% | 93% |
| design_card | 2/2 | 86% | 1585 | 19.48s | — | — |
| merge_intervals | 2/2 | 100% | 593 | 7.6s | — | — |
| parse_duration | 1/2 | 88% | 1131 | 13.54s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.1s | — | — |
| slugify | 0/2 | 80% | 464 | 5.56s | — | — |

**Read:** 3/6 strict coding, 2/2 selfdev, 86% design, 75% clarity, 100% context retention, 93% compression, 4,791 output tokens.

### ECC

**Best at:** no outright lead; strongest is design (86%).

| Task | Pass | Score | Tokens | Latency | Retention | Compression |
|---|---:|---:|---:|---:|---:|---:|
| clarity_worktree | 0/2 | 70% | 231 | 4.33s | — | — |
| context_pack | 2/2 | 100% | 504 | 7.22s | 100% | 92% |
| design_card | 2/2 | 86% | 1397 | 16.5s | — | — |
| merge_intervals | 2/2 | 100% | 608 | 7.02s | — | — |
| parse_duration | 1/2 | 85% | 986 | 14.7s | — | — |
| selfdev_median | 2/2 | 100% | 230 | 3.47s | — | — |
| slugify | 0/2 | 80% | 490 | 8.34s | — | — |

**Read:** 3/6 strict coding, 2/2 selfdev, 86% design, 70% clarity, 100% context retention, 92% compression, 4,446 output tokens.

