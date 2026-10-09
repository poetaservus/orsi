# Git layout and baseline hygiene

## Compact idle-lock controls, 9 October 2026

`codex/vault-idle-controls` starts from local main `8a6b7b2`. The idle-lock row
now reuses the tool-approval switch with a 72-pixel typed minutes field and
128-pixel inline save button. Wheel changes and spinner buttons are removed;
Save preserves the existing zero/off or positive-minutes setting. See
[focused verification](vault-idle-controls-verification.md).

Seven existing focused Windows checks passed. Native local/portable checks
verified toggle/save/restart behavior, 16 wheel cases and minimum-width layout;
panel captures were visually inspected. No full suite or live provider/model
checks. All eight settings/selection preservation entries match; actual user
profiles and running processes were left alone. Recovery evidence is under
ignored `state/backups/vault-idle-controls-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-idle-controls`, commit, fast-forward main
and remove only the merged local branch. No remote publication.

## Vault picture stacking and fades, 9 October 2026

`codex/vault-picture-fade` starts from local main `e21cd84`. The loading picture
now stays above application windows and fades in/out with 240 ms cubic easing.
Fade-in completes before blocking composition; fade-out reveals the ready view.
Retired views are collected after the fade's local event loop. See
[focused verification](vault-picture-fade-verification.md).

Twenty-three existing focused Windows checks passed. Native local/portable
checks verified the actual topmost style, stacking above a separate test process,
intermediate native opacity values in both directions, geometry and failed-load
cleanup. An actual desktop-entrypoint/repeated-launch probe also passed. The full
suite and live provider/model tests were not run. All eight settings/selection
preservation entries match; the user vault and running instance were left alone.
Recovery evidence is under ignored `state/backups/vault-picture-fade-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-vault-picture-fade`, commit,
fast-forward main and remove only the merged local branch. No remote publication.

## Vault unlock picture, 9 October 2026

`codex/vault-unlock-picture` starts from local main `c7f8916`. Successful unlock
now shows the user's supplied picture over the previous window while the unlocked
profile is composed. The original image is bundled unchanged in UI assets and
included in package data; the existing compiled build already includes that
asset directory. See [focused verification](vault-unlock-picture-verification.md).

Twenty-three existing focused Windows checks passed, plus native visual checks
for normal/maximized windows, failed initialization and a relocated portable
asset, and an actual desktop-entrypoint/repeated-launch probe. No full suite or
live provider/model tests were run. All eight configuration/selection preservation
entries match; the actual user vault and running instance were left alone.
Content-free recovery evidence is under ignored
`state/backups/vault-unlock-picture-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-unlock-picture`, commit, fast-forward main
and remove only the merged local branch. Remote branches remain untouched.

## Desktop unlock/window and saved-key follow-up, 9 October 2026

`codex/vault-unlock-lifecycle` starts from local main `39da460`. The user reported
two windows and another cloud-key prompt after unlock. Six synthetic reproductions
exposed stale window activation, obsolete unlock actions and duplicate consumer
composition after rejected actions. The fix retires/guards old views, keeps a
valid current session after rejection, coordinates repeated desktop launches and
shows explicit saved-key availability/use choices. See
[focused verification](vault-unlock-lifecycle-verification.md).

Ninety-five distinct focused checks passed, including 23 on Qt's native Windows
platform, plus an isolated native desktop entrypoint/two-process probe. The full
suite was not run. All eight settings/profile-selection hashes/absence and other
worktree tips are preserved; no actual vault was opened. Recovery evidence is under
ignored `state/backups/vault-unlock-lifecycle-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-unlock-lifecycle`, commit, fast-forward local
main and remove only the merged feature branch. No remote publication is authorized.

## Saved cloud credential correction, 9 October 2026

`codex/vault-cloud-credentials` starts from local main `4b9defa`. The reported
saved-key prompt reproduced in local/portable synthetic UI checks: Save ignored
the selected policy without a separate Apply click, and a cancelled prompt could
cache a missing key. Save/import now apply the explicit policy, saved API-key
replacement invalidates the affected cached connection, and feedback explains
intentional Ask mode. See [focused verification](vault-cloud-credentials-verification.md).

Fourteen new and 40 affected existing checks passed; the full suite was not run.
All eight recorded settings/profile-selection hashes/absence match. Preserve
prior main at `archive/2026-10-09/main-before-vault-cloud-credentials`, commit the
bounded fix, fast-forward local main and remove its merged feature branch.
Content-free preservation evidence is under ignored
`state/backups/vault-cloud-credentials-20261009/`. Other worktrees, personal
profiles and remote branches remain untouched; no remote publication is authorized.

## Personal Vault phase 4 setup and controls, 9 October 2026

`codex/vault-phase4` starts from verified local main `30053f6`. The user authorized
all phase 4 items and 4.1 and requested necessary tests only; the 2000+ suite is
excluded. Settings gains personal-profile setup/selection/unlock, credentials,
migration/original cleanup, quota/recovery/backup/restore/relocation, retention
and dismissible protected-storage guidance. See [the contract](vault-phase4-contract.md)
and [focused verification](vault-phase4-verification.md).

Focused checks passed 267 distinct cases with no final failures/errors/skips.
Real SSD, minimum-host, live provider/model and independent security gates remain
deferred; phase 5 is not started. All seven recorded user configuration/state
hashes/absence and other worktree tips are preserved. Content-free preservation
evidence is under ignored `state/backups/vault-phase4-20261009/`. The bundled
runtime gains already available, hash-verified pinned crypto dependencies without
replacing existing settings. Preserve prior main at
`archive/2026-10-09/main-before-vault-phase4`, commit the bounded change,
fast-forward local main and remove only the merged local feature branch.
No remote publication is authorized.

## Personal Vault phase 3 application integration, 9 October 2026

`codex/vault-phase3` starts from verified local main `d456cd3`. The user authorized
the next roadmap phase and necessary tests only, keeping physical SSD,
minimum-machine and independent security qualification deferred. This phase
connects an explicitly selected profile to private application state, attachments,
generated images, skills/references, diagnostics and shared credential policy;
it adds lock/switch cancellation, revocation and tool-path exclusions.
See [the contract](vault-phase3-contract.md) and
[focused verification](vault-phase3-verification.md). Setup/migration UI remains
phase 4; existing unencrypted startup remains the default until explicit selection.

Focused verification covers 271 distinct passed checks and two existing Windows
symlink skips. The full suite and live provider/model/hardware gates were not run.
Pre-change refs/worktree maps and content-free settings hashes are under ignored
`state/backups/vault-phase3-20261009/`. After verification, preserve previous main
at `archive/2026-10-09/main-before-vault-phase3`, commit the bounded change,
fast-forward local main and remove only the merged local feature branch. Preserve
other worktrees, user settings, historical/unmerged refs and remote branches.
No remote publication is authorized for this phase.

## Personal Vault phase 2 engine, 9 October 2026

The user authorized roadmap phase 2, requested necessary checks only and deferred
real SSD, minimum-host and independent security qualification. Verified phase 1
`abcd943` was fast-forwarded into local main and preserved at
`archive/2026-10-09/vault-phase1`; its merged feature branch was removed. Phase 2
starts on `codex/vault-phase2` from that local main. No remote branch is published.

The bounded engine adds authenticated catalogs/large objects, password/recovery
controls, atomic multi-record visibility, quota/free-space admission, verified
encrypted backup/restore, OS process ownership and reference-aware retention.
Application/UI/credential wiring remains for phase 3. See
[the format contract](vault-phase2-contract.md) and
[focused evidence and deferred gates](vault-phase2-verification.md).

Final focused native verification passed **71 cases in 18.56 seconds**, with no
failures/errors/skips. Compilation, import isolation, preservation hashes and
whitespace checks passed. The full suite and the explicitly deferred external
qualification gates were not run.

Preservation hashes and ref/worktree maps are under ignored
`state/backups/vault-phase2-20261009/`. After focused verification, preserve prior
main at `archive/2026-10-09/main-before-vault-phase2`, commit the bounded engine,
fast-forward local main and remove only its merged local feature branch. Preserve
other worktrees/historical tips and remote refs; do not run the full suite or infer
remote-push authorization from historical workflow records.

## Personal Vault phase 1 review branch, 9 October 2026

The user requested phase 1 of the external Personal Vault v1 roadmap on a new
branch, `codex/vault-phase1`, from local main `aeb350d`. This bounded change adds
the storage inventory, proposed format/lifecycle contract and an isolated
synthetic encryption experiment. No application storage migration or runtime
integration is enabled. See [scope, verification and pending gates](vault-phase1-verification.md).

The user explicitly requested necessary tests only. Final focused checks passed
36 tests in 3.80 seconds; large synthetic-image experiments, compilation, startup
import isolation, preservation hashes and whitespace checks passed. The full
suite and live model/API gates were not run. Physical SSD, minimum-host and
independent security qualification remain pending. Preservation hashes and
ref/worktree maps are under ignored `state/backups/vault-phase1-20261009/`.

Commit the bounded change and retain the requested branch for review. Immediate
fast-forward integration/branch deletion are deferred; local main, remote refs,
other active worktrees and user settings remain unchanged.

## Tool approval and UI integration, 9 October 2026

The user authorized merging and publishing the eight commits from `585cfdb`
through `26085ff` on `codex/tool-approval-preferences`. They add persistent tool
approval preferences, flat settings controls, the native Windows attachment
picker, a burgundy image-generation animation without the active status overlay,
and the enlarged image viewer's editable `Edit this image: ` composer prefix.

The final focused integration check passed **107 tests** without failures or
skips in 39.68 seconds. Its repository-local temporary state, cache and result
are under ignored `state/integrate-approval-ui-focus`,
`state/integrate-approval-ui-cache` and `state/integrate-approval-ui-focused.xml`.
Whitespace checks passed. The full suite was deliberately not run at the user's
request, and no live model/API calls were made for this integration.

Previous main `d850fd7` is preserved at the local annotated tag
`archive/2026-10-09/main-before-tool-approval-ui`. Integration fast-forwards local
main, removes only the merged feature branch and pushes main without force.
Other worktrees, historical/unmerged refs and user runtime settings are preserved.

## Reversal checks and stored goal evidence, 9 October 2026

`codex/reversal-check-goal-evidence` starts from published, verified main `dd87567`. It adds pre-execution checks for known revision returns and stores each agent turn's literal request with receipt-bound save/source evidence. Successful reports and provider partial text retain their existing content. Requested runtime/GUI behaviour remains unverified; no new execution capability, model profile, routing or sampling policy is introduced. See [the contract and qualification](reversal-goals.md).

