# Durable settled calls and stopped turns, 2 October 2026

Previously, tool results reached the history observer only after the entire batch completed, and
most stopped turns discarded that history. Startup reset the conversation and purged successful
journal records before they could be reconciled. A failed final model step could therefore hide a
successful approved edit from the next turn. Provider call IDs were also treated as globally
unique across messages, which rejected legitimate reuse.

## Implemented contract

`SettledCall` ties the original validated call to its normalized result, internal execution ID and
generating message identity. The runtime retains each result before another call/model step and
returns all settled records on every terminal outcome. Both observer APIs now observe individual
settlements, including earlier calls in a stopped batch. Known unknown/cancellation results are
preserved rather than replaced by a generic stop message.

The active conversation durably stores its stable session identity, session status, ordered turn
records, per-call traces and terminal outcome/usage metadata. Stopped turns get visible status
messages; incomplete replies retain their partial text. The orchestrator preserves trace on model
unavailability, internal failure, output termination, cancellation and limits. Restoring the UI
shows that history without restarting a turn. Explicit New session clears the active conversation.

Provider source IDs are scoped by a persisted generating-message identity. Native transcripts use
a deterministic bounded hash of that pair. Same-message duplicates are rejected; reuse across later
messages or turns remains correctly paired. This identity is distinct from the crash journal's
internal execution ID, permission checks and single-use approval authorization.

When detailed history could not be saved after execution, the live turn stops and further turns
are blocked. On restart, unfinished turns become stopped, and journal evidence fills missing
outcome summaries. A durable completed journal record supports a success summary; a running call
recovers as unknown. Missing output/arguments are not reconstructed. No recovery path executes,
retries or resumes an operation. Unknown outcomes block the runtime before inference and approval,
including after restart and explicit session reset. Journal terminal records are no longer purged
automatically at bootstrap before they can be recovered.

Disabled tools remain known through bounded factual summaries in plain context. Complete older
turns can still fall outside the existing context budget, but their durable records remain stored.
Corrupted history is preserved and prevents startup from silently replacing it with an empty
session. State is adopted only after atomic persistence succeeds.

## Retention and limits

Detailed traces are now persistent conversation data and may include paths, tool arguments, file
contents and edits. The active conversation is bounded to 64 MiB, 10,000 turns and 32 settlements
per turn. The crash journal still stores hashes and lifecycle metadata; baseline/verification
diagnostics contain no conversation or file contents. Explicit New session clears the active
conversation and applies the existing journal retention policy; unreviewed unknown records stay.
Existing text-only files remain readable. Traces discarded by older app versions cannot be
recreated without surviving journal evidence. Accepted model profiles, sampling and feature flags
are unchanged. Source baseline: `0ab6a4a`.

## Verification

The central regression performs a real, explicitly approved edit in a temporary Windows workspace,
then injects model disconnection. It verifies the changed bytes/hash, consumed single-use approval,
durable successful call and stopped turn. The next model request receives both the successful edit
result and the failure status, in the same process and after restart, with one approval and one
execution throughout.

Additional checks cover later stopped batches, observer/history-write failures, successful journal
recovery across a missing-trace write, actual unknown outcome after file replacement, restart
blocking without a model request, invalid/denied calls, cancellation and step limits, provider-ID
reuse/mismatch, disabled tools, corrupted startup history, partial-response restoration and UI.
All mutation fixtures use temporary files; no user's files are edited by acceptance tests. These
tests mock model responses and inject provider failures; they do not claim live model task success.

The broad focused run passed **210 tests and 5 subtests**, with one host symbolic-link check skipped.
Subsequent contract checks passed 59 tests. The final full run had **785 passes, 1 failure,
54 skips and 5 passed subtests** in 136.68 seconds. Its single failure was `WinError 5` during
authorization-journal replacement in the existing exact-path text-read integration check,
before the requested operation. That test and all 24 outcome regressions passed on recheck
(25 tests), including the final cross-turn provider-ID and explicit-reset checks. This is not
a claim that the full suite was green or that skipped live gates passed.

An earlier full run had three atomic-replacement failures and an obsolete cancellation assertion
expecting the stopped turn to disappear. The cancellation regression now verifies its durable
outcome; those four cases passed on recheck. The actual edit, approval, next-turn and restart proofs
passed in both full runs. Final evidence is also summarized without content in
`state/diagnostics/turn_outcomes_verification_v1.json`.

Focused results and full-suite results are retained under ignored `state/test-artifacts/turn-outcomes-*.txt`.
The existing intermittent Windows `WinError 5` at atomic replacement remains an open reliability
issue. This repair records and stops on persistence failure; it does not change the underlying
replacement retry policy or claim that the wider robustness audit is complete.
