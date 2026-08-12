# O.R.S.I capability runtime design

## Objective

Extend the chat-only baseline one capability at a time while maintaining explicit state,
deterministic execution, debuggability, portability, and security. OpenCode supplies design
evidence; this remains an independent Python implementation.

## Proposed flow

```text
UI
  -> AgentRuntime
  -> ModelAdapter
  -> CapabilityCall
  -> CapabilityRegistry
  -> PermissionGate
  -> CapabilityExecutor
  -> Capability implementation / OS adapter
  -> CapabilityResult
  -> SessionStore
  -> ModelAdapter
```

## Core contracts

### CapabilityCall

- Stable call ID.
- Capability name.
- Untrusted argument object.
- Turn and session IDs.

### CapabilityResult

- Success flag.
- Normalized output.
- Stable error code and safe message.
- Duration and bounded metadata.
- No raw exception objects.

### Capability

- Name and description.
- Strict Pydantic input model.
- Permission class.
- Default timeout.
- `execute(validated_input, context)`.

### CapabilityContext

- Session, turn, and call IDs.
- Cancellation token.
- Approval-request function.
- Portable root and allowed path roots.
- Progress callback with bounded metadata.

## Durable state machine

```text
pending -> awaiting_approval -> running -> completed
                    |              |
                    +-> denied     +-> error
                    +-> cancelled  +-> timed_out
```

Every transition is written atomically. Terminal states cannot execute again. On restart, pending
calls become `interrupted_before_execution`; running calls become `interrupted_unknown_outcome`.
Neither state is replayed automatically.

## Agent loop invariants

- Use provider-native function calling; never parse action commands from prose.
- Validate the tool name and arguments before permission evaluation.
- Execute one call at a time initially.
- Append the structured result before asking the model for its next step.
- Bound steps, protocol failures, repeated identical calls, and overall duration.
- A final assistant message cannot prove that an operation happened.
- The user can cancel model generation, approval waiting, or execution through one path.

## Incremental implementation order

1. Contracts and stable errors.
2. Capability interface and validation wrapper.
3. Registry with no production capabilities enabled.
4. Permission gate.
5. Executor with universal timeout and cancellation.
6. Durable call events and restart recovery.
7. Provider-native ModelAdapter.
8. Bounded AgentRuntime using a deterministic fake model.
9. `filesystem.stat` as the first production capability.
10. Add later capabilities individually: list, read, atomic write, mkdir, copy, move, trash,
    open path, application discovery/launch/close, process execution, shell, then UI automation.

## Per-capability acceptance gate

A capability remains unavailable to the model until all of these pass:

- Strict schema success and failure tests.
- Permission allow, deny, approval, cancellation, and approval-timeout tests.
- Execution success, expected failure, timeout, and cancellation tests.
- Output and metadata size limits.
- Windows path, case, symlink/reparse-point, and allowed-root tests where applicable.
- Durable lifecycle and restart-recovery tests.
- Fake-model integration test proving result round-trip.
- Manual UI smoke test.

## First production milestone

`filesystem.stat` will accept one path, resolve it through the Windows adapter, enforce the READ
policy, and return normalized metadata without file content. Only after its full end-to-end path is
green will `filesystem.list` be designed or registered.