Final focused native checks passed 74 tests. Final full native checks passed 2734 checks including 15 subtests, with 58 optional/host skips, zero failures or errors, in 412.573 seconds. Four unchanged live coding gates and two controlled live reassessment gates passed. Runtime/GUI execution through ORSI and live local-model checks remain unrun. Pre-change refs/worktrees, a verified history bundle, preservation hashes and separate qualification reports are retained in ignored `state/backups/reversal-goals-20261009/`. Settings, runtime preferences, all fourteen installed Python skill files, twelve other installed skill files, historical refs and four other worktrees remain preserved. Preserve prior main at `archive/2026-10-09/main-before-reversal-goal-evidence`, commit the verified bounded change, fast-forward local main, remove only its merged feature branch, push main without force, and verify GitHub matches the clean checkout.

## Accepted baseline consolidation, 9 October 2026

The six routing/editing phases are integrated on verified local main `15cdb3d`.
The remaining bounded `codex/settings-status-overflow` change enables wrapping
of the full agent status in General settings, preserving reachable controls at
normal and compact window sizes. Its original settings work is retained exactly;
no routing, prompts, tool behavior, model profiles, recovery rules or runtime
preferences change during consolidation.

Pre-change refs/worktree maps, a verified complete-history bundle, the uncommitted
settings patch and content-free configuration/runtime-preference hashes are
retained in ignored `state/backups/main-consolidation-20261009/`. Refreshed GitHub
main is an ancestor of local main; 23 accepted commits await publication before
this final settings commit. The authorized credential is excluded from all
unpublished history blobs and the pending settings files. Focused native settings
checks passed 23 tests. The first full run stalled in the existing attachment UI
group and was stopped; its incomplete result is retained separately. All 33
attachment UI checks then passed unchanged in isolation. The existing root test
cache write warning is separate from product results; subsequent checks use fresh
repository-local caches. Final full native regression passed 2,693 tests and 15
subtests, with 58 optional/host skips, no failures/errors, in 507.304 seconds using
an unrestricted Windows shell and fresh repository-local test/cache directories.
No acceptance prompts or existing assertions change.
The four Phase 6 live coding gates remain passed historical evidence; this
settings-only consolidation does not rerun live model or image gates.

Preserve the three merged 8 October archive branches as annotated archive tags
before removing those redundant local branch names. Keep the separate
`archive/conversational-main-20260921` checkout and the other worktrees unchanged.
After verification, fast-forward local main, switch the clean active checkout to
main, remove only its merged settings feature branch and push main without force.
Verify GitHub main matches the accepted local commit. New reversal-check and
stored-goal work then starts on `codex/reversal-check-goal-evidence` from that
published baseline. The accepted baseline and future feature work remain separate.

## Content-free diagnostics, 9 October 2026

`codex/content-free-diagnostics` starts from verified main `1186871`. Phase 6
adds fixed-category route decisions, settled terminal counts and public
stream/event/code/SDK-version diagnostics. ORSI's owned log file excludes raw
OpenAI/HTTP library records. Parser acceptance, retry ownership, durable settled
work and unknown-outcome safeguards are unchanged. Prompts, routing, tool
contracts/permissions, model/context policies and Python Coder 1.0.1 remain
unchanged. See [the diagnostic contract and qualification](content-free-diagnostics.md).

Pre-change refs/worktree maps, a verified complete-history bundle and content-free
settings/configuration hashes are retained under ignored
`state/backups/content-free-diagnostics-20261009/`. Final focused native checks
passed 223 tests without skips, failures or errors. Final full native checks passed
2,691 tests and 15 subtests, with 58 optional/host skips, no failures/errors, in
484.479 seconds. All four unchanged cloud coding cases passed, with exact bytes,
finite approved mutations, originals preserved for copies, zero failed calls,
corrections or coding images, honest unrun checks and released transports. Four
route and four terminal records contain only approved metadata and match durable
outcomes. The fourteen installed Python skill package files and twelve other
installed skill files are unchanged. Python/GUI execution through ORSI, live image
and local-model gates remain unrun in this phase. Preserve prior main at
`archive/2026-10-09/main-before-content-free-diagnostics`, commit after verification,
fast-forward local main and the active checkout without changing its settings
branch, and remove only the merged feature branch. User settings, installed
skills, other worktrees, historical tips and remote refs remain preserved. The
original unknown stream event cannot be reconstructed from the old logs.

## Python Coder host guidance, 9 October 2026

`codex/python-coder-host-guidance` starts from verified main `9c5a061`. Phase 5 changes
only the Python skill's verification guidance and version (1.0.0 to 1.0.1). It states
ORSI's actual file-tool boundary, truthful unrun checks and bounded follow-up work.
Core prompts, routing, native capabilities/permissions, model/context policies,
progressive references and skill persistence are unchanged. See
[the qualification and preservation record](python-coder-host-guidance.md).

The entire installed prior package and identity, settings/configuration hashes,
refs/worktree maps and verified Git bundle are retained under ignored
`state/backups/python-coder-host-guidance-20261009/`. Focused native checks passed
262 tests with no skips/failures/errors. All four unchanged cloud cases passed before
and after the update with exact saved bytes, finite approved mutations, honest unrun
checks and released transports. Picker/message/session scopes were tested separately.
Final full native checks passed 2,672 tests and 15 subtests, with 58 optional/host
skips, no failures/errors, in 378.60 seconds. The installed updated package matches
the qualified source byte-for-byte; all twelve references round-trip and all twelve
other installed skill files are unchanged. Python/GUI execution through ORSI and real
local-model gates remain unrun. Preserve prior main at
`archive/2026-10-09/main-before-python-coder-host-guidance`, commit after verification,
fast-forward local main and the active checkout without changing its settings branch,
and remove only the merged feature branch. Preserve other installed skills,
worktrees, historical tips, remote refs and user settings edits. Phase 6 remains separate.

## Bounded edit recovery, 9 October 2026

`codex/bounded-edit-recovery` starts separately from verified main `3650e22`.
Its runtime-only recovery groups rejected edits by target, requires newly returned
source before a retry, detects verified revision cycles, and supplies detailed
stopped-work reports through the existing UI path. The core prompts, native tool
contracts, permissions, model/context policies and 128-step/four-correction budgets
are unchanged. Existing identical-read guards and valid read-after-edit work remain.
See [the recovery contract and qualification](bounded-edit-recovery.md).

Pre-fix native reproduction recorded 16 expected failures/three passes. Initial
focused checks passed 160 tests with one host symbolic-link skip; the first full
suite passed 2,663 tests and 15 subtests with 58 optional/host skips. A reproduced
same-batch recovery gap and missing failed-target label were subsequently fixed.
Final focused delivery checks passed 101 tests with one host symbolic-link skip.
All six cloud recovery cases passed on the final code; missing/stale patches recovered
through a complete read and one approved edit, while no-op cases inspected existing
text without a mutation. All four unchanged two-file fix/copy cloud cases passed;
every final report was preserved. Final full native regression passed **2,666 tests
and 15 subtests**, with **58 optional/host skips**, no failures/errors, in **382.18
seconds**. An earlier existing installer cleanup failure and related teardown error
remain recorded separately; its complete 60-test group and final full suite passed
unchanged on recheck. Skipped live gates remain separate. ORSI did not execute
Python or a GUI.

Refs/worktree maps, a verified complete-history bundle and content-free preservation
hashes are saved under ignored `state/backups/bounded-edit-recovery-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-bounded-edit-recovery`, commit
after verification, fast-forward local main and the requested active checkout
without changing its settings branch, and remove only the merged feature branch.
Settings edits, other worktrees, historical tips and remote refs stay intact.
Phases 5–6 remain separate.

## Scoped coding guidance, 9 October 2026

The separately bounded `codex/scoped-coding-guidance` change resumes on verified
main `32dc9a9` after the independent file-task reporting prerequisite. Its original
guidance tip `9e0b902` is retained at `archive/2026-10-09/guidance-before-report-fix`;
rebasing preserved its implementation and acceptance prompts. The only product
change is prompt guidance for finite requested changes, grounded edits, explicit
copies and honest verification. See [its contract and qualification](scoped-coding-guidance.md).

Final focused native checks passed 158 tests, with one host symbolic-link skip.
All four frozen default-cloud two-file fix/copy cases passed with and without the
unchanged Python skill: two approved edits per existing-file task, four mutations
per copy task, exact saved bytes, originals preserved for copies, and honest reports
retained. No coding images, failed tool calls or semantic corrections occurred;
all transports were released. ORSI did not execute Python or a GUI. Final full
native regression passed 2,638 tests and 15 subtests, with 58 optional/host skips,
no failures/errors, in 341.98 seconds. Opt-in live gates remain separate.

Pre-integration refs/worktree maps, a verified complete-history bundle and content-free
preservation hashes are saved in ignored `state/backups/scoped-coding-guidance-final-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-scoped-coding-guidance`, commit
after verification, fast-forward main and the requested active checkout without
switching its settings branch, and remove only the merged guidance branch. User
settings edits, other worktrees, remote refs and the archived earlier tip remain
intact. Phases 4–6 remain separate.

## File-task reports prerequisite, 9 October 2026

`codex/preserve-file-task-reports` starts independently from main `8462cdb` after
Phase 3 cloud qualification exposed a pre-existing answer-rendering bug. Supporting
source reads were replacing otherwise correct completion/verification reports with
the last file's contents. The prompt-guidance work remains preserved separately on
its unmerged branch and at `archive/2026-10-09/guidance-before-report-fix`.
See [the contract and qualification](file-task-reports.md).

Final focused native checks passed 89 tests and five subtests. The frozen pre-fix
reproduction has 13 expected failures/four passes, including actual result persistence.
Final full native regression passed 2,613 tests and 15 subtests, with 58 optional/host
skips, no failures/errors, in 350.04 seconds. A prior existing Git-installer cleanup
failure and related teardown error remain recorded separately; its complete 60-test
group and final full suite passed unchanged on recheck.
The unchanged cloud fix/copy gate passed all four cases using the original main prompts;
all four published answers retained their model reports. Python/GUI execution remains
outside ORSI's available tools. Prompt/routing/tool/model/context policies are unchanged.

Pre-integration refs/worktrees, a verified complete-history bundle and content-free
preservation hashes are saved in ignored `state/backups/file-task-reports-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-file-task-reports`, commit after
verification, fast-forward local main and the requested active checkout without changing
its settings branch, and remove only the merged reporting branch. Other worktrees,
remote refs, settings edits and the unmerged guidance tip remain intact. Resume Phase 3
after this separate verification checkpoint.

## Sufficient source reads, 9 October 2026

The bounded `codex/sufficient-source-reads` change starts from verified local main
`60735e1` in the clean isolated checkout under `state/routing-intent-worktree/`,
preserving the active settings-panel edits. Phase 2 adds explicit source completeness,
larger-read recovery instructions within existing bounds, and actionable source/context
limitations. UTF handling, digests, path/approval/identity checks, prompts, profiles,
sampling and loop budgets retain their existing behavior. See
[the contract and verification record](sufficient-source-reads.md).

