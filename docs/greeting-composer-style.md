# Greeting field composer appearance

Bounded GUI change from local main `db8f80c` on
`codex/greeting-composer-style`. The settings greeting field uses the same
antialiased `ComposerFrame` paint as the chat composer: a 54-pixel rounded pill,
the shared gray gradient and inset highlight, with 17-pixel Saira text and
22-pixel side padding. The existing line edit is transparent inside that frame.
Clicking the surrounding pill directs focus to the greeting field.

The original greeting input object, normalization and preference-saving
handlers remain in place. There is no preference migration. No inference,
model, routing, prompt, approval or credential setting changes are included.

Native Windows focused settings/frame/personality/composer regression passed
49 tests and eight subtests in 18.37 seconds. Existing interaction checks cover
actual clicks, keyboard editing, saving, reopening and restoration at normal
1280 × 800 and compact 760 × 600 window sizes, preserving an unrelated setting.
The full-width check now measures the outer pill, which supplies its own padding.

Normal, compact and placeholder renders were inspected under ignored
`state/greeting-composer-preview/`, using an isolated preference file.
Focused test evidence is in ignored `state/pytest-greeting-composer-focused.xml`
with repository-local `state/pytest-greeting-composer-focused/` temporary files.

The first full native run stalled in the existing image-viewer case
`test_local_viewer_reply_keeps_one_original_and_respects_model_image_gate[True]`
after the earlier tests passed. Only the identified pytest process was stopped.
That case passed alone in 1.25 seconds with native Windows and stack diagnostics.
The final full run uses a fresh process, a separate repository-local temporary
directory and a 90-second diagnostic stack timer. Image-viewer code is unchanged.

Final full native regression passed 2,414 tests and 15 subtests in 442.24 seconds,
with 58 separately recorded optional model/provider/UI and host-dependent skips
and no failures/errors. Evidence is in ignored
`state/pytest-greeting-composer-final-full.xml`, using repository-local
`state/pytest-greeting-composer-final-full/` temporary files. No live API gate
was run for this GUI change.

Preserve prior main at `archive/2026-10-08/main-before-greeting-composer-style`.
After full verification, commit the bounded change, fast-forward local main and
remove only this merged local feature branch. Other worktrees and remote refs
remain outside the operation. Restart the normal launcher to load the restyle.
