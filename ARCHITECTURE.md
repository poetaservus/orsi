# O.R.S.I architecture

## 1. System overview

O.R.S.I is a local-first Windows desktop assistant. The Qt GUI submits a message to the
conversation orchestrator. The orchestrator builds bounded context and asks the agent runtime for
ordinary assistant text or normalized provider-native capability calls. A capability call is schema
validated, authorized by deterministic policy, optionally approved in the GUI, executed through the
journaled executor, and returned to the model as structured data.

The enforced direction is:

```text
GUI -> conversation orchestration -> agent loop -> LLM + capability catalog
                                               -> permission gate -> journaled executor
                                                                  -> OS adapter/tool
```

The GUI never performs filesystem or process actions. The LLM can request an action, but it cannot
authorize or execute one. Capability implementations cannot bypass the permission gate when invoked
through the production runtime.

## 2. Directory structure

```text
app/
  main.py                 minimal Qt entry point
  startup.py              application composition and backend selection
  agent/
    bootstrap.py          composes catalog, policy, journal, executor, and loop
    contracts.py          bounded agent result and limit models
    feedback.py           protocol-recovery and text-fallback messages
    file_resolution.py    bounded same-folder filename disambiguation
    read_progress.py      renews text-read allowances after settled file changes
    runtime.py            sequential model/tool continuation loop
  capabilities/
    catalog.py            single production registration path
    contracts.py          tool interface, context, results, and error categories
    registry.py           immutable validated capability registry
    filesystem_*.py       built-in filesystem tools
    application_launch.py allowlisted application launch tool
  conversation/
    orchestrator.py       session/turn orchestration
    context.py            context selection and token estimates
    prompt.py             system prompts derived from active capabilities
    result_grounding.py   grounds exact text-read responses
    store.py              conversation persistence
  inference/
    engine.py             provider-neutral inference interface
    contracts.py          provider-neutral tool definitions
    protocol.py           native tool-call normalization and validation
    tool_repair.py        constrained repair for text-only providers
    llama_*.py            local backends
    cloud_backend.py      OpenAI-compatible cloud backend
    openai_backend.py     OpenAI SDK Responses adapter
    openai_tools.py       strict tool schemas, exact call IDs and validated results
    hybrid.py             local/cloud selection and lazy initialization
  security/
    host_access.py        acknowledged read scope and drive allowlisting
    path_policy.py        canonical read-path resolution
    write_policy.py       protected-path and write-target rules
    permissions.py        permission decisions and single-use approvals
    default_permissions.py built-in deterministic policy construction
  execution/
    executor.py           bounded capability execution
    audit.py              crash journal and lifecycle persistence
    windows_filesystem.py Windows handle-pinning/native filesystem helpers
  settings/               validated feature, model, cloud, and path settings
  infrastructure/        application logging
  state/                  atomic generic JSON storage
  runtime/                cancellation primitives
    skills/               instruction parsing, discovery, registry, installation and selection
  ui/                     Qt presentation, worker, approvals, and widgets
config/                   non-secret checked-in runtime configuration
docs/                     status, roadmap, design history, and threat reviews
packaging/                portable-runtime and distribution build scripts
tests/                    unit, integration, security, and off-screen GUI tests
```

`runtime/`, `models/`, and `state/` at the repository root are runtime assets/data rather than
Python packages. Historical threat reviews remain under `docs/`; they document security decisions
and are not alternate implementations.

## 3. Agent execution lifecycle

1. `MainWindow` starts a `ConversationWorker`; the worker calls `ConversationService.run`.
2. `ConversationService` stores the user turn, selects bounded context, and builds the appropriate
   system prompt.
3. If the capability agent is unavailable, one bounded text-only model step runs. Otherwise the
   full visible catalog is supplied to `AgentRuntime`.
4. `AgentRuntime` accepts assistant text alongside complete normalized native capability calls.
   Multiple calls, including different capabilities, settle sequentially with independent approvals.
   Invalid, repeated, oversized, or excessive calls stop or receive bounded feedback. Consecutive
   format failures, cumulative semantic corrections and total model requests have separate limits.
