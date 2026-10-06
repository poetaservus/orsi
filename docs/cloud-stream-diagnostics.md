# Cloud stream failure diagnostics, 6 October 2026

An interrupted Responses stream previously surfaced as "The response was cut
off" regardless of the cause. The saved 47-second desktop run completed 22
capability calls and then lost its final stream after 813 ms. The retained
metadata said only `error`; no existing evidence distinguishes connection loss
from decoding or stream validation failure. This change cannot reconstruct that
discarded cause, and does not claim to fix the underlying interruption.

Completion metadata now retains an optional, finite `failure_reason`. Older
saved conversations remain readable. Fixed local messages distinguish stream
EOF, connection loss, timeout, decoding failure and individual protocol checks,
including unsupported events, sequence/identity mismatches and bounded stream
limits. Provider-reported incomplete/failed responses and unfinished tool calls
also have distinct reasons. Cancellation keeps its existing outcome.

The runtime includes the reason in its stopped message and continues to block
incomplete calls. Chat displays the reason with partial text, reconstructs it
from saved metadata on reopening, and includes the diagnostic code in the
completion tooltip. Status text already present in the message body is not
duplicated in the incomplete notice.

Interruption logs record fixed reason and event categories plus event count,
last accepted sequence, stream bytes and text character count. Unknown event
names are recorded as `unrecognized`. Exception strings, provider messages,
unknown error codes, keys, headers, response IDs, arguments, reasoning and
conversation/file contents are not added to diagnostic logs. Existing request
metrics retain timing and token counts. Unknown token usage stays unknown.

This is a bounded reporting change from local main `2cbfb49` on
`codex/cloud-stream-diagnostics`. It does not change stream acceptance, tool
authorization/execution, retries, routing, sampling, context budgets, model
profiles or acceptance prompts. No live request is sent to reproduce the user's
private conversation, and runtime settings/conversations are preserved.

## Verification

The final focused adapter/runtime/UI checks passed 191 tests, and the remaining
OpenAI budget, efficiency, replay, selection and qualification-contract checks
passed 103 tests. Real pinned-SDK streams use an isolated mock HTTP transport.
Coverage distinguishes EOF, connection and timeout; validates specific parser
failure categories; rejects private event/error text from logs; retains reasons
through runtime, worker, storage and reopened chat; and blocks incomplete calls.
The failure field rejects arbitrary provider text and accepts legacy metadata.
Existing cancellation, retry-ownership and resource-release checks still pass.

An offscreen synthetic chat preview using the application's bundled font was
visually inspected for readable wrapped status and retained partial text. The
initial fontless harness displayed missing glyphs; loading the normal application
font corrected the harness without a product font change.

The initial full unrestricted Windows run recorded 1,914 passed, one failure,
49 existing skips and 15 subtests passed. The failure was the existing protocol
limit exception wording assertion; the fixed local message now retains that
phrase, and its 103-test recheck passed. Final unrestricted Windows confirmation
passed 1,917 tests and 15 subtests, with 49 existing skips and no failures in
235.61 seconds. Live API/model qualification gates are not run; skipped gates
are not counted as deterministic passes. Test reports and the synthetic preview
stay under ignored `state/test-artifacts/`.

## Integration and recovery

Pre-integration refs and the worktree map are preserved in the verified
complete-history bundle under ignored
`state/backups/cloud-stream-diagnostics-20261006/`. After final verification,
commit the bounded change, fast-forward local main, and remove its merged local
feature branch. Historical/unmerged tips remain preserved. Other active
worktrees and remote refs are not changed or published.
The previous main is also preserved at
`archive/2026-10-06/main-before-cloud-stream-diagnostics`.
