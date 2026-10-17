# Local repetition stops and illustrated verification

17 October 2026. Bounded branch `codex/local-stop-reporting`, from local main
`45c4240`. No full suite, paid model, native user-document run or remote action.

## Demonstrated cause and path

The supplied live evidence establishes 33 model requests, 32 settled operations,
a successful final office.save, then an identical office.read target=layout
rejected before dispatch by repeat_guard / identical_call. This is a local
repetition stop; successful save does not establish task completion or a change.

AgentRuntime stages identical-call counts before dispatch. OfficeReadRepetition
observes settled receipts after execution: only successful matching-session,
matching-operation applied mutations with positive integer affected_items renew
previous successful initial reads. Saves, unchanged/failed operations and cursor
reads do not earn renewal. The staged counter is installed before receipt
observation, so renewal is not subsequently overwritten. Repeated inspections
without such receipts correctly exhaust the existing allowance. No bookkeeping
defect was demonstrated in this path; renewal and dispatch policies are unchanged.

The final runtime result retains REPEATED_CALL and creates a local progress report
with agent_recovery_stop metadata. ConversationService previously wrapped this
as IncompleteResponseError. The UI then used the generic incomplete-response
label, and the illustrated helper's exception path omitted terminal metadata and
write receipts. These reporting defects obscured the actual stop.

## Bounded correction

AgentStoppedError carries the actual local status, progress and completion
metadata. ConversationService retains its terminal outcome and settled calls;
the worker presents that progress and explanation. Restored chats identify
agent_recovery_stop as a local stop. Provider incompleteness still follows the
existing IncompleteResponseError / INCOMPLETE path, including stream and output
limit reasons. The interrupted metadata continues to mean unfinished work and
never authorizes a completed outcome.

The illustrated helper uses one allowlisted terminal projection on both normal
and exception paths: status, safe stop category, finish/failure reason, counters,
settled count, applied/unchanged receipt outcomes and affected-item counts.
Successful compositions/save and task completion are separate facts. It records
no receipt identities, session IDs, arguments, document/conversation text,
filenames, paths, keys or image bytes in this projection.

No additional recovery dispatch or automatic write replay is introduced. A
retained successful inspection remains evidence in the settled history, but the
live summary does not establish whether it was current after actual edits.
Without those receipts, another recovery request cannot be justified from this
evidence. Limits, approvals, uncertain-write protection, prompts, routing,
sampling and context policy remain unchanged.

## Verification and uncertainty

98 distinct focused checks pass: 31 Office read recovery checks (including the
owned synthetic bridge), 65 reporting/bounded recovery/completion checks, and two
additional receipt/renewal regressions. Final reporting module: 10 passed.
All use repository-local basetemp directories. The initial run lacked an imported
Qt fixture; corrected, then the presentation check passed. Two synthetic bridge
checks failed startup/teardown under the sandbox and passed unrestricted.
The default system Python lacked pytest; checks use the repository runtime.

The broader focused selection also exposed an unchanged plain-chat failure:
`test_plain_conversation_and_run_conversation_keep_partial_state` reaches an
unguarded `self.agent_runtime.registry` access with no agent runtime. It is
outside this change; its failure is recorded separately and excluded from the
passing selection. No full suite or paid/live acceptance was run.

The model's motivation for requesting another layout read, and which preceding
live writes were applied versus unchanged, remain unproven. This change does
not label the illustrated task complete. It preserves the information needed
for a future explicitly authorized run to distinguish these cases.

Recovery history bundle is under ignored
state/backups/local-stop-reporting-20261017. Preserve prior main under
archive/2026-10-17/main-before-local-stop-reporting before local integration.
Private settings, report.docx, other worktrees and remote refs are untouched.