5. The registry validates the capability name and Pydantic argument schema.
6. The permission gate evaluates canonical resources. Read rules may allow directly; writes and
   application launch require a pending, exact, expiring approval record.
7. The GUI presents only trusted approval data and resolves the approval. It does not decide policy.
8. The journaled executor records intent and authorization, executes once, records the result, and
   returns structured output to the model.
   Settled text edits/writes that prove a content change renew only that file's text-read repetition
   allowances; unchanged/failed operations and duplicate batches retain the guard. See
   [read progress verification](docs/version-aware-read-guard.md).
9. The loop continues until final assistant text or a bounded terminal status. The orchestrator
   durably stores the terminal turn outcome, visible response and every settled call in the active session.

## 4. LLM abstraction

`app/inference/engine.py` defines the common interface. Local llama.cpp, loopback llama-server, and
OpenAI-compatible cloud adapters implement it. `hybrid.py` selects the active provider without
exposing provider details to the conversation layer.

`protocol.py` converts provider responses into `ModelResponse` objects and validates native tool
calls. `tool_repair.py` provides a strict JSON fallback only when a provider cannot emit native
calls. Model-specific envelope handling stays in the inference package.

Add a provider by implementing `InferenceEngine`, keeping credentials out of configuration, adding
adapter tests, and wiring the provider into startup/hybrid selection.

## 5. Tool registration and execution

Every tool implements `Capability` and declares a stable `namespace.name`, description, strict
Pydantic arguments model, permission class, timeout and execution isolation. Legacy batch metadata
is retained for catalog compatibility; it no longer rejects normal multi-call provider responses. The
single production catalog is `app/capabilities/catalog.py`; the immutable validator and lookup API
are in `app/capabilities/registry.py`.

To add a tool:

1. Implement it beside the related built-ins and return a bounded `CapabilityResult` payload.
2. Add one feature flag if it is optional.
3. Register it in `catalog.py`.
4. Add an explicit rule in `security/default_permissions.py`; fail closed when no rule applies.
5. Add contract, denial, approval (if applicable), execution, cancellation, and integration tests.

Execution flows only through `JournaledCapabilityExecutor` and `CapabilityExecutor`. Windows-native
filesystem primitives live in `execution/windows_filesystem.py`, separate from schemas and policy.

## 6. Permission model

Read scope is either the portable application root or explicitly acknowledged local drives. UNC,
device, and unsupported drive paths are rejected. Write policy separately blocks application/state,
AppData, operating-system, recovery, installed-application, redirected, reparse, and ambiguous paths.

Write and execute permissions use exact single-use approvals. Approval records bind the capability,
canonical resource, safe preview, and when required an identity fingerprint. Expired, denied,
cancelled, changed, replayed, or unjournaled operations fail closed. Read acknowledgement never
grants write or execute authority.

## 7. Configuration

- `config/agent.json`: capability feature flags, read scope, and agent-loop limits. Normal sessions
  are bounded by individual model/tool deadlines and finite step/call/repetition/transcript limits,
  not a short universal wall-clock deadline. An optional absolute deadline remains available for
  deployments that require one.
- `config/model.json`: immutable validated per-model targets, qualification, size/SHA-256 identity,
  sampling and memory guards. `LocalModelCatalog` resolves these targets against current memory
  at startup and actual lazy loading, including reloads after switching away. Runtime selection
  stores only an ID in ignored `state/local_model_selection_v1.json`; switches never write profiles.
  Memory reductions preserve the target for later loads. CPU fallback explicitly disables GPU
  offload when the minimum GPU context cannot fit. Response limits are independent profile targets,
  capped to half the effective context; CPU uses its separately specified response limit.
- `config/cloud.json`: OpenAI Responses configuration and immutable explicit model profiles.
  GPT-6 Luna is the default; ignored `state/cloud_model_selection_v1.json` stores the selected
  model ID. The SDK owns configured retries; the adapter never silently changes models.
  Phase 1 supplies text requests; Phase 2 supplies native tools and durable stateless
  output-item/encrypted-reasoning replay. Accepted output is saved before execution;
  the existing journal and permissions remain the execution authority. Complete
  batches replay in order; interrupted batches retain evidence and only settled
  neutral pairs enter later turns. Private items never enter local requests or UI
  history. See [replay verification](docs/cloud-openai-replay.md).
  The legacy pool adapter remains for compatibility tests during migration.
  See [OpenAI migration](docs/cloud-openai.md) for the phased contract and verification.
