# UI theme implementation and essential verification, 14 October 2026

`codex/ui-themes` starts from clean local main `32a51bc`. This bounded change
implements Settings → Appearance → Theme, Original/Ocean, static theme manifests,
relative images/fonts/icons, import/update/export and profile-owned persistence.
Runtime selection stays in UI preferences and imported packages in ignored or
protected `state/themes/catalog_v1.json`. Other user preferences and acceptance
requests remain unchanged. See [theme authoring and behavior](ui-themes.md).

The runtime updates existing widgets and repaints custom surfaces. It preserves
response structure, existing code font/syntax colors, layout constants, animation
timing, notification events/artwork/audio and inference behavior. Font-family
changes invoke the existing message-sizing code and preserve text selection,
drafts, streaming/copy-feedback state and reader scroll position. No application
wide event filter is installed. Native Windows dialogs keep their own behavior.

## Passed checks

- Essential regression: **173 passed, 5 subtests passed, 2 native-only skips**,
  no failures/errors, **58.00 seconds**. Repository-local temporary storage and
  the existing offscreen Qt platform were used, in an unrestricted Windows shell
  for actual file/profile handles. The selected files cover UI/Markdown wrapping,
  settings, composer/reasoning, questions, scrolling/pickers, inline approvals,
  notifications, image viewing, presentation and preference migration.
- Final native Windows theme checks: **40 passed**, no failures/errors/skips,
  **7.71 seconds**. This includes actual font switching/reflow, all six requested
  icon overrides, an open-dropdown selection, failure preservation, custom assets,
  updates, profile isolation/migration and encrypted backup/restore.
- Native synthetic rendering at 760 × 600 and 1280 × 900 verified Saira → Segoe UI
  → Saira, with the original measured text heights restored. A chat-screen capture
  of Original matched an isolated unchanged-main capture at **all 1,152,000 pixels**.
  Ocean chat/Appearance captures were visually inspected.
- Python compilation and Git whitespace checks passed.

The last small dropdown refinement avoids resetting its model during selection;
the final 40-test native run includes that change and its popup regression.

Evidence is retained under ignored `state/ui-themes-essential-final2.xml`,
`state/ui-themes-native-complete.xml` and `state/ui-themes-visual/`. All UI content,
profiles and credentials in these checks are synthetic. The optional Desktop API
credential was not read or used; no live model request was needed to verify Qt
text wrapping. The full repository suite and live inference gates were not run,
following the user's essential-test scope.

## Earlier results and host limitations

Earlier runs retain the now-fixed copy-icon cache regression, outdated Theme
placeholder assertion, font-selection anchor bug and gradient-region raster seam.
An encrypted-profile check initially failed to acquire a handle in the sandbox;
the unrestricted native run passed. Its first native fixture also attempted to
read the intentionally locked `.lease` file; the content check now inspects the
profile's data files while excluding that lock file.

A broad native run and isolated rechecks hit an access violation while tearing
down the existing native attachment picker. The same single check reproduced on
an isolated export of unchanged main, with no theme code. It remains a separate
native Qt/test-host limitation; attachment/picker behavior and the acceptance
assertion were not changed. Those checks pass in their intended offscreen setup
with unrestricted Windows handles. The two skipped loading-logo checks require
the native platform and remain recorded as skips in the offscreen regression.

The starting branch/worktree inventories are retained under ignored
`state/backups/ui-themes-20261014/`. Prior main is retained as
`archive/2026-10-14/main-before-ui-themes`. Commit the bounded verified change,
fast-forward local main and remove only its merged feature branch. Other
worktrees, historical/unmerged tips, private runtime state and remote refs remain
unchanged. No remote publication is part of this task.
