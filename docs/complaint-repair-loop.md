# Repair the reported behavior

Integration note, 13 October 2026: after the composer and Responses reasoning
fixes were confirmed working, the user explicitly requested every remaining
change be merged into main and pushed. This branch's implementation is included
by that request. Its earlier qualification failures below remain historical
failures. See [the combined integration record](repository-integration.md).

The preserved website has three isolated variants under ignored
`state/complaint-repair-frozen-v2`: the disabled starting point, the broken backup,
and the known working comparison. SHA-256 manifests freeze their source files.
No user website source/configuration files are changed by qualification. Content-free pre-change refs
and worktree inventory are under `state/backups/complaint-repair-20261012`; prior
main is retained at `archive/2026-10-12/main-before-complaint-repair`. The disabled
variant preserves the matching original component and app source together;
the superseded first copy remains preserved separately. All three variants
build successfully. Dependencies are shared through a junction; the model
cannot edit them. Normal preview/build dependency caches may be generated.

`tools/scroll_acceptance.py` independently checks hero visibility while progress
changes, pinned partial animation, assembled logo before exit, next-section
access, immediate upward wheel movement, return-state equality, PageDown/PageUp,
actual native scrollbar navigation, and native touch synchronization. It reads
geometry and the existing animation properties; it never trusts an agent's
completion review or an inspection's overall passed flag. Reports contain fixed
check names and numeric observations. The working comparison passes all eleven
checks; the broken backup fails eight. Playwright's default hidden-scrollbar
argument is disabled in this oracle so the scrollbar check uses a real track.
Restricted-shell preview startup failures are separate from these native results.
Initial, partial, assembled and return screenshots were also visually reviewed.
The oracle permits network requests only to its isolated preview origin.

The original three replay prompts remain unchanged except the disposable path.
Only preview configuration changes its port. The exact later request about skipped frames and reverse
playback is unavailable according to the user. Its exact replay is skipped,
never reconstructed and presented as the original. Independent reverse and
frame-timing checks still apply.

## Inspection checkpoints

One approved browser session can capture four named checkpoints and its final
viewport. Each checkpoint records actual page/target scrolling, target bounds,
intersection with the viewport, selected computed properties, and verified PNG
pixels. Optional assertions compare visibility, direction or the same scroll,
bounds and styles at a previous checkpoint. Capturing never scrolls the target.
Native key and touch navigation and absolute scroll positioning are bounded
actions. One frame-timing capture samples at most 120 animation-frame callbacks
over at most two seconds; this is scheduling evidence, not proof of compositor
delivery or smoothness. Screenshot pixels still require visual review.

There are at most five images and 8 MiB combined transport bytes, with existing
viewport, step, worker deadline, same-origin HTTP/WebSocket routing and owned
process limits preserved. Parent validation verifies every screenshot's exact
owned path, PNG dimensions, bytes and digest. The continuation rechecks all
images before delivery; a tampered checkpoint invalidates the supplement.
Legacy cloud inspection evidence retains its original bytes and call pairing;
only the new optional step fields receive default sentinels during validation.
Live cloud decoding remains strict.
The real frozen working website also passed initial/partial/complete/return
capture and return-state equality in one owned session (4.5 seconds), recorded
under `state/complaint-working-inspection.json`.

Focused inspection qualification: 64 passed, one host symlink skip. Strict cloud
decoding/replay/argument recovery: 104 passed. Expanded checkpoint integrity and
legacy checks: 17 passed. These overlapping runs are not added together. A new
fixture's initial duplicate keyword and wire/domain-shape errors were corrected;
neither run is reported as a passing qualification.

Full-suite and repeated live repair qualification will be recorded below before
integration. Accepted model profiles, sampling, routing and context policy stay
unchanged. No remote publication is authorized by this change.

## Diagnosis and useful progress

An executed interaction or visual/runtime failure creates a project-scoped
diagnosis requirement. Before editing again, a later complete source read must
be received in an earlier model step. The edit/write tool's optional five-string
`repair_diagnosis` must identify the exact failed call ID, what failed, the
evidence-supported suspected cause, proposed change, and confirming observation.
This supports native tool-only responses and enforces structure/provenance,
not the truth of a model's hypothesis. Existing exact-call approvals,
redundant-edit protections, rollback and failure budgets remain authoritative.
Selector errors direct inspection correction; unavailable previews direct
startup recovery. Loading-only checks cannot clear a failed interaction scope.
Checkpoint targets are resolved once; capture timeouts after attachment and
ambiguous locators require inspection recovery rather than speculative source
changes. Overlong diagnosis references receive a precise correction.

