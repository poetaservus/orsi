# Word COM stabilization, 18 October 2026

Bounded branch: `codex/word-com-stability`, based on local `main` `be5d21d`.
Only focused tests were authorized and run. Disposable synthetic documents were
used throughout; the reported editorial document and private settings were not
edited. No model requests, acceptance-prompt edits or remote Git operations were
made. MCP input/output schemas and existing timeout budgets remain unchanged.

## Findings and limits of the incident evidence

The literal warning originates in `OfficeConnection.call` in
`app/mcp/office_connection.py`, after a dispatched write has no settled Future
when its deadline, cancellation or worker-stop condition is observed. The bridge
is disconnected and the result is `OUTCOME_UNKNOWN`. Dispatch is not proof that
the COM method started or finished. The seven-minute workflow duration alone
does not establish the duration of its final tool call.

The execution path is:

1. `OfficeCapability` prepares/rechecks local binding and exact mutation approval.
2. The cooperative capability executor in `app/execution/executor.py` applies its
   outer deadline and records uncertain external side effects for review.
3. `OfficeConnection.call` serializes dispatch and waits for the Future.
4. `_connected` invokes the MCP SDK with the per-tool read timeout, validates the
   result and matching operation identity, then settles the Future.
5. `office_server.create_live_server` invokes `OfficeSTA`, validates the result,
   and sends a receipt or sanitized failure metadata.
6. `LiveOffice`/`WordEdits.execute` recheck authority, mutate, independently verify
   content/formatting/native structure and retain owned recovery state.
7. `WindowsOffice` and `office_word_document` perform the native calls on the STA.

Composition already has a 60-second confirmation budget and 90-second outer
budget in this baseline; ordinary tools have 10/40 seconds, and bounded page
render reads have a 30-second confirmation budget. The prior ten-second report
confirmation defect was already fixed before this task. No further timeout
increase or generic delay was introduced here.

The available `state/orsi.log` predates the reported run (last modified
14 October). Existing profile diagnostics retain content-free shapes/read
failures, but did not persist write-stage/timing evidence. The exact historical
tool, call arguments, duration, exception/HRESULT and side-effect boundary could
not be recovered. No claim is made that the reproductions below identify that
specific call. The run's timestamp/log location was requested while independent
work continued; it was not provided during this investigation.

## Confirmed defects and changes

| Defect | Evidence | Change |
| --- | --- | --- |
| Omitted false pagination properties inherit source-style rules | A native eight-paragraph, two-column plan passes on one page with ordinary Normal. With Normal's KeepWithNext/PageBreakBefore enabled, the pre-fix write creates eight pages and `verify_document` raises `OfficeUnknown` after inserting the content. No HRESULT: this is application verification, not a COM exception. | Emit explicit keepNext, keepLines and pageBreakBefore values for generated paragraphs, captions, pictures and boundaries. Preserve explicit requested heading/page rules. Verify effective native pagination properties. |
| Final two-column flow is not closed for balancing | Native equal-paragraph fixture has column bottoms at 592.10 and 423.40 points: a 168.70-point difference. | Compile a single empty continuous terminal section when the final authored section has two columns. Its empty boundary/paragraph use one-point type and zero spacing to avoid an extra blank page. Native readback, capture, save/reopen and owned restoration include it. Final measured bottoms are both 592.10 points, difference **0.0**, on one page. |
| A known save can be lost during subsequent authority refresh | `_connected` previously treated failure of its post-Save-As binding read as an unknown mutation even after receiving a validated matching save receipt. A deterministic SDK-boundary test simulates exactly that failure. | Preserve the verified Word save receipt, invalidate future authority and close the connection. Do not issue another save or claim that refreshed access succeeded. |
| Exceptions retain native references across the STA boundary | Thread-pool Futures previously carried original traceback/context frames, including locals containing COM proxies. A destructor/thread-identity regression demonstrates release ownership. | Detach failures and clear native traceback/context frames on the STA before raising a sanitized failure to asyncio. Preserve fixed categories, stages and numeric HRESULTs. |
| All post-dispatch exceptions were treated as unknown without reconciliation | Simulated rejection before mutation and failure after complete insertion both previously entered the same unknown path. | On the owning STA, independently compare the current target with the approved result and original snapshot. Complete result: return the applied receipt and owned recovery. Proven unchanged: consume old authority and require a fresh read/approval. Partial, foreign, unreadable or mismatched state: remain blocked. No writer is replayed. |
| Save acknowledgement could race background persistence | `save_word` previously called Save/SaveAs2 then immediately checked Saved/path/file existence; Word supports queued background saves. | Repaginate, update page fields, repaginate, temporarily disable BackgroundSave, save synchronously, restore the option in finally, then verify Saved, destination and ordinary DOCX package structure. |
| Write evidence was transient or discarded | Native stage/HRESULT fields lived in connection memory, while profile persistence only allowlisted read and plan events. | Add allowlisted write events across native, server, client and profile logging boundaries. |

