# Settings size, dragging and button feedback, 8 October 2026

GUI-only follow-up from local main `2ba4e41`, on
`codex/settings-motion-polish`.

The preferred panel size increases by approximately 10%, from 805 × 555 to
886 × 611. Spacing, navigation and controls increase with it. The smallest text
increases to 12 pixels, row titles to 16, section/navigation labels to 18 and the
main heading to 31. Text uses antialiasing and vertical hinting; animated icons
render directly from vectors, without scaling cached text or bitmap captures.

The header is draggable within the chat window. Dragging moves only the settings
panel, preserves its position through chat/composer layout updates and reopening,
and clamps it within the available area after dragging or resizing. Smaller windows
still use the existing scrollable pages. The setting values and handlers are unchanged.

The settings close button has a larger 32 × 32 hit target, a rounded hover/press
highlight and an immediate pressed response. On activation its icon shrinks and
returns over 200 ms before dismissing the panel. Repeated clicks do not restart the
close delay; Escape can dismiss immediately. The settings cog shrinks while rotating
180 degrees, then returns to its original scale over 320 ms on each opening. Button
hit targets and layout geometry stay fixed throughout feedback. Hiding/closing stops
owned animations; application shutdown behavior remains unchanged.

## Verification

- Expanded focused GUI/settings regression: 89 tests and 5 subtests passed in
  35.32 seconds.
- Final native Windows settings/chat/frame group: 47 tests and 15 subtests passed
  in 12.84 seconds, including panel dragging, native clicks, animation completion,
  interruption, preserved drafts and resize bounds.
- Two preliminary native runs recorded 46 passed and one hover-test failure each.
  A test-window probe located the correct close-button child and active application,
  but OS pointer movement did not reliably deliver Qt enter events. The hover test
  now delivers widget enter/leave events directly and checks the rendered highlight.
  Physical desktop pointer hover is not claimed as a separately passed gate.
- Synthetic panel renders were visually inspected at 1× and 2× scaling and at
  the 760 × 600 minimum window size. Local artifacts are under ignored
  `state/settings-motion-preview/`.
- Compilation and whitespace checks passed.
- Full unrestricted regression with the offscreen Qt backend: 2,394 tests and
  15 subtests passed; 58 optional checks skipped in 329.77 seconds. No failures
  or errors. The native Windows group is recorded separately above.
- Live model/API gates were not run for this GUI-only work. Opt-in/host-dependent
  skips are separate from passed deterministic checks.

The change does not alter prompts, inference, permissions, model profiles or
runtime/user settings. Local integration preserves the previous main tip at
`archive/2026-10-08/main-before-settings-motion-polish`, fast-forwards main after
verification and removes only the merged feature branch. Remote refs and other
worktrees are outside this operation.
