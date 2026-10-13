# Profile-level personality selection

This bounded change starts from main `1315375` on `codex/profile-personalities`
at the user's request.

## Behavior and storage

**Settings → General → Personality** offers **Original** and **Choom**.
Original is the default for existing and new profiles; its 2,058-character
guidance is unchanged. Choom 1.0.0 is a composed technical voice with restrained
cyberpunk slang and deadpan humor, taken from the user's supplied Desktop draft.
The import preserves the complete source file; its YAML metadata is excluded
from the response prompt and all 4,046 characters of the personality body remain.

The selection applies to the next response in local and cloud modes, across
chat and agent requests, including compact agent policy. It replaces
only the shared personality prefix. Tool catalogs, operational instructions,
approval checks, user text, history, active skills, model profiles, sampling and
context policy remain unchanged. The normal context calculation counts the
selected personality's full text. Switching invalidates the old usage estimate.

Each unlocked profile stores a schema-v1 record containing only the selected
personality ID at `state/personality_selection_v1.json`. Encrypted profiles
encrypt that record; plain profiles keep it inside their own storage root.
Legacy unprofiled mode uses that installation's ignored state directory.
Nothing is written merely to activate the default Original voice. New chats
and restarts preserve the choice. Failed saves retain the previous effective
selection. An unreadable or unsupported saved preference is preserved, with
Original available for chat and an explanatory disabled picker.

The picker is disabled during generation/settings work. Direct service calls
also require an idle, open conversation. Profile lock revokes the setting's
storage authority, clears the selected ID and clears the old window's control.
Switching profiles never copies or merges their preferences.

## Portable packaging

The fixed Choom definition is versioned under
`app/conversation/personalities/choom-v1.0.0.txt`; no absolute Desktop path is
saved or read at runtime. It is included by both existing portable payload
exporters and by Python package data. A fresh public package includes both
choices and defaults to Original. Deploying with the current profile preserves
its saved choice, including encrypted storage, after the whole node is moved.
The user's Desktop draft and existing settings are not modified.

Imported source SHA-256:
`fce70f9c27be9c0fc4fd8755d23530da3461e23e1c1558e8fc372aab9c834e98`.

## Verification

Initial focused checks passed 120 tests after adjusting only synthetic context
headroom, a Windows lease inspection and Git text-line-ending comparison.
Final affected checks: **310 passed**, with no failures, errors or skips, in
159.78 seconds. Reports use ignored `state/personalities-final-focused.xml`
and `.log`, with repository-local temporary storage.
The first full native suite passed 3,573 tests and 15 subtests, skipped 61,
and failed one unchanged runtime timeout test in 570.87 seconds. Its 30-ms
deadline expired correctly before the blocking fixture started, contradicting
the test's assumption that it had already entered execution. The unchanged
32-test runtime group passed in isolation. This failure remains recorded in
`state/personalities-full.xml` and `.log`; it is not reclassified as a pass.
No runtime or timeout-test code was changed for the recheck.
The unchanged full rerun passed 3,573 tests and 15 subtests, skipped 61, and
recorded one failure and its teardown error in 569.92 seconds. The unchanged
Git installer `test_repository_limits_reject_before_copy[bytes]` returned
`cleanup_failed` when rejecting a temporary download; teardown found its Git
folder retained. This same Windows cleanup failure is recorded in the earlier
[repair qualification history](complaint-repair-loop.md). Native inspection
found the synthetic repository's zero-byte `config.lock` and initialization
files. An initial restricted-shell inspection denial is separate from the
actual native test failure.

The combined unchanged runtime and installer groups passed all **92 checks**
in isolation in 19.70 seconds. Reports are retained in ignored
`state/personalities-final-full.xml`/`.log` and
`state/personalities-unrelated-recheck.xml`/`.log`. Both full runs remain
recorded as failing; successful isolated rechecks do not replace the global
regression gate. No installer, runtime or corresponding test code was modified.

Coverage includes real request construction for each prompt path, unchanged
policy suffixes/catalogs and exact user text, the cloud SDK request body,
General-settings keyboard interaction and failed saves, independent encrypted
and plain profiles, restart/new-chat persistence, profile lock, invalid-file
preservation, tiny-context rejection, portable deployment/relocation and public
ZIP export. All provider responses are synthetic; paid live/model style
qualification is separate and was not run for this settings change.

Actual General settings were rendered and visually reviewed at 1280x800 and
760x600 for both choices, using an isolated synthetic profile. Logs, previews
and temporary files remain in ignored repository-local `state/`; verification
does not use the user's personal profile or conversation contents.

Prior main is preserved at `archive/2026-10-13/main-before-profile-personalities`.
The requested feature is committed on `codex/profile-personalities`; its full
regression gate remains unmet. The subsequent UI-only composer polish advanced
local main to `410d45d` and was merged back into this feature branch. All 12
narrow composer and General-settings integration checks pass on the combined
checkout (`state/composer-polish-combined.xml`). No full suite was rerun, as the
user explicitly excluded it for the UI follow-up. The active checkout retains
both features through the existing launcher. Other worktrees and remote refs
remain intact.