The balancing terminator is compiled into the approved replacement packet; it is
not an extra mutation issued after a timeout. Repeated composition does not
accumulate terminators. A plan still admits at most 16 authored sections; capture
also accepts a seventeenth section only when it is an empty, single-column,
continuous terminator. Sources explicitly disabling balancing (`noColumnBalance`)
are rejected before writing a multicolumn replacement, with an actionable message.
Explicit column/page breaks can intentionally prevent equal-height columns and
are preserved. Image/credit groups can also constrain the achievable balance.

Captions now explicitly keep with their credits when present, and pictures keep
with their caption/credit. The final credit ends the group; unrelated following
body text is not pulled into that group. Native readback checks these rules as
well as embedded media, dimensions, text and section structure.

## Threading, retries and completion

`OfficeSTA` retains one `ThreadPoolExecutor(max_workers=1)`. Lazy construction of
`WindowsOffice`, `CoInitializeEx(COINIT_APARTMENTTHREADED)`, native calls, retained
objects, release and `CoUninitialize` run on its owner. `check_thread` rejects
cross-thread access and pumps waiting messages at native entry points. There is
no separately running idle message loop or registered IMessageFilter. No evidence
identified their absence as the historical cause; neither an unbounded message
filter nor a blanket COM retry was added.

Busy (`0x8001010A`) and rejected (`0x80010001`) calls are categorized separately.
Only readback can establish that a failed mutation left its target unchanged.
That case requires fresh read and approval; it is not automatically retried.
Fully verified application is reported once and receives the original recovery
guard. Partial writes and failed verification reads stay unknown/blocked. Real
transport timeouts, cancellation, worker loss and invalid receipts retain the
existing journal review requirement and disconnect behavior. A killed bridge
cannot supply its lost native snapshot; user review remains necessary.

Normal successful composition still requires both native readback and a complete
recovery capture. An exception after insertion, during verification or capture
may be resolved by an independent successful readback, never by replaying images,
text, formatting, section breaks or save. Unknown outcome is never inferred from
appearance, dirty flags alone or file existence alone.

Diagnostics retain UTC time, tool/action, fixed stage/category, elapsed operation
and failing-step milliseconds, numeric HRESULT when present, dispatch state,
verified outcome, retry-safety classification and allowlisted plan counts. They
exclude raw argument values, document text, paths, images, asset/session IDs,
exception descriptions, tracebacks, credentials and conversation/file contents.
A transport timeout can identify the tool/deadline but cannot reconstruct the
innermost COM call after the bridge is lost. Raw historical arguments are not
retroactively recoverable from these privacy-preserving logs.

## Batching and finalization

Body text, tables, inline images, section geometry and pagination properties are
already compiled into one bounded native XML insertion. Keep this batching and
its exact approval/recovery boundary. Cache native TextColumns references and
avoid reassigning already matching geometry/count/spacing, which unnecessarily
resets layout and can regenerate document-grid metadata. Remove the redundant
early field update; the required sequence is pagination, field update, reflow,
native validation/recovery, and a separately approved save. Do not combine
unrelated edits, introduce parallel COM mutations or relax preservation checks.

## Verification and retained evidence

Evidence is in ignored `state/word-com-stability/`, with repository-local pytest
temporary directories. Relevant completed records:

- `final.xml`: **191 passed, 3 native skips**, essential affected Word modules,
  read diagnostics, save/completion, workflow and STA ownership.
