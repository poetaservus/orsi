# 40 — Excel calculation and refresh architecture

Read when choosing or modifying formulas, Tables, PivotTables, queries, or a Data
Model. Preserve a working architecture unless the request requires changing it.

## Choose the smallest sufficient route

| Situation | Possible route | Boundary |
| --- | --- | --- |
| Small, stable source and a few selectors | Excel Table or bounded ranges, formulas, linked charts | Check formula grammar, range growth, and selector semantics |
| Repeated aggregation by several dimensions | PivotTables and PivotCharts | Verify source/caches, refresh, and filter connections |
| Repeatable file import, cleaning, reshaping | Power Query feeding a Table or model | Preserve data types, source paths, errors, and refresh permissions |
| Multiple related facts/dimensions or complex filter measures | Data Model/Power Pivot with explicit measures | Verify grain, relationships, filter context, and platform support |
| Existing advanced workbook | Its established native route | Avoid a destructive round trip through an incompatible file library |

Power Query, Power Pivot, and DAX are options for real needs, not a mandatory
stack for every dashboard. A refreshable workbook is one whose dependencies
actually update; complexity alone does not make it refreshable.

Keep raw/source, calculations, and presentation conceptually distinct. Separate
sheets when that improves maintenance, not as a ceremonial sheet-count target.
Use clear names while preserving existing external references and user workflows.

## Formulas and numeric types

Use formulas or model measures for results that should change with inputs.
Write numeric values as numbers, dates as suitable date values, and identifiers
as text. Apply number formats to display currency, percent, units, and precision.
Do not replace formulas with cached values during formatting or analysis.

Prefer readable bounded ranges or structured references where the actual tool
supports them. Tables can expand and update structured references in Excel;
verify that an append through the chosen tool also updates the Table range and
downstream results. Writing cells beyond the range through a file library does
not prove that the Table or chart expanded.

Use the formula dialect accepted by the tool. OOXML/openpyxl formulas use English
function names and comma separators; native Excel interfaces may expose local
formula conventions or narrower grammar. Do not invent support for named ranges,
structured references, cross-sheet references, dynamic arrays, or DAX just
because Excel itself supports them. Check the advertised write contract.

Examples below are templates only when a real Table named Orders with the stated
columns exists and the host supports these formulas:

- Revenue: `=SUM(Orders[NetRevenue])`
- Aggregate margin: `=IF(SUM(Orders[NetRevenue])=0,NA(),SUM(Orders[GrossProfit])/SUM(Orders[NetRevenue]))`
- Visible-row revenue when that is the intended contract:
  `=SUBTOTAL(109,Orders[NetRevenue])`

The NA result marks an unavailable ratio; decide how to display it for the
audience instead of presenting a false 0%. Confirm the engine and chart's actual
handling of unavailable values. These examples are not a reason to change a
working workbook's existing method.

## Filter contexts are different

Ordinary SUM and SUMIFS calculations do not become visible-row calculations
merely because AutoFilter hides source rows. SUBTOTAL excludes filtered-out rows;
its 101–111 function numbers also exclude manually hidden rows. Choose the
behavior required by the dashboard, rather than mixing them accidentally.

A PivotTable slicer filters its connected PivotTables. It does not automatically
rewrite a separate worksheet formula's criteria. Likewise, a model measure's
filter context is not the same as a source Table's hidden-row state. Connect or
calculate each displayed value using an explicit shared scope.

## Relationships and targets

Keep dimensions unique on the intended relationship key. Profile missing keys
and unmatched facts. Do not manufacture a many-to-many relationship to suppress
an error without understanding the resulting totals.

Treat transaction-level actuals and monthly targets as different fact grains.
Joining a regional monthly target to every order line can duplicate plan values.
Use compatible aggregation or suitable dimensions and measures. Check both the
overall total and a selected subset.

For model measures, handle empty denominators and aggregation at the model level
where appropriate. Use the existing calendar and fiscal conventions. Validate
time-intelligence assumptions rather than assuming a date column automatically
provides a valid calendar table.

## Refresh as a dependency chain

Trace source → transformation → loaded table/model → calculation/PivotTable →
chart/KPI. Refresh in the required order using supported tools, wait for relevant
work to finish, and verify a changed source value reaches the final display.
A successful refresh command or changed timestamp alone is insufficient.

Distinguish source update time, completed refresh time, and calculation time.
Do not write NOW() beside Last refreshed and imply it proves data freshness.
If a connection is unavailable, retain truthful last-known data and a visible
limitation rather than inventing a successful update.

Do not change credentials, enable external connections, or add remote services
as an implicit part of dashboard styling. Prefer existing authorized sources.

## Calculation and file-library limits

openpyxl stores formulas but does not evaluate them. Loading with data_only=True
returns cached results where present and is for reading those values; saving that
representation can destroy formulas. A saved formula or an automatic-calculation
flag is not proof that current numeric results have been calculated.

Use a suitable available calculation engine for result verification. Do not force
a LibreOffice round trip through a workbook with unsupported Excel-specific
features. Preserve .xlsm content through a suitable route; keep_vba=True is not a
guarantee that every drawing, slicer, query, or other feature survives.

Read [60 — Workbook implementation](60-workbook-implementation.md) for feature
preservation and [80 — Review and evidence](80-review-and-evidence.md) for an
authorized, reversible update/refresh check.
