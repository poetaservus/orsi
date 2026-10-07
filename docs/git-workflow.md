# Git layout and baseline hygiene

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
