"""Reproducible DIRECTOR benchmark suite.

Measures only what can actually run on this host. Upstream runtime tools that
are not installed/executed are reported as not-run, not as favorable results.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from director import RELEASE_TARGET, __version__
from director.demo import build_contract, run_demo
from director.memory import MemoryIndex
from director.models import Budgets, PermissionPolicy
from director.policy import PolicyGateway
from director.providers import call_model
from director.store import Store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timer(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * p / 100))
    return round(ordered[index], 3)


def _repo_with_fixtures(tmp: Path) -> Path:
    repo = tmp / "demo-repo"
    (repo / "fixtures").mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "fixtures"
    for domain in ("general", "website", "ml", "research"):
        shutil.copytree(source / domain, repo / "fixtures" / domain)
    return repo


def bench_domains(tmp: Path, browser: bool = True) -> dict[str, Any]:
    repo = _repo_with_fixtures(tmp)
    domains = ("general", "ml", "research") + (("website",) if browser else ())
    started = time.perf_counter()
    summary = run_demo(repo, domains=domains, modes=("clean", "broken"))
    elapsed = time.perf_counter() - started
    rows = []
    for result in summary["results"]:
        rows.append(
            {
                "domain": result["domain"],
                "mode": result["mode"],
                "status": result["status"],
                "findings": len(result.get("findings") or []),
                "duration_seconds": round(float(result.get("duration_seconds") or 0), 3),
                "checks": [
                    {
                        "key": check.get("criterion_key"),
                        "outcome": check.get("outcome"),
                        "passed": check.get("passed"),
                    }
                    for check in result.get("checks", [])
                ],
            }
        )
    expected = {(r["domain"], r["mode"]): ("pass" if r["mode"] == "clean" else "fail") for r in rows}
    correct = sum(
        1
        for row in rows
        if (row["status"] == "pass") == (row["mode"] == "clean")
    )
    return {
        "benchmark": "domain_detection",
        "domains": list(domains),
        "modes": ["clean", "broken"],
        "cases": len(rows),
        "correct_discriminations": correct,
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "wall_seconds": round(elapsed, 3),
        "model_calls": summary.get("model_calls"),
        "run_root": summary.get("run_root"),
        "rows": rows,
        "limitations": [
            "controlled fixtures only; not general domain competence",
            "website depends on local Chromium/CDP",
        ],
    }


def _synthetic_corpus(index: MemoryIndex, tokens: int, title_prefix: str) -> tuple[list[str], float, int]:
    target_chars = tokens * 4
    doc_chars = 4000
    count = max(1, target_chars // doc_chars)
    rng = random.Random(1234 + tokens)
    markers: list[str] = []
    started = time.perf_counter()
    filler = "controlled synthetic supervision corpus token "
    for i in range(count):
        marker = f"marker{tokens}_{i:07d}"
        markers.append(marker)
        body = (
            f"Document {i}. Unique marker {marker}. "
            + (filler * (doc_chars // max(1, len(filler))))
        )[:doc_chars]
        index.add_text(body, f"{title_prefix}-{i:07d}", kind="synthetic")
    elapsed = time.perf_counter() - started
    return markers, elapsed, count


def bench_retrieval(tmp: Path, tiers: tuple[int, ...]) -> dict[str, Any]:
    results = []
    for tokens in tiers:
        root = tmp / f"retrieval-{tokens}"
        root.mkdir(parents=True, exist_ok=True)
        store = Store.open_or_create(root, f"retrieval-{tokens}")
        try:
            index = MemoryIndex(store)
            markers, ingest_seconds, docs = _synthetic_corpus(index, tokens, f"doc{tokens}")
            rng = random.Random(99 + tokens)
            sample = rng.sample(markers, min(100, len(markers)))
            latencies = []
            hits = 0
            for marker in sample:
                started = time.perf_counter()
                rows = index.search(marker, limit=5)
                latencies.append((time.perf_counter() - started) * 1000)
                if any(marker in (row.get("text") or "") for row in rows):
                    hits += 1
            deleted_marker = markers[0]
            deleted_rows = index.search(deleted_marker, limit=1)
            deleted_source = deleted_rows[0]["source_id"] if deleted_rows else None
            if deleted_source:
                index.forget(deleted_source)
            deleted_hits = index.search(deleted_marker, limit=5)
            db_bytes = store.path.stat().st_size
            wal = store.path.with_name(store.path.name + "-wal")
            if wal.exists():
                db_bytes += wal.stat().st_size
            results.append(
                {
                    "tier_tokens": tokens,
                    "documents": docs,
                    "ingest_seconds": round(ingest_seconds, 3),
                    "queries": len(sample),
                    "recall_at_5": round(hits / len(sample), 4) if sample else 0.0,
                    "p50_search_ms": _percentile(latencies, 50),
                    "p95_search_ms": _percentile(latencies, 95),
                    "database_bytes": db_bytes,
                    "deleted_sources": 1 if deleted_source else 0,
                    "deleted_result_count": len(deleted_hits),
                }
            )
        finally:
            store.close()
    return {
        "benchmark": "lexical_retrieval",
        "tiers": list(tiers),
        "results": results,
        "limitations": [
            "synthetic exact-marker lexical queries only",
            "not semantic, temporal, ACL or billion-token evidence",
            "10M tier is the largest run here; 100M/1B not run",
        ],
    }


def bench_mcp(tmp: Path, calls: int = 20) -> dict[str, Any]:
    root = tmp / "mcp-bench"
    root.mkdir(parents=True, exist_ok=True)
    store = Store.open_or_create(root, "mcp-bench")
    db = store.path
    store.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        [sys.executable, "-m", "director", "mcp", "serve", "--db", str(db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    try:
        def send(obj: dict[str, Any]):
            process.stdin.write(json.dumps(obj).encode("utf-8") + b"\n")
            process.stdin.flush()

        def receive() -> dict[str, Any]:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed")
            return json.loads(line)

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
        init = receive()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = receive()
        latencies = []
        for index in range(calls):
            started = time.perf_counter()
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 3 + index,
                    "method": "tools/call",
                    "params": {"name": "director_status", "arguments": {}},
                }
            )
            receive()
            latencies.append((time.perf_counter() - started) * 1000)
        send({"jsonrpc": "2.0", "id": 999, "method": "ping"})
        ping = receive()
        return {
            "benchmark": "mcp_stdio",
            "protocol": init["result"]["protocolVersion"],
            "tools": len(tools["result"]["tools"]),
            "calls": calls,
            "mean_ms": round(statistics.mean(latencies), 3),
            "p50_ms": _percentile(latencies, 50),
            "p95_ms": _percentile(latencies, 95),
            "ping_ok": ping.get("result") == {},
            "limitations": ["local stdio only; no remote/OAuth/native tool-call test"],
        }
    finally:
        try:
            process.stdin.close()
        except Exception:
            pass
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()
        try:
            process.stdout.close()
            process.stderr.close()
        except Exception:
            pass


def bench_ollama(tmp: Path, models: tuple[str, ...]) -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            available = {
                item["name"]
                for item in json.loads(response.read().decode("utf-8")).get("models", [])
            }
    except Exception:
        return {"benchmark": "local_ollama", "available": False, "results": [], "limitations": ["Ollama not running"]}
    root = tmp / "ollama-bench"
    root.mkdir(parents=True, exist_ok=True)
    store = Store.open_or_create(root, "ollama-bench")
    try:
        store.save_contract(
            build_contract(store.project_id, ("general",)),
        )
        # Replace the general demo permissions with local model permission.
        contract = build_contract(store.project_id, ("general",))
        from director.models import TaskContract
        patched = TaskContract(
            project_id=contract.project_id,
            revision=2,
            intent=contract.intent,
            deliverables=contract.deliverables,
            constraints=contract.constraints,
            non_goals=contract.non_goals,
            assumptions=contract.assumptions,
            domains=contract.domains,
            requirements=contract.requirements,
            budgets=Budgets(max_model_calls=20, max_wall_seconds=300),
            permissions=PermissionPolicy(
                allowed_actions=("read_artifact", "model_call_local")
            ),
            stopping_conditions=contract.stopping_conditions,
        )
        store.save_contract(patched)
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:ollama", 2)
        results = []
        for model in models:
            if model not in available:
                results.append({"model": model, "skipped": True, "reason": "not installed"})
                continue
            started = time.perf_counter()
            try:
                result = call_model(
                    store,
                    "Reply with exactly OK.",
                    provider="ollama",
                    model=model,
                    timeout=180,
                )
                elapsed = time.perf_counter() - started
                results.append(
                    {
                        "model": model,
                        "ok": True,
                        "wall_seconds": round(elapsed, 3),
                        "output_preview": result["output"][:80],
                        "usage": result["usage"],
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "model": model,
                        "ok": False,
                        "wall_seconds": round(time.perf_counter() - started, 3),
                        "error": type(exc).__name__,
                    }
                )
        return {
            "benchmark": "local_ollama",
            "available": True,
            "results": results,
            "limitations": ["single small prompt; not coding quality or benchmark scores", "local compute/energy not measured"],
        }
    finally:
        store.close()


def bench_selfdev_mock(tmp: Path) -> dict[str, Any]:
    root = tmp / "selfdev-bench"
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run(["git", "init"], cwd=root, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "Bench"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "bench@example.invalid"], cwd=root, capture_output=True)
    (root / ".gitignore").write_text(".director/\nvar/\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "x.py").write_bytes(b"value = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True)
    store = Store.open_or_create(root, "selfdev-bench")
    try:
        from director.selfdev import create_patch, merge_patch, record_review, test_patch
        store.save_contract(build_contract(store.project_id, ("general",)))
        patch_text = (
            "diff --git a/src/x.py b/src/x.py\n"
            "--- a/src/x.py\n"
            "+++ b/src/x.py\n"
            "@@ -1 +1,2 @@\n"
            " value = 1\n"
            "+extra = 2\n"
        )
        started = time.perf_counter()
        patch = create_patch(store, patch_text, "benchmark patch")
        test_patch(
            store,
            patch["id"],
            command=[sys.executable, "-c", "from pathlib import Path; assert 'extra = 2' in Path('src/x.py').read_text()"],
        )
        record_review(store, patch["id"], "pass", "benchmark", "mock review")
        merge_patch(store, patch["id"], reason="benchmark")
        elapsed = time.perf_counter() - started
        return {
            "benchmark": "selfdev_pipeline",
            "patch_apply_test_review_merge_seconds": round(elapsed, 3),
            "status": store.get_patch(patch["id"])["status"],
            "limitations": ["mock test command and mock review; not a real model-authored change"],
        }
    finally:
        store.close()


def coverage_matrix() -> list[dict[str, str]]:
    return [
        {"tool": "DIRECTOR core", "status": "measured", "note": "domain/retrieval/MCP/selfdev benchmarks"},
        {"tool": "OpenCode", "status": "partially measured", "note": "native MCP connection + director_status tool-call tested via loopback proxy; Claude/Codex paths not"},
        {"tool": "MCP", "status": "measured", "note": "stdio protocol/latency; remote/OAuth not"},
        {"tool": "Ollama local models", "status": "measured", "note": "latency/token accounting; not coding quality"},
        {"tool": "Headroom", "status": "not run", "note": "no runtime adapter installed; research only"},
        {"tool": "Ponytail", "status": "not run", "note": "prompt/skill runtime not installed; no ablation"},
        {"tool": "Superpowers", "status": "not run", "note": "prompt/skill runtime not installed; no ablation"},
        {"tool": "ECC", "status": "not run", "note": "catalog not activated; no runtime ablation"},
        {"tool": "Cloud providers", "status": "blocked", "note": "no credentials/spend authorization"},
        {"tool": "Kernel/container sandbox", "status": "blocked", "note": "Docker daemon not running; no container test"},
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiers", default="1000000,10000000")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-retrieval", action="store_true")
    parser.add_argument("--skip-domains", action="store_true")
    parser.add_argument("--skip-mcp", action="store_true")
    parser.add_argument("--skip-selfdev", action="store_true")
    args = parser.parse_args()
    tiers = tuple(int(item) for item in args.tiers.split(",") if item.strip())
    started = time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="director-bench-"))
    payload: dict[str, Any] = {
        "schema": "director.benchmark.v1",
        "created_at": _now(),
        "director_version": __version__,
        "release_target": RELEASE_TARGET,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "results": {},
        "coverage_matrix": coverage_matrix(),
    }
    try:
        if not args.skip_domains:
            payload["results"]["domains"] = bench_domains(tmp, browser=not args.skip_browser)
        if not args.skip_retrieval:
            payload["results"]["retrieval"] = bench_retrieval(tmp, tiers)
        if not args.skip_mcp:
            payload["results"]["mcp"] = bench_mcp(tmp)
        if not args.skip_selfdev:
            payload["results"]["selfdev"] = bench_selfdev_mock(tmp)
        if not args.skip_ollama:
            payload["results"]["ollama"] = bench_ollama(tmp, ("qwen3:1.7b", "qwen2.5-coder:7b"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    payload["total_seconds"] = round(time.perf_counter() - started, 3)
    out = Path(__file__).resolve().parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out / f"director_bench_{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(json_path), "total_seconds": payload["total_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
