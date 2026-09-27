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
- Phase 3: implemented. Bounded stderr draining retains fixed failure categories only;
  exit codes are reported, raw log-file environment overrides are removed, and capture
  stops when healthy. All 34 focused lifecycle/ownership/diagnostic tests pass, including
  multi-megabyte noisy output, secret-bearing output, timeout/retry, and close during startup.
- Phase 4: complete. Revalidation found zero legacy servers; no cleanup kill was needed.
  Added active-response window-close, preference-save failure, application exception,
  and application-quit tests. Late worker results no longer refresh a closed backend.

## Final verification — 2026-09-27

- Full regression: **712 passed, 52 skipped, 5 subtests passed**. The skipped tests include
  optional integrations; they are not counted as passing.
- Real shipped model: service shutdown (including an actual model response) passed in
  9.8 seconds; Qt window shutdown passed in 6.6 seconds. Both native process handles
  signaled termination. UI checks used Qt's offscreen platform.
- A separate real-model owner was forcibly killed after health became ready. Windows
  terminated its loaded server within the five-second assertion deadline; test passed.
- Final system check: **zero servers from this checkout**, 21,756 MiB available RAM,
  17,590,108,160 committed bytes, GPU usage 1,023 / 16,384 MiB. Memory figures are a
  momentary system snapshot, not a claim that this repair terminated the earlier orphans.
- Main remains `dc2d092f51e941bff0ca13154720a94818004d8e`. Earlier uncommitted Phase 1
  recovery changes remain unstaged; this branch includes the existing GUI work.
- `ORSI.cmd` directly launches `app.main` from this checkout, so a fresh launch uses the fix.

Re-run the opt-in real-model acceptance (requires the shipped model and Windows runtime):

```powershell
$env:ORSI_RUN_SERVER_LIFECYCLE = '1'
.\runtime\python\python.exe -m pytest tests/test_live_server_lifecycle.py -s
```

The guard prevents orphaned servers; it cannot guarantee model startup if another
application independently exhausts memory. Such failures now include a sanitized category
and native exit code when available. No context settings or capability policies were changed.
