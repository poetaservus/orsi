# Tabbed personal profile: focused verification

9 October 2026. Bounded branch `codex/vault-profile-tabs`, from local main
`b07dc62`. Implements the user-selected focused-tabs mockup from
[the design record](design/personal-profile/README.md).

## Result

The unlocked native Settings page now has five independently scrollable sections:
Storage, Cloud access, Backups, Security and Data. The profile summary, actual
mode/encryption/unlock state, Manage profile menu and Lock remain available above
them. Long locations are read-only copyable fields; actions are content-sized
and reflow at the supported minimum window size. Existing compact numeric and
wheel-safe dropdown behavior remains.

Cloud access groups radio policy choices, saved-key status, the masked credential
editor and separate encrypted-save consent. Apply policy remains explicit; Save
credential applies the selected policy as before. Changing tabs does not save
edits. Other token types remain selectable, with explanations under a disclosure.
Same-profile import rebuilds retain the selected tab and show completion feedback.
Lock clears unsaved secrets, consent and record listings. Different-profile and
unlock views start on Storage. The separate login, blur and loading fade are kept.

No vault format, encryption, prompts, routing, tools, sampling, model profiles,
provider requests or actual user settings were changed.

## Passed checks

**56 distinct focused pytest cases passed on Qt's native Windows platform**, with
no final failures, errors or skips. Only the relevant subset was run, per the
user's instruction; the full 2000+ suite was not run.

- `state/profile-tabs-focused.xml`: 49 vault-control cases, including local and
  portable setup, login, idle lock, quota, password/recovery, backup/restore,
  relocation, imports, cloud credential policy/save/reuse and stale-window guards.
- `state/profile-tabs-final-native.xml`: 11 cases, including seven additional
  Settings layout/navigation and application-shutdown checks, plus final rechecks
  of the four tab/edit/lock and same-profile import cases.
- `state/profile-tabs-feedback.xml`: six overlapping final checks of login,
  same-profile import/tab retention and failed-transition feedback.

The new tab interaction test clicks radio choices and tabs, verifies no implicit
save, saves a synthetic key with consent, locks from another tab, and unlocks to
confirm an unsaved replacement was cleared rather than persisted. The existing
import test now checks retention of the Data tab after consumer rebuild.

The first sandboxed final run passed seven non-vault cases but hit four setup
errors acquiring Windows exclusive vault handles and cache-access warnings.
The identical 11-case selection passed outside the sandbox. That restricted-shell
run is retained as environment evidence in `state/profile-tabs-final.xml`; it is
not recorded as a product failure or as a passing run.

An isolated native probe passed for both local and portable synthetic profiles:

- All five sections at 1536 × 1024, 1280 × 800 and 760 × 600: 30 captures, no
  horizontal clipping, compact actions and reachable vertically scrolled content.
- Actual credential-save button and explicit consent, menu contents, wheel-safe
  quota/minutes/backup-count/backup-days/credential-type controls, lock clearing,
  separate sharp login over its blurred backdrop and unlocked tabbed composition.
- Final large Cloud access, Backups and Security and minimum Cloud access captures
  were visually inspected, together with the earlier Storage and Data captures.

Probe report/captures are ignored under
`state/vault-profile-tabs-native/8a01c19c02fe4a2aa58c72173479a0b9/`.
All values and records used by the probes were synthetic. No external API call
or real user-vault access was required. Python syntax and Git whitespace checks
also passed.

## Preservation and limits

All eight pre-change configuration/selection fingerprints or absence entries
match. Other worktree tips are unchanged. Recovery refs/worktree maps and
content-free preservation evidence are under
`state/backups/vault-profile-tabs-20261009/`. Prior main is retained at
`archive/2026-10-09/main-before-vault-profile-tabs`; integrate locally by
fast-forward and remove only the merged local feature branch.

Physical portable SSD relocation/unplug qualification, performance on the actual
minimum machine, live provider/model gates and independent security review remain
separate deferred gates. Minimum-size layout checks do not claim minimum-machine
performance qualification. This UI change does not rerun those gates or the full
regression suite.
