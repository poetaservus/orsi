# 50 — Filters, selectors, and truthful states

Read when implementing or reviewing slicers, period selectors, drilldown, or
data availability. A dashboard control must change a meaningful result.

## Define selector scope

For each selector, establish its field, valid values, initial state, affected
metrics/visuals, comparison-period behavior, and reset path. Keep the current
period and segmentation visible without requiring the user to remember clicks.

Use common selectors together when they share a scope. Do not place duplicate
date controls on every chart simply to make the surface look interactive. Use a
separate local selector only when it answers a distinct question, with a label
that makes the scope clear.

Choose dimensions from the data and decision. Region, Channel, Category, Manager,
and Rep are not mandatory slicers. A high-cardinality identifier often belongs
in search or an exact-detail table rather than an enormous slicer rail.

## Use controls the workbook can support

- **PivotTable slicers:** create/connect only through supported tools. Check the
  intended PivotTables in Report Connections. Shared-source compatibility does
  not prove that every intended report is actually connected.
- **Table filters/slicers:** verify the effect on the source rows and every
  downstream calculation. A worksheet formula may still include hidden rows.
- **Data-validation or input-cell selectors:** wire the selected values into
  real formula criteria and labels. Validation alone does not filter a chart.
- **Existing control systems:** preserve their semantics and requested behavior
  rather than replacing them with a visual imitation.

If a control type is unavailable, choose an actually supported alternative that
preserves the needed decision, or state the unsupported part. Never draw a fake
slicer, drop-down arrow, Refresh button, or tab and claim it works. Do not add
VBA, scripts, or external services purely to rescue a decorative control.

If an All option is implemented in formula criteria, ensure it cannot collide
with a real category and that blanks/unassigned rows receive intentional handling.
If multi-selection is unsupported, do not imply that a single cell implements it.

## Cross-filtering and time context

Check the complete selected context, not one chart in isolation. A selector can
correctly change revenue while leaving the numerator of margin or plan unchanged.
Reconcile both components and the comparison after selection.

For a monthly selection with a year trend, choose deliberately: retain the year
trend and highlight the selected month, or show a selected-month detail view.
Label a trend that intentionally ignores the Month filter. Do not silently
disconnect it, or let the line collapse into one unexplained point.

For prior-period comparisons, define whether non-date filters carry over and
whether the period shifts independently of the current date filter. Targets and
actuals need compatible time and dimension scope.

## Relevant states

| Condition | Honest presentation |
| --- | --- |
| No records in the selected slice | Say which selection produced no records; make reset reachable |
| Known zero result | Show a numeric zero with its normal unit and meaning |
| Missing target/history | Mark the comparison unavailable; keep the observed value |
| Stale source | Show the last verified source/refresh basis and freshness limitation |
| Failed refresh/calculation | Preserve usable last-known results if appropriate; identify what failed |
| Read-only or unavailable operation | Explain the supported scope without a fake enabled control |
| Long labels, large values, new categories | Preserve legibility and stable category meaning |

A static workbook does not need invented web loading skeletons or pagination
states. Implement states that the actual Excel workflow can enter. Avoid a
generic No data panel when the cause and useful next action are known.

## Verify cause and effect

When authorized and supported, test one known subset, a different or combined
selection, a no-record result if the data allows it, and clearing the filter.
Check displayed values, labels, charts, detail rows, and comparison denominators.
Restore the user's intended final selection after the check.

Do not mutate production source rows solely to test a filter. Use existing known
subsets, an isolated copy, or authorized reversible changes. Inspect the saved
default selection on reopen when saving/reopening is in scope.

For discrepancies, trace the specific control, connection, formula criteria,
range, and cache before changing formatting. Read [40 — Excel model and refresh](40-excel-model-and-refresh.md)
and [80 — Review and evidence](80-review-and-evidence.md) as needed.
