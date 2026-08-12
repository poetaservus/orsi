# Current O.R.S.I baseline audit

## Scope

This document audits the conversational baseline created on 2026-08-12. It intentionally contains
no computer-action subsystem.

## Current request path

1. `MainWindow` accepts text and starts a worker thread.
2. `ConversationService` appends the user message to `ConversationStore`.
3. The service constructs bounded text history with the chat-only system prompt.
4. `HybridInferenceEngine` selects the local or cloud backend.
5. The backend returns plain text through `respond(messages)`.
6. The service persists the assistant text and the UI renders it.

No capability schemas, registries, permission prompts, command parsers, OS adapters, audit/undo
controllers, or action loops are imported by this path.

## Baseline strengths

- The active architecture is small enough to reason about completely.
- Local and cloud providers share one text-only interface.
- Conversation writes are atomic.
- The model is told explicitly that the build cannot operate the computer.
- The production import graph excludes all removed legacy action packages.
- The regression suite verifies plain model requests and absence of legacy packages.

## Known issues

### MEDIUM — inference cancellation is only cooperative at call boundaries

The Stop button sets a cancellation token, but an in-progress local generation or blocking cloud
request is not interrupted immediately. Before capabilities return, inference backends need a real
abort path or a clearly documented bounded shutdown behavior.

### MEDIUM — malformed conversation JSON can stop startup

Atomic replacement prevents partial normal writes, but `JsonStore.load` does not currently recover
from invalid JSON. Session v2 must preserve the corrupt file for diagnosis and start a safe new
record rather than crashing or silently overwriting evidence.

### MEDIUM — the UI does not replay stored messages

The model receives persisted history after restart, but the current window begins visually empty.
This is acceptable for the checkpoint but should be resolved before durable action events are added.

### LOW — cloud cancellation depends on request timeout

The blocking HTTP call has a timeout but no per-request abort handle. This is separate from future
capability cancellation and should not be hidden by the agent loop.

## Critical baseline invariant

The conversational baseline must remain runnable throughout development. New capability modules
will not be connected to startup until their contracts, executor path, state transitions, and tests
are complete.
