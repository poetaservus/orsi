# Complete integration and repository cleanup, 13 October 2026

After confirming the reasoning-response fix worked, the user explicitly
requested that every new change be merged into main, the Git repository be
cleaned and main be pushed to origin.

## Integrated work

The composer/model/reasoning controls, saved-history compatibility and live
Responses reasoning-content fix were already on main at `189be24`.
The only outstanding feature branch was `codex/scroll-behavior-acceptance`
at `97a9648`, containing 14 commits. It is merged with both histories retained.
The conflict resolution keeps main's bounded receipt reconstruction and the
branch's completion guidance and scoped verification reports. Both change
records remain available.

The approval-panel tests now measure the restored composer against its initial
height instead of the obsolete 54-pixel layout. Their animation reversal point
is adjusted for the taller composer; approval, draft and focus checks remain.
The README is updated for the current composer, cloud and shell capabilities.

The working composer, reasoning selection and Responses replay parser remain
intact. Accepted model profiles and private user settings are unchanged.
No archive-era code replaces current functionality. The separate older
conversational checkout remains attached to its historical branch.

The earlier branch's 0/3 default-cloud scroll-repair live gate remains recorded
in [its qualification history](complaint-repair-loop.md). The user's explicit
request authorizes this integration; it does not turn those historical failures
into passed acceptance runs. The unavailable later prompt remains a skipped
exact replay. Live summary qualification is a separate check.

## Verification

- 203 focused integration checks passed before the full suite.
- The first full native run passed 3,546 tests and 15 subtests, with 61 skips,
  and failed five approval-panel assertions tied to the old composer geometry.
  All 80 composer and approval checks passed after updating those assertions.
- A live Luna Medium read/summary run completed on the integrated code using
  three generated files only. All three files were read, five provider responses
  were retained, the saved history reopened successfully, the files were unchanged
  and the owned transport was released.
- Final full native suite: **3,551 tests and 15 subtests passed, 61 skipped**,
  with no failures or errors, in 636.05 seconds. Results are retained in
  ignored `state/integration-final.xml` and `.log`; temporary files use
  `state/integration-final-temp` inside the checkout.
- Opt-in live/model gates and unsupported host/platform checks are reported as
  skips separately; deterministic passes do not qualify those gates.
- Publication audit checks all outgoing commits and staged additions for
  private runtime paths and credential material, without printing secrets.

Results use repository-local temporary storage and content-free summaries under
ignored `state/`. User profiles, model files, runtime dependencies and generated
test data stay local. No user website or personal conversation is used in the
integration's live gate.

## Cleanup and publication

Both pre-integration tips are retained as recovery tags:
`archive/2026-10-13/main-before-complete-integration` and
`archive/2026-10-13/scroll-behavior-before-integration`.
Inactive historical archive branches are converted to tags of the same name
and commit. Active worktrees retain their branch attachments and files. Only
merged feature branches are removed after main advances.

Push local main to `origin/main` without rewriting history. Recovery tags and
other worktree branches remain local. Content-free ref inventories and the
publication audit are retained under
`state/backups/git-integration-20261013/`.
