# Working status UI, 6 October 2026

The user requested aligned working status, a timer with minutes and hours,
current activity beneath the timer, and smoother indicators on a new branch.
`codex/working-status-ui` starts from verified local main `ca90b4c`.

## Result

The timer, activity text and animation share a left edge and have consistent
vertical spacing. Activity text uses the available row width and wraps instead
of clipping longer stages. Elapsed labels use whole seconds, minutes and hours:
`130` seconds becomes `Working for 2 m 10s`; `3730` becomes
`Working for 1 h 2 m 10s`. Finished and stopped labels use the same format,
while recorded elapsed durations retain their original precision.

The indicator is three rounded bars with staggered, continuous height and
opacity pulses. A precise 16 ms repaint timer uses monotonic elapsed time for
the animation phase, so delayed repaints do not advance it in fixed jumps.
The timer and animation stop when the task finishes, stops, or the view closes.

Presentation callbacks report actual stages: preparing a request, choosing and
reading skill guidance, loading a local model, thinking, cloud capacity waits,
response generation, reading skill references, file operations, permission and
approval checks, writing a reply, and saving the conversation. Labels contain
fixed descriptions, with no tool arguments, paths or private content. Optional
callbacks are detached after a turn; callback failures cannot interrupt tool
execution or reveal their exception contents in logs.

This adds presentation notifications at existing stage boundaries. Prompts,
tool execution, routing, sampling, context, request counts, retries, deadlines,
model profiles and cloud rate admission remain unchanged. Cloud steps remain
32 and local steps remain 24. User settings, keys and conversation state are
not migrated or replaced.

## Verification

Final focused unrestricted Windows checks passed 246 tests and 5 subtests in
50.80 seconds. They cover timer boundaries, status alignment and long labels,
worker delivery and cleanup, real capability execution ordering, native skill
reference reads, approval/denial stages, observer failure isolation, cloud
capacity waits and lazy local loading. Existing UI, approval, shutdown,
conversation, skill activation, agent, cloud streaming and mode selection
checks are included.

The first full unrestricted run recorded 1,966 passes and 15 subtests, 49
existing skips, and one Windows folder-rename access-denied failure in
284.14 seconds. The unchanged native skill validation test's contract and
disabled-read assertions pass before its final folder rename fails. A broader
reader/UI recheck recorded 85 passes and one rename failure in a different
parameter case. An isolated unrestricted recheck of all five native validation
cases passed in 0.41 seconds. Neither skill storage nor the existing test is
changed; all results are retained in the audit. Fresh full unrestricted
confirmation passed 1,967 tests and 15 subtests, with 49 existing skips and
no failures in 297.59 seconds, including the previously failing native cases.

An initial sandboxed run recorded 86 passes and 5 subtests, with 39 failures
from restricted native Windows installer/file handles. These are separate from
product results; the corresponding unrestricted checks pass. The first new
test run recorded two test-harness errors and eight passes; the tests were
corrected to call the existing `submit` and `execute` methods. Acceptance
prompts and existing tests were not modified.

All test runs use repository-local basetemp and cache directories. JUnit
evidence is under ignored `state/test-artifacts/`. A synthetic full-window Qt
render and a cropped status preview are under ignored
`state/previews/working-status-ui/`; visual inspection caught and fixed the
long-label clipping before final focused confirmation. No paid API requests,
key changes or live model qualification gates are performed for this UI change.

## Branch and recovery

Pre-change refs, worktree map and the verified complete-history Git bundle
are under ignored `state/backups/working-status-ui-20261006/`. The bounded
change is committed and retained on `codex/working-status-ui` for review,
following the user's explicit request for a new branch. Local main remains
`ca90b4c`; the usual immediate integration and branch deletion are deferred.
Other worktrees and remote refs are unchanged. Restart `orsi.cmd` from this
checkout to load the updated UI.

## Inline highlight follow-up

Following the user's visual review, the same UI branch improves inline code
and path highlights. Horizontal padding increases from 3 to 5 pixels, vertical
padding from 2 to 4, and corner radius from 4 to 6. The grey changes from
`#303030` to `#3b3c40`. The document margin and message width calculation
account for the added padding so highlights at row edges remain visible.
Text, selection, clipboard contents and fenced code blocks retain their
existing behavior. No new tests are added for this small styling adjustment.

The existing focused UI, native inline reference and working-status checks
passed 51 tests and 5 subtests in 9.87 seconds. A synthetic Qt render is saved
under ignored `state/previews/inline-highlight/` and visually checked for both
standalone paths and references within a sentence. Full unrestricted
confirmation passed 1,967 tests and 15 subtests, with 49 existing skips and
no failures in 292.10 seconds. Live model/API gates remain unrun; no paid API
requests or key changes are made. This follow-up is committed on the existing
review branch.

## Composer icon placeholders

The user's next UI follow-up adds a plus followed by their supplied folder
icon before the composer text field. The folder's original SVG path is copied
into the app's assets and tinted white, with a 1.5-pixel stroke to match the
plus. Both have 32-pixel hit areas and a subtle rounded hover background.
They are placeholders: no attachment, file dialog, request or command is
connected. Tooltips and accessible names identify them as placeholders;
clicking them does not steal typing focus.

The controls fit in the existing 54-pixel composer without adding a row or
changing its geometry. A nested editor layout keeps the existing skill chip
beside the text field while the plus and folder remain together on the left.
Existing send/stop behavior and inline approval transitions are preserved.
The bundled assets remove any runtime dependency on the original Downloads
file. No new tests are added for the reversible icon styling.

Existing UI, skill picker, inline approval and shutdown checks passed 67 tests
and 5 subtests in 10.11 seconds. A synthetic native Qt click check confirms
both icons load, their order is correct, and clicking preserves the draft and
editor focus without creating a worker. The folder path data is compared with
the user-supplied asset. Full-size and narrow-window renders are visually
checked under ignored `state/previews/composer-icons/`. Full unrestricted
confirmation passed 1,967 tests and 15 subtests, with 49 existing skips and no
failures in 235.96 seconds. Live model/API gates remain unrun; no paid API
requests or key changes are made. This follow-up is committed and retained
on the UI review branch.