Focused native checks passed 178 tests with two host symbolic-link skips. All four
real-cloud below-line-200 fixes passed with/without the installed Python skill;
the separately corrected oversized-file verifier passed with no mutation. Python/GUI
execution and real local-model qualification remain separate from these checks.
The unchanged Phase 1 cloud fix/copy gate passed all four cases. Final full native
regression passed **2,591 tests and 15 subtests**, with **58 optional/host skips**,
no failures/errors, in **351.16 seconds**. Compilation, dependencies and whitespace
checks passed; skipped live gates remain separately recorded.

Pre-integration refs/worktree maps, a verified complete-history bundle and content-free
settings/configuration hashes are preserved in ignored
`state/backups/sufficient-source-reads-20261009/` in the isolated checkout. Preserve prior
main at `archive/2026-10-09/main-before-sufficient-source-reads`, commit after verification,
fast-forward local main and the requested active checkout without switching its settings
branch, and remove only the merged feature branch. Other worktrees and remote refs remain
unchanged. Phases 3–6 remain separate.

## Routing intent repair, 9 October 2026

The bounded `codex/routing-intent-fix` change starts from verified local main
`7b73fe3` in an isolated checkout under `state/routing-intent-worktree/`, preserving
the active settings-panel work. Phase 1 shares route/source decisions between
preview and execution, keeps coding diagnostics and screenshots on the agent
path, and limits implicit image reuse to the current visual task. Intentional
image output and explicit skill scopes retain their supported behavior.
See [the verification and delivery record](routing-intent-fix.md).

Final focused native checks passed 272 tests, and all 120 installer/launcher
checks passed with short repository-local fixtures. All four synthetic real-cloud
fix/copy cases passed with and without the installed Python skill, and the
existing live image generation/reopen/edit gate passed. Final full regression
passed 2,564 tests and 15 subtests, with 58 optional skips and no failures/errors
in 332.38 seconds. Execution of Python and GUI behavior remain outside ORSI's available
verification tools. Other opt-in live gates are separate from passed checks.

Pre-integration refs/worktree maps and a verified complete-history bundle
containing 113 refs are preserved under ignored
`state/backups/routing-intent-fix-20261009/` in the isolated checkout. Preserve
prior main at `archive/2026-10-09/main-before-routing-intent-fix`, commit after
verification and fast-forward local main. Fast-forward the requested active
checkout without switching its settings branch or discarding its uncommitted
changes. Remove only the merged local routing branch; other worktrees and
remote refs remain unchanged. Phases 2–6 of the routing/editing plan remain separate.

## Compact notification settings, 8 October 2026

The bounded `codex/compact-notification-settings` change starts from local main
`ab04871`. General settings now places a compact sound picker/preview group and
an animated sliding notification switch at the right of their rows. The switch
matches the supplied dark-track/light-thumb reference and supports mouse, Space
and keyboard focus. Normal/minimum renders were inspected at 100% and 200% scale.
Existing sound choices, preference persistence and notification delivery remain
in place. See [the updated layout record](notification-bugfixes.md).

Focused checks passed 31 tests at 200% scaling using the suite's expected Qt
offscreen platform. An initial forced Windows-platform run passed 30 tests but
one pre-existing native-notification mock failed when its partial WinDLL stub
reached the real window-frame constructor; product code was not changed for it.
Full unrestricted Windows regression passed 2,437 tests and 15 subtests, with
58 optional skips and no failures/errors, in 376.20 seconds. Compilation and
whitespace checks passed. Live model/provider gates were not run for this
presentation-only revision. Isolated renders and test reports are retained in
`state/compact-notifications-preview/` and `state/compact-notifications-*.xml`.

Preserve prior main at `archive/2026-10-08/main-before-compact-notification-settings`,
commit the verified change, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.

## Notification corrections, 8 October 2026

The bounded `codex/notification-bugfixes` change starts from local main `696162a`.
Automatic alerts are quiet while ORSI is active. Buffered audio preserves the
entire sound with device-start padding, and General settings places the enable,
sound and preview controls in full-width rows beneath their labels. Existing
user preferences, original OGG files and tool/inference behavior are preserved.
See [behavior and verification](notification-bugfixes.md).

Focused unrestricted checks passed 64 tests, with a final 31-test notification/
audio/settings recheck after the scalable preview icon change. Native playback
of both OGG files, foreground silence and resource cleanup passed. Normal and
minimum settings renders were inspected at 100% and 200% scaling. Final full
unrestricted regression passed 2,437 tests and 15 subtests, with 58 separately
recorded optional skips, no failures/errors, in 400.28 seconds. The first full
run and installer recheck's unchanged temporary-folder cleanup failures remain
recorded separately; its process-ownership cases and fresh full suite passed.
No live model/provider gate was run.

Preserve prior main at `archive/2026-10-08/main-before-notification-bugfixes`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.
Restart ORSI to load the fixes.

## Desktop notifications, 8 October 2026

The bounded `codex/desktop-notifications` change starts from local main `d6c2d6b`.
ORSI alerts for completed responses, actionable tool approvals, completed images
and task errors. General settings includes an enable control and sound selection,
using the supplied `noti_1.ogg` by default, with `noti_2.ogg`, Silent and custom
local audio options. See [behavior and verification](desktop-notifications.md).

Focused unrestricted checks passed 51 tests. Both bundled OGG files played to
completion without audio errors; native shell delivery, minimized-window restore
and resource cleanup passed. Normal and compact settings renders were inspected.
Final full unrestricted Windows regression passed 2,424 tests and 15 subtests,
with 58 separately recorded skips, no failures/errors, in 391.68 seconds.
An initial unchanged installer cleanup failure passed all 60 installer checks
independently and the fresh full suite. No live model/provider gate was run.

Preserve prior main at `archive/2026-10-08/main-before-desktop-notifications`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees, remote refs, existing user preferences, model
profiles and inference policy remain outside the operation. Restart ORSI to load
the notification controls and event handling.

## Greeting reference appearance, 8 October 2026

The bounded `codex/greeting-reference-style` GUI change starts from local main
`7993af0`. Greeting shares the exact flat input style used by the Skills source
field in the user's reference, including its border, corner radius, spacing,
font and height. The original input and saving handlers remain in place. See
[the appearance and verification record](greeting-reference-style.md).

Normal and compact renders were pixel-identical to the reference control at
equal size and text. Native focused checks passed 60 tests and 13 subtests.
An initial full-suite installer file I/O failure passed all 26 installer checks
on an independent rerun. No installer or acceptance-prompt changes were made.
Final full native regression passed 2,414 tests and 15 subtests in 404.64 seconds,
with 58 separately recorded optional/host skips and no failures or errors.
No live API gate was run.

Preserve prior main at `archive/2026-10-08/main-before-greeting-reference-style`,
commit after full verification, fast-forward local main and remove only the
merged feature branch. Other worktrees and remote refs remain outside the
operation. Restart the normal launcher to load the reference appearance.

## Greeting composer appearance, 8 October 2026

The bounded `codex/greeting-composer-style` GUI change starts from local main
`db8f80c`. Greeting now uses the shared antialiased composer pill and gradient,
with matching text styling and comfortable padding. The existing input object
and saving handlers remain in place. See
[the appearance and verification record](greeting-composer-style.md).

Native focused settings/frame/personality/composer checks passed 49 tests and
eight subtests in 18.37 seconds. Final full native regression passed 2,414 tests
and 15 subtests in 442.24 seconds, with 58 separately recorded optional/host
skips and no failures/errors. A stalled initial image-viewer check passed both
its isolated rerun and the fresh full suite. Normal, compact and placeholder
renders were inspected using isolated preferences. No live API gate was run.

Preserve prior main at `archive/2026-10-08/main-before-greeting-composer-style`,
commit after verification, fast-forward local main and remove only this merged
feature branch. Other worktrees and remote refs remain outside the operation.
Restart the normal launcher to load the restyle.

## Cloud runtime work budget, 8 October 2026

The bounded `codex/cloud-runtime-budget` fix starts from local main `0ff7bff`.
Cloud turns receive 128 steps, 128 model requests and 256 calls, with matching
durable history capacity and a paused-task progress summary at a work-budget
stop. Existing metadata batches may contain seven calls, each independently
authorized and journaled. Local budgets, model profiles, sampling, routing,
context policy and mutation approvals remain in place. See
[the behavior and verification record](cloud-runtime-budget.md).

Final native focused regression passed 246 tests in 87.76 seconds. Full native
regression passed 2,414 tests and 15 subtests in 422.06 seconds, with 58 separately
recorded optional/host-dependent skips and no failures/errors. An initial
temporary Git-folder cleanup failure passed both the focused and full reruns;
installer code was not changed. No live provider gate was run.

A verified complete-history bundle containing 104 refs and ref/worktree maps
is preserved under ignored `state/backups/cloud-runtime-budget-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-cloud-runtime-budget`,
commit after verification, fast-forward local main and remove only this merged
feature branch. Other worktrees, remote refs and live runtime selection remain
outside the operation. Restart the normal main launcher to load the new budget.

## Greeting input visibility, 8 October 2026

The bounded `codex/greeting-input-visibility` GUI fix starts from local main
`d1dfcb7`. Greeting uses a prominent full-width field beneath its label in
General, preserving the existing saving behavior. Native focused checks passed
45 tests and five subtests, including actual clicks, keyboard editing and
preference restoration at normal/minimum window sizes. See
[the verification record](greeting-input-visibility.md).

Full native regression passed 2,399 tests and 15 subtests in 371.53 seconds,
with 58 separately recorded optional/host-dependent skips and no failures/errors.
Preserve prior main at
`archive/2026-10-08/main-before-greeting-input-visibility`, commit after
verification, fast-forward local main and remove only the merged feature branch.
Other worktrees and remote refs remain outside the operation.

## Embedded settings tabs, 8 October 2026

The bounded `codex/settings-embedded-tabs` GUI change starts from local main
`009510e`. A larger antialiased panel groups everyday preferences, models,
embedded Skills and Image Generation controls, and appearance. Future options
are disabled placeholders. Existing service handlers and user runtime stores
remain in place; see [the layout and verification record](settings-embedded-tabs.md).

Final native GUI/skills/frame checks passed 60 tests and 15 subtests. Full native
regression passed 2,398 tests and 15 subtests in 334.09 seconds, with 58 separately
recorded optional/host-dependent skips and no failures/errors. Synthetic normal,
compact and 2× display renders were inspected. No live model/API gate was run.
Preserve prior main at `archive/2026-10-08/main-before-settings-embedded-tabs`,
commit the verified change, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.

## Visual-output routing, 8 October 2026

The bounded `codex/visual-output-routing` repair starts from local main `993e5dd`.
It recognizes reference sheets and other visual outputs within the creation
clause, removes the fixed adjective-length cutoff, preserves written/analysis
tasks, and resolves original images for referential creation and view changes.
The fresh-start policy and backend/model settings remain unchanged.

Final native focused checks passed 113 tests. Full native regression passed
2,388 tests and 15 subtests, with 58 separately recorded skips, in 278.33 seconds.
Stable composer reproduction, original-byte checks and qualification limits are in
[the verification record](visual-output-routing.md). No live API gate was run.
A verified complete-history bundle containing 97 refs and worktree identities
is retained under ignored `state/backups/visual-output-routing-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-visual-output-routing`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees, remote refs and live runtime state remain
untouched.

