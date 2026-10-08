# Greeting field reference match

Bounded GUI change from local main `7993af0` on
`codex/greeting-reference-style`. The greeting uses the same flat input style
as the Skills repository/folder/link field shown in the user's reference:
`#343f50` background, a one-pixel `#4a5667` border, six-pixel corner radius,
eight-pixel padding, 14-pixel Saira text and 42-pixel outer height.
Both controls share the same stylesheet rules. The composer wrapper is removed.

The original greeting input object, text, normalization, maximum length and
preference-saving handlers remain in place. No preference migration or inference,
model, routing, prompt, approval or credential changes are included.

At normal 1280 × 800 and compact 760 × 600 window sizes, rendered greeting and
Skills input images were compared at equal size and text. Both comparisons were
pixel-identical. Synthetic previews use isolated preferences under ignored
`state/greeting-reference-preview/`.

Native settings/frame/UI/skill-settings regression passed 60 tests and 13
subtests in 35.54 seconds, including actual greeting editing and restoration.
The existing full-width check again measures the input itself. Focused evidence
is in ignored `state/pytest-greeting-reference-focused.xml`, with repository-local
`state/pytest-greeting-reference-focused/` temporary files.

The initial full native run passed 2,413 tests and 15 subtests with 58 skips,
but `test_reference_only_update_is_a_conflict_until_explicit_removal` failed on
an installer file I/O error (410.32 seconds). All 26 skill-package installation
checks passed independently in 1.63 seconds on the native rerun. Installer code
and acceptance prompts are unchanged. Rerun evidence is in ignored
`state/pytest-greeting-reference-installer-check.xml`.

Final full native regression passed 2,414 tests and 15 subtests in 404.64 seconds,
with no failures or errors. The 58 optional/host-dependent skips are recorded
separately in ignored `state/pytest-greeting-reference-final-full.xml`.
Temporary files stay under repository-local
`state/pytest-greeting-reference-final-full/`. No live API gate was run.
`git diff --check` passed.

Preserve prior main at `archive/2026-10-08/main-before-greeting-reference-style`.
After full verification, commit, fast-forward local main and remove only this
merged local feature branch. Other worktrees and remote refs remain outside
the operation. Restart the normal launcher to load the reference appearance.
