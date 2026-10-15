# 90 — Analytical patterns by decision

Read to select a business blueprint. These patterns supply questions and traps,
not facts, thresholds, mandatory KPIs, palettes, or chart counts. Prefer the
user's existing definitions and keep one coherent primary view with reachable
detail. Use [10 — Data and metrics](10-data-and-metrics.md) for calculation logic
and [30 — Charts and comparisons](30-charts-and-comparisons.md) for encoding.

## Sales and commercial execution

Decision: where is performance off plan, and which segment/account needs
attention? Consider actual versus comparable plan, trend, largest variance
contributors, and exact account/order exceptions.

Confirm gross/net revenue, returns, currency, date basis, and target allocation.
Monthly targets must not repeat per transaction. Distinct customers can overlap
across segments. Pair revenue with profitable growth when margin is available.
Choose slicers from the decision rather than adding every familiar sales field.

## Finance and management review

Decision: what changed against plan/prior period, and what explains the material
variance? Consider outcome versus plan, additive variance drivers, and detail.

Preserve fiscal periods, accounting definitions, sign conventions, currencies,
and consolidation rules. Revenue, profit, cash flow, and balances are different
measures; do not sum a balance over time as if it were a flow. Negative-base
comparisons require interpretation. Do not invent materiality limits, exchange
rates, or accounting adjustments for visual convenience.

## Operations and service

Decision: what needs action, by whom, before when? A ranked exception table can
lead; throughput, backlog, cycle time, and service attainment provide context.

Define overdue/SLA eligibility and the start/end event for durations. Backlog is
a stock, incoming work is a flow. Weight team rates by eligible cases. Averages
can conceal long-tail delays; use distributions/percentiles only when correctly
supported. Do not invent owners, action logs, or service targets.

## Inventory and supply

Decision: where do shortage, excess, age, or concentration create risk? Consider
ranked exposure, coverage/aging distribution, and SKU/location detail.

Confirm snapshot date, product/location grain, available versus on-hand stock,
committed quantity, units, and demand horizon. Do not sum snapshots across dates.
Days of cover needs a valid demand rate; zero/missing demand is not an arbitrary
huge coverage value. Reorder and aging rules need an authoritative basis. With
only a current snapshot, do not manufacture a trend or forecast.

## Product, funnel, and cohorts

Decision: which population/stage changed and deserves investigation? Consider a
consistent funnel, comparable retention cohorts, and diagnostic detail.

Define identity, eligibility, event window, cohort entry, and retained activity.
Sequential stage populations must be comparable. Recent cohorts have fewer
observed periods; future cells are not zero retention. Preserve the denominator
after segmentation. A subgroup's share of all users differs from within-group
conversion. Observational comparisons do not establish causation.

## Choose and adapt

When the brief is clear, select a suitable composition and proceed. When two
materially different decisions remain plausible, offer a concise choice or ask
the missing question. Do not pack every pattern into one dashboard or require a
blueprint approval ceremony for routine work.
