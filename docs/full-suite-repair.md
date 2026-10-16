# Full-suite repair, 16 October 2026

`codex/full-suite-repair` starts from clean local main `cdd7f5b`. The requested
full regression found 50 failures: 47 translation-coverage cases and three
offscreen Qt UI cases. This change repairs the catalog gap and dropdown
rendering, and makes the login font fixture independent of installed host fonts.
A subsequent native run also exposed a Git cleanup race; its affected selection
reproduced the previously intermittent local package publication denial.

## Changes

- Add the Word approval title `Edit` to all 45 language catalogs and regenerate
  the 44 compiled non-English catalogs. Every pre-existing message, translation,
  annotation and location is preserved. The Hungarian entry uses `Szerkesztés`
  with its approval context; review fingerprints are updated and native review
  remains pending.
- Settings dropdowns, including notification sound, own a `QListView` and styled
  item delegate. The view adjusts its rows when resized. The offscreen Fusion
  backend previously supplied a menu view/delegate that clipped row geometry
  and painted menu borders despite the existing borderless-item stylesheet.
  The original border, hover, visibility and cancellation assertions are kept.
- The custom login appearance fixture explicitly loads the application's public
  bundled Outfit font and still checks exact family/color preservation and
  exclusion of private theme assets. Offscreen Qt did not expose Segoe UI and
  correctly fell back to Saira; the original host-font assumption was invalid.
- The native-write approval integration fixture keeps Qt's event loop running
  and allows ten seconds for worker startup and cleanup. Content-free thread
  stacks identified cold NumPy imports through language detection during the
  original two-second wait. File bytes, displayed status, absence of composer
  approval, notification behavior and owned-worker exit assertions are retained.
- Git cleanup waits up to five seconds for owned, already-cleaned directories
  after file deletion is pending. Only Windows sharing violations and directory
  not empty errors are retried, with directory identity checked on every attempt.
  Incomplete cleanup and redirects still prevent publication.
- Local package publication uses the existing bounded Windows state-publication
  tolerance (at most 900 ms), with source identity checked before each rename
  attempt and ancestor pins held throughout. Native regressions verify recovery
  after a reader closes, refusal while a reader remains, and refusal of a replaced
  source directory. Existing-destination rename behavior is unchanged.
- Native shell fixtures wait for complete server metadata or terminal/output
  status instead of assuming a background process is ready after one second.
  A content-free probe measured PowerShell readiness at 1.219 s after a running
  receipt at 1.031 s. The expiry fixture allows five seconds for its descendants
  to start before checking automatic cleanup without another tool call. All
  ownership, cancellation, readiness-label, exit-status and output-bound
  assertions remain; production shell behavior and deadlines are unchanged.

The Qt interfaces are documented in [QComboBox](https://doc.qt.io/qt-6/qcombobox.html#setView),
[QListView resize mode](https://doc.qt.io/qt-6/qlistview.html#resizeMode-prop), and
[QStyledItemDelegate](https://doc.qt.io/qt-6/qstyleditemdelegate.html).
The view owns its delegate; each control has its own view and delegate.

Prompts, capability routing and permissions, sampling, model profiles, context policy and private
runtime settings are unchanged. Existing acceptance prompts are unchanged.

## Verification

The original full run recorded **4,222 passed, 50 failed, 69 skipped**, with
two existing Qt activation deprecation warnings, in **1,379.50 seconds**.
Its log, JUnit XML, catalog diagnosis and separate Windows recheck are retained
under ignored `state/full-suite-20261016-01/`.

All 45 repaired catalogs validate and compile. A comparison against the starting
Git versions verifies that `OrsiUI/Edit` is the only added message and all
existing messages are byte-equivalent when serialized individually.

The final focused run passed the **169 translation, Hungarian, login, settings,
theme and font checks**, then reached the cold-import approval timeout. After
repairing that fixture, its complete module passed **16 tests in 17.16 seconds**.
The remaining affected Office/notification selection and native UI rechecks
passed **74 tests in 93.66 seconds** on the Windows backend, including both native
loading-helper cases. This covers 254 distinct affected tests plus five repeated
or additional native UI checks. The original dropdown assertions are unchanged.

Initial repair iterations and failures are retained separately. A diagnostic
probe also reached the old cleanup deadline with a live QThread and terminated;
the passing cold-start module retains and verifies the worker-exit assertion.
None of those initial runs is labeled passing.

The first native full regression cleared the original 50 failures but recorded
**4,273 passed, one failed, one teardown error and 67 skipped** in **1,534.91
seconds**. The byte-limit clone returned cleanup failure instead of download
limit because Windows reported error 145 while removing its temporary root.
The run remains recorded as failed.

Two held-reader deletion regressions now pass. The later installer selection
also captured Windows error 5 at local publication; three native publication
regressions pass after the guarded retry repair. The final combined installer,
package rollback, process ownership and atomic-state selection passed **182
tests in 56.00 seconds**. Five native regressions were added in total.

The repaired byte-limit cleanup case passed **30 repeated runs** (13.50 seconds
in JUnit), and the local publication/rollback case passed **200 repeated runs**
(27.92 seconds in JUnit). Each repetition uses a separate synthetic workspace;
the inspection and rejection assertions are unchanged.

The active checkout was then tested with the integrated Word repairs. Its first
complete run recorded **4,330 passed, 6 failed, 70 skipped**, **15 passing
subtests**, in **1,437.67 s**. All six failures were shell fixture startup races.
Their isolated recheck reproduced seven assertions, including output arrival.
After the fixture correction, **66 shell checks passed in 39.86 s**.

The second complete run recorded **4,335 passed, 1 failed, 70 skipped**, **15
passing subtests**, in **1,538.43 s**. The remaining failure exposed a real
Office failed-receipt worker-cleanup race, repaired and qualified separately in
[the Word repair record](office-word-page-breaks.md): 148 focused Office checks
and the repeated native three-page report gate pass.

The final completed full run recorded **4,339 passed, 1 failed, 70 skipped**,
**15 passing subtests**, in **1,397.83 s**. All repaired UI, translation,
installer, shell and Office cases passed. The sole failure was Windows
`WinError 5` when the unchanged reference-reader depth-limit test renamed its
synthetic directory after validation. Its complete module passed **73 tests in
1.24 s** unchanged on recheck; the intermittent denial remains unresolved.
This full run is not claimed clean. Two existing Qt activation deprecation
warnings remain. The user requested stopping; an extra unchanged run was
interrupted around 11%, its owned process was confirmed stopped, and no further
tests were run.

The 70 skips cover 51 optional model/provider gates, nine opt-in Office cases,
eight unavailable symbolic-link cases and two native display cases. The Word
report desktop gate passed separately. No real provider requests were made.
Full logs and JUnit XML are retained under ignored
`state/full-suite-word-page-breaks/`, alongside the earlier
`state/full-suite-repair-20261016/` records.

## Git recovery

The pre-change status, refs, worktree map and verified complete-history bundle are retained under ignored
`state/backups/full-suite-repair-20261016/`. Prior main is preserved at
`archive/2026-10-16/main-before-full-suite-repair`. After verification, commit
the bounded change, fast-forward local main and remove only the merged local
feature branch. Other worktrees, historical/unmerged tips and remote refs remain
outside this operation.
