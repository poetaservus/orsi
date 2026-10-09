# Image generation preview motion, 8 October 2026

The bounded `codex/image-preview-motion` change starts from verified local main
`a982423`. It changes the generation placeholder's presentation: faster, wider
cloud movement, muted red accents, deeper navy, and a padded status row with a
warm pulsing dot and a left-to-right reflection across the text.

## Presentation and cost

The four cached cloud textures use `#142942`, `#78372d`, `#9a4032` and `#091a30`
over a `#101720` base. Their centers travel farther, size and opacity breathe,
and individual rates differ. The main motion period is 10 seconds, down from
14, with a 33 ms timer instead of 40 ms. Phase uses continuous elapsed time so
different layer rates do not jump when the main period completes.

The status row uses a 13 px medium Saira font, 24 px outer padding and a subtle
lower-edge shade for contrast. During generation, a six-pixel warm dot pulses
and a soft highlight crosses the glyphs every 3.6 seconds, including a quiet
gap. Text paths are cached and narrow layouts elide text. The full status stays
available to accessibility. Terminal status remains static without the active
dot or shimmer. The generated-image crossfade, original bytes, frame aspect
ratio and request behavior are unchanged.

Textures/grain remain shared between instances. Existing pause behavior for
hidden, scrolled-out and minimized previews and terminal shutdown is retained.
The added reflection is a small gradient over cached glyphs; it does not use
blur effects or regenerate cloud textures each frame.

## Verification

Native focused checks passed 36 tests in 9.95 seconds: placeholder cache/aspect
and pause/terminal lifecycle, generated-image transfer and original-byte save,
request failure/cancellation, follow-up context, acceptance and working status.
Existing tests and acceptance prompts were unchanged; no new cosmetic snapshot
tests were added.

Six synthetic frames from 0 to 9.9 seconds, a narrow frame and terminal status
were visually inspected using the app's bundled Saira font. An initial isolated
render omitted the app font setup and showed fallback glyph boxes; the render
harness was corrected to load the same bundled font as the app. That was a
verification setup issue, not a change to app typography.

An offscreen 280 px preview probe captured 180 frames with a mean render time
of 0.777 ms, p95 0.961 ms and maximum 1.512 ms. These figures include screenshot
capture overhead on this host and establish only isolated widget cost, not
live app/GPU responsiveness. Synthetic frames and timing data are retained in
ignored `state/image-preview-visual/`. No provider/model request was made.

Final full native regression passed 2,339 tests and 15 subtests in 325.30 seconds,
with 58 skips and no failures/errors. Skips comprise 51 opt-in live/model gates
and seven host-dependent symbolic-link checks; they are separate from passing
deterministic checks. Dependency consistency and Git whitespace checks passed.
Tests use repository-local basetemp; JUnit evidence is under ignored
`state/test-artifacts/image-preview/`.

## Recovery and integration

Pre-integration refs/worktree identities and a verified complete-history bundle
containing 94 refs are retained under ignored
`state/backups/image-preview-motion-20261008/`.
Prior main is preserved at `archive/2026-10-08/main-before-image-preview-motion`.
After verification the bounded change is committed, fast-forwarded into local
main and its merged local feature branch removed. Other active worktrees,
remote refs and runtime settings remain untouched. Restart O.R.S.I. to load
the revised preview.

## Active status overlay removed, 9 October 2026

The follow-up on `codex/tool-approval-preferences` removes the pulsing dot and
visible Generating image label from the active preview. Cached cloud/grain
animation, lower-edge shading and accessibility status remain. Stopped, failed
and unavailable messages still render as static text.

Six focused placeholder, result-transfer and failure/cancellation tests passed
in 4.95 seconds. The initial sandbox run passed four tests; two result-transfer
tests hit Windows file-handle access restrictions before exercising the preview.
All six passed when rerun unrestricted. Synthetic active/stopped previews were
visually inspected at 280 px and 160 px; artifacts and the passing test report
are under ignored `state/image-preview-without-label/` and
`state/image-preview-label-native.xml`. Whitespace checks passed. The full suite
was intentionally skipped at the user's request; no live model/API calls were
made. The feature branch is retained.

## Burgundy palette follow-up, 9 October 2026

The two warm cloud textures now use darker burgundy `#541c2b` and `#702438`.
The navy layers, grain and motion are unchanged. Both existing placeholder tests
passed in 0.75 seconds, and six motion phases were visually inspected. Artifacts
are under ignored `state/burgundy-preview/` and `state/burgundy-preview-focused.xml`.
Whitespace checks passed. Only focused tests were run as requested; no live
model/API calls were made. The change remains on `codex/tool-approval-preferences`.
