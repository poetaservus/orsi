# Browser verification and answer retention

This bounded change starts from local main `84ee315` on
`codex/browser-verification-preview`.

## Browser inspection

Inspection of the user's `Desktop/orsi_website/anim` Vite project initially
returned `invalid_output`. A delayed preview-server regression reproduced the
failure: a refused connection escaped a Playwright route callback and its
traceback contaminated the worker's structured output. The handler now records
the failed reference and aborts its route. The existing startup retry can then
complete without corrupting the receipt. Genuine failed resources still fail
inspection.

Local resource fetching and navigation allow ten seconds instead of two, so
development modules can finish transforming. The caller's overall inspection
deadline, output cap, approval scope and owned-process cleanup remain in force.
Visibility assertions use Playwright's bounded wait for asynchronously mounted
elements rather than an immediate visibility sample. Interaction actions are
not replayed automatically.

The real development preview also revealed Chromium local-network checks
blocking Vite's same-origin development WebSocket after routed HTTP responses.
The disposable browser context grants `local-network-access` only to the
approved preview origin. Exact host/port HTTP and WebSocket routing still
blocks other origins and redirects; this does not permit remote browsing.
See the [Playwright permission contract](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-grant-permissions).

Closing a rejected socket inside the initial script's routing callback could
stall navigation. Rejected sockets never connect to a server. Their bounded
mock routes close after navigation; later routes remain disconnected and end
with the disposable context. Rejected references are explicitly reported.
Regression fixtures verify that another loopback server receives no HTTP,
redirect or WebSocket connections.

## Answer retention

Empty provider events start a new stream within the same turn. They no longer
erase an existing proposed answer while the completion checker requests more
work. Substantive new text replaces the preview, and turn start/end still clear
it. Completion assessment JSON remains hidden by the existing review boundary.

The final response handler also keeps the preview visible while refreshing the
context meter and inference controls. It clears the preview immediately before
adding the final bubble, within the same UI slot. Success and failure use this
handoff; incomplete notices and next-turn cleanup remain intact.

## Verification

All **68 focused checks passed** with the native Windows runtime and a
repository-local `--basetemp`. Coverage includes real Chromium with console and
windowless worker executables, slow preview startup and modules, asynchronous
mounting, development sockets, failed references, HTTP/redirect/socket origin
boundaries, deadlines and owned-process release, desktop inspection, durable
verification receipts, completion streaming, errors, cancellation, scrolling,
and shared image-response presentation. The report is ignored
`state/browser-preview-final.xml`.

Both the actual Vite development server and the existing built preview passed
inspection on `Desktop/orsi_website/anim`. Each returned a complete structured
receipt, passed the scoped visibility/text checks, reported no browser problems
and released its owned processes. The development viewport screenshot was
inspected. These checks establish the recorded surface, not every possible
website interaction. The existing website build was reused and source was not
edited. No provider API calls or full suite were needed for this repair.

Synthetic screenshots of the actual application during checking and after
completion confirm the answer remains readable with no clipping. They are
ignored `state/browser-preview-checking.png` and
`state/browser-preview-completed.png`.

Content-free integration evidence is under ignored
`state/backups/browser-verification-preview-20261011/`. Preserve prior main at
`archive/2026-10-11/main-before-browser-verification-preview`, commit,
fast-forward local main and remove only the merged feature branch. Preserve
configuration, historical tips and other worktrees; do not publish remotely.
Restart the desktop application to load the updated source.