## Photograph routing and fresh startup, 8 October 2026

The bounded `codex/image-routing-fresh-start` repair starts from local main
`e5c9c89`. Photograph requests, including the screenshot's `Genereate` spelling,
reach native image generation. Startup starts an empty active session and
archives the prior conversation/image references through the existing safe
archive path, replacing the earlier generated-image resume exception.

Native focused confirmation passed 136 tests and five subtests. Full native
regression passed 2,348 tests and 15 subtests, with 58 separately recorded skips,
in 276.67 seconds. Exact-prompt SDK reproduction and archival checks are in
[the verification record](image-routing-fresh-start.md). No live model/API gate
was run. A verified complete-history bundle containing 96 refs and worktree
identities is retained under ignored `state/backups/image-routing-fresh-start-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-image-routing-fresh-start`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other active worktrees, remote refs and runtime settings remain
untouched.

## Image preview motion, 8 October 2026

The bounded `codex/image-preview-motion` change starts from local main `a982423`.
The image generation placeholder gains wider/faster drifting red and dark navy
clouds, a padded status row, a pulsing dot and a text reflection. Request behavior,
result transfer and original-image bytes are unchanged.

Native focused checks passed 36 tests. Full native regression passed 2,339 tests
and 15 subtests, with 58 separately recorded skips, in 325.30 seconds. Synthetic
rendering and verification evidence are in [the verification record](image-preview-motion.md). No live
model/API gate was run. Historical refs and worktree identities are retained
in a verified complete-history bundle under ignored
`state/backups/image-preview-motion-20261008/`. Preserve prior main at
`archive/2026-10-08/main-before-image-preview-motion`, commit after verification,
fast-forward local main and remove only the merged feature branch. Other active
worktrees, remote refs and runtime settings remain untouched.

## Composer motion polish, 8 October 2026

The bounded `codex/composer-motion-polish` change starts from local main
`fe0909f`. Image drafts display thumbnails, the plus control pulses, wheel
scrolling eases, and the image viewer and asynchronous Qt attachment picker
fade open. Local-image lag/composer collapse was investigated only; admission,
inference and composer-height behavior remain unchanged.

Final native focused checks passed 160 tests and five subtests. Final full native
regression passed 2,339 tests and 15 subtests, with 58 separately recorded skips
in 331.03 seconds. Evidence, the earlier installer I/O failure/retry, synthetic visual
checks and investigation limits are in [the verification record](composer-motion-polish.md).
No live model/API gate was run.

Refs/worktree identities and a verified complete-history bundle containing
92 refs are retained under ignored `state/backups/composer-motion-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-composer-motion-polish`,
commit after verification, fast-forward local main and remove the merged local
feature branch. Other active worktrees, remote refs and runtime settings remain
untouched.

## Skill reference count, 8 October 2026

The bounded `codex/skill-reference-count-32` change starts from local main
`69d5856`. The shared package ceiling rises from 16 to 32 Markdown references,
with byte limits, excerpts, cloud pacing, profiles and inference policies intact.
The desktop `2d-game-dev` skill is installed into the global catalog; all 20
references passed native reading and exact-byte verification, with the four
existing skills and source bytes preserved.

Unrestricted focused checks passed 338 tests; full native regression passed
2,334 tests and 15 subtests, with 58 optional skips and no failures/errors in
356.44 seconds. The restricted-run failures remain separate sandbox evidence.
No live model/API gate was run. See [the verification record](skill-reference-count-32.md).

Refs/worktree identities and a verified complete-history bundle containing
91 refs are retained under ignored `state/backups/skill-reference-count-32-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-skill-reference-count-32`,
commit the verified change, fast-forward local main and remove the merged local
feature branch. Other active worktrees and remote refs remain untouched.

## Native image generation integration, 7–8 October 2026

Eight bounded `codex/image-generation-*` subphases start from local main
`553e333`. Each was verified, committed, fast-forwarded into main and pushed
under the user's explicit eight-subphase authorization; its merged local feature
branch was removed. The port includes independent image settings, native cloud
generation, original-resolution storage, follow-up editing, a cached animated
placeholder, viewer/save presentation and cancellation/failure handling.
Application startup resumes conversations containing generated images so their
saved originals remain visible and editable.

The final full suite passed 2,332 tests and 15 subtests, with 58 separately
recorded opt-in/host-dependent skips. Actual generation, reopening, editing and
transport release passed twice. Earlier access probes and native test failures
remain recorded separately in [the image-generation record](image-generation.md).
The final acceptance repair reuses immutable Windows DLL bindings shared by
protected image reads; file identities, handles and permission checks stay fresh.

All pre-port refs were preserved in the verified complete bundle under
`state/backups/image-generation-20261007/`. Each prior integration tip is retained
at `archive/2026-10-07/main-before-image-generation-<subphase>`. Other worktrees
and their active branches remain untouched. Runtime image choices belong under
ignored state; credentials and live image data were not committed.

## Image viewer overlay integration, 7 October 2026

The bounded `codex/image-viewer-overlay` change starts from local main `9031aa6`.
The viewer fills the available screen, shows a larger source-backed image over
a blurred/dimmed capture of the chat, and uses the same composer paint, controls,
typography and stylesheet as the main chat. Preview decoding now retains portrait
detail up to a 4096 × 4096 bound. Local/cloud follow-up sends keep their existing
source-reference and draft-preservation path. Inference and model profiles are
unchanged.

The focused viewer/composer/chat/native-window group passed 96 tests and 15
subtests. Two earlier combined UI runs aborted in a native Qt copy-feedback wait;
the viewer test fixture now holds its QApplication for the whole session and
cleans up its temporary parent explicitly. The final full regression passed
2,292 tests and 15 subtests, with 58 optional gates skipped, in 357.51 seconds.
Synthetic renders were inspected at 1920 × 1080. Live model/API gates were not
rerun for this presentation change; see [the viewer record](image-viewer.md).

Before integration, refs and worktree identities were preserved in the verified
complete bundle under `state/backups/image-viewer-overlay-20261007/`. Previous
main is retained at `archive/2026-10-07/main-before-image-viewer-overlay`. The
user's standing merge-and-push instruction authorizes integration and publication.
Other worktrees and historical tips remain untouched.

## Image-only input integration, 7 October 2026

The bounded `codex/image-only-grounding` change starts from verified local main
`8ae0aa0`. Shared local/cloud attachment guidance explains that supplied visual
input is available independently of filesystem access and defines the behavior
for image-only messages. Saved text and source bytes remain unchanged; no skill,
tool, routing, sampling or profile changes accompany this prompt repair.

The original image passed three repaired GPU full-pipeline checks; fresh runs
before the repair also passed, so the original refusal was not reliably
reproduced. The new synthetic image-only GPU gate passed, including a follow-up
that retained the user's explicit task. All 145 focused regressions passed.
The full suite recorded 2,289 passed, one unchanged native state-replacement
retry assertion failure, 58 skipped and 15 subtests in 369.89 seconds. The first
117-test isolated native recheck passed the original failing test but hit a
different unchanged skill-reader directory-rename denial (116 passed, one
failed); the fresh combined recheck passed all 117 tests in 1.87 seconds.
These failures remain recorded and do not constitute a passing full suite.

Before integration, refs and worktrees were saved with a verified complete
bundle under `state/backups/image-only-grounding-20261007/`. The prior main is
retained at `archive/2026-10-07/main-before-image-only-grounding`. The user's
standing merge-and-push instruction authorizes promotion and publication of
this bounded change. Other worktrees and historical tips remain untouched.
See [image-only input](image-only-input.md) for evidence and limitations.

`C:\Users\yaboy\Desktop\orsi_test` is the active linked checkout. Its shared Git directory is
under `C:\Users\yaboy\Desktop\o.r.s.i\.git`; the original checkout remains on
`archive/conversational-main-20260921`. That archive checkout is not the current application.

`main` holds the latest locally verified integration. Use one short-lived `codex/<change>` branch
for a bounded change. After its required checks pass, commit it, fast-forward local `main`, return
the active checkout to `main`, and remove the merged branch. Avoid stacks of finished phase branches.
Remote publication is a separate operation; local integration does not imply that GitHub was updated.

On 1 October 2026, 31 historical local branch tips were preserved as lightweight tags under
`archive/2026-10-01/<original-branch-name>`, then removed from the local branch list. Tags preserve
both merged and unmerged history. The other checkout's active archive branch was retained. Local
`main` was fast-forwarded to the existing chooser source at `b2f4e3e`, without rewriting history.
This is the source starting point for baseline repair, not a claim that the audit defects were fixed.

Before cleanup, all refs were saved in the verified bundle
`state/backups/branch-hygiene-20261001/all-refs-before.bundle`. The same directory contains the
original branch map, working-tree status, and the user's exact pre-migration model configuration.
This backup is machine-local and ignored by Git. Historical tips are also recoverable through the
archive tags even without the bundle. To resume a historical tip, create a new `codex/` branch at
its tag; do not move `main` backwards or reset an active checkout to recover old work.

Source configuration defines accepted/qualified profile targets. Ignored runtime state records
which model is selected. A clean Git status must not be confused with a matching runtime baseline:
use the diagnostic snapshot for revision, effective flags, model identity and effective limits.

## User-approved UI integration, 2 October 2026

The user approved the response formatting, borderless window and fixed transparent top controls
at UI revision `0253456`, then explicitly requested integration into main and GitHub branch cleanup.
This integration includes that working UI and this record. It is user-approved promotion, not a
claim that skipped per-model live qualification gates passed. The latest UI/native-window checks
passed 45 tests and 15 subtests; the full follow-up suite recorded 833 passed, 1 intermittent Windows
history-save failure and 54 skipped, with the failing test group passing its 15-test isolated recheck.
See [window verification](frameless-window-2026-10-02.md).

Before cleanup, all Git refs were saved and verified in the ignored backup bundle
`state/backups/branch-hygiene-20261002-ui/all-refs-before.bundle`, with ref and worktree maps alongside
it. The previous main is preserved at `archive/2026-10-02/main-before-response-ui`.
Unmerged qualification work is preserved at `archive/2026-10-02/codex/live-qualification-gate`
(`a9fb566`); the older remote integration tip is preserved at
`archive/2026-10-02/remote/codex/phase-integration-test` (`ecd70d6`). These archive tags are published
before the obsolete branches are removed. Neither unmerged tip is incorporated into main.

Eight other remote phase/UI branches are ancestors of the approved working state and can be
removed after publishing main. The original archive checkout remains on its existing branch.

## User-approved tool catalog and inline styling integration, 3 October 2026

