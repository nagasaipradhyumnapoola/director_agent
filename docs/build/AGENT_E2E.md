# Agent → orchestrator: end-to-end evidence

Date: 2026-11-24

## Deterministic path (pass)

Command:

```powershell
python benchmarks/agent_orchestrate_eval.py
```

Result:

```json
{
  "mode": "deterministic_orchestrator",
  "status": "finished",
  "passed": 2,
  "total": 2
}
```

The agent called the orchestrator for a design + clarity goal. The orchestrator
planned, routed, executed the design card (14/14 rubric) and clarity template
(10/10 rubric) and the agent finished without a model call. Artifact:
`benchmarks/results/agent_orchestrate_eval.json`.

## Real local model (partial, recorded honestly)

Command:

```powershell
python benchmarks/agent_e2e.py qwen2.5-coder:7b ollama
```

Result:

```json
{
  "model": "qwen2.5-coder:7b",
  "status": "finished",
  "steps": 4,
  "used_route": false,
  "used_recipe": true
}
```

The model used the verified `slugify` recipe (`Straße -> strasse`) and finished,
but it repeated the recipe and did not call `route` for the design half. The
agent now ignores repeated identical calls and nudges the model to finish; the
transcript is in `benchmarks/results/agent_e2e.json`.

**Conclusion:** the protocol is proven end-to-end with deterministic planning and
with a scripted model; a 7B local model is not yet a reliable autonomous router.
The orchestrator itself is 7/7, so the product can route deterministically where a
recipe exists and delegate open-ended work to the agent/model.

## Reproduction

```powershell
$env:PYTHONPATH="src"
python benchmarks/orchestrate_eval.py
python benchmarks/agent_orchestrate_eval.py
python benchmarks/agent_e2e.py qwen2.5-coder:7b ollama
```
