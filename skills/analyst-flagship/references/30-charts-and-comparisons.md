# 30 — Charts and honest comparisons

Read when selecting, changing, or reviewing charts and visual encodings.

## Start with the question

Write the comparison the visual needs to answer before choosing its type. If a
single value and a sentence answer it better, a chart is unnecessary. If exact
values and identifiers matter, retain a table even when a chart supplies context.

| Question | Useful starting view | Check |
| --- | --- | --- |
| Which categories are largest or most at risk? | Sorted horizontal bars or ranked table | Sorting, category labels, full comparison population |
| How did a measure change over time? | Line chart; columns for discrete period totals | Dates, gaps, period completeness, consistent aggregation |
| How far are we from plan? | Actual/target comparison or variance bars | Compatible grain, units, and signed variance |
| What contributes to a total or change? | Ranked contributions; waterfall if supported | Reconciled start/end, additive components |
| How is a distribution shaped? | Histogram or box plot if supported | Bins, sample size, outliers, comparable populations |
| Are two numeric measures associated? | Scatter plot | Correct X/Y pairing; association is not causation |
| How does performance vary across cohorts/periods? | Matrix or restrained heatmap | Cohort definitions, maturity, denominator, missing cells |
| What share does each category represent? | Ranked bars or a simple part-to-whole view | Shares reconcile; negative values and tiny segments are unsuitable for pies |

Use native supported chart types. If a specialized visual is unavailable, choose
a simpler honest representation and describe the difference. Do not invent a
chart-creation tool or use a pasted image as an undisclosed interactive substitute.

Give charts visual character with coordinated series colors, deliberate marker
sizes, clean plot areas, selective labels, and aligned module frames. Combine
different types when they answer different questions: for example, a broad trend,
ranked region bars, and a compact category-share view. Native PivotCharts and
manually formatted supporting tables are welcome. Chart variety is a design
opportunity, not a requirement to add redundant views.

## Scale and encoding

Bars encode length: use a zero baseline so lengths remain comparable. Line and
scatter charts may use a narrower scale when it clarifies variation, with clearly
labeled limits and an explanation if the scale could mislead. Never crop an axis
to manufacture a dramatic result. Use log scales only for appropriate positive
data, a genuine analytical reason, and an audience that can interpret them.

Keep repeated small charts on comparable scales when comparisons depend on
height. If scales differ for a reason, label them. A dual-axis chart can suggest
a relationship through arbitrary scaling; prefer separate aligned panels unless
the two axes are necessary and unmistakably labeled.

Encode values with position/length before decorative volume. Keep expressive
surfaces and accents when they aid the composition; avoid perspective, bevels,
exploded slices, or effects that distort values or reduce legibility.

## Titles and labels

Show the measure, unit, time basis, and relevant selected context. An insight
title is useful only when the statement remains true after filtering or is
updated with the data. Otherwise use a precise neutral question or label.

Place labels directly where they reduce legend hunting. Avoid labeling every
point in a dense time series. Use an accessible legend when it is clearer. Keep
category colors stable across views and selected subsets. Do not rely on color
alone for actual/target, good/bad, or selected/unselected meaning.

Retain enough precision for the decision. Put a shared unit such as EUR thousands
or hours in a stable label. A compact summary can show rounded values while the
detail table retains exact values; make the difference understandable.

Check axis and series ranges: headers must not become data, category counts must
match points, and the last intended row/period must be included. Native chart
links should point to refreshable summaries or model results, not frozen copies
of displayed values.

## Time and filter behavior

Distinguish a missing observation from a true zero and a future period. Do not
fill gaps with zeros or interpolate without an analytical basis. Identify partial
periods near the affected point/title, not only in a distant footnote. Use a
supported annotation or distinct marker/column treatment where useful. Omit
future months unless a calendar view adds meaning; retain blanks rather than
drawing a fall to zero. Do not compare partial totals with full-period totals.

A Month selector should not turn a year trend into a mysterious isolated point.
Either retain the useful year context and label its scope, or clearly present a
selected-month detail view. A chart deliberately unaffected by a filter must say
so; accidental disconnected visuals are defects.

For top-N views, state whether ranking is recomputed after selection. Do not
compare a changing top-N population as if the entities were fixed. Combine a
long tail as Other only when the aggregation is meaningful and auditable.

## Conditional formatting is analysis

Choose formatting from a defined question: target breach, overdue age,
out-of-stock risk, unusual variance, or concentration. Tie thresholds to the
metric contract in [10 — Data and metrics](10-data-and-metrics.md). Red/orange/green
needs defined bands; display the status in words as well as color. Check exact
threshold boundaries and missing values. Reverse good/bad logic when lower is
better; a neutral trend arrow need not imply a performance judgment.

Color scales are relative to the chosen range; they are not absolute performance
ratings. Keep blank and unavailable values out of a fake bad-performance class.
Data bars need consistent scale across comparable rows. Add text or a numeric
column for the exact value and status.

## Forecasts and annotation

Do not add forecasts, causal claims, or arbitrary trend projections for visual
completeness. If requested, state the basis, history coverage, assumptions, and
uncertainty, and separate projected from observed data. An annotation should
explain a supported event or definition, not invent a story behind a spike.

Read [50 — Filters and states](50-filters-and-states.md) for interaction scope,
and [80 — Review and evidence](80-review-and-evidence.md) for chart verification.
