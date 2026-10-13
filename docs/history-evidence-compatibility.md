# Saved repair-history compatibility

The composer branch started from verified main, while the user's earlier
scroll-repair branch had already persisted additional verification fields.
Main's strict history reader rejected those fields, returning no conversation
service and preventing Send. A synthetic frozen record reproduced the failure
before this change for both terminal and interrupted turns.

Retain the known bounded verification format from `97a9648` and reproduce its
projection only for receipts carrying `evidence_version: 2`. Both the turn and
outcome goals must still match the settled receipts exactly. Unknown fields,
fabricated assertions, changed screenshot hashes, unsupported success claims,
malformed receipts and mismatched evidence versions remain rejected. Stored
failures and stale checks remain failures and stale checks. Screenshot
observations still require review and never establish whole-task success.

This integrates the history contract only. Composer controls, model profiles,
API reasoning selection, prompts, live tool contracts, routing and sampling
retain their existing behavior. No history reset or user-state migration is
required. Normal startup retains the prior session in its profile archive.

## Verification

127 necessary native Windows checks passed with repository-local temporary
storage (`state/history-evidence-final-temp`). The focused checks cover legacy
and v2 history, interruption recovery, stale/failed evidence, tampering,
archives, recall, provider replay, goals and composer reasoning. A synthetic
encrypted profile successfully passed real application startup, archived its
prior request and evidence, and sent a new message through the composer Send
button to an in-memory provider. Windows handle restrictions affected an
initial sandbox run; native checks passed.

The user's encrypted profile was not unlocked, read or modified. Its actual
restart remains a user-side check. No live API requests or full-suite run were
made, consistent with the requested scope. Test output is under
`state/history-evidence-final.log` and `.xml`; fixtures contain synthetic data.

The bounded branch starts at composer commit `766dba3`. Preserve that main tip
as `archive/2026-10-13/main-before-history-evidence-compatibility`, commit,
fast-forward local main and remove only this merged branch. Retain the earlier
unmerged repair branch and other worktrees. No remote publication.
