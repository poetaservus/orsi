# Read progress and repetition guard, 7 October 2026

The reported cloud follow-up stopped after 36.54 seconds at model step 12.
Its settled trace contains a full text read, two successful exact edits with
intervening reads, and a third full-read request blocked before execution. Each
saved version had a different digest, but the repeat guard compared only tool
name and arguments across the turn. The two-call allowance therefore mistook
verification of changed content for a stalled loop. The failed search-text edit
earlier in that turn did not itself trigger the terminal stop. Both successful
edits were retained; the cloud's 32-step limit had not been reached.

## Fix

A turn-local `ReadProgressTracker` observes settled native tool results. It
remembers each successful text-read fingerprint, the resolved result path, and
the complete-file digest when available. After a successful `filesystem.edit_text`
or `filesystem.write_text`, it renews only the text-read allowances for the same
resolved file when the returned digest proves a content change. Windows path
matching is case-insensitive and accepts the native canonical result paths.

Successful exact edits also renew a prior truncated read: the existing exact-edit
implementation rejects no-op replacements before execution. Whole-file writes
without a known prior digest remain conservative, because successful replacement
alone does not prove different bytes. Missing or malformed write digests renew
nothing. A read with a truncated digest may consequently need a larger source
read to establish the version before repeated whole-file replacements.

Unchanged content, failed or denied operations, and edits to other files renew
nothing. Other capabilities retain their existing repetition counts. Each changed
file still has the configured two identical reads available before another
settled change. Duplicate calls in one batch remain rejected before execution;
unsettled changes in that same batch do not grant an early allowance. Step and
call limits still bound workflows that continue changing files.

The tracker performs no filesystem reads, launches no model requests, and grants
no permissions. It observes results only after the existing durable settlement
path succeeds. Prompts, routing, model profiles, context policy, tool contracts,
approvals and configured limits are unchanged. Actual game files and user settings
are outside this patch.

## Verification

The pre-fix synthetic native reproduction reported seven expected failures and
eleven passes in 15.86 seconds. Identical read/edit/read acceptance sequences
failed in both local and cloud modes; no-progress guard checks passed. The report
is retained in ignored `state/pytest-read-guard-before.xml`.

After the fix, focused native checks passed **136 tests**, with one existing
host symbolic-link skip, in 42.30 seconds. Twenty new regressions exercise actual
read/edit/write adapters and approvals on synthetic files, both inference modes,
full and truncated source reads, retained edited bytes and result history,
unchanged-file loops, unrelated changes, no-op writes, failed/denied edits, renewed
two-read limits, duplicate batches and canonical path matching. The pre-fix
acceptance sequences and existing guard tests are unchanged.

The first full native run passed 2,028 tests and 15 subtests, with 49 existing
skips, two failures and one teardown error in 251.87 seconds. All new guard checks
passed. The failures were in unchanged modules: Git installation reported failed
cleanup of a temporary download after its size limit rejected the repository;
reference inventory validation hit Windows access denied when renaming its
fixture folder. The cleanup also caused its teardown assertion. Their complete
133-test groups passed the isolated native recheck in 18.94 seconds. No installer,
reader, Windows handle implementation, or existing acceptance test was altered.
Both reports remain in ignored `state/pytest-read-guard-full.xml` and
`state/pytest-read-guard-native-recheck.xml`.

Final full native regression passed **2,030 tests and 15 subtests**, with
**49 existing skips**, no failures, in 241.63 seconds. Host symbolic-link checks
and opt-in live model/API/UI gates remain separate from passed deterministic
checks. The final report is ignored `state/pytest-read-guard-full-final.xml`.
Dependency consistency and authored-file whitespace checks passed. No paid API
calls or key changes were made to reproduce or verify this harness error.

## Integration

Developed on `codex/version-aware-read-guard` from local main `d00fe59`.
Pre-change refs, the worktree map and a verified complete-history bundle are
preserved in ignored `state/backups/version-aware-read-guard-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-version-aware-read-guard`.
After verification, commit, fast-forward local main, push main under the user's
existing instruction and remove the merged local feature branch. Other active
worktrees and remote feature/archive branches are outside this operation.
Restart O.R.S.I. to load the updated guard.
