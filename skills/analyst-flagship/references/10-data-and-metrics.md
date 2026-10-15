# 10 — Data truth and metric contracts

Read before creating or changing calculations, periods, or analytical claims.

## Profile the relevant source

Establish row grain, key fields, types, date coverage, numeric ranges, missing
values, duplicates, and units. An order, order line, daily snapshot, invoice,
customer, and month are different grains even when columns share names.

Preserve identifier text: leading zeros and long account codes are not numeric
measures. Distinguish true dates from ambiguous text and locale-specific parsing.
Check whether timestamps share a timezone or business cutoff when day boundaries
matter. Do not guess conversions for mixed currencies or incompatible units.

Read and aggregate at the declared coverage. Record whether totals are based on
all relevant rows, a selected period, or a sample. A sample can reveal a type
problem but cannot establish a complete total or absence of rare exceptions.
Avoid treating subtotal/header rows as transactions.

Do not remove duplicates on appearance alone. Repeated order IDs may represent
valid order lines; repeated snapshots may be intentional observations. Resolve
which keys define uniqueness before deduplicating or counting entities.

## Give each displayed measure a contract

For a substantive dashboard, retain enough information to reconstruct each KPI:

| Field | Decision it resolves |
| --- | --- |
| Definition and source | Exactly what is measured, from which field/table |
| Grain and aggregation | Sum, distinct entity count, ratio, weighted average, latest snapshot |
| Unit and precision | Currency, quantity, percent, duration, percentage points |
| Period and date basis | Calendar/fiscal period; order, invoice, service, or delivery date |
| Comparison | Comparable prior period, target, baseline, or no comparison |
| Filter scope | Which selectors affect the value and its denominator |
| Interpretation | Whether higher/lower is better and how status is justified |

Keep the record proportional: a methods note can suffice for a small workbook.
Do not create a large dictionary for three obvious measures.

## Aggregation traps

- **Ratios:** total margin is total gross profit divided by total revenue, not
  the arithmetic average of row margins. Weight rates by the appropriate
  exposure, not by the number of visible rows.
- **Entity counts:** count orders/customers at their identity grain. Distinct
  counts across segments are not necessarily additive.
- **Snapshots:** inventory, balances, and headcount often describe a point in
  time. Do not sum daily balances into a monthly balance.
- **Targets:** a monthly regional target joined to every transaction becomes
  duplicated. Aggregate actuals and targets at compatible grains or use a model
  that preserves the target grain.
- **Joins:** verify key uniqueness and unmatched records; a many-to-many merge
  can multiply amounts while leaving plausible-looking rows.
- **Currency and units:** label one currency/unit per measure or apply an agreed
  conversion basis. Never silently add incompatible amounts.

## Comparisons that mean what they say

Verify the source date type and date system. For monthly buckets, use first-of-
month starts and exclusive next-month ends, such as `DATE(2026,1,1)` through
`<DATE(2026,2,1)`. Generate subsequent boundaries with date functions or a reliable
date library; never guess serials or add 30/31 days. Format the labels as dates.
Check boundary rows and reconcile all buckets, including stated exclusions, to
the headline total before proceeding to styling.

Verify coverage from the source and reporting cutoff; the last transaction alone
does not prove completeness. Label partial months beside the trend or affected
KPI. Compare equal elapsed periods only when history and cutoff support it;
otherwise leave the comparison unavailable. Do not infer deterioration by
comparing month-to-date with a full month. Calendar and fiscal periods differ.
Use Period total, YTD, or Full-year total only when the covered dates justify it.

For positive, meaningful denominators, relative change is
`(current - prior) / prior`. When prior is zero, missing, or negative, decide how
the business interprets change; do not produce an impressive infinite growth
claim. Show an absolute change or an explained unavailable comparison where
appropriate.

From 20% to 25% is **+5 percentage points** and **+25% relative change**. Label the
one being shown. An increase in defect rate is not automatically a green arrow.

## Performance status, trend, and missing comparisons

Choose the supported interpretation for each relevant KPI:

| Basis | Display |
| --- | --- |
| Authoritative target/rule with defined bands | Red/orange/green with status text, target/variance, and a discoverable rule |
| Comparable history, no performance rule | Computed change/arrow labeled versus that period; neutral color unless good/bad is justified |
| No valid benchmark/history | Keep the observed value; show Target not set or Comparison unavailable where expected |

Targets alone do not define three status bands. Use thresholds from the user,
existing workbook, or an explicit assumption accepted for this task; never invent
a 90/95% scheme. Record direction, boundary inclusivity, period and filter scope.
Low revenue rank is not failure; high cost or defect growth is not improvement.
Do not duplicate the same missing-target badge on every card if one clear shared
note suffices. A descriptive dashboard need not imply that targets are required.

## Missing values and errors

Keep zero, blank, unavailable, and not applicable distinct. Decide how a true
no-record result should display for each metric. An unknown margin denominator
should not become 0% through an indiscriminate `IFERROR(...,0)` wrapper.

Handle expected boundary conditions deliberately. Investigate unexpected formula
errors, broken links, and type failures rather than hiding them behind blanks.
Missing dates should not silently disappear from reporting; keep an explicit
unassigned category or report the exclusion.

## Reconcile before styling

Reconcile key totals with an independent calculation from the same admitted
source coverage. Check a known subset and an edge case as well as the all-data
total. For ratios, reconcile numerator and denominator separately. For targets,
check that segmentation and date selection do not duplicate or drop values.

When the task permits a synthetic example, one useful check is two rows with
revenue 100/900 and gross profit 50/90: overall margin is 140/1000 = 14%, not the
30% average of 50% and 10%. This is test data, not a business benchmark.

Read [40 — Excel model and refresh](40-excel-model-and-refresh.md) for implementation
choices and [50 — Filters and states](50-filters-and-states.md) for denominator
and selector behavior.
