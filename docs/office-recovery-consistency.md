# Office recovery consistency, 20 October 2026

## Reproduction and cause

The reported Excel turn retained successful saves but stopped at the identical
capability guard. The original blocked capability name was obscured and was not
recovered, so the historical screenshot alone cannot distinguish discovery from
saving. The desktop inspection failure is a separate, valid project ownership
boundary; it must not be relaxed to inspect an Office document.

An isolated native Excel reproduction establishes the accounting defect: after
two real edits, readbacks and saves, the third identical `office.documents`
proposal stops after ten settled operations. The old runtime renews initial reads
after edits, but saves and metadata discovery keep their lifetime call counts.
Completion review also omits Office receipts and supplies software project
inspection guidance to Office work.

## Bounded repair

`OfficeProgress` tracks trusted connection epochs, confirmed document/session
aliases, observed edits and saves. Contract defaults are normalized before repeat
accounting. Same-document reattachment and new operation IDs do not mint progress.
A confirmed applied edit renews that document's successful initial reads and
saves, plus relevant initial metadata discovery. A first save of a newly observed
revision, or a confirmed new Save As destination, permits metadata refresh;
repeated saves of the same state do not. Saving in place never renews source reads.

Office repeat decisions run immediately before each sequential dispatch, allowing
an earlier edit in the same batch to settle before assessing its save. Duplicate
operations within one batch remain rejected up front. No call is automatically
replayed. Ordinary budgets, native resource binding, approvals, cancellation,
rollback limits and unknown-outcome boundaries remain authoritative.

A rejected mutation intent can earn one repetition renewal after a later complete
current snapshot is received and the proposed retry actually names that snapshot.
Cursor pages must form the same contiguous session/target/snapshot sequence.
Partial or failed later reads invalidate older retry proof; edits and connection
changes do too. Denied, uncertain and malformed writes earn no renewal. This
accounting does not validate native edit coverage or grant write authority.

Completion ledger version 2 records scoped Office metadata, read pages, applied
edits, saves, unchanged operations and failures. Later edits or uncertain writes
make earlier content reads and saves stale. Existing saved reviews default to
ledger version 1, preserving their original meaning. Runtime receipt bookkeeping
remains outside the model's three-field assessment schema. Office-specific review
guidance uses supported native checks and reports unavailable Excel visual scope.

Stops record fixed reasons, an observed progress counter and a related receipt,
without document titles, paths, contents or raw arguments. A consumed retry is
distinguished from a missing snapshot. Historical stops without state comparison
say so explicitly. Existing retained proposals and settled receipts survive.

## Focused qualification

Only focused and essential tests were run, with repository-local temporary
directories and the pytest cache disabled. No full suite or live model/API ran.

- Final deterministic/runtime selection: **115 passed**. This covers Office
  progress, evidence and diagnostics; mixed software/Office verification scope;
  long completion ledgers; denied prerequisites and review tool rejection; the
  existing filesystem recovery workflow and historical review anchors; and the
  previous null-output context compaction regressions. A final regression proves
  fresh evidence earns exactly one additional mutation dispatch, followed by an
  undispatched stop if that intent fails again.
- Existing owned Word stdio read/edit regression: **2 passed**. The initial
  sandbox execution could not start/release its worker normally; the unrestricted
  focused rerun passed. The environment failure is not classified as a product
  failure.
- Final disposable native Excel gate: **1 passed**. A scripted
  model drives the real Office bridge through 15 settled operations: attachment,
  three edits, four complete readbacks, three identical saves and four identical
  metadata lookups. All six write approvals occur normally. Readbacks verify
  values and calculated formulas; ZIP/XML inspection independently verifies the
  saved XLSX value, formula and cache. A current ready ledger v2 survives durable
  conversation reload. The owned Excel process and worker both exit.

The native gate first reproduced the old third-lookup stop. Its first positive
run completed the product workflow but exposed a missing optional `openpyxl`
dependency in the test's final artifact check; that check now uses standard-library
ZIP/XML parsing. This fixture failure is separate from product qualification.
The final combined focused selection passes **118 distinct checks**. Content-free
native diagnostics are under `state/test-tmp/office-recovery-final/`.

## Limits and integration

The native gate verifies a disposable workbook, not arbitrary dashboard design or
rendering. Excel still has no screenshot tool in this Office contract. Read-page
observations never imply a whole workbook was checked. Native Word rendering and
review requirements remain in force. Sessions attached before the turn are kept
separate until receipts establish their document relationship; the runtime does
not guess aliases from user text.

The running app and user documents, including `dataset.xlsx`, are untouched.
Restart Orsi to load the change. No API key was accessed. Settings, model profiles,
sampling, context policy, core/acceptance prompts and project inspection ownership
rules remain unchanged; only scoped completion-review guidance is refined.

The branch starts at local main `29f8df1`, preserving its context compaction fix.
After verification preserve prior main at
`archive/2026-10-20/main-before-office-recovery-consistency`, commit the bounded
change, fast-forward local main and remove only its merged feature branch. Other
worktrees, historical/unmerged branches and remote refs remain untouched.
