# Composer alignment and first-frame popup placement

This UI-only change starts from local main `1315375` on
`codex/composer-menu-polish`. The pending personality feature remains on its
existing branch and is preserved independently.

Composer controls share a 34-pixel height and a vertical center line. Send and
Stop fill their action slot without the previous downward offset and clipping.
Attachment icons have matching stroke styling and balanced sizes; Send uses
a vector outline. The shared image-viewer composer receives the same alignment.

The model menu is positioned during its Show event, before the first visible
frame. Qt's default combo scroll effect is suspended only during the synchronous
opening call and its prior setting is restored immediately. Move/resize events
retain the upward position, and the trigger uses an upward chevron.

## Verification

The new first-frame and clipping assertions reproduced both defects before the
fix: three focused cases failed. After the fix, **58 relevant tests passed** in
25.90 seconds using the bundled Windows runtime and Qt's offscreen backend.
The report is retained in ignored `state/composer-polish-focused.xml`.

Coverage includes initial Show and Paint geometry, repeated opening, both
startup and bottom composer positions at two window sizes, Escape, keyboard
model selection, reasoning selection, attachments, image replies and UI motion.
Synthetic rendered previews at 1280x800 and 760x600 were visually inspected,
including the long local-model label. Private profile settings were not used.

The full suite was explicitly excluded by the user for this presentation change.
Live API/model qualification was not run; deterministic request tests use a
synthetic transport. Inference behavior and accepted profiles are unchanged.

After verification, retain prior main at
`archive/2026-10-13/main-before-composer-menu-polish`, commit, fast-forward local
main and remove only the merged UI branch. Merge the updated main back into
`codex/profile-personalities` so the active checkout retains both features.
The personality branch's previously recorded full-suite limitations remain
unchanged. Other worktrees and remote refs are preserved.
