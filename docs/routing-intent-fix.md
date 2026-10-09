# Routing intent repair — Phase 1

Prepared 9 October 2026. The bounded `codex/routing-intent-fix` change starts
from verified local main `7b73fe3`, implementing Phase 1 of
`Desktop/routingfix.md`. Work is isolated in `state/routing-intent-worktree/`
to preserve the active checkout's unfinished settings-panel changes.

## Behavior

`ConversationService.image_route_decision` supplies the route, fixed reason,
effective explicit skill, source category and ordered immutable references.
Both the composer preview and worker use that decision path. The worker resolves
its decision under the turn lock before admitting attachments.

Intent comes from the requested action and output. Fenced code, inline code,
quoted excerpts, traceback frames and indented diagnostics are excluded from
classification; the original message and screenshot bytes still reach normal
inference. Drawing identifiers, Python source fixes, requested versioned copies,
negation and corrections remain on the agent path with the enabled file catalog.
Negating a written output does not veto an affirmative visual request.

Visual follow-ups resolve sources only after the current request establishes
visual intent. An intervening file task or unrelated conversation ends implicit
source reuse. Generic pronouns and versions do not select an old image. Explicit
source selection can reopen that visual task. Image inspection remains analysis,
and an explicit selected original takes precedence over older generated results.
Durable image history and original bytes are retained.

Message and session skill selections receive the same treatment. A selected skill
can disambiguate a generic visual property request but cannot veto `/image`, named
visual creation or concrete image edits. Skill persistence and picker behavior
are unchanged. Natural photographs, illustrations, reference sheets, diagrams,
view changes and common image edits retain the image path.

This phase changes routing and source selection only. Prompts, tool behavior,
sampling, context limits, model profiles, turn budgets, approval and cancellation
contracts are unchanged. Larger source reads, coding guidance, edit recovery,
skill guidance and expanded diagnostics remain separate Phases 2–6.

## Deterministic verification

The new regression module adds 127 cases, including actual SDK request bodies,
the twelve-tool production catalog, screenshot bytes, Qt composer preview,
historical-image isolation, selected-source identity and both skill scopes.
Existing acceptance prompts and assertions are unchanged.

Final focused native verification passed 272 tests. All 120 existing Git skill
installer/skill installer checks passed with the portable runtime available and
a shorter repository-local fixture path. Compilation, dependency consistency
and Git whitespace checks passed.

Final full native verification passed **2,564 tests and 15 subtests**, with
**58 optional skips**, no failures/errors, in **332.38 seconds**. Reports are retained in
`state/routing-verified-focused.xml`, `state/routing-short-recheck.xml` and
`state/routing-verified-full.xml` within the isolated checkout.

The preceding full run passed 2,560 tests and 15 subtests, with 58 optional skips
in 366.86 seconds. The frozen final revision includes four further
image-inspection/source-selection regressions and receives its own full run.

The first restricted run could not open pinned ancestor handles and is not
product-failure evidence. The preliminary unrestricted full suite recorded 2,549
passed, two failures, one teardown error, 58 optional skips and 15 passing
subtests. Its isolated checkout lacked the ignored portable runtime, and the
deep fixture directory exposed temporary Git cleanup/download failures. A longer
isolated installer recheck recorded 101 passed, 19 failures and one teardown
error; shortening the repository-local fixture path passed all 120 checks.
Neither failing run is relabeled passing, and installer code/assertions were
not changed. The final suite uses the existing runtime through an ignored
junction and short owned fixtures under the active repository's ignored state.

## Live qualification

The user authorized reuse of their existing local credential. The final live
gate uses isolated synthetic Python files, a synthetic bug screenshot, copied
installed skill assets, an isolated cloud selection and the unchanged production
catalog, sampling, prompts and turn limits. Fixture permission rules restrict
reads/writes to the synthetic area; mutation approval remains bound to the
requested target. The installed skill and user's files, conversations, settings
and model selection are not modified.

All four real cloud cases passed on the configured default `gpt-6-luna`: an
existing-file fix and an explicitly requested copy, each with and without the
installed `python-coder` skill. Every case completed with zero image results,
zero failed tools, two or four calls, verified destination bytes and preserved
original bytes for the copy workflow. The plain existing-file case also began
with a real generated image to verify that it could not redirect the later code
request. All owned transport threads were released. The installed entry-point
identity remained `ab4643c14f92c4c176a11f3f6f6bb8767b9c16515f168b60422970a4e6aa23b2`.

The unchanged existing live image gate passed generation, reopen and an edit
using `gpt-image-2.5-flare` at low quality, and released its transport. Summaries
are retained under `state/routing-live-verified/summary.json` and
`state/routing-image-live/summary.json`. Earlier summaries remain separate;
the initial gate's two skill cases were skipped because its assumed directory
name did not match the registry's hashed installation directories. Registry
discovery resolved the actual installed package before final qualification.

Reports retain only numeric counts, identities and fixed categories. Keys,
prompts, screenshots, source, patches and raw provider events are excluded from
diagnostic summaries. Synthetic conversation/fixture content remains in its
separate ignored area. ORSI did not execute Python or test GUI behavior; live
coding qualification proves saved-byte changes and bounded tool completion on
these small files. The larger 453-line Pythagoras file is outside this phase's
live qualification. Other opt-in live/model gates remain separately skipped.

## Local delivery and recovery

All 113 pre-integration refs, worktree identities and a verified complete-history
bundle are retained under ignored
`state/backups/routing-intent-fix-20261009/` in the isolated checkout. Preserve
prior main at `archive/2026-10-09/main-before-routing-intent-fix`, commit the
verified change and fast-forward local main. The active checkout can be
fast-forwarded while keeping its existing settings branch and uncommitted
settings changes, without switching or resetting it. Remove only the merged
routing branch. Other worktrees and remote refs remain outside this operation.
