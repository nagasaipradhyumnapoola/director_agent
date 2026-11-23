# Benchmarks

These are small, reproducible smoke measurements, not product claims.

- `retrieval_smoke.py` — synthetic lexical FTS5 ingestion/search latency. It is
  not semantic memory, temporal/update/ACL evaluation, or billion-token scale.
- The controlled pilot demo (`python -m director demo`) is the domain
  discrimination benchmark: clean fixtures must pass, seeded broken fixtures
  must fail, with zero model calls.

Run:

```powershell
$env:PYTHONPATH="src"; python benchmarks/retrieval_smoke.py
```

Raw results are written under `benchmarks/results/`.