- `app/settings/`: strict loaders and models. Environment overrides are applied here, not in tools.

Secrets are never accepted in checked-in headers or JSON. Cloud keys come from the configured
environment variable or the in-memory GUI prompt. Runtime directories are created explicitly by
`main.py`; importing settings has no filesystem side effect.

## 8. Logging and persistence

Normal diagnostics use Python logging configured by `infrastructure/logging.py` with bounded rotated
files under `state/orsi.log`. Conversation content and file contents are not logged by default.
Malformed structured responses log only the provider/model, failure code, finish reason, and token
counts so output-budget failures can be diagnosed without recording generated or file content.
Capability intent, authorization, completion, failure, and unknown outcomes are stored separately in
the crash journal. Conversation and UI preference JSON writes use atomic replacement.

`conversation/store.py` retains the active session identity/status, ordered turns, visible messages,
per-call settled traces and terminal `AgentRunResult` metadata in the conversation file. Each settled
result is observed and persisted before the next call or model continuation, including denied,
cancelled and unknown results. Runtime results retain these records even if the observer or a later
batch/model step fails. History persistence failure stops continuation and blocks further live
turns; it does not justify replaying an operation.

Restart restores the same session and marks unfinished turns interrupted. Before constructing
context, the service reconciles crash-journal evidence missing from the detailed trace. Those
recovered summaries retain only call identity, capability and lifecycle outcome; missing arguments
or detailed output are not invented. Bootstrap no longer purges terminal journal records before
this recovery. Explicit New session clears conversation traces and applies journal retention;
unreviewed unknown outcomes survive that purge and block turns before inference or execution.

Every generating response has a persisted `provider_message_id`. Source call IDs are scoped to
that message; native transcript IDs are deterministic hashes of the scope/call pair. Reusing a
provider ID in another message or turn is valid, while duplicates within the same message and
mismatched results remain rejected. Disabled capabilities are represented as bounded factual
summaries rather than unadvertised executable transcript calls. The UI restores visible history,
including stopped and partial replies, without starting work. Malformed history is preserved and
fails closed rather than silently creating a fresh session.

Conversation traces are content-bearing user history and may contain arguments, paths, edits and
read results. They are bounded to 64 MiB and cleared only by an explicit session reset. This changes
the former in-memory-only trace retention; diagnostics and the content-free crash journal retain
their existing privacy boundary. Existing text-only conversation files remain readable.

`infrastructure/baseline.py` writes an allowlisted snapshot to
`state/diagnostics/effective_baseline_v1.json` at startup, successful switches, mode changes and
inference/tokenization updates. It records revision and tracked/untracked change status, effective flags after
read acknowledgement and agent fallback, bounded agent limits, selected model identity and profile
hash, target/effective limits, sampling, memory guard and current GPU memory. No prompts, replies,
file contents, host paths, cloud credentials or server credentials enter this snapshot. Diagnostic
write failure is non-fatal. A startup snapshot describes configured limits; later snapshots reflect
the loaded backend. Live switch evidence is kept separately under ignored `state/test-artifacts/`.

Completion state is part of the response contract. `inference/completion.py` holds bounded
finish-reason and token-usage metadata. Plain conversational adapters return a string-compatible
`CompletionText`; structured `ModelResponse` carries the same metadata and any bounded partial
assistant text. A known early termination, including `length`, is checked before native argument
decoding/repair and before constrained fallback JSON decoding. Even syntactically valid tool
arguments cannot authorize execution when their generation ended early. Cloud output-limit
responses retain their state instead of being discarded through provider failover.

`AgentRunStatus.INCOMPLETE` is distinct from `COMPLETED`; its result retains partial text and per-step
completion metadata, and stops without an automatic continuation. Conversation history stores
partial assistant text with completion/usage metadata; provider prompt messages keep their existing
role/content contract. Previously executed tool results remain in the in-memory trace when the
final generation is incomplete. Grounding does not replace partial text with a completed answer.

