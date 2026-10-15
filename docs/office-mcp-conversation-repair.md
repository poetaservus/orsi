# Office conversation failure and full-suite repair, 15 October 2026

With Office connected in Cloud mode, even a greeting failed with
`The compact agent prompt received an unsupported catalog.` The conversation
layer rejected the reviewed Office names before making a model request. The
phase 2–4 MCP checks had exercised the agent runtime directly and missed this
conversation-layer boundary.

This bounded repair starts from local main `c1f305c` on
`codex/office-catalog-regression`. The compact prompt validator now derives its
additional accepted names from the reviewed `OFFICE_TOOLS` contracts. Unknown
names and duplicate names remain rejected. The legacy prompt's catalog is
unchanged. No prompt wording, accepted task prompts, model profiles, sampling,
routing, context policy, Office schemas or permission/approval behavior changed.

Startup also treats an inference adapter without a mode attribute as local,
matching the existing Office exposure checks. An absent mode cannot grant cloud
Office authority. A startup test verifies that such an adapter still answers a
greeting with Office disconnected.

## Other defects and stale checks exposed by the full run

- Compact profile number fields now have 40 pixels of height. Their old
  36-pixel height left only 24 pixels for the enlarged Settings font's 25-pixel
  metrics. Existing tests still require readable text, actual typing and
  persistence across lock/unlock.
- The attachment picker factory again uses the intended plain native
  `QFileDialog`, preserving its native-dialog configuration and translated
  title at creation. Its synthetic fixture supplies OS selection/cancellation
  without opening Windows Shell UI. Programmatic Qt accept/reject is not a
  reliable driver for the native Shell dialog. The real dialog configuration,
  completion signals, file import workers, draft preservation and dismissal
  paths remain checked; automated Shell-chrome interaction is not qualified.
- The response-language fixture settles the Settings layout before scrolling
  its selector into view. The corner-control fixture uses the current Settings
  close button, verifies its completion signal and restored chat controls, and
  closes its window in `finally`. An earlier failed assertion had leaked that
  test window into ten later vault-window assertions.
- Shared border checks accept the switch's deliberately blue enabled track and
  verify that focus adds no separate painting. Existing switch rendering and
  keyboard behavior checks remain authoritative. Animation completion is
  deterministic rather than relying on a marginal wall-clock delay.

The 45 source catalogs and 44 compiled non-English catalogs were refreshed.
`No skills installed.` reuses each locale's existing `No skills installed`
translation with terminal punctuation. The unused `Adjust interface text size`
source was removed. Every unrelated translation is unchanged; each catalog
still has 737 shared sources. The Hungarian catalog retains its 38 extra pilot
sources and annotation ordering. Its editorial fingerprints record this small
maintenance change; native-language review remains pending.

## Verification

The new conversation regression reproduced the exact reported exception before
the repair: **2 failed, 2 passed**. It now covers a greeting before connection,
a greeting while connected, a real SDK/stdio read through `ConversationService`,
Cloud/Local/Cloud visibility, disconnect, and released bridge ownership.
It also checks all eight reviewed contract names and rejection of unknown and
duplicate names.

The initial default-platform full run recorded **77 failed, 4,062 passed,
65 skipped and 15 subtests passed in 1,316.13 seconds**. It is retained as a
failing run, not relabeled after repairs. Its failures included stale catalogs,
UI assertions and leaked-window effects, plus two native Windows directory
rename denials that passed unchanged in isolation. Offscreen popup/font
differences were checked separately on Qt's Windows platform. Preliminary native
picker-driving interruptions remain in their logs and are not passing gates.
Six failures came from the first repair attempt caching a combined allowlist and
missing the replay fixtures' synthetic catalog extensions. The final validator
combines the existing and reviewed Office names at validation time.

The final affected selection passed **100 checks in 103.09 seconds** on Qt's
Windows platform, without failures, errors or skips. It includes the conversation
boundary, provider replay, attachment completion/cancellation, profile-number
typing/persistence, Settings closing, borders, vault-window lifecycle, directory
relocation and junction rejection. All 45 source catalogs validate and compile;
a separate comparison proves that unrelated translated wording was preserved.
Compilation and whitespace checks pass.

The fresh full suite passed **4,141 tests and 15 subtests**, with **63 skips,
zero failures and zero errors**, in **1,448.80 seconds**. It ran with
`QT_QPA_PLATFORM=windows`, normal Windows process permissions, bundled Python,
and repository-local `state/pytest-office-catalog-full-final/` temporary storage.
Two unchanged test-only Qt `setActiveWindow` deprecation warnings remain.
The earlier directory-rename checks pass unchanged in this full run. The skipped
checks cover opt-in provider/model/Office gates and unavailable host symlink
operations; they are not counted as passed live qualification.

Ignored evidence:

- `state/office-catalog-before.xml`
- `state/office-catalog-full.xml` and `.log` (initial failing run)
- `state/office-catalog-qualified-focused.xml` and `.log`
- `state/office-catalog-maintenance.json`
- `state/office-catalog-full-final.xml` and `.log`

All test data and provider responses are synthetic. Live provider billing,
physical second-host qualification and opt-in live model/Office gates remain
separate from this suite. No user credentials, real documents or private profile
settings were used as fixtures. A running ORSI process must be restarted to load
the code repair.

Ref/worktree inventories are preserved in
`state/backups/catalog-full-suite-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-catalog-regression`, commit the verified
change, fast-forward local main and remove only its merged feature branch.
Other worktrees, historical/unmerged tips, private settings and remote refs
remain intact.
