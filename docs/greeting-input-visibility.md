# Greeting input visibility, 8 October 2026

Bounded GUI fix from local main `d1dfcb7` on
`codex/greeting-input-visibility`. General now gives Greeting a dedicated
full-width input beneath its label and description, rather than a compact
right-hand control. The input has a 44-pixel height, 16-pixel text, a clearer
border, hover/focus feedback, a placeholder and an accessible name.

The existing greeting text-change, normalization and preference-saving handlers
remain in place. No preference migration or runtime-store replacement occurs.
Verification uses isolated preference files, including an unrelated preference
that must survive editing.

- Native Windows focused GUI checks: 45 tests and five subtests passed in
  12.64 seconds.
- The new interaction check verifies the entire input is visible, enabled,
  unobstructed and clickable at 1280 × 800 and 760 × 600. Actual keyboard edits
  update the welcome message, save on focus exit and restore after reopening.
  Switching tabs and reopening Settings retains the input and its value.
- Synthetic normal/compact panel renders were visually inspected under
  ignored `state/greeting-field-preview/`.
- Compilation and whitespace checks passed.
- Full unrestricted native Windows regression: 2,399 tests and 15 subtests
  passed in 371.53 seconds, with no failures/errors. The 58 skipped opt-in
  model/cloud and host-dependent symlink gates are recorded separately.
- Live model/API gates are outside this GUI fix and were not run.

Before local integration, preserve main at
`archive/2026-10-08/main-before-greeting-input-visibility`. Commit the verified
fix, fast-forward local main and remove only its merged feature branch. Other
worktrees and remote branches remain outside the operation.