Read reassessment now follows settled project revisions, inspection scenarios
and unresolved check identities. Each revision gets one initial reassessment
and at most one newly exposed failure reassessment. Different screenshot bytes,
measurement values, error text or scenarios alone cannot earn more reads.
Proven edits still renew their necessary rechecks. Focused diagnosis, progress,
rollback, strict cloud and completion qualification passed 158 checks.

## Completion scope and evidence

Review asks for further work only for a named unmet requirement and missing
observation. Explicit skipped-browser instructions are respected and that
behavior remains unverified. Generic loading/visibility cannot replace the
requested interaction. Command results, interaction assertions, visual
observations and frame-timing capture are recorded separately; pixels always
remain pending visual review and callback timings do not certify smoothness.
Versioned new receipt projections preserve exact legacy history reconstruction.
Completion, durable verification, answer retention and scope qualification
passed 112 checks. A too-long diagnosis rejection in its initial test run was
corrected to the existing 500-character error bound; that run was not passing.
Inspection/summary requests report observed defects; review must not demand
an unrequested source repair before allowing that report to complete.

## Qualification

The initial full-suite run exposed context-budget and legacy strict-wire fixture
regressions. Compact diagnosis and completion guidance fixed these without
increasing context windows, changing acceptance prompts, or changing profiles.
The subsequent full suite passed **3,504 tests**, with **61 skips** and **15
subtests**, in 629.88 seconds. Follow-up native recovery qualification passed
96 tests, including checkpoints, diagnosis, summary scope, strict cloud tools,
existing 8K read-after-mutation and default 14B context regressions. Overlapping
runs are not summed. Restricted-shell handle failures remain separate from the
passing native runs.

Live qualification uses `tools/verify_complaint_repair.py` and isolated copies,
with the user's approved credential and explicit approval to send source,
screenshots and replay conversation to `api.openai.com`. Summaries preserve
only status/counts, fixed checks and process/configuration identities. Original
replay histories stay under ignored state. No secrets enter diagnostics.
The initial three live attempts failed the release gate: one stopped during
repair, and two stopped during summary recovery. Those failures are preserved
under `state/complaint-live-qualification` rather than counted as passing tests.
They exposed ambiguous-selector classification and summary review scope errors.
The next qualification is retained under `state/complaint-live-recovery`;
all three attempts stopped because the harness denied a read-only
local-preview readiness probe. The corrected harness permits only reviewed
probe forms for that attempt's precise origin and verifies actual process exit,
distinguishing PID reuse and terminated processes from running owned processes.
An actual owned Windows child confirmed the cleanup distinction.

The final harness run, `state/complaint-live-final`, qualified **0 of 3** unchanged
default-cloud replays. Attempts 1 and 2 reached the repair turn and stopped at
existing repetition/rollback limits; attempt 3 stopped at the bounded semantic
correction limit during the summary turn. All three independent resulting-page
checks failed. All three runtimes and acceptance workers released their owned
processes. There were no denied harness approvals. The frozen source and
accepted settings remained unchanged; the user's website source still matches
the preserved working comparison. `IncompleteResponseError` in these records
reports the app's bounded recovery stop, not an API authentication/transport
failure.

The release criterion remains unmet. The implementation stays committed on
`codex/scroll-behavior-acceptance`; local main remains at its verified baseline
`aae279a`. No fast-forward or feature-branch deletion is performed while the
required repeated live behavioral gate fails. Neither deterministic success,
successful cleanup, a build, nor a model's completion review substitutes for
that gate. The exact later skipped-frames/reverse-prompt replay remains skipped
because the original wording is unavailable.

The final full suite on the follow-up implementation recorded **3,515 passed,
61 skipped, 15 subtests passed, one failed test and its teardown error** in
800.47 seconds (`state/complaint-final-full.xml`). The unchanged
`test_repository_limits_reject_before_copy[bytes]` Git skill installer test
reported `cleanup_failed` while rejecting its bounded temporary download, and
its teardown found the retained temporary folder. The installer, process helper
and test have no diff from main. Its entire **60-test group passed** on the
native isolated rerun (`state/complaint-installer-recheck.xml`). The full run
is still recorded as failing; the isolated rerun does not turn it into a passed
full-suite gate. The previous 3,504-pass full result remains a separate earlier
run. The 61 skips comprise eight host symlink limitations, two platform gates,
and 51 unrelated opt-in model/cloud/UI gates; these are not counted as passes.
`state/complaint-repair-summary.json` records the content-free final gate status.
