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
