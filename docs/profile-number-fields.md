# Profile number-field correction, 10 October 2026

The user reports that the portable pilot works for profile creation, vault unlock
and vault contents, but its quota, idle-lock minutes, managed backup count and
backup-age fields appear blank and unusable. This bounded correction starts
from local main `3803022` on `codex/profile-number-fields`.

## Correction

The pilot bundles Qt 6.12.0, while the working checkout uses Qt 6.11.1. On native
Qt 6.12, a styled `QSpinBox` with `NoButtons` ends up with a one-pixel-wide text
editor. Its hidden step buttons retain right alignment, and the stylesheet
layout clips the edit field at their zero-position rectangles. The
[Qt 6.12 implementation](https://github.com/qt/qtbase/blob/6.12/src/widgets/styles/qstylesheetstyle.cpp)
contains this layout path in `SC_SpinBoxEditField`.

`CompactNumberInput` now assigns left alignment to its hidden step-button
subcontrols. Buttons remain hidden; the editor has room for text again. The
fixed size, ranges, wheel handling, save actions, confirmation and vault policies
are unchanged. The correction also covers quota entry in the new-profile dialog.

The smoke observer can optionally run a check after unlock and durable-record
verification. That callback runs after the automated unlock key release, so
additional event processing cannot delete the retired login editor mid-keypress.
It changes only test observation, not application behavior.

## Portable update

`dist/orsi-number-fields-fix-20261010.zip` is a **1,366-byte** overlay containing
one application file, `app/ui/inputs.py`, plus `README_FIX.txt` and a manifest.
Its SHA-256 is:

```text
abc024f1a252aeb5adf130260c5659eebd4c6d4d0fc95372a1a3e1ecb2224abf
```

Close O.R.S.I fully. Copy the ZIP's `app` folder into the existing portable
application folder containing `ORSI.cmd`, allowing replacement of
`app/ui/inputs.py`. Keep the existing profiles, state, configuration and runtime
folders. The update does not include or replace any of them.

The manifest records the original pilot's file hash and the corrected file hash.
The corrected payload is normalized to Git's LF source representation; its
SHA-256 is `7f1fdbfd88b8761b491f04eba70f764965411ffe134bd60814e26402e8477db4`.
The original 291 MiB pilot ZIP and its pristine unpacked sibling are preserved.
Future pilot assemblies from the corrected source include this fix directly.

## Necessary verification

- A native Qt 6.12 reproduction matched the user's blank fields: the editor was
  **1 pixel wide**. With the correction it is **63 pixels wide**, and the typed
  value is visible. Native captures were inspected.
- **3 focused cases passed in 7.49 seconds on Qt 6.12.0**: both local and
  portable profiles, plus the new-profile dialog. Actual mouse/keyboard entry
  edits all four settings, accepts the real backup-retention confirmation,
  saves, locks and unlocks, then verifies the restored values.
- **5 focused cases passed in 13.47 seconds on Qt 6.11.1**: the same three cases
  and the two existing local/portable cases for uncommitted profile-tab edits,
  saved credentials and lock clearing. These are **8 passing executions across
  5 distinct cases**, with no skips. Both runs used native Windows and
  repository-local pytest temporary/cache directories.
- The exact update ZIP was applied only to an owned extraction of the original
  pilot, after verifying its previous source hash. Its actual windowless
  runtime unlocked a synthetic encrypted profile, composed the real cloud
  backend and tools, displayed/edited/saved all four number fields, and retained
  the personal/credential records and archived chat. SDK clients, vault keys and
  leases, loading helpers and desktop ownership were released. **Zero network
  connection attempts; zero owned test processes remained.** Storage and backup
  captures from that patched pilot were visually inspected.

An initial combined windowless probe crashed because it entered another event
loop inside the unlock key handler; QTest then sent key release to a deleted
login editor. A console diagnostic passed, and the corrected observation timing
then passed on `pythonw` with exit zero. The initial harness diagnostic is kept
separately and is not counted as a passed check.

The user requested only necessary tests, so no full-suite repeat or live provider
call was made. Evidence is under ignored `state/profile-number-fields-*` and
`state/profile-number-{before,after}.*`. No actual user vault was opened or
changed by these checks.

## Preservation and integration

Fourteen starting configuration/runtime/artwork fingerprints match, and the four
other worktree tips and attachments are unchanged. Recovery evidence is under
`state/backups/profile-number-fields-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-profile-number-fields`, commit, fast-forward local
main and remove only the merged feature branch. No remote publication.

The user's portable success is reported evidence, not an independent second-host
or removable-media durability qualification. Those broader gates remain as
recorded in [the pilot package record](portable-pilot-package.md).
