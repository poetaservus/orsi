# Office dashboard patches and read packing, 15 October 2026

Native chart/shape/PivotTable/slicer creation and fills were added subsequently;
see [native Excel dashboard creation](excel-dashboard-objects.md). The boundaries
below describe the earlier cell-patch phase.

This bounded change starts from local main `2b771b9` on
`codex/office-dashboard-patches`. A user-created destination worksheet received
static KPI values, then a rejected overlapping Excel patch was repeated until
the turn stopped. The previous adapter rejected every overlap, including ordinary
value-plus-header/currency formatting. It also prohibited sheet-qualified
formulas, so the native tool could not build a source-linked dashboard. Full
used-range reads returned individual cells in 32-item pages, requiring nine
model/tool exchanges for a 36-by-8 source sheet.

## Changes and boundaries

An Excel patch now composes compatible assignments to each unique cell before
review or execution. Disjoint fields and identical assignments can share a
cell; conflicting values, formulas or formatting still reject the entire patch
before any write. One cell is written and recovered once. The exact original
arguments and composed state remain part of approval identity. Existing 16-change,
1,000-cell, single-use approval and uncertain-outcome limits remain intact.

Formula validation now accepts bounded sheet-qualified references within the
attached workbook, with quoted names and escaped apostrophes. Referenced
worksheets receive private retained identities included in the approval digest
and checked before dispatch and each cell write. Replacing a source worksheet
under the same name changes authority and rejects the old guard. Restoration
also verifies the retained source identities. References are capped at 1,024
retained sheet identities per connection and released on reconnect/shutdown.
External workbook/path references, 3D references, defined names, dynamic reference
functions, UDFs and network functions remain rejected. `SUMPRODUCT`, `NUMBERVALUE`
and `CHAR` join the existing pure built-in function subset for ordinary KPI
aggregation and numeric-text handling.

Native qualification exposed another issue: an earlier approved cell write can
recalculate a later target formula during the same patch. Initial preflight
still compares every complete state exactly. After the patch has changed a
value/formula, each later formula's expression and supported formatting remain
exactly checked, while its derived value may recalculate. Literal values remain
exactly checked throughout. Formula/value/format edits, sheet replacement or
uncertain dispatch still stop further writes. No application-wide calculation,
event or alert setting is changed.

Full `SheetName!used` reads now pack contiguous row segments into typed
value/formula matrices with exact range labels. Default pages cover up to 100
cells, within existing item, character and 16-KiB result limits. Private snapshots
retain complete individual-cell coverage for edits, fragments and conflicts.
The 288-cell fixture now needs **three read exchanges instead of nine**. Explicit
rectangular/selection reads retain their previous representation. This reduces
model round trips and repetitive JSON; it is not a measured live-model latency
guarantee.

The existing tool description explains linked dashboard formulas, supported
same-workbook references and overlap composition. Accepted v1 schemas, manifests,
tool names, permissions, user preferences, model profiles, system/acceptance
prompts, routing and context policy are unchanged. Stop reports now include
settled Excel patches, restorations and saves instead of incorrectly implying
that a successful Office mutation never happened.

Worksheet creation, chart creation, column widths, fills and table-cell edits
remain outside this native contract. An existing destination worksheet is still
required. Bounded linked formulas update with their referenced cells; appending
rows outside the referenced range still requires refreshing the data extent and
updating the formulas. Existing static dashboards are not rewritten by this code
change.

## Necessary verification

The final affected Office/agent/approval/recovery-report selection passed
**315 checks in 54.09 seconds**, without failures, errors or skips. It covers
compatible and conflicting overlaps, restoration, quoted same-workbook formulas,
external/3D/dynamic-reference rejection, replaced-sheet authority, packed result
bounds and private edit coverage, native-call permissions, approval ON/OFF,
recalculation within a patch and exact pre-dispatch conflict checks.

One normal-Windows native qualification created only a test-owned workbook and
existing source/destination sheets. Through the production MCP, permission and
executor path it read 288 source cells in three pages, wrote a 16-cell linked
dashboard with overlapping formatting, checked the calculated KPIs, restored
the patch, reapplied it, changed synthetic source values and confirmed that the
KPIs updated. It released its bridge and owned Excel process. The qualification
took **15.94 seconds with zero model/provider requests**; this includes fixture
setup and cleanup and is not an end-to-end app/model benchmark.

The first native restoration attempt exposed the recalculation bug and its
uncertain test outcome was preserved. A subsequent fixture reused that journal
and correctly hit the review gate. Final qualification uses a fresh isolated
test state directory; no real uncertain-operation journal was bypassed or cleared.

The accepted manifest matches. The full contract measures **8,446 wire bytes /
3,200 reserve tokens**, inside its existing 9,000-byte/3,500-token budget.
Compilation and whitespace checks pass. Per the user's instruction, the full
suite was not rerun; live model/provider output quality and end-to-end inference
latency remain unqualified. No user workbook was edited or saved.

Ignored evidence: `state/office-dashboard-essential-final.{log,xml}`,
`state/office-dashboard-native.{log,json}` and
`state/office-dashboard-contract.{log,json}`. Content-free inventories are under
`state/backups/office-dashboard-patches-20261015/`.

Restart ORSI and reconnect Office before retrying on the existing destination
worksheet. Preserve prior main at
`archive/2026-10-15/main-before-office-dashboard-patches`, commit the verified
change, fast-forward local main and remove only the merged feature branch.
Other worktrees, historical/unmerged tips, private settings and remote refs
remain intact.
