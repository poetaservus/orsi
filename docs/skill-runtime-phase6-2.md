# Phase 6.2: frozen extension boundaries

This document records the existing Skill Runtime v1 boundary. It adds no manager,
loader, adapter, protocol, permission path or runtime API. The application
architecture and accepted model configuration remain unchanged.
The interfaces were checked against integration revision `9aba6a7` on
3 October 2026.

## Definitions and authority

| Extension | Role | Current O.R.S.I. implementation |
| --- | --- | --- |
| Skill | Instructions/context that can influence model behavior. | `app/runtime/skills/`; validated `SKILL.md`, discovery, installation, selection and prompt rendering. |
| Tool | Callable capability with a schema and controlled execution. | `Capability`, `CapabilityRegistry`, agent runtime, permission gate and journaled executor. |
| MCP | External tool/resource protocol. | No MCP client or server-registration path is implemented here. |
| Plugin | Package that may group skills, tools, MCP definitions, hooks, configuration and metadata. | No plugin package loader or lifecycle is implemented here. |
| Hook | Code invoked at a defined lifecycle point. | Skill metadata cannot register or execute hooks; a plugin-hook API is not implemented. |

A skill is never a tool registration or a permission grant. Naming an operation
in Markdown, describing a server in YAML, or shipping an executable next to
`SKILL.md` creates no callable operation, network connection, hook or approval.
The current installer copies only `SKILL.md`; scripts, assets, references, plugin
manifests and dependency installers are not imported or executed.

Core/security restrictions remain binding. User instructions take precedence over
applicable project instructions, which take precedence over active skill guidance
and model defaults. The model may use skill guidance to decide which **existing**
tool to request. Application code still validates, authorizes, approves when
required, journals and executes every concrete call. Skill selection never
changes the enabled catalog, schemas, model settings or permission rules.

## Existing flow and ownership

```text
SKILL.md -> parser / safe loader -> SkillRegistry
                                      |
                    explicit activation or metadata-only selector
                                      |
                         conversation prompt construction
                                      |
                        existing inference / agent runtime
                                      |
              existing CapabilityRegistry -> permission / approval
                                      |
                         journaled executor -> tool adapter
```

`app/startup.py` composes a discovered registry into `ConversationService`.
The normal application discovers the global scope; a project scope must be
explicitly supplied. The skill registry owns instruction snapshots. The separate
capability registry owns validated callable definitions. Neither registry merges
the other registry's contents or interprets its metadata.

The selector sees only skill names/descriptions and the current request. It
returns one validated name or no match; it does not receive instruction bodies,
tool definitions or conversation history. The conversation service loads the
selected snapshot and injects one escaped, labelled JSON section through the
existing context-admission path. No skill-specific code enters provider adapters.
Without an active skill, the original core prompt is returned unchanged.

Explicit selection lasts for the session until changed/cleared. Automatic
selection is scoped to the current turn. A new session clears both. Ordinary
conversation and tool calls retain their existing validation and execution path.

## V1 interfaces to preserve

The public skill exports are in
[`app/runtime/skills/__init__.py`](../app/runtime/skills/__init__.py).
The following are the current contracts, not a newly invented plugin API:

| Interface | Contract |
| --- | --- |
| `SkillDefinition` | `name`, `description`, exact `instructions`, `root_path`, `source_path`, and inert optional `metadata`. A frozen data definition, with no execution methods. |
| `parse_skill(...)` | Parses supplied Markdown/frontmatter into a definition without reading files, starting inference or activating anything. Stable structured parse errors contain no content excerpts. |
| `load_skill(...)` | Loads one bounded UTF-8 regular file within an explicitly supplied root, using the existing safe Windows read policy. |
| `discover_skills(...)` | Returns effective definitions and structured issues from approved scopes. Same-scope ambiguity is rejected; valid project definitions take precedence over global definitions. |
| `SkillRegistry` | `discover`, `reload`, `get`, `list`, and detached `report` snapshots. Construction does not scan; cached reads perform no filesystem access. Roots/limits are read-only and scopes are explicit. |
| `SkillCandidate` / `SkillSelection` | Metadata-only selection input and validated decision/usage output. Unknown, malformed, incomplete or unavailable router output falls back without executing content. |
| `with_active_skill(core_prompt, skill)` | Preserves the core prompt; appends exactly one lower-priority section for a definition. `None` returns the unchanged core prompt. Metadata and paths are not injected. |
| `ConversationService` | Accepts an optional `SkillRegistry` and automatic-selection flag; exposes `activate_skill`, `deactivate_skill`, `active_skill`, and `skill_selection`. `/skill <exact-name>` activates; `/skill` clears. |
| `SkillInstaller` | Global-only local installation, list/info/removal. Complete validation precedes publication. Identical bytes are idempotent; changed content requires explicit removal before reinstalling. Project overrides are read-only to this installer. |
| `GitSkillInstaller` | Bounded public HTTPS repository inspection, followed by the same local transaction. Reports the inspected revision; no checkout, credentials, repository hooks, dependencies or package code run. |

