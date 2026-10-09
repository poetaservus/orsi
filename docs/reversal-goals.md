# Reversal checks and stored goal evidence

This bounded change starts at published main `dd87567` on
`codex/reversal-check-goal-evidence`. It addresses observed follow-up edits that
successfully undid earlier edits before the existing revision-cycle guard stopped
the task. It changes runtime recovery and conversation evidence; routing, the
twelve native capabilities, approvals, model profiles, sampling, context policy,
core prompts and the installed Python Coder package remain unchanged.

## Reversal preflight

The runtime reconstructs UTF-8 bytes only from complete returned source whose
digest matches those bytes, preserving BOM and newline bytes. It can also retain
the predicted bytes of a subsequent settled text mutation when its returned digest
matches. It uses the existing pure edit planner to predict the next revision,
without additional filesystem access or permission authority.
The last settled mutation digest remains separate from the latest read digest:
a truncated read cannot erase it and bypass a whole-file reversal check. That
retained digest is a historical receipt, not a claim to have read current bytes.

An edit or whole-file write returning to a known earlier revision is rejected
before approval or execution. Its failed receipt explains that no reversal ran.
The model gets one bounded reassessment for that target. A rollback must follow a
new complete source read received after the rejection and include an explanation
in the assistant text accompanying the proposed call. The explanation is a model
claim, not verified semantic evidence. Normal exact-diff approval remains required.
One such rollback can succeed; another return to an earlier revision stops before
execution. Distinct new edits retain their existing budgets.

An excerpt cannot establish complete-file revision prediction. A pending exact
reversal cannot bypass reassessment with a truncated read. The existing settled
revision-cycle guard remains the fallback for other changes whose complete bytes
cannot be reconstructed. This is a guard against known revision returns, not a
semantic detector for every possible loop. A new user turn starts a new tracker,
so an explicit later undo is not blocked by an earlier turn's history.

## Durable goals and completion evidence

Each agent turn stores one goal containing the exact latest request. The runtime
does not guess a semantic checklist from prose or treat generated text as an
independent test. The goal belongs to that turn; earlier goals remain in history.

For settled text edits and writes, artifact evidence records the resolved path,
saved SHA-256, and the internal successful mutation receipt ID. A later complete
read matching that saved digest adds its own receipt ID. A new mutation clears
that check. A different observed revision, missing target, uncertain write
outcome, or subsequent move/trash/overwrite invalidates applicable evidence.
Source checks never prove Python execution, imports, GUI behavior or tests.

Goal state is `active`, `reported_unverified` when the model finishes, or `stopped`.
`behaviour_verified` is always false with the present capability catalog. A model
cannot set it true. The stored completion evidence and runtime-owned stopped
reports distinguish save receipts and matching source reads from unrun
runtime/GUI checks. Successful answers and provider partial text retain their
existing content. Attachment-only goals retain empty request text and link to the
turn's original user message with its durable attachment references. A reminder derived from
settled evidence asks the model to compare the current request with the work and
continue only for an identified unmet requirement.

Goals are persisted with each settled receipt in the existing ignored conversation
store. On loading, they must equal the projection of the actual request and durable
receipts, including receipt IDs and digests. Interrupted turns retain evidence and
become stopped without replay. Older histories without goals remain loadable.
Unknown journal-only mutations retain the existing review requirement; goal
evidence does not grant execution authority. Goal text, paths, source and patches
are excluded from content-free route/turn diagnostics and baseline snapshots.

## Qualification

The existing cycle unit test now expects pre-execution rejection and retention of
the successful change, rather than three approvals for a completed undo/redo
cycle. Its user prompt is unchanged. All live acceptance prompts remain unchanged.
New deterministic checks cover fresh-read reassessment, legitimate rollback,
blocked repeated reversals, BOM/CRLF preservation, whole-file writes, later user
undo, truncated and missing source, invalidated checks, restart recovery, legacy
history and fabricated evidence.

`tools/verify_reversal_goals.py` is opt-in. Three controlled setup responses create
a successful change followed by a rejected reversal; only the subsequent
reassessment calls the live configured model. Separate plain/Python Coder cases
must retain the requested bytes, perform exactly one approved mutation, obtain a
matching source read, restore durable goals, report verification honestly, and
release their transports. This does not claim the live model itself produced the
synthetic reversal. Production limits are unchanged.

Pre-change refs/worktree maps, a verified complete-history bundle, configuration
and settings hashes, and qualification summaries are retained under ignored
`state/backups/reversal-goals-20261009/`. Live fixture artifacts are isolated under
ignored `state/reversal-goals-live-*`. Python/GUI execution through ORSI and live
local-model checks remain unrun. Native regression and live results are recorded
separately before integrating and pushing this change.

Final native focused qualification passed 74 checks in 80.250 seconds. Final full native regression passed 2734 checks (including the existing 15 subtests), with 58 optional/host skips, zero failures/errors, in 412.573 seconds. JUnit counts include subtests. All four unchanged live coding cases passed with expected bytes, finite approved mutations, preserved requested originals, truthful unrun checks and released transports. Both final controlled-reversal live reassessment cases passed with one rejected reversal, one approved mutation, a matching source read, restored goal evidence and two live requests each. The initial full run identified successful-report rewriting and attachment-only compatibility issues; both were fixed without changing those existing assertions. A subsequent full run passed before review identified the truncated-read whole-write bypass. Both new boundary cases failed before its fix, then passed alongside the focused checks and final full suite. Earlier reports remain retained separately. Python/GUI execution through ORSI and live local-model gates remain unrun.
