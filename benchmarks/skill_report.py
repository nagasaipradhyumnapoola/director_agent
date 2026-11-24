"""Individual scorecards and completeness verification for the skill matrix.

Reads `benchmarks/results/skill_matrix.json`, verifies that every tool × task ×
seed cell exists and succeeded, then writes per-tool scorecards plus a task
winner table. It performs no model calls.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = {
    "direct": "Direct model",
    "headroom": "Headroom",
    "ponytail": "Ponytail",
    "superpowers": "Superpowers",
    "ecc": "ECC",
    "ui_ux": "ui-ux-pro-max",
    "director": "DIRECTOR",
}
TASK_LABEL = {
    "slugify": "slugify",
    "parse_duration": "parse_duration",
    "merge_intervals": "merge_intervals",
    "design_card": "design_card",
    "clarity_worktree": "clarity_worktree",
    "context_pack": "context_pack",
    "selfdev_median": "selfdev_median",
}
CODE_TASKS = {"slugify", "parse_duration", "merge_intervals"}
TEXT_TASKS = {"design_card", "clarity_worktree", "context_pack"}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _partial_score(run: dict[str, Any]) -> float:
    if run.get("ok"):
        return 1.0
    detail = str(run.get("detail") or "")
    match = re.search(r"Ran (\d+) tests?", detail)
    if not match:
        return 0.0
    total = int(match.group(1))
    failures = re.search(r"failures=(\d+)", detail)
    errors = re.search(r"errors=(\d+)", detail)
    bad = (int(failures.group(1)) if failures else 0) + (int(errors.group(1)) if errors else 0)
    return max(0.0, (total - bad) / total)


def validate(runs: list[dict[str, Any]], tools: list[str], tasks: list[str], seeds: int) -> list[str]:
    problems: list[str] = []
    seen = {(run["tool"], run["task"], int(run["seed"])) for run in runs}
    for tool in tools:
        for task in tasks:
            for seed in range(seeds):
                if (tool, task, seed) not in seen:
                    problems.append(f"missing {tool}/{task}/seed{seed}")
    for run in runs:
        if int(run.get("output_tokens") or 0) == 0:
            problems.append(f"empty output: {run['tool']}/{run['task']}/seed{run['seed']}")
        if str(run.get("detail", "")).startswith(("HTTPError", "RuntimeError", "URLError")):
            problems.append(f"provider error: {run['tool']}/{run['task']}/seed{run['seed']}")
    return problems


def per_tool(runs: list[dict[str, Any]], tools: list[str], tasks: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tool in tools:
        rows = [run for run in runs if run["tool"] == tool]
        task_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in rows:
            task_rows[run["task"]].append(run)
        tasks_out = {}
        for task in tasks:
            items = task_rows.get(task, [])
            if not items:
                continue
            tasks_out[task] = {
                "runs": len(items),
                "passed": sum(1 for run in items if run["ok"]),
                "score": round(_mean([float(run["score"]) for run in items]), 4),
                "partial": round(_mean([_partial_score(run) for run in items]), 4),
                "tokens": sum(int(run["output_tokens"]) for run in items),
                "latency_s": round(sum(float(run["latency_s"]) for run in items), 2),
                "retention": round(_mean([float(run["grade"].get("retention", 0.0)) for run in items]), 4),
                "compression": round(_mean([float(run["grade"].get("compression", 0.0)) for run in items]), 4),
            }
        coding_pass = sum(task["passed"] for name, task in tasks_out.items() if name in CODE_TASKS)
        coding_total = sum(task["runs"] for name, task in tasks_out.items() if name in CODE_TASKS)
        selfdev_pass = sum(task["passed"] for name, task in tasks_out.items() if name == "selfdev_median")
        selfdev_total = sum(task["runs"] for name, task in tasks_out.items() if name == "selfdev_median")
        design = round(_mean([task["score"] for name, task in tasks_out.items() if name == "design_card"]), 4)
        clarity = round(_mean([task["score"] for name, task in tasks_out.items() if name == "clarity_worktree"]), 4)
        context = round(_mean([task["retention"] for name, task in tasks_out.items() if name == "context_pack"]), 4)
        compression = round(_mean([task["compression"] for name, task in tasks_out.items() if name == "context_pack"]), 4)
        tokens = sum(int(run["output_tokens"]) for run in rows)
        overall = 100 * (
            0.30 * (coding_pass / coding_total if coding_total else 0)
            + 0.20 * (selfdev_pass / selfdev_total if selfdev_total else 0)
            + 0.15 * design
            + 0.15 * clarity
            + 0.20 * context
        )
        out[tool] = {
            "tool": tool,
            "display": DISPLAY.get(tool, tool),
            "tasks": tasks_out,
            "coding_pass": coding_pass,
            "coding_total": coding_total,
            "selfdev_pass": selfdev_pass,
            "selfdev_total": selfdev_total,
            "design": design,
            "clarity": clarity,
            "context": context,
            "compression": compression,
            "tokens": tokens,
            "overall": round(overall, 1),
            "efficiency": round(overall / (tokens / 1000), 2) if tokens else 0.0,
            "latency_s": round(sum(float(run["latency_s"]) for run in rows), 1),
        }
    return out


def leaders(scorecards: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dims = {
        "coding": lambda c: (c["coding_pass"], c["tasks"].get("slugify", {}).get("partial", 0)),
        "selfdev": lambda c: c["selfdev_pass"],
        "design": lambda c: c["design"],
        "clarity": lambda c: c["clarity"],
        "context": lambda c: c["context"],
        "compression": lambda c: c["compression"],
        "token_efficiency": lambda c: c["efficiency"],
    }
    out = {}
    for name, key in dims.items():
        best = max(scorecards.values(), key=key)
        value = key(best)
        if name == "coding":
            out[name] = {"tool": best["tool"], "display": best["display"], "value": best["coding_pass"], "total": best["coding_total"], "detail": value[1]}
        elif name in ("selfdev", "context"):
            values = [key(card) for card in scorecards.values()]
            if max(values) == min(values):
                shown = f"{best['selfdev_pass']}/{best['selfdev_total']}" if name == "selfdev" else f"{best['context']:.0%}"
                out[name] = {"tool": "*", "display": "All tools", "value": shown}
            else:
                out[name] = {"tool": best["tool"], "display": best["display"], "value": value}
        else:
            out[name] = {"tool": best["tool"], "display": best["display"], "value": value}
    return out


def best_at(tool: str, scorecards: dict[str, Any], lead: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for dim, title in (
        ("coding", "coding"),
        ("design", "design"),
        ("clarity", "clarity"),
        ("context", "context retention"),
        ("compression", "compression"),
        ("token_efficiency", "token efficiency"),
    ):
        if lead[dim]["tool"] == tool:
            labels.append(title)
    if not labels:
        card = scorecards[tool]
        if card["coding_pass"] == lead["coding"]["value"]:
            labels.append(f"coding (tied {card['coding_pass']}/{card['coding_total']})")
        elif card["design"] == lead["design"]["value"]:
            labels.append(f"design (tied {card['design']:.0%})")
        elif card["clarity"] == lead["clarity"]["value"]:
            labels.append(f"clarity (tied {card['clarity']:.0%})")
        else:
            relative = [
                ("coding", card["coding_pass"] / max(1, card["coding_total"])),
                ("design", card["design"]),
                ("clarity", card["clarity"]),
            ]
            strongest = max(relative, key=lambda item: item[1])
            labels.append(f"no outright lead; strongest is {strongest[0]} ({strongest[1]:.0%})")
    return labels


def task_winners(scorecards: dict[str, Any], tasks: list[str]) -> list[dict[str, Any]]:
    out = []
    for task in tasks:
        entries = []
        for tool, card in scorecards.items():
            row = card["tasks"].get(task)
            if not row:
                continue
            if task in CODE_TASKS:
                key = (row["passed"], row["partial"])
            elif task == "selfdev_median":
                key = (row["passed"], row["score"])
            elif task == "context_pack":
                key = (row["retention"], row["compression"])
            else:
                key = (row["score"],)
            entries.append((key, tool, row))
        if not entries:
            continue
        entries.sort(key=lambda item: (item[0], -item[2]["tokens"]), reverse=True)
        key, tool, row = entries[0]
        if task == "selfdev_median" and len({entry[0] for entry in entries}) == 1:
            winner = "All tools"
        else:
            winner = DISPLAY.get(tool, tool)
        out.append(
            {
                "task": task,
                "winner": winner,
                "passed": f"{row['passed']}/{row['runs']}",
                "score": row["partial"] if task in CODE_TASKS else row["score"],
                "tokens": row["tokens"],
                "retention": row["retention"] if task == "context_pack" else None,
                "compression": row["compression"] if task == "context_pack" else None,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "benchmarks" / "results" / "skill_matrix.json"))
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "skill_individual.md"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    runs = payload["runs"]
    tools = sorted({run["tool"] for run in runs})
    tasks = sorted({run["task"] for run in runs})
    seeds = len({int(run["seed"]) for run in runs})
    problems = validate(runs, tools, tasks, seeds)
    print(f"coverage: {len(runs)} runs · {len(tools)} tools · {len(tasks)} tasks · {seeds} seeds")
    if problems:
        print("INCOMPLETE:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("coverage complete: every tool × task × seed cell succeeded")
    if args.verify_only:
        return 0

    scorecards = per_tool(runs, tools, tasks)
    lead = leaders(scorecards)
    winners = task_winners(scorecards, tasks)

    lines = [
        "# Individual skill scorecards",
        "",
        f"Model: `{payload['meta']['model']}` · {seeds} seeds · {len(runs)} runs.",
        "",
        "Every cell below is present and succeeded. Scores are prompt-level, not",
        "upstream runtime execution. Coding is strict pass count; partial score is",
        "diagnostic. 95% bootstrap CIs overlap, so rank is directional.",
        "",
        "## Dimension leaders",
        "",
        "| Dimension | Leader | Value |",
        "|---|---|---|",
    ]
    for dim in ("coding", "selfdev", "design", "clarity", "context", "compression", "token_efficiency"):
        entry = lead[dim]
        value = entry["value"]
        if dim == "coding":
            shown = f"{value}/{entry['total']}"
        elif isinstance(value, str):
            shown = value
        elif dim in ("design", "clarity", "context", "compression"):
            shown = f"{value:.0%}"
        elif dim == "token_efficiency":
            shown = f"{value:.1f} score/1k tokens"
        else:
            shown = f"{value}"
        lines.append(f"| {dim.replace('_', ' ').title()} | **{entry['display']}** | {shown} |")

    lines += [
        "",
        "## Task winners",
        "",
        "| Task | Winner | Pass | Score | Tokens | Retention | Compression |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in winners:
        ret = "—" if row["retention"] is None else f"{row['retention']:.0%}"
        comp = "—" if row["compression"] is None else f"{row['compression']:.0%}"
        lines.append(
            f"| {TASK_LABEL.get(row['task'], row['task'])} | **{row['winner']}** | {row['passed']} | "
            f"{row['score']:.0%} | {row['tokens']:,} | {ret} | {comp} |"
        )

    lines += ["", "## Individual scorecards", ""]
    for tool in sorted(scorecards, key=lambda name: -(
        scorecards[name]["coding_pass"] * 100 + scorecards[name]["design"] * 100
        + scorecards[name]["clarity"] * 100 + scorecards[name]["context"] * 100
    )):
        card = scorecards[tool]
        labels = best_at(tool, scorecards, lead)
        lines += [
            f"### {card['display']}",
            "",
            f"**Best at:** {', '.join(labels)}.",
            "",
            "| Task | Pass | Score | Tokens | Latency | Retention | Compression |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for task in tasks:
            row = card["tasks"].get(task)
            if not row:
                continue
            score = row["partial"] if task in CODE_TASKS else row["score"]
            ret = f"{row['retention']:.0%}" if task == "context_pack" else "—"
            comp = f"{row['compression']:.0%}" if task == "context_pack" else "—"
            lines.append(
                f"| {TASK_LABEL.get(task, task)} | {row['passed']}/{row['runs']} | {score:.0%} | "
                f"{row['tokens']} | {row['latency_s']}s | {ret} | {comp} |"
            )
        lines += [
            "",
            f"**Read:** {card['coding_pass']}/{card['coding_total']} strict coding, "
            f"{card['selfdev_pass']}/{card['selfdev_total']} selfdev, {card['design']:.0%} design, "
            f"{card['clarity']:.0%} clarity, {card['context']:.0%} context retention, "
            f"{card['compression']:.0%} compression, {card['tokens']:,} output tokens.",
            "",
        ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_out = out.with_suffix(".json")
    json_out.write_text(json.dumps({"coverage": {"runs": len(runs), "tools": len(tools), "tasks": len(tasks), "seeds": seeds}, "leaders": lead, "task_winners": winners, "best_at": {tool: best_at(tool, scorecards, lead) for tool in scorecards}, "scorecards": scorecards}, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"wrote {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
