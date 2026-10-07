# Explicit skill selection, 7 October 2026

The user reported that an ordinary error follow-up acquired a `/python-coder`
caption without selecting the skill. The prior service default asked the active
model to select a skill using the latest message and installed catalog metadata.
Even though composer attachments expired after their turn, that separate router
could choose the same skill for a later message.

## Current behavior

Both local and cloud modes now require explicit selection. An unselected message
makes no skill-routing model request and injects no active skill instructions.
Previous messages and answers remain in the existing conversation history, so a
follow-up still has context. Earlier skill captions are historical records and
do not activate a skill on another turn.

A composer attachment still applies to its outgoing turn, including tool
continuations and approval waits, and expires on completion or failure. Attach
the skill again to apply its instructions to a later turn. The legacy session
activation API and slash command remain deliberate user selections; a temporary
message attachment still restores any previously explicit session selection.

`ConversationService` now defaults `automatic_skills_enabled` to false.
`build_application` also passes false explicitly, independently of the chosen
inference mode. The selector implementation and its explicitly opted-in
qualification fixtures remain available; the application exposes no automatic
selection toggle. Skill contents, tools, approvals, model configuration, sampling,
and context admission are unchanged.

## Verification

Final native Windows focused checks passed **313 tests**, with no skips or failures,
in 16.98 seconds. New regressions cover both local/cloud modes, chat/tool turns,
and switching modes before the error follow-up. Synthetic backends are scripted
to select a real installed fixture skill if the router is called; they receive
zero router requests and exactly the three expected answer requests. The same
checks verify retained user/assistant history, unchanged tool definitions,
explicit instruction injection, attachment expiry, and captions only on the
selected message. Startup is exercised in both modes with isolated state and
fake backends, plus the existing lazy Responses tool-startup checks.

The existing empty-catalog, catalog-refresh routing, and oversized upstream
admission tests now opt into automatic selection explicitly, preserving their
acceptance inputs and selector expectations. The startup catalog test now expects
one direct answer request for either a populated or empty catalog. The existing
automatic qualification matrix already opts in and is unchanged. The first full
run reported these three old-default expectations as failures (2,007 tests and
15 subtests passed, 49 skipped, 228.26 seconds); no Windows access failure occurred.
Its report is retained in ignored `state/pytest-explicit-skill-full.xml`.

Final full native Windows regression passed **2,010 tests and 15 subtests**, with
**49 existing skips**, no failures, in 230.82 seconds. The skipped host-dependent
symbolic-link and opt-in live model/API/UI gates remain separate from these
deterministic checks. Reports and temporary state are repository-local under
ignored `state/`; the final reports are `pytest-explicit-skill-focused-final.xml`
and `pytest-explicit-skill-full-final.xml`. Dependency consistency and authored-file
whitespace checks passed. No paid API calls or key changes were made. Restart
O.R.S.I. to rebuild the running service with the new selection policy.

## Integration

Developed on `codex/explicit-skill-selection` from local `main` `8fb396c`.
Pre-change refs, the worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/explicit-skill-selection-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-explicit-skill-selection`.
After verification, commit the bounded change, fast-forward local main, and
remove the merged local feature branch. The user's existing instruction to merge
and push new changes authorizes publishing main. Other worktrees and remote
feature/archive branches are outside this operation.
