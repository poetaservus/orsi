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
