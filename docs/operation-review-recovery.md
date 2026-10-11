# Interrupted-operation recovery

An interrupted operation previously set a durable review flag that stopped every
subsequent agent turn before inference. Even an ordinary chat message displayed
“A previous write outcome requires review before another operation can run.”
The journal had an acknowledgement method, but the application exposed no way
for the user to review it.

## Behavior

Chat can now complete while earlier operations await review. Permitted read-only
tools can inspect the affected files and earlier history. Their existing path
restrictions and permission decisions still apply. Commands, changes and other
non-read operations remain paused, both in the agent and the journaled executor.
The agent checks this before preparing an edit, so stale patch contents cannot
turn a required human review into a correction loop. Paused new calls are
recorded as denied, rather than incorrectly acquiring another unknown outcome.

The app shows **Review interrupted operations** above the conversation. The
panel lists operation types, times and retained references without exposing
arguments, paths, credentials or file contents. A checkbox and explicit button
acknowledge the exact displayed operations in one atomic journal transition.
New interruptions outside that snapshot stay pending. Cancelling, closing the
panel or starting a new chat does not acknowledge anything.

Acknowledgement preserves the unknown outcome and does not retry operations,
authorize new calls or mark an earlier task complete. A subsequent change still
requires its normal permission and approval. No model-callable recovery tool is
added. Existing explicit journal retention remains in force.

If a running result could not be persisted, tools remain blocked until restart.
The app explains this and disables acknowledgement until restart has recovered
the durable running record. Chat remains available. A failed acknowledgement
leaves the panel open and the durable flags intact.

The same recovery uses encrypted profile storage. Profile lock and window close
close the panel and clear its retained display data. User settings and existing
journals are not reset or migrated by this repair.

## Qualification, 11 October 2026

Two focused reproductions failed on the original guard: ordinary chat and a
read-only check both stopped with `internal_failure`. Both pass after repair.
Native focused qualification passed **195 distinct tests**, covering chat,
permission denials, mutation blocking, direct executor enforcement, restart,
atomic acknowledgement and storage failure, fresh approved edits, conversation
outcomes, inline approvals, Qt interactions/scrolling and encrypted profiles.
Synthetic screenshots of the banner, panel and recovered conversation were
inspected; this caught and corrected a low-contrast button and clipped text.

One older configuration fixture fails separately:
`test_agent_runtime_is_connected_only_through_the_startup_feature_gate` expects
the configuration before `shell_run_enabled` was added. Its exact inputs and
fixture were extracted from unchanged main `3ec1c1f` and reproduce the same
failure. They remain unchanged in this bounded branch. Intermediate fixture
errors and their corrected Qt lifecycle/layout checks are retained separately.

No full suite or live API gate ran for this change. The reported failure happens
before inference; deterministic recovery and actual Qt/native file operations
exercise that boundary without sending user data. Content-free qualification and
preservation evidence live under ignored
`state/backups/operation-review-recovery-20261011/`; baseline reproduction and
synthetic screenshots are under `state/operation-review-baseline/` and
`state/operation-review-visual/` respectively.

Work begins on `codex/operation-review-recovery` from local main `3ec1c1f`.
Preserve prior main at
`archive/2026-10-11/main-before-operation-review-recovery`, commit the bounded
repair, fast-forward local main and remove only the merged feature branch.
Preserve configuration, historical refs, other worktrees and remote branches;
no publication.