The platform/file-safety and selector limits remain part of these interfaces.
No adapter may bypass them through manual registry mutation or private installer
helpers. Optional metadata is preserved as data, not a configuration channel.
Parser acceptance does not certify that a skill's proposed workflow is supported.

Content-free observability is documented in the
[Phase 6.1 report](skill-runtime-phase6-1.md). Hashes identify instruction
snapshots; diagnostic token estimates do not alter admission or require extra
inference. Persistent skill configuration overrides remain deferred under the
[Phase 5.2 decision](skill-runtime-phase5-2.md).

## Future compatibility boundary

A future package adapter can identify supported `SKILL.md` entries in a package
and hand them to the existing validated installation/discovery path. The shared
skill model and prompt renderer contain no TasteSkill, Claude or provider-specific
execution contract. Provider selection remains a separate inference concern.

If that future package also declares tools, MCP servers, hooks, commands or
configuration, those entries need separately designed, validated and authorized
interfaces. They cannot be smuggled through `SkillDefinition.metadata`, Markdown,
the skill selector or a `SKILL.md` import. An adapter must report unsupported
components rather than silently claiming complete package compatibility.

The roadmap's eventual Capability Manager and compatibility adapters are future
concepts. This checkpoint does not add their classes, manifest formats, transport,
hook execution, command dispatch, credential handling or Claude compatibility.
The existing agent bootstrap and registries remain the production composition.
Future changes must preserve the distinction between instruction import and
executable authority, with their own tests and authorization boundaries.

## Final regression and check-in

This checkpoint changes only this report, `ARCHITECTURE.md` and `README.md`.
Manual source inspection confirmed the separate registries, inert metadata,
provider-independent definitions, safe installation and unchanged permission path.
The overview documents now acknowledge the implemented skill runtime and the
existing full enabled tool catalog; these corrections do not change runtime code.

Verification covers parser/loader, discovery/registry, routing, prompt construction,
security/permissions, local/Git installers, pinned third-party compatibility,
observability, existing tool calls, conversation/context and provider/model checks.
The relevant existing checks passed **716 tests, with two host-dependent symlink
checks skipped**, in 44.35 seconds. The final full suite passed **1,410 tests and
15 subtests, with 58 skipped**, in 194.64 seconds. The existing full-suite skips
are seven host-dependent symbolic-link checks and 51 opt-in live-model, cloud or
UI gates; none is counted as a pass. The launcher command `ORSI.cmd skill --help` succeeded without
starting inference or changing installed skills. Local documentation links,
dependency consistency and authored-file whitespace checks passed.

Reproduction uses a native Windows shell and repository-local temporary files:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_parser.py tests/test_skill_loader.py tests/test_skill_discovery.py tests/test_skill_registry.py tests/test_skill_selection.py tests/test_skill_activation.py tests/test_skill_diagnostics.py tests/test_skill_installer.py tests/test_skill_git_installer.py tests/test_skill_git_process.py tests/test_tasteskill_compatibility.py tests/test_simple_skill_compatibility.py tests/test_tasteskill_configuration_validation.py tests/test_capability_registry.py tests/test_capability_executor.py tests/test_permissions.py tests/test_host_access_policy.py tests/test_agent_runtime.py tests/test_conversation.py tests/test_context_budget.py tests/test_context_recovery.py tests/test_inference_protocol.py tests/test_cloud_inference.py tests/test_provider_response_recovery.py tests/test_local_models.py tests/test_model_baseline.py tests/test_default_14b_context.py -p no:cacheprovider --basetemp .pytest-tmp-phase6-2-focused --junitxml=state/test-artifacts/skill-phase6-2/focused.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-phase6-2-full --junitxml=state/test-artifacts/skill-phase6-2/full.xml
```

Ignored `state/test-artifacts/skill-phase6-2/` holds the test reports. No new tests
were added for this documentation-only change; the existing contracts/security
tests exercise the boundaries being frozen.

No new live-model, cloud or third-party skill test is run in this step. The
smaller-skill manual acceptance test is the user's next activity. Completing the
roadmap implementation does not relabel earlier live qualification results or
skipped gates as passes.

Phase 6.2 and its required deterministic final regression are complete. The next
check is the user's smaller open-source skill acceptance test; no later extension
work has been started.
