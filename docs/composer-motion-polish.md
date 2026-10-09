# Composer and motion polish, 8 October 2026

The bounded `codex/composer-motion-polish` change starts from local main
`fe0909f`. It implements requested presentation changes 1, 3, 4 and 5. The
local-image lag and composer collapse in request 2 are investigated only;
admission, inference, the composer-height path and model settings are unchanged.

The attachment picker described below was replaced by the native Windows picker
on 9 October 2026; see the follow-up at the end of this document.

## Presentation

Attached/pasted images have 56 px preview cards with 48 px thumbnails and a
removal button. Visible filenames/details are hidden for images, including
clipboard and saved-image drafts. Documents retain their name/detail cards.
Image names, preparation warnings and failures remain available to accessibility
and hover metadata; original attachment bytes and source identities are retained.

The plus control paints a small shrink/return pulse without changing its
32 px layout geometry or click target. It applies to the main composer and
the shared image-viewer composer. Mouse-wheel detents ease over 150 ms in chat,
image/attachment rows, code and approval previews, and skill lists. List views
use pixel scrolling. Trackpad pixel input remains direct (Qt retains native
pixel accumulation in line-based code editors). Slider dragging, keyboard
scrolling and Ctrl gestures interrupt an outstanding animation. Scrolling
up during streaming cancels follow-tail, including an already queued callback.

The image viewer and attachment picker fade in over 180 ms. The picker uses
a dark Qt-owned file dialog opened asynchronously, retaining the supported
filters and local single-file/cloud multiple-file modes. Cancel leaves the
draft intact; repeated opens reuse the existing picker, and app shutdown
dismisses it and stops its fade. Qt documents that
`DontUseNativeDialog` selects a widget-based dialog; this permits the app to
own its opening animation. See [QFileDialog](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFileDialog.html)
and [wheel delta semantics](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QWheelEvent.html).

## Local-image investigation (no fix)

`MainWindow.submit` retains the attachment until `ConversationWorker.admitted`
fires. Real local admission first prepares the vision model, verifies prepared
source data and durably begins the turn. Adapter-specific context preparation
also runs before admission when supplied. Only then does `_attachment_admitted`
clear the tray. This retention protects the submitted draft if admission fails.

`_refresh_attachment_composer` explicitly calls `_animate_composer_height` with
`animated=False`. A synthetic local-vision admission probe on the unmodified
UI reproduced a direct 130 -> 54 px jump, with no intermediate heights. With
an artificial 350 ms model-preparation delay and 500 ms reply delay, collapse
occurred around 484 ms from submit in the intro and 578 ms in an established
chat. Final height was 54 px in both cases. This confirms delayed abrupt
collapse, not a persistent wrong final height in these synthetic runs.

At 1920 x 1080, the largest sampled event-loop gaps were 16 ms and 31 ms.
Synchronous bottom-glass blur painting reached 16 ms per call, with 12 and
four blur calls respectively. This is a plausible UI contributor to slight
lag, not proof of the actual GPU/model's contribution. The real model was not
started or profiled. Context-meter refresh can also make a synchronous local
image-token-count request with a five-second timeout when the model is ready;
the running-generation guard normally prevents that count during active output.
That path is another investigation lead, not a demonstrated cause here.

Content-free probe data is in ignored `state/composer-lag-probe/summary.json`.
The probe uses synthetic images and isolated conversations; no live user
conversation or credential was inspected. No model/profile/prompt/tool policy,
state-ownership or height-animation change accompanies this investigation.

## Verification and recovery

Initial existing UI checks passed 113 tests and five subtests. The expanded
159-test run found a new test sampling scroll range before Qt finished layout
(158 passes, one failure, five subtests). The test now waits for actual layout;
all four new behavioral checks passed. Expanded confirmation passed all 159
tests and five subtests in 50.03 seconds. Final focused checks, including picker
shutdown, passed 160 tests and five subtests in 55.73 seconds. An earlier command
named two absent test files and collected no tests; it is not passing verification.

