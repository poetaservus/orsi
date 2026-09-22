# O.R.S.I architecture

## 1. System overview

O.R.S.I is a local-first Windows desktop assistant. The Qt GUI submits a message to the
conversation orchestrator. The orchestrator builds bounded context and asks the agent runtime for
either ordinary assistant text or one provider-native capability call. A capability call is schema
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
4. `AgentRuntime` accepts either assistant text or one normalized native capability call. Invalid,
   mixed, repeated, oversized, or excessive calls stop or receive bounded feedback.
5. The registry validates the capability name and Pydantic argument schema.
6. The permission gate evaluates canonical resources. Read rules may allow directly; writes and
   application launch require a pending, exact, expiring approval record.
7. The GUI presents only trusted approval data and resolves the approval. It does not decide policy.
8. The journaled executor records intent and authorization, executes once, records the result, and
   returns structured output to the model.
9. The loop continues until final assistant text or a bounded terminal status. The orchestrator
   stores the visible response and retains only the structured history needed for the active session.

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
Pydantic arguments model, permission class, timeout, execution isolation, and batch limit. The
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
- `config/model.json`: local model path and generation/context limits.
- `config/cloud.json`: provider endpoint, ordered model pool, safe headers, and the name of the
  API-key environment variable. Cloud pool failover is bounded by the configured candidates;
  malformed native tool responses never execute, and the first successful model remains sticky.
  Retryable provider failures use a configured attempt cap with exponential backoff. Candidate
  requests and the complete pool/retry step have separate configured time budgets.
- `app/settings/`: strict loaders and models. Environment overrides are applied here, not in tools.

Secrets are never accepted in checked-in headers or JSON. Cloud keys come from the configured
environment variable or the in-memory GUI prompt. Runtime directories are created explicitly by
`main.py`; importing settings has no filesystem side effect.

## 8. Logging and persistence

Normal diagnostics use Python logging configured by `infrastructure/logging.py` with bounded rotated
files under `state/orsi.log`. Conversation content and file contents are not logged by default.
Capability intent, authorization, completion, failure, and unknown outcomes are stored separately in
the crash journal. Conversation and UI preference JSON writes use atomic replacement.

## 9. Security boundaries

- Model output is untrusted until protocol and schema validation succeed.
- File names, file contents, snippets, and tool results are data, never instructions.
- Natural-language understanding does not grant authority.
- Authorization and approval are deterministic application code.
- UI approval surfaces receive trusted previews from capability implementations.
- The executor enforces permission/execution compatibility and bounded cancellation/timeouts.
- Unknown write outcomes block retries until reviewed.

There is no shell/console tool, general process launcher, clipboard/window automation, plugin loader,
or skills runtime in this repository. `application.launch` currently supports only its explicit
allowlist and still requires approval.

## 10. Natural-language resolution

There is no production regex command router after this cleanup. General intent and tool selection are
handled by the model against the schemas exported from `capabilities/catalog.py`, normalized in
`inference/protocol.py`, and continued by `agent/runtime.py`. The only deterministic resolver is the
narrow recovery in `agent/file_resolution.py`: after an extensionless read/find miss, it may list the
same directory and accept one obvious exact name/stem/extension match. Test-only natural-language
parsers live under `tests/support/` and cannot enter production startup.
