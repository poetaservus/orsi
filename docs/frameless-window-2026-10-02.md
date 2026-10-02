# Borderless window

The UI candidate on `codex/response-formatting` removes the Windows title bar while retaining
the existing chat surface and response formatting. Three neutral controls remain visible at
the top right. The empty upper strip is a native caption drag area; buttons and the revealed
toolbar remain interactive. The toolbar reserves room for the controls.

`app/ui/window_frame.py` retains Windows caption, sizing, system-menu, minimize and maximize
styles, handles native caption/edge hit tests, and removes the visible non-client frame with
`WM_NCCALCSIZE`. Maximized content fits the selected monitor's work area. Native hover messages
still reveal the existing toolbar. Signed screen coordinates and device-pixel conversion avoid
assuming that every monitor starts at zero or has 100% scaling.

Windows maximize/restore controls use `ShowWindow`. The initial native test found that Qt's
`showNormal()` after a Windows caption double-click cleared Qt's state without clearing the
native maximized state. Using the Windows operation resolves this, including minimize/restore
from a maximized window. Other platforms/offscreen tests use Qt controls and native system move.
The close button calls the existing close path, preserving cancellation and worker/model cleanup.

Verification:

- Full regression: 834 passed, 54 skipped, 15 subtests passed in 130.91 seconds.
  Log: ignored `state/frameless-regression.log`.
- UI/frame/shutdown checks: 45 passed, 15 subtests passed. Log:
  ignored `state/frameless-focused.log`.
- Final targeted checks after the native hover guard and active-worker close-button test:
  9 passed, 10 subtests passed.
- Actual Windows subprocess checks at 100% and 150% scaling verify that client and window
  dimensions match without a title bar, caption and corner resize hits, control hit exclusions,
  native caption double-click, monitor work-area maximization, restore geometry, minimize,
  restore from minimized/maximized state, system-menu close, toolbar reveal, and retained Snap
  styles. They load no model, settings store, or saved conversation.
- Synthetic preview: ignored `state/frameless-window-preview.png`.

Interactive drag-to-Snap and Windows 11 Snap-layout popups were not automated. Native caption
and sizing operations are delegated to Windows; custom maximize buttons do not implement the
Windows 11 hover popup. Mixed-monitor DPI transitions remain a manual check.

The full required per-model live qualification matrix was not rerun. Skipped live gates are
not evidence of qualification, and this change does not promote the candidate to main.
