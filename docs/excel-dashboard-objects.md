# Native Excel dashboard creation

The Excel connector previously exposed cell values, formulas and a small amount
of formatting. A dashboard skill could describe charts, colored cards and
interactive filters, but could not create them through that connector.

`codex/excel-dashboard-objects` starts from local main `adc5d0f`. It extends the
existing `office.excel_edit` contract with native dashboard objects and cell fills.
The same document selection, permissions, approval UI, journal and unknown-outcome
stop apply. Runtime settings, model selection, sampling, routing, acceptance
prompts and context limits are unchanged.

## Supported operations

| Feature | Supported creation |
| --- | --- |
| Cell fills | Solid `#RRGGBB` or `none`; captured theme/tint/pattern restoration |
| Charts | Column, bar, line, line with markers, area, pie, doughnut, scatter and stacked column; title, legend, series colors and geometry |
| Shapes | Rectangle, rounded rectangle, oval, chevron and up/down arrows; text, colors, font size/bold and optional live cell link |
| PivotTables | Bounded local range or Table data; one to four row fields, one value field; sum/count/average/min/max |
| Slicers | A field from an existing bounded local PivotTable, native caption/style/columns and geometry |

`office.read` now accepts `SheetName!objects`. Workbook discovery returns the
quoted `objects_target`; object metadata includes exact PivotTable output
rectangles so the agent can read the correct source for a slicer. This is
metadata discovery, not a substitute for reading the underlying source cells.

`GETPIVOTDATA` joins the existing supported pure formula functions, allowing a
KPI cell and a linked shape to follow native PivotTable slicer selections.
Slicers filter their connected PivotTables; unrelated worksheet formulas need
an explicit link to that selected context.

## Scope and binding

All destinations are existing worksheets. Object creation uses unique names and
never replaces an existing object. The model supplies typed parameters, not COM
member names, VBA, external connections or executable code. Geometry uses Excel
worksheet points.

Each source includes its own complete read snapshot. It must belong to the same
attached workbook and session. Source values/formulas, worksheet identity and
native object inventory participate in preparation and approval binding. The
destination A1 snapshot binds a drawing to its worksheet; PivotTables instead
require a complete snapshot of their reserved blank rectangle. Ordinary edits
still refuse protected, merged, spilled, array, Table and hyperlink cells;
read-only Table cells may supply dashboard sources.

The existing 1,000-cell patch, 16 ordinary changes, byte and recovery-memory
limits remain. A patch can create at most eight native objects. A source range
has at most 1,000 cells. Charts require a text header row and a label/X column;
scatter X values must be numeric. Native PivotTable caches and slicer item
collections are also bounded before creation.

A PivotTable reserve needs at least
`2 * (source_rows - 1) * row_field_count + 8` rows and
`row_field_count + 1` columns. The conservative allowance covers intermediate
native layouts. Reserved cells must be blank and separate from existing pivots,
ordinary patch targets, other PivotTable destinations and object sources in the
same patch. Build calculations first, then read them and create dependent objects.

## Verification and recovery

The adapter reads back native names, geometry, styling, chart series, shape links,
PivotTable fields and slicer connections. A partial or unverified write blocks
further mutations and enters the existing uncertain-outcome review; it is not
retried or rolled back automatically.

Owned creation recovery checks the retained native state and worksheet/source
identities. Shapes, charts and slicers retain native shape IDs; a new PivotTable
receives an ownership tag. These avoid relying on unstable Excel COM collection
wrappers. User changes or object replacement prevent restoration. A connected
slicer must be removed before restoring its PivotTable.

Pivot recovery requires a fresh read of the reserved cells. Native removal clears
the table and may reset data-cell number formats; only the captured original
format is admitted as an alternative to the applied format during that owned
transition. Original captured cells/fills are restored and verified. Deletion of
owned objects returns no redo token. Existing cell-only restoration behavior is
preserved. Excel may retain an unused internal PivotCache after table removal;
the connector does not claim to purge those internal caches.

Saving is still a separate guarded operation. Native saved/reopened feature
checks are distinct from in-memory edit receipts. Recovery handles live only in
the active connection.

## Contract and history compatibility

The tool names and permission classes remain unchanged. The accepted Excel edit
input schema now includes optional `objects` and `fill_color`. Strict live
decoding continues to require the advertised wire shape. A narrow history-only
adapter accepts pre-upgrade evidence missing these fields only when both original
provider bytes and settled calls omit them; original call bytes and identities
are replayed unchanged.

The expanded eight-tool catalog measures **13,860 UTF-8 wire bytes** and **5,004
offline reserve tokens**, under reviewed ceilings of **14,500 bytes / 5,300
reserve tokens**. This updates the schema ceiling for the new typed payloads;
model context policy is unchanged. The accepted manifest, compilation and
whitespace checks pass. No billed-token measurement or provider call was made.

## Qualification

The final focused connector, approval/recovery and affected protocol selection
passed **304 checks in 69.40 seconds**. The initial focused run found one discovery
fixture that expected the old metadata shape; its expected `objects_target` was
updated and the final selection passed. The 4,200-test full suite was not run,
following the user's explicit essential-tests-only instruction.

Both final native gates passed in **35.01 seconds**, with clean shutdown.
Direct-adapter and production-stdio gates use test-owned Excel instances and
synthetic workbooks. They verify fills with theme recovery, a real
PivotTable, linked KPI shape, static text label, chart, slicer, dependent-slicer refusal, object
discovery, filter propagation, save/reopen preservation and owned-object
restoration. Reports retain content-free outcomes, release checks and zero
provider requests. Earlier native findings corrected late-bound PivotTable range
access, separate data fields, linked-shape formula syntax, slicer properties,
COM wrapper ownership and the table-removal format transition. A test-fixture
shutdown warning was addressed by explicitly borrowing the test caller's STA.
The first failed gate's leftover fixture was positively identified by its PID,
synthetic sheet/data/Table fingerprint and released; no user workbook was changed.

Evidence remains under ignored `state/`:

- `excel-dashboard-essential-final.{log,xml}`
- `excel-dashboard-native-labels.{log,xml}` and its repository-local basetemp reports
- `excel-dashboard-objects-contract-final.json`
- `backups/excel-dashboard-objects-20261015/`

Live model/task latency, larger workbook/OLAP/data-model qualification and a
second Office host remain unrun. Passing packaging or deterministic checks does
not claim a model has produced a polished business dashboard.

## Integration and use

Prior main is preserved at
`archive/2026-10-15/main-before-excel-dashboard-objects`. After verification, commit
the bounded change, fast-forward local main and remove only the merged feature
branch. Other worktrees, historical/unmerged tips, remote branches, user settings
and installed skills remain intact.

Restart ORSI and reconnect/select the intended Excel document to load the updated
contract. No skill reinstall is required for this connector change.

## Native API references

- [Microsoft: embedded chart creation](https://learn.microsoft.com/en-us/office/vba/api/excel.chartobjects.add)
- [Microsoft: native shape creation](https://learn.microsoft.com/en-us/office/vba/api/excel.shapes.addshape)
- [Microsoft: local PivotCache creation](https://learn.microsoft.com/en-us/office/vba/api/excel.pivotcaches.create)
- [Microsoft: slicer cache creation](https://learn.microsoft.com/en-us/office/vba/api/excel.slicercaches.add)
- [Microsoft: native slicer creation](https://learn.microsoft.com/en-us/office/vba/api/excel.slicers.add)
- [Microsoft: saved PivotTable tag](https://learn.microsoft.com/en-us/office/vba/api/excel.pivottable.tag)
