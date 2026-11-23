# Benchmarks

These are small, reproducible local measurements, not product claims.

- `run_benchmarks.py` — domain discrimination, 1M/10M lexical retrieval, MCP
  latency, local Ollama latency/accounting, selfdev pipeline.
- `prompt_ablation.py` — baseline vs pinned Ponytail/Superpowers/ECC/Headroom
  **skill instructions** with one local model and one task. Runtimes are not
  executed.
- `retrieval_smoke.py` — small synthetic FTS5 smoke.

Full methodology, results and limitations: `docs/build/BENCHMARKS.md`.

Run:

```powershell
$env:PYTHONPATH="src"; python benchmarks/retrieval_smoke.py
```

Raw results are written under `benchmarks/results/`.
