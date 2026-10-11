# Project verification, conversation context and source pages

This local change starts from main `527b5e9` on
`codex/verification-context-paging`. It implements the three newly requested
features. Earlier task completion checks remain separate from these checks.

## Bounded project verification

`project.verify` runs one project build or selected test command. Supply the
project directory, `kind` (`build` or `test`), exact absolute executable and an
argument array. Scripts use their interpreter, such as `node.exe` with the npm
CLI file or a Python executable with the project's documented test arguments.
Batch wrappers and command shells are rejected. Each invocation requires the
existing trusted approval flow for its exact arguments, directory and executable
identity. The preview explains that this runs project code with account access;
it is a lifecycle bound, not a security sandbox.

Each command has a 1–120 second deadline, 48 KiB of captured stdout/stderr,
closed stdin and a limited environment without inherited provider keys.
An atomic Windows job owns the worker and descendants, with a 16-process and
1 GiB job ceiling. Cancellation, timeout, excess output and normal exit release
the owned process tree. A failed command remains a settled receipt with
`passed=false`, exit code, stop reason and truncated-output indicator. Runtime
approval, cancellation and unknown-outcome boundaries still apply.

`project.inspect` follows build/test verification for UI changes. Browser mode
opens an isolated headless Chromium context at one approved loopback HTTP
origin. It can start a temporary preview server in the approved project; that
server ends with the inspection. External resources and redirects are blocked,
downloads disabled and service workers blocked. Up to twelve bounded steps
support click, fill, visible/text assertions and actual mouse-wheel scrolling.
Receipts include console/page errors, failed or HTTP-error resources, missing
fragment targets, broken images, horizontal overflow, scroll movement and a
viewport screenshot. It inspects loaded resources, not every unvisited route.

Desktop mode attaches to an existing PID whose working directory is the approved
project. Approval also binds process creation time and executable identity.
It inspects one visible window, up to 100 controls over five levels, and the
same bounded interaction types through Windows UI Automation. Targets use a
unique automation ID or exact accessible name. Read assertions wait briefly for
asynchronous changes; actions are never silently retried. `PrintWindow` captures
the approved window instead of sampling unrelated overlapping desktop pixels.
The inspector releases its worker, and leaves the existing target app running.

Screenshots are retained under ignored `state/verification/`. Temporary input
specifications are removed. Screenshots require visual review: automated layout
and interaction checks do not establish every aspect of visual correctness.
Install the `verification` extra and Playwright Chromium for inspection. This
checkout has the dependencies installed in its ignored runtime and Chromium
under `state/playwright/`; a missing dependency produces an explicit failed,
incomplete inspection. There are no live model/provider calls in these checks.

Goals retain scoped build/test/browser/desktop receipts, including failures.
Later project file mutations make earlier checks stale. Durable history validates
these records against the original settled calls on reload. Completion guidance
requires accounting for failed, stale, denied and unrun checks. The existing
`behaviour_verified=false` remains truthful: a particular check cannot prove the
entire user request or all possible behaviour.

## Long conversation context

Production enables deterministic context recovery and completed-turn summaries.
Programmatic feature defaults remain off. All original user messages and
attachments stay literal in model context, preserving standing constraints
without guessing which sentences are permanent. Unfinished turns retain their
tool pairs and an explicit, protected unresolved-work record. They cannot be
mistaken for the current request or summarized as completed.

When admission fails or less than a quarter of the context remains, completed
turns can become historical summaries of assistant claims, receipt identities,
paths, revisions and outcomes. A summary is adopted only if it saves space.
Original tool arguments, source bodies and opaque provider replay leave that
request together, while the original conversation remains unchanged on disk and
in the UI. Superseded source revisions also become explicit retired receipts;
pages of the same revision stay available. Historical claims are not current
instructions or authorization to replay an action.

`conversation.read_turn` is bound to the active conversation. It recovers bounded,
revision-bound UTF-8 pages of the original request, answer and neutral settled
evidence. It excludes opaque provider reasoning and expired skill reference
bodies. Summaries name the original turn and this recovery tool. If exact user
constraints and unfinished work still cannot fit, admission stops explicitly
instead of silently deleting them. No semantic summarization calls, acceptance
prompt changes, routing changes or model-profile changes are needed.

## Large source files

`filesystem.read_text` keeps its existing byte/line ceilings and adds byte
`offset` and `expected_revision`. Every result supplies `offset`, `text_offset`,
`end_offset`, concrete page encoding, revision, `has_more`, `next_offset` and
an exact `next_read` argument object. Follow `next_read` until the required source
is reached. Revision mismatches require restarting at zero.

Pages end on encoded character boundaries, preserve line endings and consume
the BOM only on the first page. A byte limit smaller than the next character
returns a continuation with enough room to progress. The revision token binds
file identity/size/timestamps; it is not a whole-file digest. `sha256` is supplied
only when the actual complete file bytes were read at zero. A final page is not
misrepresented as the complete file.

Serialized text is also capped at 40 KiB so escaped text and UTF-16 source cannot
overflow the executor's 64-KiB result budget and lose structured continuation.
Such a page sets `truncated_by_output` and continues from the last returned byte.

If context recovery shortens a source page, it retains a contiguous prefix and
recomputes continuation from the last byte actually shown. It never joins distant
source fragments into apparently contiguous code or skips the hidden portion.
Original receipts remain durable and unchanged.

## Qualification and local integration

Only focused checks for the changed paths and their direct integrations run,
using repository-local temporary directories and native Windows access.
They include real build/unit-test commands, healthy and broken Chromium previews,
wheel-scroll regression detection, a real Qt desktop interaction/capture, owned
descendant cleanup, a twenty-turn context session, history recall and large
Unicode source reconstruction. Live provider/local-model gates and the full
repository suite are separate and unrun at the user's request.

Final qualification passed 376 focused native tests with one host symlink skip
in 65.16 seconds. The final page-output bound and its affected source/context
paths then passed 120 tests with the same skip in 42.41 seconds, including two
additional encoded-page regressions. A final verification-boundary check passed
19 tests in 6.98 seconds, including two additional correctable executable-path
failures. Together these cover 380 distinct passing checks and one host skip.
Reports are retained under ignored `state/verification-context-qualified.xml`,
`state/paging-output-final.xml` and `state/verification-boundaries-final.xml`.
The synthetic desktop screenshot was also inspected visually after capture.
Historical scripted fixtures now supply completion-review responses; acceptance
user requests remain unchanged. No full-suite or live gate is counted as passed.

Local integration follows `AGENTS.md`: preserve prior main and metadata, commit
the bounded change, fast-forward local main and remove only its merged feature
branch. Other worktrees, historical tips and remotes are preserved.
