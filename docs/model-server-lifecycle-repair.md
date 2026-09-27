# Permanent model-server lifecycle repair

Branch: `codex/model-server-lifecycle` (from the current GUI branch).

## Problem and scope

Closing ORSI stops the capability runtime but does not close the inference backend.
Eight old local servers survived their application processes and retained about 99.5 GiB
of private committed memory. A new model then failed during startup. Memory exhaustion
is strongly indicated; the exact native error was lost because server output was discarded.

Keep the existing GUI and uncommitted Phase 1 recovery work intact. Do not change model,
context, capability permissions, or write-retry policies. Never terminate a server merely
because its executable is named llama-server.exe.

## Phase 0 — Establish the baseline

0.1 Create the dedicated branch and record this plan before implementation.
0.2 Trace normal exit, startup failure, cancellation, mode switching, and lazy loading.
0.3 Preserve unrelated changes and identify only this checkout's verified legacy orphans.

Exit gate: the ownership gap and required cleanup paths are documented.

## Phase 1 — Close owned backends on normal shutdown

1.1 Make inference shutdown terminal and idempotent, including lazy and hybrid wrappers.
    An unloaded backend must not be initialized just to close it or restarted after closing.
1.2 Connect window/application shutdown and exception cleanup to backend closure, even
    when capability cleanup fails. Preserve existing window cleanup behavior.
1.3 Cover close-before-load, close-after-load, repeated close, cancellation, initialization
    races, and cleanup failures with deterministic tests.

Exit gate: normal application exit releases its local process and cannot load a replacement.

## Phase 2 — Enforce ownership after crashes or forced termination

2.1 Give every local server Windows job-object ownership with kill-on-job-close semantics.
    Establish ownership at process creation so a parent crash cannot leave an unowned child.
2.2 Fail startup safely if ownership cannot be established. Keep handles private and release
    them on every failure/cancellation path; do not attach or kill other applications' servers.
2.3 Verify actual Windows process behavior with lightweight child processes: normal close,
    parent force-kill, creation failure, and unrelated-process survival.

Exit gate: terminating the owner also terminates its child, including during startup.

## Phase 3 — Preserve safe startup diagnostics

3.1 Capture bounded startup error information without allowing pipe backpressure or unbounded
    files. Do not persist API keys, prompts, tool arguments, generated text, or raw command lines.
3.2 Report exit code and a sanitized failure category (such as memory allocation failure),
    while distinguishing early exit, startup timeout, and process-ownership failure.
3.3 Test noisy output, secret-bearing output, early exit, timeout, cancellation, and retry.

Exit gate: the next startup failure is diagnosable without leaking conversation or credentials.

## Phase 4 — Recover resources and verify the complete lifecycle

4.1 Revalidate and stop only legacy servers from this checkout whose original parents are
    gone (including PID reuse), with no active connections. Record process/memory counts.
4.2 Run the regression suite and real local-server start/health/close cycles, including an
    application-exit path. Confirm no new orphan remains and resource usage is released.
4.3 Review the isolated diff, save implementation checkpoints, and report exact passed checks
    and any unverified UI/manual conditions. Keep main unchanged.

Exit gate: repeated real lifecycles return to the process baseline; crash ownership tests pass;
diagnostics are bounded and sanitized. A passing mocked shutdown test alone is insufficient.

## Progress

- Phase 0: complete. The service never closed inference, and a duplicate window-close
  handler overrode preference cleanup. Server output was discarded; no OS ownership guard existed.
- Phase 1: implemented. Lazy/hybrid closure is terminal, service and application exit
  close inference, window close preserves preferences and waits for a cancelled worker.
  Focused inference/lifecycle/UI tests pass (including initialization and cleanup-failure cases).
- Phase 2: implemented. `CreateProcessW` receives `PROC_THREAD_ATTRIBUTE_JOB_LIST`
  and a private kill-on-close job before the child runs. No unguarded fallback.
  All 19 ownership/server tests pass, including real parent force-kill, descendants,
  unrelated-process survival, launch failures, and stable handle counts.
  Design reference: [Microsoft's atomic job assignment explanation](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812).
- Phases 3–4: pending.
