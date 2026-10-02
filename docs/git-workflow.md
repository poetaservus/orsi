# Git layout and baseline hygiene

`C:\Users\yaboy\Desktop\orsi_test` is the active linked checkout. Its shared Git directory is
under `C:\Users\yaboy\Desktop\o.r.s.i\.git`; the original checkout remains on
`archive/conversational-main-20260921`. That archive checkout is not the current application.

`main` holds historical integration source; past deterministic verification and skipped live tests
do not certify it as the working baseline. Use one `codex/<change>` branch for a bounded candidate.
Commit before running the mandatory exact-revision live matrix. Promote only with
`tools/promote_working_baseline.py --report <report> --promote`: it verifies every required live
workflow and profile, fast-forwards local `main`, marks `working-baseline`, returns to `main`, and
removes the merged candidate branch. Failed or blocked candidates stay on their single unmerged
branch. No `working-baseline` ref is created until a complete run passes.

Manual Git merges do not produce qualification evidence. The supported promotion command and
release packaging enforce the gate; this is not protection against an owner deliberately bypassing
the workflow with raw Git. No shared Git hooks are installed in the other active checkout.
Remote publication is separate; local integration does not imply that GitHub was updated.

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

See [mandatory live qualification](live-qualification-2026-10-02.md). Profile labels such as
`accepted`, `load_tested` and `experimental` describe model targets and history, not build qualification.
