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
