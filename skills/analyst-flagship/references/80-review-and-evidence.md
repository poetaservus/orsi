# 80 — Bounded review and evidence

Read before completing substantial work. Review actual outcomes, including the
requested visual ambition, rather than trusting a self-rating.

## One inspection, a repair batch, a confirmation

Collect defects across the workbook and relevant views. Prioritize wrong values,
data loss, misleading comparisons, and broken controls. For a creative/design
brief, also treat a visibly generic or insufficiently composed result as an
unmet requirement. Fix observed issues together, then confirm affected results.

Continue beyond this cycle for an observed blocking defect or a new failure from
the fixes. Stop speculative cosmetic churn. State unresolved blockers when they
cannot be corrected within the supported scope; do not quietly accept them.

## Evidence categories

| Category | Useful evidence | Insufficient by itself |
| --- | --- | --- |
| Metric logic | Reconciled totals/subsets at the admitted grain | Plausible KPI or first-page sample |
| Calculation | Values evaluated by a suitable available engine | Formula text or auto-calc flag |
| Interaction | Observed selector effects and reset | A visible control or formula pattern |
| Refresh | Changed input reaches the output after refresh | Command receipt or current clock |
| Visual | Inspected workbook at relevant view/zoom | Styles, object sizes, or source code |
| Preservation | Relevant before/after values, formulas, and features | Successful save |
| Persistence | Saved artifact read/reopen where supported | In-memory edit or preview image |

Report verified, unavailable/unrun, or failed categories with material coverage
limits. An unavailable check is neither a pass nor evidence of a defect.

## Data and calculation

Reconcile totals, entity counts, and ratio components to the same source coverage
and selected context. Check join multiplication, target grain, units/currencies,
partial periods, comparison bases, percentage-point versus relative change, and
whether higher/lower is better. Check status bands at their boundaries and keep
missing benchmarks neutral. Confirm partial-period labels, total captions, and
whole-number entity counts. Include a relevant edge condition such as no records,
a zero denominator, missing target/history, or a long identifier.
Investigate unexpected errors; do not conceal them behind error-to-zero wrappers.

## Interaction and refresh

Check all data, a known subset, a changed/combined selection, and reset as useful.
Inspect KPIs, denominators, charts, period labels, detail rows, and intended
connections together. A year-context trend may deliberately ignore Month only
when labeled. Category colors must retain their meaning after selection.

For updateable workbooks, verify range growth/refresh through an authorized
reversible change or isolated copy where practical. Check source-to-display
propagation, then restore and confirm the test change. Do not mutate production
source merely to create a test or call a changed timestamp refresh proof.

## Visual craft and anti-slop

Inspect the actual rendering when supported, at normal reading size:

- The primary decision and visual focal point are clear.
- KPI cards have deliberate geometry, hierarchy, spacing, and live values. A
  coordinated row is valid; emphasis reflects actual importance.
- Colors, native shapes, icons, and subtle effects serve one authored direction.
  Preserve attractive choices rather than stripping them into a plain worksheet.
- Requested creative changes are visible. A new header color alone is insufficient
  when the user asked for richer cards, chart variety, slicers, and table design.
- Main charts and controls form a connected first view with the KPIs. Helper
  summaries, long notes, and empty gaps do not displace the analytical surface.
- Check the complete sheet for clipped/overlapping modules and wasted space;
  inspect the initial window and detail route at a readable zoom.
- Chart types answer distinct questions; labels, axes, units, legends, and table
  detail are readable. Slicers and manually styled tables belong to the same system.
- Arrows/statuses are data-backed; no fabricated metrics, arbitrary counters,
  fake controls, or static images presented as interactive visuals survive.

Use [20 — Composition and taste](20-composition-and-taste.md) for positive design
recipes. Improve composition before adding more objects. Heuristic scores cannot
establish usefulness, analytical correctness, or visual quality by themselves.

## Preservation and delivery

Verify scope: polish preserves relevant formulas/values/source; repairs preserve
working unrelated results. Check native features at risk from the chosen route,
including drawings, macros, filters, and connections. Confirm the requested
format/destination and saved artifact where supported. Leave the intended sheet
and selection useful; release only task-owned resources.

Complete means essential requested behavior and visual treatment are implemented
with no observed blocking defect. If tools deliver a subset, name it and the
remaining work. Briefly report changes, actual checks, and unverified categories.
Do not claim native construction, evaluated results, visual inspection, refresh,
or persistence from evidence that establishes only a plan or partial patch.
