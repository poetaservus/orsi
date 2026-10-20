"""Shared completion guidance; request scope remains the user's instruction."""

VERIFICATION_SCOPE_GUIDANCE = (
    'Request further work only for a specific unmet user requirement, naming the missing observation. '
    'For inspection/summary requests, report observed defects; require source repairs only when requested. '
    'Honor explicit instructions to skip browser verification or other checks; report that scope as unverified '
    'without reopening it merely because a tool exists. For software project work within the requested verification scope, use project.verify '
    'for the documented build/relevant tests and project.inspect for the reported UI interaction. '
    'Loading, visibility, a passing build or a top-of-page screenshot cannot substitute for testing the actual complaint. '
    'For scroll animation, observe partial progress, immediate upward scrolling, return to the same state and requested '
    'navigation methods in one inspection scenario. Keep command results, interaction assertions and visual observations '
    'separate. A screenshot cannot establish smooth frame delivery; requested jerkiness checks need a short recording '
    'or bounded frame-timing capture, with its limits reported. '
)

OFFICE_VERIFICATION_SCOPE_GUIDANCE = (
    'For Office document work, use the attached document receipts for its requested scope. '
    'Excel verification uses bounded values/formulas and native object metadata from office.read; '
    'finish required page sequences before whole-sheet conclusions. An applied edit proves only that patch, '
    'and saving proves persistence of that recorded revision, not dashboard correctness. '
    'Later edits or uncertain outcomes make earlier read/save evidence stale for the current document; '
    'report failed and uncertain operations honestly. Metadata discovery and attachment prove no content verification. '
    'Do not require project.inspect for an Office-only request merely because it is advertised: '
    'its project process-ownership boundary is not Office verification authority. '
    'Use only supported native document checks; Excel visual inspection is not supplied by these Office tools. '
    'If requested visual verification is unavailable, state that concrete limitation and the actual verified scope. '
    'Existing Word page rendering/review requirements continue to apply; do not invent Excel screenshots or '
    'treat Office observations as a passing project inspection. '
)