- `diagnostics-final.xml`: **31 passed**, new focused deterministic cases after
  the added guards/save-boundary check; overlaps the preceding selection.
- `wire.xml`: **6 passed**, including two new busy/applied cases through actual
  STA, SDK, capability executor and journal; overlaps other checks.
- `catalog.xml`: **1 passed**, existing stdio integration after updating its stale
  expected tool list to include the already-existing word_review tool.
- These records cover **200 distinct deterministic checks**, not 229 independent
  cases (the overlapping runs are not summed).
- `caption-qualified.xml`: **1 native pass**, final strengthened disposable gate:
  inherited rules, final-page balance, continuous 1/2/1 transitions, repeated
  image/caption composition, save/reopen, repagination and exact owned restore.
- `picture-bridge.xml`: **1 native pass**, production MCP picture registration,
  immutable source substitution, authoring/paragraph reads, rendered-page review,
  composition, guarded restore, foreign-change refusal and saving embedded media.
- `workflow-native.xml`: **1 native pass**, current production bridge review,
  correction, save, rendering, reopen and retention after closing-response failure.
- `contract.json`: accepted manifest matches and schema budgets pass unchanged.
  Whitespace checks pass.

The new regression file is `tests/test_office_word_com_stability.py`. It covers
timeouts before dispatch and after dispatch with/without a side effect, receipt
preservation, busy/rejected calls, partial/complete/unchanged outcomes, recovery
without repeated insertion, repeated formatting, privacy and STA release.

Earlier failures are retained, not relabeled passes: sandbox COM activation
denial (`0x80070005`), sandbox asyncio socket-pair/owned-process stalls, the native
168.70-point imbalance, and two outdated existing fixture expectations. The
legacy picture fixture expected a second composition without the review now
required by main; it was aligned to that existing policy without changing
production approval rules. Its synthetic partial-write mode previously completed
the entire text/table before raising; it now makes a genuine partial change,
while new separate cases cover fully applied writes followed by exceptions.

One new native reopen fixture initially opened the same already-open path in the
same Word instance, then closed the aliased original. Subsequent restore correctly
failed with `0x80010108` (disconnected). The fixture now reopens a byte-identical
disposable copy. The final native pass includes that corrected save/reopen and
restoration sequence. Test-owned Word and MCP processes were released.

No full repository suite or live-model editorial acceptance was run. These tests
do not measure a production intermittent-failure rate. The original four-photo
document was not available for section/style inspection or layout comparison.

## Before/after reliability

| Before | After |
| --- | --- |
| Inherited pagination can insert the report, then fail verification with mostly empty pages. | The reproduced plan verifies on one page under both ordinary and adverse source styles. |
| Last-column bottoms differ by 168.70 points in the equal-paragraph fixture. | Both columns end at 592.10 points, with no extra page. |
| Rejected, partial and completely applied writes share an unknown result. | Independent readback distinguishes unchanged, partial/unknown and fully applied; no mutation replay. |
| Post-save authority failure can erase a valid save receipt. | Save receipt survives; future access is revoked. |
| Failure details are transient and traceback-held proxies may escape the STA. | Content-free operation evidence persists and native failure locals are released on their owner. |

## Microsoft references

- [Threading support in Office](https://learn.microsoft.com/en-us/visualstudio/vsto/threading-support-in-office?view=visualstudio):
  STA serialization, message pumping and busy-call rejection.
- [KeepWithNext](https://learn.microsoft.com/en-us/office/vba/api/word.paragraphformat.keepwithnext):
  paragraph pagination behavior.
- [SectionStart](https://learn.microsoft.com/en-us/office/vba/api/word.pagesetup.sectionstart)
  and [NoColumnBalance](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.nocolumnbalance?view=openxml-3.0.1):
  continuous sections and compatibility settings affecting balancing.
- [BackgroundSave](https://learn.microsoft.com/en-us/office/vba/api/word.options.backgroundsave)
  and [BackgroundSavingStatus](https://learn.microsoft.com/en-us/office/vba/api/word.application.backgroundsavingstatus):
  asynchronous save queues. The implementation selects synchronous persistence
  instead of polling the application-wide queue or adding delays.
