# 00 — Analytical foundations

Read for the brief, audience, scope, and decisions that precede a build.

## Define the decision

Translate the brief into a useful question: which orders need intervention;
where margin missed plan; which stock creates service risk; whether comparable
cohorts retained better. Identify the audience and review cadence. Operators need
exceptions, identifiers, owners, and next steps; executives need outcomes and
drivers; analysts need segmentation and auditable detail. Different levels can
coexist without putting everything on one screen.

Use the entry point's three dials to resolve tradeoffs. Preserve familiar Excel
interaction: visual character must not make sorting or clearing a filter harder.

## Inspect before asking

Inspect existing dashboards, source Tables/ranges, calculation areas, charts,
controls, queries, and notes through supported tools. Check representative values
and row grain; existing business definitions outrank generic industry examples.

For complete-data requests, discover the extent and finish the relevant bounded
pages without omissions or duplication. A first page is not a complete source.
Large sources may need supported aggregation instead of cell-by-cell model input;
make that method and its coverage clear.

Ask about consequential unknowns: net/gross sales, fiscal calendars, duplicates,
mixed currencies, authoritative targets, or source-edit permission. Infer routine
visual decisions and a useful dashboard approach from the available data. Missing
targets need not stop descriptive reporting or trigger a questions-only gate.

## Respect the requested mode

| Mode | Work to do | Preserve |
| --- | --- | --- |
| New build | Definitions, dependencies, layout | Sources and unrelated features |
| Analytical repair | Reproduce and fix calculation/filter defects | Working unrelated results and styling |
| Visual polish | Hierarchy, geometry, readability, color | Values, formulas, relationships, interactions |
| Critique only | Prioritized findings with evidence | Workbook contents and state |
| Requested prototype | Agreed workflow with labeled synthetic data | Distinction from business results |

Do not migrate a model during polish or rewrite sources merely for convenience.
Identify out-of-scope analytical defects and their consequences instead of
silently changing business definitions.

## Make uncertainty visible

Separate observed facts, calculations, hypotheses, and recommendations. A lower
conversion rate is observable; its cause needs evidence. Do not invent targets,
benchmarks, forecasts, or explanations to complete a card. Keep no events,
missing values, unavailable comparisons, stale data, and failed queries distinct.

## Keep the work proportional

A small dashboard may need one source, a summary, and a few views. Add model
layers, administrative sheets, macros, or documentation only for a real need.
Read [10 — Data and metrics](10-data-and-metrics.md) for definitions and profiling,
and [90 — Analytical patterns](90-analytical-patterns.md) for domain questions.
Patterns guide selection; they do not supply facts or targets.