Synthetic renders of the composer, plus pulse, picker and viewer were visually
inspected. Motion samples show multiple intermediate wheel positions and both
windows progressing from opacity zero to one. These offscreen checks establish
layout and property progression, not a live Windows-compositor acceptance run.
Render/progression artifacts are under ignored `state/composer-motion-visual/`.
Dependency consistency and Git whitespace checks passed. No API request or
real-model qualification gate was run.

The initial full native regression recorded 2,337 passes, one failure, 58 skips
and 15 passing subtests in 346.02 seconds. The failure was a Windows installer
I/O error in `test_metadata_names_are_never_filesystem_components[Case]`, outside
the changed UI paths. All seven cases of that parametrized test passed on an
isolated retry. Its underlying OS error is suppressed by the installer, so the
cause is not established; no installer change was made. Final full native
regression passed 2,339 tests and 15 subtests, with 58 skips and no failures/errors
in 331.03 seconds. The 58 skips comprise 51 opt-in live/model gates and seven
host-dependent symbolic-link checks; none are counted as passed gates.
All pytest basetemp directories are repository-local; numeric/JUnit evidence
is under ignored `state/test-artifacts/composer-motion/`.

Pre-integration refs/worktree identities and a verified complete-history bundle
containing 92 refs are under ignored `state/backups/composer-motion-20261008/`.
Prior main is preserved at `archive/2026-10-08/main-before-composer-motion-polish`.
After verification, the bounded change is committed and fast-forwarded into
local main, and only its merged local feature branch is removed. Other active
worktrees, remote refs and user runtime settings are preserved. Restart O.R.S.I.
to load the presentation changes.

## Native attachment picker follow-up, 9 October 2026

The composer + control now opens the standard Windows file picker. A plain
`QFileDialog` replaces the styled subclass, forced widget-dialog option, picker
fade and picker-specific scrolling. Qt's native eligibility checks the dialog's
meta-object class, so removing only `DontUseNativeDialog` from the subclass would
not be sufficient. See the [native-dialog contract](https://doc.qt.io/qt-6/qfiledialog.html#Option-enum)
and [Qt 6.11 implementation](https://github.com/qt/qtbase/blob/6.11/src/widgets/dialogs/qfiledialog.cpp).

Supported file filters, local single-file/cloud multiple-file modes, asynchronous
completion, repeated-open ownership, cancellation, parent shutdown and attachment
preparation retain their existing paths. The image viewer keeps its opening fade;
other file dialogs and user settings are unchanged.

This bounded follow-up remains on `codex/tool-approval-preferences`, continuing
from `725a814`; main and remote refs are unchanged under the user's request to
keep the work on a feature branch. Existing picker checks now require a plain
dialog with native mode eligible, while retaining their file-selection and draft
assertions. Focused attachment, motion and shutdown checks passed 43 tests in
16.01 seconds using native filesystem access and repository-local test storage.

An isolated Windows-platform smoke exercised the real composer and production
picker factory without application startup or model requests. Both local and
cloud modes displayed a Windows `#32770` dialog with the modern `DirectUIHWND`
shell browser. A preselected local file accepted through Qt produced an exact
owned attachment copy; cloud cancellation preserved the draft, repeated opens
reused the picker, and parent closure dismissed it. Screenshots were visually
inspected after native painting settled. Script and images remain ignored under
`state/native-picker-smoke.py` and `state/native-picker-smoke/`. This is native UI
and attachment-lifecycle verification, not live model qualification.

Full native regression passed 2,753 tests and 15 subtests, with 58 existing
optional/host skips and no failures/errors, in 532.80 seconds. It used
`--basetemp=state/native-picker-full` and a repository-local cache; JUnit reports
are `state/native-picker-focused.xml` and `state/native-picker-full.xml`.
Changed Python sources parsed successfully and Git whitespace checks passed.
Live model/API gates were not rerun for this picker-only change. Restart ORSI
to load the native picker.
