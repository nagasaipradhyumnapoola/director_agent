"""Prompt-level skill matrix benchmark for DIRECTOR.

Runs identical tasks through seven procedure prompts:
direct, Headroom, Ponytail, Superpowers, ECC, ui-ux-pro-max and DIRECTOR.
Coding and selfdev tasks are graded by executing tests; design, clarity and
context tasks use fixed rubrics. This is an ablation, not a claim that the
upstream runtimes or hooks were executed.

Usage:
    python benchmarks/skill_matrix.py --seeds 2
    python benchmarks/skill_matrix.py --provider ollama --model qwen2.5-coder:7b
    python benchmarks/skill_matrix.py --tools director,ponytail --tasks slugify
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import matrix_tasks as tasks  # noqa: E402
from director.keychain import get_secret  # noqa: E402
from director.store import Store  # noqa: E402

PROXY_BASE = "http://127.0.0.1:31415/v1"
OLLAMA_BASE = "http://127.0.0.1:11434"
SECRET_NAME = "provider/freellm"
DEFAULT_MODEL = "auto"


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 90) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("provider response was not an object")
    return parsed


def proxy_key() -> str | None:
    try:
        store = Store.open(ROOT)
        try:
            return get_secret(store.project_id, SECRET_NAME)
        finally:
            store.close()
    except Exception:
        return None


def chat_proxy(messages: list[dict[str, str]], model: str, max_tokens: int, seed: int, key: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {key}"}
    last: Exception | None = None
    for attempt in range(3):
        try:
            parsed = _post_json(f"{PROXY_BASE}/chat/completions", payload, headers, timeout=90)
            content = parsed["choices"][0]["message"]["content"]
            usage = parsed.get("usage") or {}
            return {
                "text": str(content),
                "input_tokens": int(usage.get("prompt_tokens") or estimate_tokens(json.dumps(messages))),
                "output_tokens": int(usage.get("completion_tokens") or estimate_tokens(str(content))),
                "provider": "proxy",
                "model": str(parsed.get("model") or model),
            }
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(min(8, 2 * (attempt + 1)))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(4, 2 * (attempt + 1)))
    raise RuntimeError(f"proxy failed after retries: {last}")


def chat_ollama(messages: list[dict[str, str]], model: str, max_tokens: int, seed: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens, "seed": seed},
    }
    parsed = _post_json(f"{OLLAMA_BASE}/api/chat", payload, {}, timeout=300)
    content = parsed.get("message", {}).get("content", "")
    return {
        "text": str(content),
        "input_tokens": int(parsed.get("prompt_eval_count") or estimate_tokens(json.dumps(messages))),
        "output_tokens": int(parsed.get("eval_count") or estimate_tokens(str(content))),
        "provider": "ollama",
        "model": str(parsed.get("model") or model),
    }


def chat(messages: list[dict[str, str]], provider: str, model: str, max_tokens: int, seed: int) -> dict[str, Any]:
    key = proxy_key() if provider in ("auto", "proxy") else None
    if provider in ("auto", "proxy") and key:
        try:
            return chat_proxy(messages, model, max_tokens, seed, key)
        except Exception as exc:
            if provider == "proxy":
                raise
            print(f"  proxy failed ({type(exc).__name__}); falling back to Ollama", flush=True)
    ollama_model = "qwen2.5-coder:7b" if provider == "auto" and model == DEFAULT_MODEL else model
    return chat_ollama(messages, ollama_model, max_tokens, seed)


def artifact(kind: str, text: str) -> str:
    if kind == "code":
        return tasks.extract_code(text)
    if kind == "html":
        return tasks.extract_html(text)
    if kind == "diff":
        return tasks.extract_diff(text)
    return text.strip()


def run_one(tool: str, task_name: str, seed: int, provider: str, model: str, max_tokens: int) -> dict[str, Any]:
    task = tasks.TASKS[task_name]
    system = tasks.read_skill(tool)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task["prompt"]},
    ]
    started = time.perf_counter()
    limit = min(max_tokens, int(task.get("max_tokens", max_tokens)))
    reply = chat(messages, provider, model, limit, seed)
    latency = time.perf_counter() - started
    payload = artifact(task["kind"], reply["text"])
    try:
        grade = task["runner"](payload)
    except Exception as exc:  # a malformed artifact is a failed run, not a crashed benchmark
        grade = {"ok": False, "score": 0.0, "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}
    return {
        "tool": tool,
        "task": task_name,
        "seed": seed,
        "ok": bool(grade.get("ok")),
        "score": float(grade.get("score") or 0.0),
        "detail": str(grade.get("detail") or "")[:1200],
        "grade": grade,
        "latency_s": round(latency, 3),
        "input_tokens": reply["input_tokens"],
        "output_tokens": reply["output_tokens"],
        "provider": reply["provider"],
        "model": reply["model"],
        "artifact_chars": len(payload),
        "artifact": payload[:4000],
    }


def _code_score(run: dict[str, Any]) -> float:
    if run.get("ok"):
        return 1.0
    if float(run.get("score") or 0.0) > 0:
        return float(run["score"])
    detail = str(run.get("detail") or "")
    match = re.search(r"Ran (\d+) tests?", detail)
    if not match:
        return 0.0
    total = int(match.group(1))
    failures = int(re.search(r"failures=(\d+)", detail).group(1)) if re.search(r"failures=(\d+)", detail) else 0
    errors = int(re.search(r"errors=(\d+)", detail).group(1)) if re.search(r"errors=(\d+)", detail) else 0
    return max(0.0, (total - failures - errors) / total) if total else 0.0


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    rng = random.Random(42)
    for tool in sorted({run["tool"] for run in runs}):
        rows = [run for run in runs if run["tool"] == tool]
        coding = [run for run in rows if tasks.TASKS[run["task"]]["kind"] == "code"]
        selfdev = [run for run in rows if run["task"] == "selfdev_median"]
        design = [run for run in rows if run["task"] == "design_card"]
        clarity = [run for run in rows if run["task"] == "clarity_worktree"]
        context = [run for run in rows if run["task"] == "context_pack"]

        def mean(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        coding_rate = mean([1.0 if run["ok"] else 0.0 for run in coding])
        coding_score = mean([_code_score(run) for run in coding])
        selfdev_rate = mean([1.0 if run["ok"] else 0.0 for run in selfdev])
        design_score = mean([run["score"] for run in design])
        clarity_score = mean([run["score"] for run in clarity])
        retention = mean([run["grade"].get("retention", 0.0) for run in context])
        compression = mean([run["grade"].get("compression", 0.0) for run in context])
        overall = 100 * (
            0.30 * coding_rate
            + 0.20 * selfdev_rate
            + 0.15 * design_score
            + 0.15 * clarity_score
            + 0.20 * retention
        )
        summary[tool] = {
            "coding_rate": round(coding_rate, 4),
            "coding_score": round(coding_score, 4),
            "coding_passed": sum(1 for run in coding if run["ok"]),
            "coding_total": len(coding),
            "selfdev_rate": round(selfdev_rate, 4),
            "selfdev_passed": sum(1 for run in selfdev if run["ok"]),
            "selfdev_total": len(selfdev),
            "design": round(design_score, 4),
            "clarity": round(clarity_score, 4),
            "context_retention": round(retention, 4),
            "context_compression": round(compression, 4),
            "input_tokens": sum(run["input_tokens"] for run in rows),
            "output_tokens": sum(run["output_tokens"] for run in rows),
            "latency_s": round(sum(run["latency_s"] for run in rows), 1),
            "overall": round(overall, 1),
        }
        summary[tool]["ci95"] = _bootstrap_ci(runs, tool, rng, rounds=1000)
    return summary


def _bootstrap_ci(runs: list[dict[str, Any]], tool: str, rng: random.Random, rounds: int = 1000) -> list[float]:
    """Stratified bootstrap over seeds within each task category.

    Small-sample and directional: it shows how much the score moves when the
    observed seeds are resampled. It is not a population confidence interval.
    """
    categories = {
        "coding": [run for run in runs if run["tool"] == tool and tasks.TASKS[run["task"]]["kind"] == "code"],
        "selfdev": [run for run in runs if run["tool"] == tool and run["task"] == "selfdev_median"],
        "design": [run for run in runs if run["tool"] == tool and run["task"] == "design_card"],
        "clarity": [run for run in runs if run["tool"] == tool and run["task"] == "clarity_worktree"],
        "context": [run for run in runs if run["tool"] == tool and run["task"] == "context_pack"],
    }
    weights = {"coding": 0.30, "selfdev": 0.20, "design": 0.15, "clarity": 0.15, "context": 0.20}
    scores = []
    for _ in range(rounds):
        total = 0.0
        total_weight = 0.0
        for name, rows in categories.items():
            if not rows:
                continue
            sample = [rng.choice(rows) for _ in rows]
            if name in ("coding", "selfdev"):
                value = sum((1.0 if run["ok"] else 0.0) for run in sample) / len(sample)
            elif name == "context":
                value = sum(run["grade"].get("retention", 0.0) for run in sample) / len(sample)
            else:
                value = sum(run["score"] for run in sample) / len(sample)
            total += weights[name] * value
            total_weight += weights[name]
        scores.append(100 * total / total_weight if total_weight else 0.0)
    scores.sort()
    return [round(scores[int(rounds * 0.025)], 1), round(scores[int(rounds * 0.975) - 1], 1)]


def markdown(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    display = {
        "direct": "Direct model",
        "headroom": "Headroom",
        "ponytail": "Ponytail",
        "superpowers": "Superpowers",
        "ecc": "ECC",
        "ui_ux": "ui-ux-pro-max",
        "director": "DIRECTOR",
    }
    ranked = sorted(summary.items(), key=lambda item: (-item[1]["overall"], -item[1]["coding_rate"], item[1]["output_tokens"]))
    lines = [
        "# DIRECTOR skill matrix",
        "",
        f"Model: `{meta['model']}` · provider: `{meta['provider']}` · seeds: {meta['seeds']} · tasks: {len(meta['tasks'])}",
        "",
        "Prompt-level ablation. Upstream runtimes/hooks were not executed. Coding/selfdev are test-graded; design/clarity/context are rubric-graded.",
        "",
        "| Rank | Tool | Coding | Selfdev | Design | Clarity | Context | Compression | Tokens | Overall | 95% CI |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, (tool, row) in enumerate(ranked, 1):
        lines.append(
            f"| {index} | **{display.get(tool, tool)}** | {row['coding_passed']}/{row['coding_total']} ({row['coding_score']:.0%}) | "
            f"{row['selfdev_passed']}/{row['selfdev_total']} | {row['design']:.0%} | "
            f"{row['clarity']:.0%} | {row['context_retention']:.0%} | "
            f"{row['context_compression']:.0%} | {row['output_tokens']:,} | **{row['overall']:.1f}** | "
            f"{row.get('ci95', ['—', '—'])[0]}–{row.get('ci95', ['—', '—'])[1]} |"
        )
    lines += [
        "",
        "Overall = 30% coding + 20% selfdev + 15% design + 15% clarity + 20% context retention.",
        "",
        "Limits: one model, one host, prompt-level procedures, no upstream runtime/hook execution, no human visual judging. The matrix is a directional ablation, not a universal leaderboard.",
    ]
    return "\n".join(lines) + "\n"


def self_test() -> int:
    """Exercise extraction and rubrics without a model."""
    code = "```python\ndef slugify(text, max_length=80):\n    return ''\n```"
    assert "def slugify" in tasks.extract_code(code)
    assert tasks.design_rubric("<!doctype html><html lang=en><meta name=viewport><main><h1>x</h1></main>")["score"] < 1
    assert tasks.clarity_rubric("worktree container filesystem network privilege")["score"] < 1
    assert tasks.context_rubric("ORBIT-7")["retention"] > 0
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--provider", choices=["auto", "proxy", "ollama"], default="auto")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--tools", default=",".join(tasks.TOOLS))
    parser.add_argument("--tasks", default=",".join(tasks.TASKS))
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "skill_matrix.json"))
    parser.add_argument("--resume", action="store_true", help="keep successful rows, rerun empty/error rows")
    parser.add_argument("--force-tools", default="", help="comma-separated tool ids to rerun even if successful")
    parser.add_argument("--recompute", action="store_true", help="re-summarize an existing JSON without model calls")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.recompute:
        path = Path(args.out)
        payload = json.loads(path.read_text(encoding="utf-8"))
        runs = payload.get("runs", [])
        summary = summarize(runs)
        meta = payload.get("meta", {})
        meta["seeds"] = len({int(run.get("seed", 0)) for run in runs}) or 1
        meta["tasks"] = sorted({run["task"] for run in runs})
        meta["tools"] = sorted({run["tool"] for run in runs})
        meta["recomputed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path.write_text(json.dumps({"meta": meta, "summary": summary, "runs": runs}, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(markdown(summary, meta), encoding="utf-8")
        print(markdown(summary, meta))
        return 0

    tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    task_names = [item.strip() for item in args.tasks.split(",") if item.strip()]
    for tool in tools:
        if tool not in tasks.TOOLS:
            raise SystemExit(f"unknown tool: {tool}")
    for name in task_names:
        if name not in tasks.TASKS:
            raise SystemExit(f"unknown task: {name}")

    started = time.perf_counter()
    runs: list[dict[str, Any]] = []
    all_jobs = [
        (tool, task_name, seed)
        for tool in tools
        for task_name in task_names
        for seed in range(max(1, args.seeds))
    ]
    previous: dict[tuple[str, str, int], dict[str, Any]] = {}
    if args.resume and Path(args.out).is_file():
        try:
            old = json.loads(Path(args.out).read_text(encoding="utf-8"))
            previous = {(row["tool"], row["task"], int(row["seed"])): row for row in old.get("runs", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            previous = {}
    jobs: list[tuple[str, str, int]] = []
    forced = {item.strip() for item in args.force_tools.split(",") if item.strip()}
    for job in all_jobs:
        prior = previous.get(job)
        if job[0] in forced:
            jobs.append(job)
            continue
        if prior is not None and int(prior.get("output_tokens") or 0) > 0 and not str(prior.get("detail", "")).startswith(("HTTPError", "RuntimeError", "URLError")):
            runs.append(prior)
        else:
            jobs.append(job)
    total = len(jobs)
    done = 0

    def record(run: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        runs.append(run)
        print(
            f"[{done}/{total}] {run['tool']} · {run['task']} · seed {run['seed']} "
            f"-> {'PASS' if run['ok'] else 'fail'} · score {run['score']:.2f} · "
            f"{run['output_tokens']} out tokens · {run['latency_s']}s",
            flush=True,
        )

    def error_run(tool: str, task_name: str, seed: int, exc: Exception) -> dict[str, Any]:
        return {
            "tool": tool,
            "task": task_name,
            "seed": seed,
            "ok": False,
            "score": 0.0,
            "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
            "grade": {},
            "latency_s": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "provider": args.provider,
            "model": args.model,
            "artifact_chars": 0,
        }

    if args.concurrency > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.concurrency, 8)) as pool:
            futures = {
                pool.submit(run_one, tool, task_name, seed, args.provider, args.model, args.max_tokens): (tool, task_name, seed)
                for tool, task_name, seed in jobs
            }
            for future in concurrent.futures.as_completed(futures):
                tool, task_name, seed = futures[future]
                try:
                    record(future.result())
                except Exception as exc:
                    record(error_run(tool, task_name, seed, exc))
    else:
        for tool, task_name, seed in jobs:
            try:
                record(run_one(tool, task_name, seed, args.provider, args.model, args.max_tokens))
            except Exception as exc:
                record(error_run(tool, task_name, seed, exc))
            time.sleep(0.35)

    summary = summarize(runs)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": args.provider,
        "model": args.model,
        "seeds": max(1, args.seeds),
        "tasks": task_names,
        "tools": tools,
        "total_seconds": round(time.perf_counter() - started, 1),
        "methodology": "prompt-level procedure ablation; deterministic tests and fixed rubrics; upstream runtimes not executed",
        "weights": {"coding": 0.30, "selfdev": 0.20, "design": 0.15, "clarity": 0.15, "context": 0.20},
        "limitations": [
            "one model and one host",
            "prompt-level procedures, not upstream runtime execution",
            "no human visual or editorial judging",
            "rubrics reward explicit checks and can be gamed by mentioning them",
        ],
    }
    payload = {"meta": meta, "summary": summary, "runs": runs}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(summary, meta), encoding="utf-8")
    print(markdown(summary, meta))
    print(f"json: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
