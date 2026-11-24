"""Resumable large-scale lexical retrieval benchmark.

The regular benchmark builds a whole tier in one process. On a memory-constrained
host that can hit a process limit near 100M tokens. This helper ingests a bounded
number of documents per invocation into a persistent store, so the same tier can
be completed across several short processes and then queried once.

Usage:
    python benchmarks/retrieval_scale.py --tokens 100000000 --docs-per-run 10000 \
        --workdir benchmarks/results/scale-100m
    # repeat until it prints "complete": true, then read the final report
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from director.memory import MemoryIndex
from director.store import Store

DOC_CHARS = 4000
FILLER = "controlled synthetic supervision corpus token "


def _count(store: Store) -> int:
    row = store.conn.execute(
        "SELECT COUNT(*) AS n FROM memory_sources WHERE project_id=? AND kind='synthetic'",
        (store.project_id,),
    ).fetchone()
    return int(row["n"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", type=int, required=True)
    parser.add_argument("--docs-per-run", type=int, default=10000)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()

    target_chars = args.tokens * 4
    count = max(1, target_chars // DOC_CHARS)
    root = Path(args.workdir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = Store.open_or_create(root, f"retrieval-{args.tokens}")
    try:
        index = MemoryIndex(store)
        done = _count(store)
        started = time.perf_counter()
        before = done
        stop = min(count, done + max(1, args.docs_per_run))
        for i in range(done, stop):
            marker = f"marker{args.tokens}_{i:07d}"
            body = (
                f"Document {i}. Unique marker {marker}. "
                + (FILLER * (DOC_CHARS // max(1, len(FILLER))))
            )[:DOC_CHARS]
            index.add_text(body, f"doc{args.tokens}-{i:07d}", kind="synthetic")
        elapsed = time.perf_counter() - started
        done = _count(store)
        complete = done >= count
        report: dict[str, object] = {
            "tokens": args.tokens,
            "docs_target": count,
            "docs_done": done,
            "complete": complete,
            "this_run_docs": stop - before,
            "this_run_seconds": round(elapsed, 3),
            "db_bytes": sum(p.stat().st_size for p in (root / ".director").glob("director.db*")),
        }
        if complete:
            rng = random.Random(99 + args.tokens)
            sample = rng.sample(range(count), min(args.queries, count))
            latencies = []
            hits = 0
            for i in sample:
                marker = f"marker{args.tokens}_{i:07d}"
                t0 = time.perf_counter()
                rows = index.search(marker, limit=5)
                latencies.append((time.perf_counter() - t0) * 1000)
                if any(marker in (row.get("text") or "") for row in rows):
                    hits += 1
            latencies.sort()
            report.update(
                {
                    "recall_at_5": hits / len(sample),
                    "p50_ms": round(latencies[len(latencies) // 2], 3),
                    "p95_ms": round(latencies[int(len(latencies) * 0.95) - 1], 3),
                    "max_ms": round(max(latencies), 3),
                    "queries": len(sample),
                }
            )
            out = Path("benchmarks/results") / f"retrieval_{args.tokens}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
