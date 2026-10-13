# Composer effort slider and control placement

This bounded presentation change starts from main `f334762` on
`codex/composer-effort-slider` at the user's request.

Attachment buttons remain on the left. Model, reasoning, microphone and Send/Stop
controls sit together on the right, with the microphone immediately beside
Send. The microphone remains an inactive placeholder.

The model dropdown opens above its trigger and stays inside the available
screen area. The reasoning button opens a rounded panel above the composer,
showing the model, selected effort, a blue track, discrete stops and a white
handle. The slider uses the selected profile's supported efforts in their
existing order; Sol does not expose Luna's None setting.

Mouse movement previews the effort; release commits it once. Arrow, Home and
End keys also select levels. Escape or dismissal cancels an uncommitted drag.
The popup closes when the window moves or resizes, the composer hides, or
generation disables the controls. Failed saves restore the effective selection
and displayed effort. Mouse-wheel scrolling does not change the selection.

Selections still reach `reasoning.effort` through the existing service and
per-model preference store. Production prompts, tool behavior, accepted model
profiles, sampling/context policy and user settings are unchanged.

## Verification

Focused native checks: **87 passed**, with no failures, errors or skips, in
20.62 seconds. Results are retained in ignored
`state/effort-slider-final-focused.xml` and `.log`.
Full native suite: **3,553 tests and 15 subtests passed, 61 skipped**, with no
failures or errors, in 600.43 seconds. Reports are retained in ignored
`state/effort-slider-full.xml` and `.log`, with temporary files under
`state/effort-slider-full-temp`. Opt-in live/model and unsupported host/platform
gates remain separately skipped.

The actual widgets were rendered and visually reviewed at 1280x800 and 760x600
for the composer, effort popup and upward model list. The previews use isolated
synthetic state under ignored `state/effort-slider-previews/`.

API construction is checked through synthetic SDK responses, including an
actual slider selection reaching the next request, switching models away and
back, supported ranges, saved preferences and transport shutdown. No paid live
API or model qualification is needed for this presentation change; those gates
remain separate from deterministic results.

Temporary test files and reports stay under ignored repository-local `state/`.
After verification, preserve prior main with a recovery tag, commit the bounded
change, fast-forward local main and remove its merged feature branch under the
repository workflow. Other worktrees and remote refs remain intact.
