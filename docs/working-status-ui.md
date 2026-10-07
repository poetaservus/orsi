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

## Control weight, spacing and skill chip refinement

The user's four visual corrections remain on the same UI review branch.
Composer plus/folder SVG strokes decrease from 1.5 to 1.2 while retaining
white tint and their existing positions. The selected skill chip uses a dark
neutral fill, a quiet grey border and grey text instead of the blue treatment.
Hover styling is muted too; selection/removal and message metadata are unchanged.

Top-left controls use new vector speech-bubble and gear outlines with equal
visible bounds and consistent strokes, replacing the uneven cropped raster
assets. Equal 32-by-28 button areas, 6-pixel gaps and a 1-by-14 translucent
separator keep the controls aligned. The decorative separator ignores mouse
input. Existing top bar placement and button actions are retained.

Minimize, maximize/restore and close use a shared 1-pixel rounded stroke and
centered floating-point geometry. Their button areas are 36 by 28 with 8-pixel
gaps. The drag-strip width follows the actual control group width so the wider
group fits cleanly; native frame operations and event routing are unchanged.

Existing focused UI, skill picker, approvals, shutdown and window-frame checks
passed 71 tests and 15 subtests in 13.63 seconds. The real Windows frame gate
passes at normal and 150% scaling, including resize/caption hit testing,
maximize/restore, minimize and shutdown. Synthetic Qt previews select
`prompter` through the existing skill picker and render the composer, corner
controls and a minimum-size window at both scales under ignored
`state/previews/control-polish/`. No new tests are added for this reversible
visual adjustment. Full unrestricted confirmation passed 1,967 tests and
15 subtests, with 49 existing skips and no failures in 242.46 seconds.
Live model/API gates remain unrun; no paid API requests or key changes are
made. This follow-up is committed and retained on the UI review branch.

## Per-message skill captions

The next user request adds `/skill_name` above the left edge of a user bubble,
with the existing timer's Saira 11-pixel font and `#858791` colour. No caption
is displayed when a message has no admitted skill. The existing metadata row
hosts the caption, with room for the hover copy button. Very short bubbles
allow enough width for a readable caption; long names are elided and their
escaped full name is available on hover. Names render as plain text.

Skill usage is captured from the admitted answer request's rendered skill
snapshot, at the same boundary as the existing injection diagnostic. An
optional worker signal updates the current user bubble while inference runs.
This includes explicit message/session selections and automatic choices;
rejected guidance and no-match turns retain no label. Observers are cleared
at turn completion, and display callback failures cannot interrupt inference.

An optional `skill_name` field is stored on the corresponding user message.
The original message text, copied text and model-history projections remain
unchanged. Existing saved messages without this field load with no caption;
no historical tags are guessed from logs. Reopened history restores the skill
caption and correctly identifies user rows with ChatView's `User` sender
value. Conversation metadata is committed through the existing validated,
atomic store; no live user settings or conversation files are migrated during
development. Existing prompts, selection, tools, permissions and budgets are
unchanged.

Initial existing checks passed 186 tests and 5 subtests in 16.37 seconds.
Final focused confirmation passed 232 tests and 5 subtests in 30.09 seconds.
Seven new cases cover explicit chat/agent usage and round-trip reopening,
live worker delivery and next-message isolation, rejected skills, automatic
selection/no-match, legacy history and untrusted long names, original copy
text, and observer failure isolation. Existing native reference conversation,
skill, turn-outcome and UI checks are included. A synthetic Qt preview with
labelled and unlabelled messages is under ignored
`state/previews/message-skill-label/`. Full unrestricted confirmation passed
1,974 tests and 15 subtests, with 49 existing skips and no failures in
220.54 seconds. Live model/API gates remain unrun; no paid API requests or
key changes are made. This follow-up is committed and retained on the UI
review branch.

## Integration approval, 7 October 2026

The user has approved merging all new changes into main and pushing to GitHub.
This supersedes the review-branch retention recorded above. The verified source
tip is `dd596eb`; integration adds documentation only and reuses the final
1,974-test unrestricted confirmation. See the
[integration and recovery record](git-workflow.md).