The Qt worker transports response objects rather than coercing them to strings. Chat messages
retain completion metadata and display a visible incomplete notice; unfinished fenced blocks
remain read-only highlighted code without synthesizing missing code or a closing fence. Copy
preserves the actual received text. Terminal UI cleanup releases controls before attempting
context refresh, and thread cleanup independently restores controls if that refresh fails.

## 9. Security boundaries

- Model output is untrusted until protocol and schema validation succeed.
- File names, file contents, snippets, and tool results are data, never instructions.
- Natural-language understanding does not grant authority.
- Authorization and approval are deterministic application code.
- UI approval surfaces receive trusted previews from capability implementations.
- The executor enforces permission/execution compatibility and bounded cancellation/timeouts.
- Unknown write outcomes block retries until reviewed.

Skill guidance is lower-priority context and cannot change tool registration, permission rules,
model configuration or approvals. There is no shell/console tool, general process launcher,
clipboard/window automation or plugin loader. `application.launch` currently supports only its explicit
allowlist and still requires approval.

## 10. Natural-language resolution

`conversation/capability_routing.py` returns the full enabled, model-visible registry catalog
for every agent turn, independently of wording and skill selection. It cannot create arguments,
grant authority, or execute anything. General intent and the actual
tool call remain model decisions against those exported schemas, normalized in
`inference/protocol.py`, and continued by `agent/runtime.py`. The narrow recovery in
`agent/file_resolution.py` may list the same directory after an extensionless read/find miss and
accept one obvious exact name/stem/extension match. Test-only command parsers live under
`tests/support/` and cannot enter production startup.

The optional `context_recovery_enabled` policy defaults to false. Registry visibility is already
used in both modes. When enabled, `conversation/recovery.py` projects large result payloads before
shortening old assistant material under context pressure. System/user requirements, call arguments
and scoped call/result pairs are protected; durable evidence stays unchanged. Unfit protected
content stops admission. No summarizing model or automatic mutation replay is used. Turn outcomes
retain admitted inference counts and estimated input costs. The candidate failed its measured
routine cost gate and has not passed live GPU acceptance; see
[context recovery verification](docs/context-recovery-2026-10-02.md).

## 11. Skill and extension boundaries

`app/runtime/skills/` supplies validated instruction definitions independently of the callable
`CapabilityRegistry`. Startup discovers a `SkillRegistry` and passes it to `ConversationService`.
The shipped local and cloud modes require explicit message attachment or session activation
to choose a skill. The service defaults automatic selection off, and startup explicitly disables
it; the metadata-only selector remains available to callers that deliberately opt in.
Plain follow-ups retain conversation history without a new skill injection. For a selected skill,
conversation orchestration renders its exact body into a labelled, escaped, lower-priority prompt
section through the existing admission policy. Provider adapters and the executor retain their
existing interfaces. Optional skill metadata is inert and cannot register code or configuration.

The local and public HTTPS Git installers publish only validated `SKILL.md` bytes to global
storage. They do not execute package content or import scripts/assets/references. Project scopes
must be explicit; registry construction and cached lookup do not read arbitrary project folders.
Normal conversation remains available without any skill selected.

A **skill** is instructions/context, a **tool** is a callable capability, **MCP** is an external
tool/resource protocol, and a **plugin** is a package that may group those components with hooks,
configuration and metadata. MCP transport, plugin loading, lifecycle hooks, an umbrella Capability
Manager and Claude compatibility remain future work. Their implementation must not turn skill
metadata or Markdown into an execution or authority channel.

See [Phase 6.2](docs/skill-runtime-phase6-2.md) for the frozen v1 interfaces and future adapter
boundaries, and [Phase 6.1](docs/skill-runtime-phase6-1.md) for content-free skill observability.

## Attachment input foundation

