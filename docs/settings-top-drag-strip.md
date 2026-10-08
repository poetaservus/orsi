# Settings top-edge drag area, 8 October 2026

GUI-only correction from main `51aecbb` on `codex/settings-top-drag-strip`.
Dragging moves from the title/header row to an independent 18-pixel strip at the
very top of the panel, inside its rounded corners. The title and close button
sit below that strip. The close button explicitly uses the normal arrow cursor,
instead of inheriting the drag cursor. Its hover and click animation are retained.
The strip resizes with the panel, and existing drag bounds and position retention
continue to apply. Settings, runtime state and model behavior are unchanged.

- Native Windows focused GUI/frame checks: 48 tests and 15 subtests passed in
  14.97 seconds. Checks verify top-edge hit testing, separate close-button and
  drag regions at normal/minimum sizes, cursor ownership, close activation,
  actual panel movement, retained positions, bounds and existing animations.
- Compilation and whitespace checks passed.
- Full unrestricted regression with the offscreen Qt backend: 2,395 tests and
  15 subtests passed; 58 optional checks skipped in 347.27 seconds. No failures
  or errors. Native Windows results are recorded separately above.
- No live model/API gates were run. Opt-in/host-dependent skips remain separate
  from passed deterministic checks. Local verification artifacts are under
  ignored `state/settings-top-drag-preview/`.

Integration preserves prior main at
`archive/2026-10-08/main-before-settings-top-drag-strip`, fast-forwards local main
and removes only this merged feature branch. Remote refs and other worktrees
are outside the change.
