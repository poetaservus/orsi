# Full-window Settings, 14 October 2026

Settings now fills the application window, replacing the independently draggable
1120 × 740 panel. It remains the same navigation, pages, fields, buttons, profile
tabs, colors and action handlers. The native caption band keeps its existing
move, resize, minimize, maximize and close controls. The Settings close button
and Escape return to chat.

The Settings view is a sibling of the chat root. A temporary Qt blur effect
softens the actual chat behind it; Settings and the reused window controls remain
sharp. A uniform translucent tint maintains the current theme's contrast. The
Settings gradient, outer floating border and rounded panel corners are gone.
The chat background itself and theme palettes are unchanged.

Body/control text grows from 14 to 16 pixels in normal windows. Section labels
grow by the same two pixels, retaining the existing hierarchy. Below 900 pixels
wide, the increase is one pixel so the existing compact profile controls continue
to fit. Typography is derived from original stylesheet sources, so reopening or
switching themes cannot accumulate increases. App-owned dialogs and chat keep
their existing font sizes. Control dimensions stay the same; the compact sound
picker loses excess right padding so its default name fits at the larger size.

While Settings is visible, the covered chat root is disabled for keyboard input.
The same window-control and caption-strip instances are temporarily parented
above it. Hiding Settings removes the owned blur, restores their parents and the
root's prior enabled state, and returns focus where possible. Explicit disabled
states from active work remain disabled. Profile lock, window close and worker
shutdown use the same cleanup path. No chat images are saved for the blur.

The accepted GUI-language work is integrated locally at `4619c92`; this bounded
presentation change starts from that local main on `codex/settings-full-window`.
Before integration, preserve main's tip, commit the verified change, fast-forward
local main and remove only its merged feature branch. Historical refs, other
worktrees and remote refs are outside this change. Inventory snapshots are under
ignored `state/backups/settings-full-window-20261014/`.

Verification is restricted to essential native UI checks, as requested. It covers
full-window geometry through resize/maximize, actual blurred pixels, sharp
controls, larger fonts, theme palettes and focus borders, navigation, close/Escape,
retained drafts/selections, language switching, compact image/profile controls,
profile lock/login and embedded-worker completion/close behavior. No full-suite
or live model/API qualification is performed. Prompts, routing, model profiles,
sampling, context, permissions, translations and stored user settings are unchanged.

The first panel-only check passed 19 tests and failed two obsolete floating-panel
drag expectations. Those tests now verify full-window fitting and caption/control
ownership. The first native panel run then passed all 23 tests. A wider essential
run passed 45 checks and eight subtests, with one genuine compact Hungarian profile
overflow from the two-pixel font increase. The responsive one-pixel increase at
minimum size fixes it; the unchanged fitting check and resize check both pass.
Earlier pytest-cache access warnings are test-output permissions, not product
failures. The final run uses an isolated repository-local basetemp without a cache.

Native synthetic screenshots and caption/layout measurements are under ignored
`state/settings-full-window-preview/`. Verification reports use
`state/settings-full-*.xml`.

The final essential native run passes **46 tests and eight subtests in 85.99
seconds**, with no failures, errors or skips (`state/settings-full-final.xml`).
Forty-five synthetic native screen states cover Original/Conformist, English/
Hungarian, normal/minimum sizes, profile sections and the return to locked login.
Their measurements show no caption overflows, no horizontal content overflows
and full-window Settings geometry in every active Settings state. Representative
screens were visually inspected. A separate native minimize/restore check also
preserves the open Settings view, active window controls and subsequent blur
cleanup. Source/catalog, whitespace and unchanged configuration checks pass.
