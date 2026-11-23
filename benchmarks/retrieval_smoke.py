"""Synthetic lexical memory smoke benchmark.

This is a smoke test of FTS5 plumbing and latency, not semantic memory,
domain-general retrieval, or billion-scale evidence.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import tempfile
import time
from pathlib import Path

from director.memory import MemoryIndex
from director.store import Store


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=500)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--out", default="benchmarks/results/retrieval_smoke.json")
    args = parser.parse_args()

    rng = random.Random(20261123)
    words = [f"term{i:04d}" for i in range(args.files)]
    root = Path(tempfile.mkdtemp(prefix="director-bench-"))
    store = Store.open_or_create(root, "retrieval-smoke")
    index = MemoryIndex(store)
    ingest_started = time.perf_counter()
    expected: dict[str, int] = {}
    source_ids: list[str] = []
    for i, word in enumerate(words):
        text = (
            f"Document {i}. The unique marker is {word}. "
            "This controlled synthetic text exists only to exercise lexical indexing. "
        ) * 8
        source_id = index.add_text(text, f"doc-{i}", kind="synthetic")
        source_ids.append(source_id)
        expected[word] = i
    ingest_seconds = time.perf_counter() - ingest_started

    query_words = rng.sample(words, min(args.queries, len(words)))
    latencies: list[float] = []
    hits = 0
    for word in query_words:
        started = time.perf_counter()
        results = index.search(word, limit=1)
        latencies.append((time.perf_counter() - started) * 1000)
        if results and f"doc-{expected[word]}" in results[0]["title"]:
            hits += 1
    latencies.sort()

    def pct(p: float) -> float:
        index_at = min(len(latencies) - 1, int(len(latencies) * p / 100))
        return round(latencies[index_at], 3)

    db_bytes = store.path.stat().st_size
    wal = store.path.with_name(store.path.name + "-wal")
    if wal.exists():
        db_bytes += wal.stat().st_size
    result = {
        "kind": "synthetic lexical FTS5 smoke; not semantic or billion-scale",
        "date": "2026-11-23",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "files": args.files,
        "queries": len(query_words),
        "source_bytes": sum(len(w) * 8 * 3 for w in words),
        "database_bytes": db_bytes,
        "ingest_seconds": round(ingest_seconds, 4),
        "recall_at_1": round(hits / len(query_words), 4) if query_words else 0.0,
        "p50_search_ms": pct(50),
        "p95_search_ms": pct(95),
        "max_packet_byte_upper_bound": None,
        "model_calls": 0,
        "limitations": [
            "exact synthetic marker queries only",
            "no temporal/update/deletion/ACL/contradiction evaluation",
            "not evidence of semantic retrieval or billion-token capacity",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    store.close()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