The user explicitly requested merging and pushing the current branch after reviewing the
stable tool catalog and rounded grey inline references. The integrated source revisions are
`ca82326` (tool availability), `ee2ba69` (inline styling) and `d601dc5` (native Windows font
detection and rounded backgrounds). The previous main is `1daa20a`. This integration does
not incorporate the archived qualification-gate branch or change model profiles and limits.

At `ca82326`, the repeated live matrix passed 10/10 workflows for 14B, 6/10 for 3B and 6/10
for VL 4B: 22/30 overall, so qualification remained false. The same 14B confirmation/restart
workflow passed 2/2 on the repair versus 0/2 on unchanged main. Measured total tokens increased
from 43,338 to 94,061 across those matched sessions; the larger catalog has a material context
cost. Generated Breakout code was checked for compilation, not gameplay execution. Owned
validation servers exited. Content-free diagnostics are stored locally in the ignored
`state/stable-catalog-summary.json`; raw conversations and runtime settings are not published.

The final styling checks passed 66 focused tests and 5 subtests, including the native Qt Windows
backend. The full suite recorded 844 passed, 3 failed, 54 skipped and 15 subtests passed.
The three failures were Windows access-denied errors during atomic conversation persistence;
all three passed their isolated recheck. These failures and skipped gates remain unresolved
qualification evidence. The user's explicit merge instruction authorizes this integration;
it does not turn these results into a fully qualified baseline.

## User-approved personality integration, 3 October 2026

The user explicitly requested merging and pushing personality revision `8d95e03` after reviewing
its results. The previous main is `28482ae`. The shared voice guidance and its tests are integrated
without changes to model profiles or runtime authorization. See [personality verification](personality.md)
for the full regression and repeated live smoke results, including failures and omitted qualification
gates. User-approved integration does not change those results into full qualification.

## User-approved context-efficiency integration, 3 October 2026

After testing the isolated `TEST b481941` preview, the user explicitly approved
the changes and requested merging into main and pushing. Main is fast-forwarded
from `aa0bf7c` to the tested source `b481941`, including accepted list-marker
revision `0c58c13`. The following documentation commit records that approval;
application source matches the tested candidate.

The full regression passed 923 tests and 15 subtests, with 54 legacy skips. The
required repeated live matrix passed 21/30 cells and remained unqualified.
User-approved integration does not relabel those failures or enable recovery.
Accepted model profiles, limits, sampling and runtime selection are unchanged.
See [context-efficiency measurements](context-efficiency-stages.md).

Before integration, refs were preserved in the verified ignored bundle
`state/backups/context-efficiency-integration-20261003/all-refs-before.bundle`.
Local archive tags preserve `main-before-context-efficiency`,
`accepted-working-before-context-efficiency` and `context-efficiency-tested`
under `archive/2026-10-03/`. Merged local feature branches can be removed after
publication; no unrelated active checkout or remote feature branch is changed.
The detached preview remains available with independent state. Its launcher,
runtime/model links, conversations, settings and validation artifacts are local
only; normal `ORSI.cmd` and `ORSI_TEST.cmd` launch main after integration.

## User-approved skills UI integration, 4 October 2026

After reviewing the message picker and Settings-only installer, the user explicitly
requested merging into main and pushing to GitHub. Local main fast-forwards from
`9afeaf5` to the verified feature history: `78ce269` adds per-message attachments,
`e3467f9` simplifies the picker styling, and `9d41df3` adds Settings management.
The integration record changes documentation only; application source remains
the tested candidate.

The final regression passed 1,479 tests and 15 subtests, with 58 existing skips.
Two isolated Settings audits installed the real frontend-design and handoff
sources without model requests or changes to the user's skills/model profile.
An earlier full-run Git temporary-folder cleanup failure and its passing 60-test
recheck remain recorded in [Settings verification](skill-settings.md). Existing
skipped qualification gates are not relabeled as passes.

At integration, GitHub main `3da153d` was an ancestor of local main, 14 commits
behind it. The normal main push includes those already integrated skill-runtime
commits and the approved UI work. No force push, remote branch deletion or
other worktree modification is authorized or needed.

Before integration, all refs were preserved in the verified ignored bundle
`state/backups/skill-ui-integration-20261004/all-refs-before.bundle`, with ref
and worktree maps alongside it. The merged local `codex/message-skill-picker`
branch is removed after successful publication. Historical tips remain in the
bundle and existing archive refs; other checkouts retain their current branches.

## User-approved OpenAI cloud integration, 4 October 2026

After testing the separate cloud launcher and the Luna output-budget adjustment,
the user explicitly requested merging the cloud update into main and pushing to
GitHub. This supersedes the implementation-period instruction to leave main
unchanged. Main fast-forwards from `b22b904` through tested application source
`45fccb1`; the following integration record changes documentation only.

The integration includes the pinned OpenAI Responses SDK, native strict tools,
durable stateless response/encrypted-reasoning replay, streaming and cancellation,
context/cache measurements, packaging verification, the cloud model selector and
the 16,384-token Luna output reserve. Luna remains the cloud default; normal
startup remains local where available, with automatic fallback disabled. Ignored
runtime selection, conversations, UI preferences, local models and user skills
are preserved rather than replaced by test-fixture state.

The last focused check passed 193 tests. The full suite recorded 1,700 passed,
1 failed, 49 skipped and 15 subtests passed. The Skill Settings worker timeout
also reproduced on a pre-budget-change source snapshot. The real large-write
fixture completed a 9,110-token call; its separate exact-copy assertion failed
because the model omitted the final newline. See the retained
[output-budget verification](cloud-openai-output-budget.md). User approval does
not relabel either failure or skipped gates as a pass.

Both cloud profiles remain unqualified. Phase 4.1 recorded Luna 28/30 and Sol
30 blocked due to API permission; those measurements used the old output budget.
Legacy deletion remains gated on successful qualification. This integration
does not change prompts, permissions or profile qualification flags to bypass
those limits.

GitHub main was `b22b904` before integration. All refs are preserved in the
verified ignored bundle under
`state/backups/cloud-openai-integration-20261004/`, alongside configuration
copies and the normal runtime's distribution-version inventory. The normal
runtime needs `openai==2.54.0`; its dependency plan is checked before installation,
without replacing existing satisfied dependencies or local inference packages.

Only main is published. After successful publication, the merged local
`codex/cloud-openai` branch is removed and its test checkout remains detached at
the integrated tip, preserving its independent state and test launcher. No
remote feature branches or unrelated active checkouts are changed.

## Maximum Luna output allowance, 4 October 2026

After integration, the user requested the highest supported output allowance.
The bounded `codex/cloud-max-output` change starts from local main `a4aba0c`.
Luna receives its documented 128,000-token output allowance, with matching
context reserve, a finite 30-minute deadline and expanded bounded streaming
capacity. The input allowance, Sol profile, user settings and qualification
flags are preserved. See [maximum-output verification](cloud-openai-max-output.md).

Verification passed all 247 focused checks and the full regression: 1,704 tests
and 15 subtests passed, 49 skipped, no failures. Two short live requests accepted
the 128,000-token wire setting; a real isolated Qt selector switch away/back
confirmed effective limits and resource release. This does not claim a live
128,000-token generation or successful qualification of previously blocked gates.

Configuration copies, ref/worktree maps and a verified all-ref recovery bundle
are preserved under ignored `state/backups/cloud-max-output-20261004/`. After
verification the bounded change is committed, local main fast-forwards and the
merged local feature branch is removed. Other active worktrees retain their
original tips. The earlier detached test checkout retains `a4aba0c`; test the
new allowance by restarting the normal main launcher.

## Maximum cloud input budgets, 4 October 2026

The user requested the maximum possible cloud input cap while leaving local
mode unchanged. The bounded `codex/cloud-max-input` branch starts from local
main `35eb8eb`. Both cloud profiles use their full documented 1,050,000-token
context window, with remaining space allocated to input after their unchanged
output reserves: Luna 922,000 and Sol 1,045,904, each including the existing
256-token safety margin. Local configuration and agent policy are unchanged.

Verification passed 270 focused checks and the full Windows regression: 1,709
tests and 15 subtests passed, 49 skipped, no failures. Two synthetic live Luna
requests used more than 45,000 input tokens, exceeding the former cap; the
isolated Qt selector verified cloud switching and effective limits. Owned
resources were released. Maximum-context live qualification and Sol permission
gates remain separate from these checks. See
[maximum-input verification](cloud-openai-max-input.md).

Configuration copies, ref/worktree maps and a verified all-ref recovery bundle
are preserved under ignored `state/backups/cloud-max-input-20261004/`. After
verification the change is committed, local main fast-forwards and its merged
local branch is removed. Other worktrees retain their prior heads, including
the detached older cloud test checkout. Restart the normal main launcher to
load the new budgets.

## Quiet startup and inline approvals, 4 October 2026

The user requested a new branch to remove startup/cloud warnings and replace
approval windows with Enter/Esc review in the input area. The bounded
`codex/inline-tool-approvals` change starts from local main `e5d4831`. Configured
host read access is used at startup without a warning; per-operation write and
launch authorization stays with the existing runtime. No model profile or user
runtime configuration changes are included.

The final focused run passed 268 tests and 5 subtests, with 1 existing skip.
Existing application-launch checks passed 21 tests, and native Windows UI checks
passed 47 tests and 5 subtests. The full unrestricted regression passed 1,719
tests and 15 subtests, with 49 existing skips and no failures. See
[inline approval verification](inline-tool-approvals.md). Skipped live gates
remain separate from deterministic verification.

All pre-integration refs and the worktree map are preserved in the verified
ignored bundle under `state/backups/inline-approvals-20261004/`. The previous
main is also preserved at `archive/2026-10-04/main-before-inline-tool-approvals`.
Following the repository working baseline, verification is followed by a local
commit, fast-forward of main, and removal of the merged local feature branch.
Remote refs and other active checkouts are not changed or published.

## Approval composer animation, 4 October 2026

The user requested smooth composer growth and retraction for approval review.
The bounded `codex/approval-composer-animation` follow-up starts from local main
`c5e0c53` and adds a 240 ms eased height transition with a fixed bottom edge.
Decisions remain immediate, and interrupted animations resume from the current
height. Model and runtime authorization behavior are unchanged.

