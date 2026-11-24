# Changelog

## Unreleased — UI, autonomy and skill matrix

- Landing page, loopback control room and Diro/The Conductor character.
- `director ui` preview server (loopback, no directory listing).
- `director autonomy` continuous supervised self-improvement scheduler.
- `benchmarks/skill_matrix.py` prompt-level skill ablation with a JSON/Markdown
  report and a dashboard view.

## v1.0.0-local-supervised — 2026-11-24

Local, single-user, supervised project supervisor.

### Added

- Durable contracts, SQLite schema v4, fenced queue, budgets, policy gateway,
  evidence freshness/acceptance, bounded context and lexical memory.
- Deterministic artifact scanner with link/hardlink/junction/secret/bounds
  controls and unsupported-format honesty.
- Website pilot (real Chromium/CDP journey, keyboard, mobile, console, network,
  accessibility), ML pilot (manifest/leakage/held-out/reproducibility/slices),
  research/document pilot (sources/claims/conflicts/calculation/render).
- Bounded MCP stdio server + generic/OpenCode/Claude/Codex adapter generation.
- Supervised selfdev pipeline: patch allowlist → isolated git worktree → full
  tests → independent review → owner merge, no auto-push.
- Local Ollama provider, stub/command providers, OpenAI-compatible provider with
  OS-keychain credentials and token/cost accounting; owner grants and budgets.
- 24/7 deterministic worker, queued patch testing, proposal engine, autostart
  (per-user Startup folder).
- Verified ZIP backups/restore/prune, health/doctor, redacted audit log.
- Opt-in scheduled maintenance: worker-created verified backups + pruning.
- Bounded Docker runner: read-only mount, no network, uid 65534, cap-drop ALL,
  resource limits; integration tested on Docker 29.6.2.
- Benchmarks: domain detection, 1M/10M/100M lexical retrieval, MCP, local
  models, selfdev, upstream skill-prompt ablation.
- Production Docker image (`director:local`) with CI build/init/status job.

### Security

- Default deny; no cloud spend/network by default; secrets in OS keychain;
  bounded frames/arguments/output; path/link protection; redaction.
- Process-level containment by default; the optional Docker runner is bounded
  but not a hardened microVM.

### Known limitations

- Controlled fixtures only; no general domain certification.
- Native OpenCode connection + tool-call verified through a loopback
  OpenAI-compatible proxy; Claude/Codex native paths untested.
- No real cloud provider credential/spend was authorized; the cloud path is
  tested against a loopback OpenAI-compatible proxy/mock.
- 1B retrieval is a measured scaling limit, not a completed result; Headroom
  runtime, upstream runtimes/hooks, A2A, computer-use beyond the browser pilot,
  and multi-user auth are not shipped.
