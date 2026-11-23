# Known limitations (v1.0.0-local-supervised)

## Scope

- Controlled fixtures only: three pilots prove the shared evaluator contract and
  discrimination on seeded defects, not general domain competence.
- No live web freshness or external source verification. Local/Ollama and
  mock OpenAI-compatible routing exist; no real cloud call/key/spend, no
  autonomous provider loop, no A2A or computer-use.
- Windows 11 + Python 3.14 is the validated platform. POSIX paths exist but were
  not exercised end-to-end.

## Isolation

- Process-level supervision only: temp workspace, scrubbed env, output/time caps,
  process-tree kill, Windows job object. **Not a kernel/container sandbox.**
- ML trainer runs `-I -P` with a trusted absolute script, so fixture stdlib
  shadowing is blocked, but a fixture still runs with user privileges.
- Browser probe uses a disposable profile and disabled DNS, but is not a general
  browser-hardening claim.
- Do not run untrusted repositories, training code, notebook cells or document
  macros under this release.

## Detection quality

- Secret detection is pattern-based; a zero-finding scan is not a security audit.
- ML leakage detection is heuristic: duplicate rows, duplicate ids and
  target-derived/high-correlation features. Subtle proxies can evade it.
- Slice checks skip groups below 20 test rows (`low_support`); an evaluator can
  avoid the slice bar by producing only small groups.
- Static website checks are not a full HTML validator; visual taste and screen
  reader interoperability need human review.
- Research render inspection is structural; it is not editorial review and does
  not prove a source is correct.

## Evidence lifecycle

- A newer failing/blocked result supersedes an older pass; acceptance uses the
  latest criterion evidence.
- Scan verification re-walks/re-hashes the tree (cached only within one verify
  pass). Large trees make `verify` expensive.
- A pre-evaluator block (e.g., budget exhausted) records blocked evidence but may
  leave older fresh passes; acceptance is per-criterion latest evidence, not a
  whole-project immutability proof.
- Waiver validity is bound to contract revision/hash; changing the contract
  requires a new waiver.

## Host and integration

- OpenCode native tool-call is blocked on installed V1.19.4 (config connects,
  run agent exposes no MCP tools to the local model); Claude/Codex native paths
  are not tested. Only connection and MCP protocol/SDK are claimed.
- Autostart is a per-user Startup-folder entry, not a Windows service; it needs
  an active user logon.
- Local model authoring can produce correct-but-dead code; review may hold it.
- External agents can bypass DIRECTOR; enforcement covers only mediated actions.
- 24/7 means while the host and worker run. Sleep/shutdown/budget exhaustion stop
  work; a new context window does not replenish budget.

## Self-improvement

- The 24/7 worker is proposal-only; it cannot write code, spend, merge, push or
  deploy. `improve apply` is blocked.
- `selfdev` executes an agent/human-authored patch in an isolated git worktree
  with full tests, an independent review record and owner merge. It is not a
  kernel sandbox and does not author patches by itself.
- It requires a clean working tree, an unchanged base commit and local git; it
  never pushes/deploys.
- Provider-driven autonomous authoring exists for local Ollama; real cloud
  authoring and broader sandboxing remain gated (see `docs/SELF_IMPROVEMENT.md`).

## Memory

- Lexical FTS5 baseline only; no measured semantic/dense retrieval, no
  billion-token scale, no temporal graph evaluation.
- Memory is project-scoped and tainted; retrieved text never grants authority,
  but it can still influence model reasoning.

## Operational

- Single-user local design; no authenticated multi-tenant service.
- No production security audit or third-party certification.
- Generated adapter files must be reviewed and merged into project-scoped host
  configuration; enabling them is the owner's action.