Verification passed 248 focused tests and 5 subtests, with 1 existing skip;
13 native Windows animation/approval checks; and the full regression of 1,721
tests and 15 subtests, with 49 existing skips and no failures. See
[animation verification](inline-tool-approvals.md#composer-animation-follow-up).

The pre-integration refs and worktree map are preserved in a verified ignored
bundle under `state/backups/approval-animation-20261004/`. The previous main is
preserved at `archive/2026-10-04/main-before-approval-animation`. Following the
working baseline, the verified change is committed, local main fast-forwards,
and the merged feature branch is removed. Other active worktrees and remote
refs are unchanged.

## Skill badge composer layout repair, 4 October 2026

The user requested a separate branch to repair the skill badge overlapping the
composer input. The bounded `codex/skill-chip-composer-layout` fix starts from
local main `5bb7261` and places the badge in the nested message row instead of
the outer approval stack. Selection and approval behavior are unchanged.

Native focused checks passed 69 tests and 5 subtests. The first full run hit the
previously recorded Skill Settings installer worker timeout, with 1,720 passed,
1 failed, 49 skipped, and 15 subtests passed. The isolated Settings/picker
recheck passed 19 tests. The full confirmation passed 1,721 tests and 15
subtests, with 49 existing skips and no failures. The earlier intermittent
failure remains recorded in [picker verification](message-skill-picker.md).

All pre-integration refs and the worktree map are preserved in the verified
ignored bundle under `state/backups/skill-chip-layout-20261004/`; the previous
main is preserved at `archive/2026-10-04/main-before-skill-chip-layout`.
Following the working baseline, verification is followed by committing the fix,
fast-forwarding local main, and removing the merged feature branch. Remote
refs and other worktrees are unchanged.

## Skill package format, Phase 1, 5 October 2026

The user requested the first phase of supporting Markdown references, using a
very small pack suitable for local models. The bounded
`codex/skill-package-format-v1` branch starts from local main `92c3a7b`.
The change defines the package/path/limit/failure contract, supplies a 1,591-byte
integer-clamp fixture with two short references, and freezes future live prompts.
It enables no resource imports or reader tools and changes no runtime behavior.
See [format and verification](skill-package-format-v1.md).

The focused run passed 266 tests with 2 existing skips. The full unrestricted
Windows regression passed 1,724 tests and 15 subtests, with 49 existing skips and
no failures. Reference-loading live gates are deferred until implementation;
deterministic compatibility checks do not qualify local or cloud model behavior.

Refs, worktrees and a verified all-ref bundle are preserved under ignored
`state/backups/skill-package-format-20261005/`. The previous main is preserved at
`archive/2026-10-05/main-before-skill-package-format`. After verification the
bounded change is committed, main fast-forwards and the merged branch is removed.
Other active checkouts and remote refs are unchanged.

## Skill package installation, Phase 2, 5 October 2026

The user requested Phase 2 on the bounded `codex/skill-package-install-v1`
branch from local main `b6021fc`. Local folders and Git snapshots now preserve
bounded supporting Markdown; Settings previews folders/repositories with counts,
size and package names. Whole-package byte comparisons, generated ownership
inventory, rollback and removal protect unrelated content. Single-file imports
remain available. Reference reading and model injection are not enabled.
See [implementation and verification](skill-package-install-v1.md).

The broad focused suite passed 520 tests with 2 existing skips; the final
Git/package recheck passed 74. The full unrestricted Windows suite passed
1,765 tests and 15 subtests, with 49 existing skips and no failures. An isolated
Qt preview/install visual audit passed with zero model requests. Earlier native
cleanup/test-wait failures and a failed optional diagnostic probe are recorded
separately. Model acceptance prompts, profiles and runtime authority are unchanged.

Refs, worktrees and a verified all-ref bundle are preserved under ignored
`state/backups/skill-package-install-20261005/`. The previous main is preserved
at `archive/2026-10-05/main-before-skill-package-install`. After verification the
bounded change is committed, local main fast-forwards and its merged feature
branch is removed. Other active checkouts and remote refs are unchanged.

## Skill reference reader, Phase 3, 5 October 2026

The user requested Phase 3 on the bounded `codex/skill-reference-reader-v1`
branch from local main `e22d6c9`. The change adds a revocable reader, compact
resource metadata, package/content-version checks, bounded UTF-8 continuation,
a replaceable storage interface and a scoped capability adapter. Native document
access opens/enumerates through directory handles and rechecks namespace identity.
The production catalog and conversation behavior remain unchanged until Phase 4.
See [reader implementation and verification](skill-reference-reader-v1.md).

The final focused unrestricted Windows suite passed 480 tests with 2 existing
skips, including 73 new reader cases. The full unrestricted suite passed 1,838
tests and 15 subtests, with 49 existing skips and no failures. Live local/cloud reference loading
is deferred until conversation integration. Acceptance prompts, fixtures, model
profiles, user settings, routing and context policy are unchanged.

Refs, worktrees and a verified complete-history bundle are preserved under ignored
`state/backups/skill-reference-reader-20261005/`. The starting main is preserved
at `archive/2026-10-05/main-before-skill-reference-reader`. Following verification,
the bounded change is committed, local main fast-forwards and its merged feature
branch is removed. Other active checkouts and remote refs are unchanged.

## Skill references in conversations, Phase 4, 5 October 2026

The user requested Phase 4 on `codex/skill-reference-conversations-v1`, starting
from verified local main `f31a483`. Active packages now supply compact inventories
and a turn-scoped reader. Matching package/version excerpts can be reused in
follow-ups, with bounded context accounting, stale-scope revocation and filtered
provider replay. Ordinary host access and write approvals remain unchanged.
See [conversation implementation and verification](skill-reference-conversations-v1.md).

The final focused cleanup/reference/outcome check passed 69 tests, including
37 Phase 4 cases. The isolated registry/conversation recheck passed 76 tests.
Earlier full-run cleanup regressions were fixed. A later native directory-rename
failure remains recorded separately. The final full unrestricted Windows
confirmation passed 1,875 tests and 15 subtests, with 49 existing skips and no
failures, including the directory-rename case.
Live local/cloud qualification remains Phase 5. Acceptance prompts, the tiny
fixture, model profiles, sampling, runtime settings and skill selection are unchanged.

Refs, worktrees and a verified complete-history bundle are preserved under ignored
`state/backups/skill-reference-conversations-20261005/`. The starting main is
preserved at `archive/2026-10-05/main-before-skill-reference-conversations`.
After verification the bounded change is committed, local main fast-forwards
and its merged feature branch is removed. Other active checkouts and remote refs
are unchanged; this phase does not publish to GitHub.

## Skill reference qualification, Phase 5, 5 October 2026

The user requested Phase 5 and authorized reuse of their existing desktop key
file for live cloud checks. `codex/skill-reference-qualification-v1` starts from
verified local main `05221dc`. The branch adds an isolated tiny-pack live matrix,
a restricted generated-code evaluator, a fail-closed qualification checker and
the retained [qualification audit](skill-reference-qualification-v1.md).
Application behavior, accepted profiles, runtime selection and frozen prompts
are unchanged. No credential is copied or published.

Candidate `789e011` completed 100 required cells: 36 passed, 44 failed and 20
blocked. Each local model passed 6/20; Luna passed 18/20; Sol's first request
was denied by account permissions and its remaining 19 cells were not attempted.
All owned resources exited and user configuration hashes were unchanged. A
wording-check false negative for typographic apostrophes was fixed in `866efed`;
the fresh Luna subset again passed 18/20, with genuine disabled-reader fallback
failures. Original and subset evidence remain separate. The reference feature
is unqualified; this audit does not promote any model or release flag.

Initial deterministic full runs passed 1,910 and then 1,912 tests, each with
49 existing skips and 15 subtests passed. The evaluator's final focused check
passed 38 tests. A later full run recorded 1,911 passed and two unchanged native
test failures, retained in the audit. Their isolated recheck passed 117 tests;
final full confirmation passed 1,913 tests and 15 subtests with 49 existing skips
in 225.23 seconds, including both previously failing native cases.

All pre-integration refs, worktrees and a verified complete-history bundle are
preserved under ignored `state/backups/skill-reference-qualification-20261005/`.
The prior main is preserved at
`archive/2026-10-05/main-before-skill-reference-qualification`. After deterministic
verification, commit the audit, fast-forward local main and remove its merged
feature branch. Other active worktrees and remote refs remain unchanged.

## Cloud stream diagnostics, 6 October 2026

The user requested retaining safe failure reasons and displaying the specific
cloud interruption category. The bounded `codex/cloud-stream-diagnostics`
branch starts from local main `2cbfb49`. Reasons survive the adapter, agent
runtime, saved conversation, worker and chat; logs retain only fixed categories
and counters. Incomplete calls stay blocked. See the
[diagnostics and verification record](cloud-stream-diagnostics.md).

The final focused checks passed 191 tests; the other affected OpenAI contract
checks passed 103. The initial full run had one protocol-limit wording failure,
which was corrected and passed its focused recheck. Final unrestricted Windows
confirmation passed 1,917 tests and 15 subtests, with 49 existing skips and no
failures in 235.61 seconds. Live API/model qualification gates remain unrun,
separate from deterministic passes.

All pre-integration refs and the worktree map are preserved in the verified
complete-history bundle under ignored
`state/backups/cloud-stream-diagnostics-20261006/`. After verification, commit
the bounded change, fast-forward local main and remove its merged local branch.
Runtime selection and user conversations/settings are preserved; other active
worktrees and remote refs are unchanged.
The previous main is also preserved at
`archive/2026-10-06/main-before-cloud-stream-diagnostics`.

## SDK stream-error diagnostics, 6 October 2026

Following the user's reproduced failure, `codex/cloud-sdk-error-diagnostics`
starts from local main `969ddc4`. The pinned SDK raises provider stream errors
before yielding their events, which the initial diagnostic handler incorrectly
grouped with decoding failures. The bounded follow-up separates provider,
decoding and SDK schema errors and allowlists recognized provider codes. The
user's subsequent normal-app run confirms `rate_limit_exceeded` after 22
successful tool calls. No private message/body is logged and no agent API
request or transcript replay is performed. See the
[follow-up evidence](cloud-stream-diagnostics.md#sdk-provider-error-follow-up-6-october-2026).

The focused checks passed 204 tests. Full unrestricted Windows confirmation
passed 1,930 tests and 15 subtests, with 49 existing skips and no failures in
236.04 seconds. Existing live qualification gates remain unrun; the user's
reproduction is diagnostic evidence. Model limits, prompts, retry/routing and
tool execution policy are unchanged. Rate-limit pacing is separate follow-up
work rather than an unverified model-profile adjustment.

Pre-integration refs and the worktree map are preserved in the verified bundle
under ignored `state/backups/cloud-sdk-errors-20261006/`; previous main is also
preserved at `archive/2026-10-06/main-before-cloud-sdk-errors`. After verification,
commit, fast-forward local main and remove the merged local feature branch.
Other active worktrees, user settings/conversations and remote refs remain
unchanged.

## Cloud step budget, 6 October 2026

The user requested the maximum supported cloud step count while retaining 24
for local mode. `codex/cloud-max-steps` starts from verified local main
`36e2df4`. The accepted configuration now selects 32 cloud steps and 24 local
steps, including after switching modes and in the temporary skill-reference
runtime. The existing hard 32-step contracts and other budgets are unchanged.
See the [implementation and verification record](cloud-step-budget.md).

The unrestricted focused checks passed 168 tests. Full unrestricted Windows
confirmation passed 1,937 tests and 15 subtests, with 49 existing skips and no
failures in 237.32 seconds. Live API/model qualification gates remain unrun and
separate from deterministic checks.

The previous agent configuration, refs, worktree map and verified
complete-history bundle are preserved under ignored
`state/backups/cloud-max-steps-20261006/`. The previous main is also preserved at
`archive/2026-10-06/main-before-cloud-max-steps`. After verification, commit,
fast-forward local main and remove the merged local feature branch. Other
active worktrees, user runtime selection/conversations and remote refs remain
unchanged.

## Cloud rate pacing, 6 October 2026

The user's latest normal-app failure is a provider token rate limit while the
32-step cloud budget is active. `codex/cloud-rate-pacing` starts from local main
`e05aee4`. The user reports 200,000 TPM and 500 RPM; the reproduced run records
309,803 total tokens across 21 completed operations in about 44 seconds.
See the [content-free evidence and verification record](cloud-rate-pacing.md).

The bounded change adds Responses request admission using a rolling minute
ledger and numeric server capacity/reset headers. It retains capacity after
long/interrupted streams and preserves SDK retry/partial-stream behavior.
The user's bootstrap account limits stay in ignored runtime state. Accepted
model profiles, sampling, prompts, tool behavior, context and deadlines are
unchanged; cloud steps remain 32 and local 24.

Final unrestricted focused checks passed 301 tests in 26.73 seconds. Final full
unrestricted confirmation passed 1,954 tests and 15 subtests, with 49 existing
skips and no failures in 248.54 seconds. An earlier full run's unchanged Windows
folder-rename access-denied failure is retained in the audit; its 49-test
isolated recheck and final full confirmation pass. Live API/model gates remain
unrun and separate from deterministic checks. No paid API requests or key
changes were made during verification.

Pre-change refs and the worktree map are preserved in the verified bundle under
ignored `state/backups/cloud-rate-pacing-20261006/`. Preserve prior main at
`archive/2026-10-06/main-before-cloud-rate-pacing`, commit the verified bounded
change, fast-forward local main and remove its merged local branch. Other active
worktrees, user conversations/selection/keys and remote refs are unchanged.

## Working status UI review branch, 6 October 2026

The user's explicit request places the working status changes on a new branch,
`codex/working-status-ui`, from local main `ca90b4c`. See the
[implementation and verification record](working-status-ui.md). Commit the
bounded verified change and retain this branch for review; immediate
fast-forward integration and branch deletion are deferred for this request.
Local main, other worktrees and remote refs remain unchanged. Pre-change refs,
worktree map and the verified complete-history bundle are preserved under
ignored `state/backups/working-status-ui-20261006/`.

Final unrestricted focused checks passed 246 tests and 5 subtests. Final full
unrestricted confirmation passed 1,967 tests and 15 subtests, with 49 existing
skips and no failures in 297.59 seconds. Earlier intermittent native Windows
folder-rename failures and the successful five-case isolated recheck remain
in the verification record. No existing native implementation or acceptance
test was changed. Live model/API gates remain unrun and separate from these
passed checks; no paid API requests or key changes were made.

## Working status UI integration, 7 October 2026

The user now authorizes merging every new change into `main` and pushing it
to GitHub. This supersedes the UI branch's review deferral above. The verified
UI source tip is `dd596eb`, containing working status, inline highlights,
composer placeholders, control styling and per-message skill captions.
Local main starts at `ca90b4c`; fetched `origin/main` remains `92c3a7b`.
Both are ancestors of the UI tip, so integration requires no source changes.
The push includes the eleven earlier unpublished local-main commits as well
as the five UI commits and this documentation record.

The latest unrestricted full suite passed 1,974 tests and 15 subtests, with
49 skips and no failures in 220.54 seconds. This integration reuses that
verification of the unchanged source; live model/API gates remain unrun.
See [the UI verification record](working-status-ui.md).

Pre-integration refs, worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/working-status-integration-20261007/`.
Preserve prior main at `archive/2026-10-07/main-before-working-status-ui`,
commit this record, fast-forward local main and push only main to origin.
Remove the merged local UI branch after successful integration. Other active
worktrees and remote feature/archive branches are outside this operation.

## Python Coder skill, 7 October 2026

The user requests an open-source synthesis matching the editorial discipline of
the O.R.S.I. flagship design package. `codex/python-coder-skill` starts from local
main `5c1e613`. The bounded change adds the authored `skills/python-coder` package,
twelve references, provenance/license notices, documentation and behavioral
artifact checks. See [the research and verification record](python-coder-skill.md).
No application runtime, provider configuration or existing installed skill is
changed. The new package is installed through the existing package installer.

Unrestricted focused checks passed 127 tests in 3.23 seconds. Full unrestricted
Windows confirmation passed 2,000 tests and 15 subtests, with 49 existing skips
and no failures in 247.00 seconds. Native package installation and all reference
continuations round-trip correctly; the published examples are exercised for
validation, failed saves, cleanup failures and structured concurrency. Live model
qualification remains unrun and separate from these passed deterministic checks.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/python-coder-skill-20261007/`. Preserve prior main at
`archive/2026-10-07/main-before-python-coder-skill`. Commit the verified change,
fast-forward local main, and remove the merged local feature branch. The user's
earlier instruction to merge and push new changes authorizes publishing main;
do not publish or delete remote feature/archive branches or alter other worktrees.

## Explicit skill selection, 7 October 2026

`codex/explicit-skill-selection` starts from local main `8fb396c`. The user reports
an unselected follow-up acquiring a Python Coder skill and asks for explicit
selection in both local and cloud modes. The bounded change disables automatic
selection at the service default and application composition boundary. Explicit
attachments and existing conversation history retain their established behavior.
See [the implementation and verification record](explicit-skill-selection.md).

Final native focused verification passed 313 tests with no failures or skips.
Full native regression passed 2,010 tests and 15 subtests, with 49 existing skips
and no failures in 230.82 seconds. The first run's three old-default test
expectations and their explicit fixture updates are retained in the verification
record; live model/API gates remain separate from deterministic checks.

Pre-change refs, the worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/explicit-skill-selection-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-explicit-skill-selection`.
After verification, commit, fast-forward local main and remove the merged local
feature branch. The user's existing instruction to merge and push new changes
authorizes publishing main only; other active worktrees and remote feature/archive
branches are outside this operation.

## Read progress guard, 7 October 2026

`codex/version-aware-read-guard` starts from local main `d00fe59`. The reported
cloud error was a false repetition stop on a third read after two successful
edits to the same file. The bounded change uses settled native results to renew
only the affected text-read allowances after proven content changes. No-progress
calls, writes, duplicate batches, permissions and configured budgets retain their
existing limits. See [the implementation and verification record](version-aware-read-guard.md).

Pre-fix synthetic reproduction failed the seven progress expectations while
passing eleven guard checks. Focused native verification after the fix passed
136 tests with one existing host symbolic-link skip. Final full native regression
passed 2,030 tests and 15 subtests, with 49 existing skips and no failures in
241.63 seconds. The first run's unchanged installer cleanup and reader rename
errors are retained in the verification record; all 133 tests in those groups
passed their isolated native recheck. Live model/API gates remain separate from
deterministic verification. Actual game files, model profiles and user settings
are unchanged.

Pre-change refs, the worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/version-aware-read-guard-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-version-aware-read-guard`.
After verification, commit, fast-forward local main, and remove the merged local
feature branch. The user's standing merge-and-push instruction authorizes
publishing main only. Other active worktrees and remote feature/archive branches
are outside this operation.

## Attachment foundation, 7 October 2026

`codex/attachment-foundation` starts from local main `2c96700`. The user approved
phase 1 of the five-phase image/file input plan. The bounded change adds immutable
snapshot storage and durable ordered references, worker/service/inference interfaces,
local per-message admission and explicit unsupported-backend gates. Existing
production adapters and the composer + placeholder remain disabled for attachments;
extraction, actual vision and cloud uploads belong to later phases. See
[the phase 1 implementation and verification record](attachments-phase1.md).

Final focused native checks passed 160 tests in 9.21 seconds. Full native regression
passed 2,070 tests and 15 subtests, with 49 existing skips and no failures in
246.74 seconds. All 40 new attachment contract cases passed, including Windows
source/copy handle checks. Live attachment model/API qualification is deferred
to the provider phases. Dependency and Git whitespace checks passed. No user
settings, model profiles, sampling or prompt policies were changed.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/attachment-foundation-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attachment-foundation`. After verification, commit,
fast-forward local main and remove the merged local feature branch. The user's
standing merge-and-push instruction authorizes publishing main only; other active
worktrees and remote feature/archive branches remain outside this operation.

## Attachment composer and preparation, 7 October 2026

`codex/attachment-composer` starts from local main `b0f271b`. The user approved
phase 2 of the image/file input plan. The bounded change activates + selection,
ordered removable draft cards, image thumbnails, local file dropping and clipboard
input. A cancellable worker copies and prepares supported images/documents outside
the GUI event thread. Production attachment inference remains gated until the
provider phases; unavailable sending retains the complete draft and manual skill.
See [the phase 2 contract and verification record](attachments-phase2.md).

Final focused native checks passed 150 tests and five subtests in 13.26 seconds.
Full native regression passed 2,119 tests and 15 subtests, with 49 existing skips
and no failures in 251.16 seconds. All 49 new composer/preparation cases passed.
The initial batch test's event-loop starvation and its actual Qt-loop check are
recorded separately; acceptance prompts were unchanged. Actual composer rendering
was visually inspected. Dependencies and Git whitespace checks passed. Live
attachment model/API gates remain deferred to the provider phases; no paid API
requests were made. User settings, profiles and existing model/tool policies
were unchanged.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/attachment-composer-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attachment-composer`. After verification, commit,
fast-forward local main and remove the merged local feature branch. The user's
standing merge-and-push instruction authorizes publishing main only; other active
worktrees and remote feature/archive branches remain outside this operation.

## Local document input, 7 October 2026

`codex/local-document-input` starts from local main `5b74da8`. The user approved
phase 3A of the image/file input plan: local text-document input only. Both local
llama.cpp adapters now consume complete extracted documents as user source material,
with accounting, intact attachment-turn admission, follow-ups, archive restoration
and native tool continuations. Local image input and cloud input remain gated for
their later phases. See [the phase 3A verification record](attachments-phase3a.md).

Focused native checks passed 160 tests. The accepted 14B live smoke passed with
the existing production catalog, isolated read scope, actual 16,384 context and
4,096 output reserve. The first restricted-catalog continuation failure is recorded
separately; acceptance tasks, sampling and production policies were unchanged.
The owned test server exited. Dependencies and whitespace checks passed; no cloud
API requests were made. Versioned model profiles and user settings were untouched.
Final full native regression passed 2,147 tests and 15 subtests, with 50 optional
skips and no failures in 316.34 seconds. The phase's opt-in live smoke was run
separately and passed; other skipped live gates remain unqualified.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/local-document-input-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-local-document-input`. After full verification,
commit, fast-forward local main, publish main under the user's standing authorization
and remove only the merged local feature branch. Other worktrees and remote branches
remain outside this operation.

## Attached document source grounding, 7 October 2026

`codex/attached-document-grounding` starts from local main `4e4134b`. A real attached
PDF was successfully extracted, but the 14B model searched the user's disk instead.
The bounded repair clarifies available document source text in scoped trusted policy;
plain chats, routing, tool implementations, profiles and sampling are unchanged.
Validation also exposed Windows snapshot-directory rename denials. Snapshot publication
now uses the existing state writer's short bounded tolerance, with cancellation and
immutable-byte/parent-pin protections preserved; the native handle-release fixture uses
that tolerance without accepting persistent leaked handles.
See [the failure analysis and verification](attached-document-grounding.md).

Final expanded focused checks passed 200 tests. The accepted 14B live check passed both generic
attachment reading with zero filesystem calls and explicit native file operations
with attached source. The user's actual PDF also passed an isolated read with no
filesystem calls, preserving their active conversation and prepared source bytes.
Content-free summaries retain only numeric counts/fixed outcomes, and owned servers
exited. Optional live gates and the initial full suites' Windows snapshot/fixture
rename errors are recorded separately from passed checks.
Final full native regression passed 2,157 tests and 15 subtests, with 50 optional
skips and no failures in 264.16 seconds. Dependencies and whitespace checks passed.

Pre-change refs/worktree maps and a verified history bundle are preserved under
ignored `state/backups/attached-document-grounding-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attached-document-grounding`. After full verification,
commit, fast-forward/publish main under the standing user instruction and remove only
the merged local feature branch. Other worktrees and remote branches remain untouched.

## Local vision input, 7 October 2026

`codex/local-vision-input` starts from verified local main `b47c01f`. Phase 3B adds bounded
native image input for the explicitly selected Qwen3-VL 4B and verified matching projector,
without changing the default 14B, its sampling, manual skill activation or tool permissions.
The projector is an ignored local model resource; only its pinned identity is versioned.
See [the local image contract and qualification](attachments-phase3b.md).

GPU qualification covers visual formats, different images across turns, follow-up/archive
recall, real native tool continuation and a real 14B → vision → 14B switch. The separate CPU
image gate verifies its actual limits. Numeric diagnostics preserve no source/response bodies;
all owned model servers exited, and user selection/profile bytes were preserved by the tests.
Optional live gates and native Windows fixture failures remain separate verification evidence.

Pre-change refs, worktree maps and a verified complete-history bundle are preserved under
ignored `state/backups/local-vision-input-20261007/`. Prior main is retained at
`archive/2026-10-07/main-before-local-vision-input`. After verification, commit the bounded
change, fast-forward/publish main under the standing user authorization and remove only the
merged local feature branch. Other active worktrees and remote branches are outside this work.

Final native regression passed **2,189 tests and 15 subtests, with 52 optional skips and
no failures in 259.39 seconds**. GPU and CPU live vision gates passed separately; the
full-run Windows fixture denials, isolated successful rechecks and optional skips are
recorded in the phase contract. Dependency, compilation and whitespace checks passed.

## Native cloud attachment input, 7 October 2026

`codex/cloud-attachment-input` starts from verified local main `eebb431`. The user approved
phase 4A of the attachment plan and authorized reuse of the existing API credential. The bounded
change projects immutable references to native OpenAI image/file input, checks actual multimodal
input tokens on the worker, and preserves source input through follow-ups, restored/archive
chats and native tool continuations. Local adapters/profiles, sampling, manual skill/model
selection, step budgets and user runtime settings remain unchanged. See
[the phase 4A contract and qualification](attachments-phase4a.md).

Expanded deterministic verification passed 326 tests. Default-profile real-cloud qualification
passed seven synthetic source inputs, scanned PDF page recognition, two-image cross-turn recall,
reopening/archive recall and actual stat/continuation with the twelve-tool production catalog.
The key stayed in memory, source/response bodies stay in ignored synthetic fixture state, numeric
diagnostics omit source and credential contents, and owned transport resources closed. Final full
native regression passed 2,221 tests and 15 subtests, with 53 optional skips and no failures/errors
in 278.479 seconds. Other cloud-profile access, maximum capacities and unrelated skipped gates
are not relabeled as qualified. Compilation, dependency and whitespace checks passed.

Pre-integration refs/worktree maps and a verified complete-history bundle with 76 refs are
preserved under ignored `state/backups/cloud-attachment-input-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-cloud-attachment-input`. Commit the bounded verified change,
fast-forward local main and publish main under the user's standing merge-and-push instruction.
Remove only this merged local feature branch. Other worktrees and remote feature/archive branches
are outside this operation. Phase 4B capacity qualification and phase 5 lifecycle work remain.

## Cloud attachment capacity, 7 October 2026

`codex/cloud-attachment-capacity` starts from verified local main `150a49a`. The user approved
phase 4B and retains authorization to reuse the existing API key for cloud verification.
The bounded change measures source-bearing groups before admission, fits attachment reply
allowances to account ceilings, adds numbered native source labels and preserves composer
drafts on capacity rejection. Accepted model profiles, sampling, prompts, tool behavior,
manual skill/model selection, local attachment count/GPU behavior and user settings are unchanged.
See [the phase 4B capacity and verification record](attachments-phase4b.md).

Live capacity qualification passed 1,500 images, a 49,999,999-byte PDF and 256 files; the original
phase 4A follow-up/archive/tool-continuation gate also passed with unchanged requests. Initial
live source-order recognition failures and the numbered-label repair are retained in the record.
Skipped full-size JSON and other-profile qualification are separate from passed live gates.
Credentials remain session-only, and numeric diagnostics omit source/response/key contents.

Final full native verification passed 2,236 tests and 15 subtests, with 56 optional skips,
no failures/errors and a duration of 258.313 seconds. Expanded focused checks passed 200
tests before numbered labels and 67 after the label refinement. Compilation, dependency
consistency and whitespace checks passed. Separate live gates and skipped qualification
remain explicitly identified in the capacity record.

Before integration, all 77 pre-change refs and the worktree map were preserved in a verified
complete-history bundle under ignored `state/backups/cloud-attachment-capacity-20261007/`.
Prior main is retained at `archive/2026-10-07/main-before-cloud-attachment-capacity`. After
verification, commit the bounded change, fast-forward local main and publish main under the
standing user instruction. Remove only the merged local feature branch. Other active worktrees
and remote feature/archive branches remain outside this operation. Phase 5 remains pending.

## Attachment context and lifecycle, 7 October 2026

`codex/attachment-lifecycle` starts from verified main `b61f602`. The user approved the final
attachment implementation phase. The bounded change preserves rejected composer drafts until
durable admission, transfers snapshot ownership atomically with history, cleans up owned unsent
copies and records cloud context overflow distinctly. Existing context/prompt/routing/sampling
and tool policies, profiles, one-attachment local limit, manual skill/model selection and GPU
architecture are unchanged. See [phase 5 evidence and limitations](attachments-phase5.md).

Final native full regression passed 2,260 tests and 15 subtests, with 57 optional skips and no
failures/errors in 266.097 seconds. Expanded checks passed 291 tests; the final ownership/source
handle recheck passed 85 tests. Real cloud stop/crash/archive and production-tool gates passed.
GPU vision and actual 14B → VL → 14B switching passed with unchanged profiles/user selection and
released owned processes. The 14B document gate read attachments correctly but omitted a requested
stat call on two branch runs and the unchanged prior baseline. That model-choice limitation remains
separate from passing lifecycle checks; its acceptance prompt/policy was not altered to pass.
Compilation, dependency and whitespace checks passed. Numeric diagnostics contain no keys or
source/response content, and live credentials remain session-only.

Pre-integration refs/worktree maps and a verified complete-history bundle are preserved under
ignored `state/backups/attachment-lifecycle-20261007/`; prior main is retained at
`archive/2026-10-07/main-before-attachment-lifecycle`. Commit the verified change, fast-forward
main and publish main under the standing user authorization. Remove only the merged local
feature branch, preserving other active worktrees and remote feature/archive branches.

## Sent image previews, 7 October 2026

`codex/chat-image-previews` starts from verified main `990d401`. Image attachments
now appear inside user bubbles: one larger rounded preview or an ordered row of
miniatures, with horizontal scrolling for long rows and snapshot-backed restoration.
Background verification/decoding and a bounded cache keep large image selections
responsive. Only display, documentation and tests change; inference and user settings
retain their existing behavior. See [the preview contract and evidence](chat-image-previews.md).

Expanded focused checks passed 144 tests and five subtests; final UI/composer checks
passed 72 tests and five subtests, and the final format/cache group passed 12 tests.
The first full run's unchanged native skill-reader rename denial passed its entire
73-test isolated recheck. Final full native regression passed **2,274 tests and 15
subtests**, with **57 optional skips**, no failures/errors, in **330.37 seconds**.
Actual app rendering was visually inspected using synthetic images. Compilation,
dependencies and whitespace checks passed; live model/API gates remain separate and
were not rerun for this display change.

Pre-integration refs and worktree maps are preserved in a verified complete-history
bundle under ignored `state/backups/chat-image-previews-20261007/`. Prior main is
retained at `archive/2026-10-07/main-before-chat-image-previews`. After verification,
commit, fast-forward main, publish main under the standing user authorization and
remove only the merged local feature branch. Other worktrees and remote branches
remain untouched.

## Image viewer and follow-up composer, 7 October 2026

`codex/image-viewer-reply` starts from main `023f10c`. Clicking a miniature opens a
near-screen-size image viewer with navigation and an image follow-up composer.
Replies reuse verified original references through the established attachment/send
path, preserve existing drafts and cancel automatic sending if the viewer closes
during preparation. Local mode retains one image per message; cloud can explicitly
include the set. A trusted output-image display hook supports future cloud generation,
which remains unimplemented. See [the contract and qualification](image-viewer.md).

Expanded focused native checks passed 162 tests and five subtests; final viewer/composer
checks passed 41 tests. Actual synthetic rendering, compilation, dependency consistency
and whitespace checks passed. The initial full run recorded 2,287 passed, one unchanged
reader-fixture Windows rename denial, 57 skipped and 15 subtests in 373.36 seconds.
The first isolated reader recheck recorded 72 passed and a different rename denial;
the second passed all 73 tests. The final full rerun recorded **2,287 passed, one
unchanged registry rename failure, 57 skipped and 15 subtests** in **378.15 seconds**.
All **112 registry/reader tests passed** their final combined native recheck. Both
full-run failures remain explicit unresolved Windows verification evidence; no full
run is labeled passing, and skill-reader/registry behavior or assertions were not
changed. Live model/API gates remain separately skipped for this UI change.

Pre-integration refs/worktree maps and a verified complete-history bundle are
preserved under ignored `state/backups/image-viewer-reply-20261007/`; prior main is
retained at `archive/2026-10-07/main-before-image-viewer-reply`. Commit the bounded
change, fast-forward main, publish main under the standing user authorization and
remove only the merged local feature branch. Other active worktrees, remote branches,
user settings, accepted profiles and inference policies remain unchanged.
