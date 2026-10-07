# 90 — Complete Python applications: CLI, service and desktop

Read for runnable applications and their real interaction paths. Choose the
section matching the requested surface; do not add every framework.

## Command-line tools

Use the project's parser or standard-library `argparse` when adequate. Define
defaults, validation, help text and exit behavior. Success output belongs on
stdout and diagnostics on stderr when machine-readable piping depends on that
contract. Keep formatting separate from the operation so JSON output stays valid.

Avoid prompts during noninteractive use unless explicitly requested. Define
overwrite/collision policy and meaningful exit codes. Do not perform destructive
work merely to implement `--help` or validate arguments. Test invocation from
another working directory and paths with spaces/Unicode where relevant.

## Services and APIs

Reuse the existing framework, version and sync/async conventions. Validate input
schemas and authorization at the boundary. Map domain failures to the documented
API contract; avoid exposing internal models, traces or credentials. Use a
bounded request lifecycle and an appropriate transaction around writes.

Create clients/pools at an owned lifecycle boundary and close them at shutdown.
Do not instantiate a new client per request solely from a copied example.
Define health/readiness semantics, configuration precedence and basic diagnostics
only to the depth the service needs. Test the real request/response boundary and
required database behavior, with external dependencies isolated where appropriate.

Do not convert a route to `async def` while keeping blocking work in its call path.
Consult the installed framework's supported offload/lifecycle mechanisms. Creating
a background task is not durable job delivery; long-running jobs may need an
existing queue and a retry/idempotency contract.

## PyQt and PySide desktop applications

Preserve the selected binding and supported version. PyQt and PySide are different
dependencies; do not mix their imports/signals or silently switch one to the
other. Check licensing suitability and actual multimedia/plugin support.

Keep widget access on the GUI thread. Signal/slot handoffs carry results from
workers; model and controller boundaries should support that ownership. Avoid
blocking file scans, downloads or computation on the UI thread. Use workers only
where necessary: a multimedia backend does not automatically require another
thread merely to play audio.

Build a complete state flow: startup, empty state, current selection, working,
success/error, cancellation and shutdown. Disable only conflicting operations
and preserve input/state on failure. Disconnect or release timers, callbacks,
workers and owned clients so a closed window does not leave background work.

For a player, derive behavior from the actual request: accepted files, playlist
selection/order, play/pause, next/previous, volume, progress and requested repeat/
shuffle semantics. Distinguish displayed progress from seek interaction when
only one was asked for. Verify codec availability through the installed backend
on each claimed platform; listing extensions does not establish playback support.
Do not promise identical multimedia behavior across OSes from one local test.

Layout should handle resizing, keyboard focus and long content. A requested
minimal interface is a product constraint, not permission to omit errors or
important controls. Use existing icons/styles and clear state feedback; do not
force dark mode or decoration unrelated to the brief.

## Delivery checks

Provide actual runnable code, declared dependencies, startup instructions and
required configuration. Avoid a script that depends on imaginary sibling files,
undocumented assets or a developer-only absolute path. If the user requests one
file, honor it when feasible; otherwise choose structure based on the work.

Run a startup/smoke check in the target environment, then the critical operation
and relevant failure/shutdown path. Distinguish synthetic/offscreen UI checks
from native interaction, media decoding and packaged application verification.

Official reference: [Qt worker-object/thread behavior](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html).
For worker ownership read [50](50-concurrency.md); for distribution read
[60](60-packaging-and-tooling.md); finish with [95](95-review.md).
