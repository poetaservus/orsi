# Office workbook range discovery and completion repair, 15 October 2026

This bounded change starts from local main `ed4aa49` on
`codex/office-range-discovery`. A workbook-wide read followed by dashboard
generation used a prefix ending at row 15. Inspection confirmed populated data
past that prefix and dashboard formulas explicitly limited to it. There is no
15-row engine limit. The exact second-attempt semantic error was not retained,
so this change does not claim to reproduce that particular failure.

## Changes

The existing `office.read` tool now supports two Excel targets without changing
the accepted v1 schemas, manifest, tool names or permissions:

- `workbook` returns paged worksheet names, used-range addresses, dimensions and
  correctly quoted `SheetName!used` targets. This is metadata, not a cell read.
- `SheetName!used` reads the full frozen used extent through existing bounded
  pages and one accumulated Excel snapshot. Coordinates are retained lazily,
  allowing reads beyond the old 1,000-cell explicit-rectangle bound without
  allocating a descriptor for every cell. A changed extent invalidates its
  continuation instead of silently omitting newly added rows.

Used extents follow Excel's `UsedRange`, which can include formatted blank cells.
Existing result/character bounds, snapshot-memory limits, call budgets, document
identity checks and exact approvals remain authoritative. Explicit rectangular
reads, edits and formula references retain their existing limits.

The model-visible descriptions explain workbook discovery, continuation cursors,
the exact `office.excel_edit` name and its supported existing-sheet/local-formula
subset. No alias for a guessed edit-tool name is introduced. The conversation
system prompts, acceptance prompts, routing, sampling, context policy and private
settings are unchanged.

A turn-local agent check watches successful full-read pages. An early final
answer receives a continuation reminder using the exact returned cursor. Another
final answer without progress stops as unfinished; a failed continuation also
stays unfinished. No read is automatically dispatched and continuation reminders
do not consume the semantic-correction budget. Initially malformed requests can
still be corrected. Explicit previews remain bounded previews and do not force
additional reads.

When settled Office errors exhaust the existing semantic-correction budget, the
bounded terminal message includes the actual tool and normalized underlying
error. This preserves the limit and pre-write rejection instead of hiding the
cause behind a generic semantic-limit message.

This is read discovery and completeness protection, not new-sheet creation or
cross-sheet formula support. It does not statically prove that every generated
KPI formula uses the right source rows, and it does not rewrite existing
dashboards. Unsupported native edits remain rejected before dispatch.

## Necessary verification

The affected Office read/edit/contract/permission/conversation/approval and agent
runtime/completion/provider-recovery selection passed **215 tests in 42.76
seconds**, with no failures, errors or skips. After tightening initial malformed
request handling and keeping opaque cursors out of user-facing messages, the
**eight new regressions passed in 4.68 seconds**. These
include 36-row and 128-row reads, a lazy 800,000-cell native-coordinate plan,
quoted worksheet names, changed extents, actual SDK/stdio continuation after a
premature answer, stalled completion and unsupported-edit diagnostics. Existing
approvals, formula restrictions and semantic limits passed their affected tests.
Preliminary test-composition/assertion failures are retained separately.

One normal-Windows native gate created only a test-owned synthetic Excel
workbook, discovered a quoted worksheet and read its 36-by-8 used range through
the production permission/executor/MCP/COM path. All **288 cells across nine
pages** shared one snapshot; the bridge and owned Excel process were released.
The product issued no mutations and no provider requests. A preceding attempt
to inspect the exact user's open workbook found no matching open document, so
that attempted check is not counted as passed. No user workbook was edited or
saved by this repair.

The accepted manifest still matches. The six exposed Excel tools measure
**5,247 wire bytes / 2,037 reserve tokens**; the full eight-tool contract measures
**8,117 bytes / 3,090 reserve tokens**, within the existing budget. Compilation
and whitespace checks pass. The full suite was deliberately not rerun because
the latest user instruction requested only necessary tests. Live provider/model
acceptance and second-host qualification were not run.

Ignored evidence:

- `state/office-range-essential-final.xml` and `.log`
- `state/office-range-final-ux.xml` and `.log`
- `state/office-range-native-synthetic.json`
- `state/office-range-contract.json`

Restart ORSI and reconnect Office to load the new tool descriptions and read
targets. Begin a fresh workbook read before regenerating a dashboard; an existing
partial dashboard is not repaired automatically.

Content-free inventories are retained under
`state/backups/office-range-discovery-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-range-discovery`, commit this change,
fast-forward local main and remove only its merged feature branch. Other
worktrees, historical/unmerged tips, private settings and remote refs remain intact.
