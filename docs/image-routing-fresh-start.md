# Photograph routing and fresh startup, 8 October 2026

The bounded `codex/image-routing-fresh-start` repair starts from verified local
main `e5c9c89`. It addresses the supplied screenshot's normal tool-agent response
to a photograph-generation request and the previous chat appearing on launch.

## Causes and resulting behavior

The image intent detector accepted `photo`/`photos` but omitted
`photograph`/`photographs`. The screenshot also spells the opening verb
`Genereate`; neither that spelling nor the photograph noun was recognized.
The request consequently fell through to the normal agent, where the reported
Blender response originated. The detector now recognizes photograph nouns and
that specific spelling variant. The same verb set is used for text-request
exclusions, so a request to generate a prompt/list/script remains a text task.
The prompt sent to native generation is preserved exactly; no prompt rewriting,
tool permissions, model selection, sampling or backend configuration changes.

Application startup previously kept the active session whenever any message
contained generated images. It now always starts a fresh session using the
existing `new_session(preserve_history=True)` path, after durable outcome
reconciliation. This archives prior messages/turns and their image references
before replacement; original files remain in attachment storage. The active
chat and inference history start empty. Explicitly opening a store remains
supported, and an archived image can be reattached for editing in a fresh chat.
No existing runtime conversation, settings or attachment file was edited by
the repair process; startup applies the archival behavior on the next launch.

## Verification

Native focused confirmation passed 136 tests and five subtests in 12.05 seconds.
The exact multi-paragraph screenshot request, with the visible spelling, was
run through the mocked native SDK with the agent enabled. It produced an image,
selected the native image-generation tool, sent the original prompt unchanged
and created no agent tool journal records. Eight intent regression cases cover
photograph requests, spelling tolerance and analysis/text-prompt exclusions.
Content-free before/after diagnostics also confirm that the prior main's
detector returned false for the provided prompt and the repaired detector
returns true, without making a request. They are retained alongside JUnit data.

The startup integration test now checks the requested fresh-session behavior:
a new session identity, empty visible messages/turns, the introductory UI, no
implicit previous-image follow-up, a complete archived previous session and
exact original image bytes. Explicit reattachment of the archive's image still
supports the existing edit prompt. Other existing acceptance prompts remain
unchanged; the earlier resume-on-start assertion was replaced because the
user now requests fresh startup. Direct store-reopening acceptance remains.

An initial command named a nonexistent startup test file and collected no
tests. The next focused run passed 135 tests/five subtests with one new-test
assertion failure: the test assumed typed input parts, but attachment-free
requests correctly use plain-string content. The assertion was corrected to
inspect that representation, without changing product code or the prompt.

Final full native regression passed 2,348 tests and 15 subtests in 276.67 seconds,
with 58 skips and no failures/errors. Skips comprise 51 opt-in live/model gates
and seven host-dependent symbolic-link checks, separate from deterministic
passes. Dependency consistency and Git whitespace checks passed. All basetemp
paths are repository-local, with JUnit evidence under ignored
`state/test-artifacts/image-routing/`. No real provider/model request was run;
the successful image result uses the SDK's mocked transport and isolated stores.

## Recovery and integration

A verified complete-history bundle containing 96 refs, pre-integration refs
and worktree identities are retained under ignored
`state/backups/image-routing-fresh-start-20261008/`.
Prior main is preserved at `archive/2026-10-08/main-before-image-routing-fresh-start`.
After verification, commit the bounded repair, fast-forward local main and
remove only its merged feature branch. Other active worktrees, remote refs,
model profiles and runtime settings remain untouched. Restart O.R.S.I. to load
the fixes and start a fresh chat.
