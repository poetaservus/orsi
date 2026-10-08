# Visual-output routing, 8 October 2026

The bounded `codex/visual-output-routing` repair starts from verified local main
`993e5dd`. The previous photograph repair did not cover the reported character
modeling reference sheet or generation of another view of an existing character.

## Cause and behavior

The matching active request was inspected narrowly during diagnosis, together
with content-free runtime metadata. It had no explicit skill, and the latest
effective baseline recorded Cloud mode. Its opening requested a professional
character modeling reference sheet. The detector did not recognize that output;
the later image noun also fell beyond the fixed 100-character creation window.
The predicate returned false, allowing the normal tool agent to answer instead
of calling native generation. A generated image was later recorded in the same
live session, so this is a routing gap rather than evidence that generation is
unavailable in that backend.

Creation now examines the requested output within its sentence/clause, with
no adjective-length cutoff. It recognizes reference sheets with visual context,
character/model/sprite sheets, concept art and common visual output nouns such
as portraits, paintings, icons, textures, diagrams and storyboards. It does not
borrow an image mention from a later unrelated sentence.

Within an eligible creation clause, the first recognized output determines
whether it is written or visual: a report containing photographs stays a report, while an image of
a person holding a report stays an image. Prompt-writing, code/document tasks
and analysis remain text requests. An unqualified reference sheet of Python
functions is not treated as character artwork. The explicit `/image` command
and existing image editing/analysis paths remain supported.

Referential creation and view changes, such as generating this character from
the side or generating a side view, now resolve the latest retained generated
original through the existing source-selection path. The same predicate is
used for classification and follow-up resolution. Those requests send original
image bytes to native generation. Unrelated fresh-image, report and folder
creation do not inherit a previous generated image through this new path.

No prompt rewriting, native-tool protocol, provider/model settings, sampling,
reference-file limits, startup/session behavior or rendering changes accompany
the repair. The fresh-start behavior from `993e5dd` remains: after restarting,
create the reference sheet again or explicitly attach a saved original before
asking for another view.

## Verification and limits

Final native focused checks passed 113 tests in 14.11 seconds. Forty added
regression cases cover visual/text intent, long clauses, original-byte reuse
and the composer-to-preview-to-result flow. The composer reproduction uses a
stable fictional reference-sheet brief with the reported leading request shape,
a mocked SDK and an enabled agent. It verifies one native image request,
unchanged prompt content, transfer of the same preview into the result, and no
agent tool journal records. Source-reuse checks compare the bytes sent to the
original retained image. Existing acceptance prompts remain unchanged.

Before/after content-free diagnostics show false -> true for both the reference
sheet fixture and the reported side-view wording with an image source. Evidence
is retained under ignored `state/test-artifacts/visual-output-routing/`.
No live API request or credential inspection was performed by this repair.

An attempted one-off qualification read mutable active conversation state: a
different request had become latest, then the matching request was no longer
retained. Both failures are setup evidence, not passing qualification. The
stable composer regression avoids depending on a user's changing chat. Its
initial assertions sampled the preview before queued activity arrived and then
assumed one activity notification; the app correctly delivers repeated activity
notifications that reuse one preview. The test now verifies that asynchronous
preview/result invariant without changing product UI or the prompt. Intermediate
runs recorded 108 passes plus the new-test assertion failure; confirmation
passed 109 tests before four final intent cases raised the total to 113.

Full native regression passed 2,388 tests and 15 subtests in 278.33 seconds,
with 58 skips and no failures/errors. Skips comprise 51 opt-in live/model gates
and seven host-dependent symbolic-link checks, separate from deterministic
passes. Dependency consistency and Git whitespace checks passed. Tests use
repository-local basetemp. Real model/provider qualification and live UI acceptance
are separate from the mocked SDK and offscreen Qt verification above.

## Recovery and integration

A verified complete-history bundle containing 97 refs and pre-integration
refs/worktree identities are under ignored
`state/backups/visual-output-routing-20261008/`.
Prior main is preserved at `archive/2026-10-08/main-before-visual-output-routing`.
After verification, commit the bounded repair, fast-forward local main and
remove only its merged feature branch. Other active worktrees, remote refs,
model profiles, live chat files and runtime settings remain untouched.
Restart O.R.S.I. to load the corrected classifier and source-resolution predicate.
