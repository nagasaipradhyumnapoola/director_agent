# DIRECTOR architecture

## One accountable core, thin hosts

DIRECTOR is a standalone local service plus thin interfaces. It owns intent,
permission, budget, durable state, context selection, evidence and completion.
Hosts (OpenCode, Claude, Codex, custom agents) connect over local MCP; host
adapter files are convenience examples, not the product core.

```
contracts + acceptance
        |
events -> fenced queue -> deterministic checks -> optional scoped workers
        |                         |
        |                         v
policy/effect gateway      evidence receipts (state-bound)
        |                         |
budget ledger --------------------+
        |                         |
        v                         v
context packet / memory    acceptance decision
        |
MCP stdio / CLI / 24/7 worker
```

## Modules

| Path | Responsibility |
|---|---|
| `security.py` | path/link/junction/hardlink rejection, bounded JSON, redaction, atomic writes |
| `models.py` | typed `TaskContract`, requirements, criteria, budgets, permissions |
| `store.py` | SQLite schema v3, repository, fenced queue, budgets, memory, grants, proposals |
| `policy.py` | default-deny capability gateway and owner grants |
| `evidence.py` | receipts, freshness verification, criterion acceptance |
| `context.py` | bounded context packet with untrusted-content labels |
| `memory.py` | safe file/text ingestion with provenance, taint, deletion |
| `analysis.py` | deterministic scanner + recomputable tree snapshot |
| `runner.py` | temp workspace, scrubbed env, output/time caps, process-tree kill, Windows job object |
| `lifecycle.py` | detached worker, heartbeat, pause/resume/stop, recovery |
| `improve.py` | deterministic self-improvement proposals (proposal-only) |
| `mcp_server.py` | bounded newline JSON-RPC 2.0 stdio MCP server |
| `adapter.py` / `opencode_adapter.py` | generated host configs, never auto-enabled |
| `domains/` | pilot profiles and evaluators |

## Durable entities (SQLite)

projects, goals, task_contracts, requirements, criteria, artifacts, events,
investigations, findings, evidence, grants, approvals, budgets,
budget_reservations, memory_sources/chunks/facts, graph_edges, notifications,
checkpoints, waivers, proposals.

Schema migrations are additive (`user_version` 1 → 2 → 3). WAL mode, foreign
keys, `busy_timeout`, `trusted_schema=OFF`.

## Queue and fencing

- Claiming increments a generation and sets a unique lease token + expiry.
- Publishing/completion requires the same token and generation and a live lease.
- Expired leases are reclaimed; if attempts reached the cap, the investigation
  becomes `failed` (crash retries count).
- A single transaction can publish evidence + findings + completion.
- Retry caps apply to crashes (lease expiry) as well as explicit failures.

## Evidence and acceptance

Each receipt records subject path/SHA-256, check name/version, params,
environment, collector, outcome, confidence, limitations, raw reference, task
revision, policy hash and time. Verification recomputes the subject hash (or the
whole scanned tree for `artifact_scan`) and checks policy/revision/expiry.

**Latest evidence per criterion wins, regardless of outcome.** A newer fail or
block supersedes an older pass. Completion requires every mandatory criterion to
have a fresh pass or an owner waiver bound to the current contract revision/hash.

## Policy and budgets

- Actions are denied unless the contract enables them **and** an unexpired owner
  grant matches actor, action, resource prefix, revision and optional payload
  hash.
- An active deny overrides allows; invalid/expired grants are inactive.
- Pilots are granted only by owner-side `provision_pilot_grants` (CLI/demo).
  Evaluators cannot mint grants; they enforce grant timeout limits when run.
- Budgets reserve atomically under `BEGIN IMMEDIATE`; settle/release update
  reserved/spent. Model calls and cloud spend default to zero.

## Context and memory

Source blobs are stored separately from chunks/indexes. FTS5 is the lexical
baseline. Retrieved text is labeled `untrusted-data`; it cannot become
instructions or authority. The packet is bounded, reports truncation, and states
that host headroom is unknown. Memory deletion removes chunks and FTS rows and
supports safe re-ingestion.

## Pilots

- **Website:** static HTML/CSS checks plus a real headless Chromium CDP probe
  (search → add → checkout, Tab/Enter keyboard, 390/1280 overflow, console
  errors, network requests, AX tree, screenshots). Missing browser = blocked.
- **ML:** manifest/provenance, duplicate/target-derived leakage, baseline vs
  held-out accuracy using trusted thresholds, two-run determinism, slices and
  resource report. Trainer runs `-I -P` with a trusted absolute script.
- **Research/document:** dated sources, verbatim quotes, supersession/conflict
  handling, trusted-tolerance calculation, required current-source citations,
  rendered HTML and optional DOCX inspection.

## Enforcement boundary

DIRECTOR enforces its own mediated actions (scanner, queue, runner, budgets,
grants). An external host keeps its own permissions and may bypass DIRECTOR.
MCP tools are advisory/read-mostly plus local enqueue; they cannot grant
permission, spend money or apply code. Process-level containment is not a kernel
sandbox.

## 24/7 improvement

`director start` runs a detached deterministic worker: scans, proposal
generation, heartbeat, recovery, zero model calls. Proposals are durable and
owner-approved only. Autonomous code application is explicitly blocked in v0.1
(see `docs/SELF_IMPROVEMENT.md`).
