# OpenCode handoff and verified host notes

> **Build update (2026-11-23):** the build ran in OpenCode and produced the
> v0.1 release. See [BUILD_STATUS.md](BUILD_STATUS.md), [../CONTEXT.md](../CONTEXT.md)
> and [HARNESS_INTEGRATION.md](HARNESS_INTEGRATION.md).

Prepared **2026-11-23** for `D:\directer agent`.

## Start the future build

OpenCode is installed. Local read-only checks returned **1.19.4** from both the CLI and installed package metadata. Its help supports a project path, `--agent`, `--prompt`, model selection and the listed debug/MCP commands. No model session, provider request, plugin install or upgrade was launched during this preparation.

Run:

```powershell
opencode "D:\directer agent"
```

Then paste:

> Read AGENTS.md and OPENCODE_BUILD_PROMPT.md in this project. Follow the complete prompt, refresh only relevant changed research, and build the v0.1-supervised-three-domain release end to end. Keep the research evidence, use bounded resources and verify every mandatory criterion. Begin with the actual workspace/runtime check and concise execution plan, then proceed with the authorized local build. Do not push or publish.

The full standalone prompt is at the project root. `docs/MASTER_BUILD_PROMPT.md` remains the generic version. Initial preparation created no runtime plugins, providers, permissive global settings or application source files.

## What was verified in current official documentation

These are dated documentation observations, not proof every capability is enabled in this installation. Detect the active runtime/schema instead of inferring it solely from the binary's major number.

| Surface | Observation | Builder consequence |
|---|---|---|
| Project instructions | AGENTS.md provides persistent project guidance; instruction sources combine and can be discovered as the project is explored. [Instructions](https://opencode.ai/docs/instructions/) | Keep bootstrap short. Load full task/research documents on demand, not through a giant instructions glob. |
| Agents | Current docs distinguish primary/subagent modes, built-in roles and child permissions/context. [Agents](https://opencode.ai/docs/agents/) | Use the actual available roles; one controller, scoped children and independent review where useful. |
| Permissions | Current V2 docs use ordered action/resource/effect rules; later matching rules win. [Permissions](https://opencode.ai/docs/permissions/) | Verify the active format before generating rules; a broad late allow can undo an earlier restriction. |
| Skills | The skill tool loads a selected body and permission-checks its ID; support files are read separately. [Skills](https://opencode.ai/docs/skills/) | Select by relevance, load progressively, avoid duplicate canonical/host variants. |
| Plugins | Local discovery and configured plugin-directory loading differ; dependencies/updates may execute outside an agent tool call. [Plugins](https://opencode.ai/docs/plugins/) | Do not auto-install upstream bundles. Inspect, pin and explicitly enable a reviewed adapter. |
| MCP | Current docs distinguish server configuration, local commands, protocol selection and connection behavior. [MCP](https://opencode.ai/docs/mcp-servers/) | Use a tested local stdio boundary first. Verify actual host/server protocol pairing and keep external services opt-in. |
| Compaction | Current docs describe context buffers, retained recent context and background summaries with additional token cost. [Compaction](https://opencode.ai/docs/compaction/) | Persist a recovery ledger independently; measure summary cost/fidelity and leave output/tool headroom. |
| Configuration migration | Current migration guide documents interface/configuration changes. [Migration](https://opencode.ai/docs/migrate-v1/), [configuration](https://opencode.ai/docs/config/) | No blind copying between old examples and current docs; feature-detect and validate before changes. |
| CLI | Official CLI docs support starting in a selected project. [CLI](https://opencode.ai/docs/cli/) | The startup command above is also confirmed by the installed CLI help. |

## Execution boundaries and efficiency

1. The build agent's current configured provider is distinct from DIRECTOR's future background model calls. Building in OpenCode does not grant DIRECTOR unlimited autonomous API spend.
2. Preserve user/global settings. Never dump resolved provider configuration or inherited environments into logs or model-visible reports. Inspect only safe capability fields when necessary.
3. Avoid automatically enabling OpenCode's broad auto-approval flag. Configure narrow permissions compatible with the active runtime and keep action-bound approval for consequential effects.
4. CLI flags and project instruction files do not create a sandbox. Domain pilots need the isolated execution/evidence boundary specified in the blueprint.
5. Do not use Claude's hooks.json as an OpenCode plugin implementation. Inspect OpenCode's actual supported plugin events/API and test it against the installed host.
6. A configured plugin, generated adapter, SDK round trip, native OpenCode tool call and successful domain outcome are separate evidence levels.
7. The original upstream research is pinned and complete at its stated inventory depth. Refresh changes and semantically trace selected executable components; do not repeat the entire unchanged inventory exercise.

No claim is made that the local OpenCode installation has been upgraded, reconfigured, connected to DIRECTOR or proven against the proposed application. This is a prepared handoff for the future build.