User messages may retain ordered `AttachmentReference` metadata while immutable
binary snapshots live outside conversation JSON in ignored state. The worker and
conversation service preserve these references, including attachment-only messages
and follow-ups. Legacy plain text history retains its model input shape.
`AttachmentStore` publishes flushed copies atomically and verifies manifests,
sizes and hashes before exposing a pinned read-only stream. Archives share the
same copies; import/save failures do not remove existing history or referenced
files. No attachment provides skill or filesystem execution authority.

Attachment inference and counting require explicit adapter support. Lazy/hybrid
wrappers preserve the selected mode, and unsupported backends reject attached
requests before inference. Both local llama.cpp adapters now implement text-document
input and native agent continuations; local vision and cloud inputs remain gated. See
[the phase 1 contract and verification record](docs/attachments-phase1.md).

Phase 2's `ui/attachments.py` owns ordered composer drafts and a cancellable Qt
preparation worker, while `conversation/attachment_processing.py` reads verified
snapshots and caches versioned text/dimension records beside them. The GUI renders
image previews and explicit document limitations; it does not parse documents or
encode clipboard images on the event thread. Removing entries, resetting sessions
and closing cancel outstanding preparation. Unsupported inference leaves the
draft intact before requesting credentials or beginning a model turn. Extraction
cannot activate skills or grant filesystem/tool authority. See
[the phase 2 preparation contract and verification record](docs/attachments-phase2.md).

Phase 3A's `conversation/local_documents.py` verifies/prepares local document snapshots
and renders them as JSON source material inside the owning user message. A scoped
counter projects the same complete text for the existing tokenizer while context selection
still sees attachment references, preserving atomic turns and oversized-current-turn
guards. Only selected transient requests become text before chat/native tool dispatch;
durable conversation JSON retains the original text and references. Native continuations
retain the rendered user message without duplicate projection. Per-turn caches expire
before verification on the next turn and on session reset. The lazy startup hint permits
document/image admission checks without loading a model in the GUI. The PDF cache adds
an optional readable-page count; older PDF caches are regenerated from verified snapshots
before local use. See [phase 3A](docs/attachments-phase3a.md).

Phase 3B extends local source projection with typed inline image parts. Original bytes and
references remain immutable in state; the conversation worker decodes verified still images
to orientation-correct lossless PNG transport, without resizing or OCR. Native protocol
validation permits only bounded inline image bytes in user messages, never URLs/paths or
privileged roles. Images remain intact through native call/result continuations and context
recovery. Binary transport has separate per-image/request bounds while existing transcript
text/call/result size limits remain enforced. The native adapter counts actual image patches
through the pinned `/v1/chat/completions/input_tokens` route on an idle owned server; offline
counting reserves the enforced maximum image patch count. Counting never starts a server.
The versioned vision configuration binds both model and projector hashes, verifies compatible
metadata, includes projector/encoder memory in context resolution and passes explicit native
projector/image-token flags. Selection stays manual; cloud and the Python backend do not
inherit local vision support. See [phase 3B](docs/attachments-phase3b.md).

Phase 4A's `conversation/cloud_attachments.py` projects verified immutable snapshots
to native Responses `input_image` and `input_file` parts only at transport dispatch.
Durable history and agent transcripts retain bounded ordered source references rather
than binary payloads or expiring provider IDs. Explicit native attachment tool support
allows those references through the existing strict call/result validator; generic and
local adapters retain their existing gates. Stateless replay retains the original user
sources through follow-ups, reopened/archived histories and native continuations.
Cloud composer preparation verifies file sources without applying local extraction limits
or writing empty local document caches. Image validation/thumbnails retain the existing
still-format and pixel guards. Scoped trusted guidance identifies source availability and
document/spreadsheet limitations without granting attachment instructions authority.

UI/context selection uses content-free offline size estimates. On the worker, the existing
cancellable SDK transport calls Responses input-token counting with the same native input,
reasoning and tool schemas before generation. Actual counts gate the profile's maximum input
and account pacing; binary base64 is not counted as text. A count error, source change,
cancellation, oversized request or generation failure never loses attachments by falling
back to text/local mode. Request storage remains disabled and inline transport creates no
Files API resources to expire or clean up. Phase 4B qualifies maximum capacities and phase 5
covers broader context/recovery lifecycle cases. See [phase 4A](docs/attachments-phase4a.md).
