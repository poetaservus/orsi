"""Shared completion guidance; request scope remains the user's instruction."""

VERIFICATION_SCOPE_GUIDANCE = (
    'Request further work only for a specific unmet user requirement, naming the missing observation. '
    'Honor explicit instructions to skip browser verification or other checks; report that scope as unverified '
    'without reopening it merely because a tool exists. Within the requested verification scope, use project.verify '
    'for the documented build/relevant tests and project.inspect for the reported UI interaction. '
    'Loading, visibility, a passing build or a top-of-page screenshot cannot substitute for testing the actual complaint. '
    'For scroll animation, observe partial progress, immediate upward scrolling, return to the same state and requested '
    'navigation methods in one inspection scenario. Keep command results, interaction assertions and visual observations '
    'separate. A screenshot cannot establish smooth frame delivery; requested jerkiness checks need a short recording '
    'or bounded frame-timing capture, with its limits reported. '
)
