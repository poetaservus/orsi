# Managed persistent shell sessions

This bounded change starts from local main `f35d4a5` on
`codex/persistent-shell-sessions`.

Previously, a foreground `npm.cmd run dev` could report ready and then reach the
command deadline. The runner correctly stopped its owned processes, leaving the
user's request to keep a server running unfinished. A supplied parent folder
without `package.json` could also cause an avoidable request for another path.

## Contract

`shell.run` keeps its foreground default and existing 60-second deadline,
300-second maximum, output bounds, exact-call approvals and child cleanup.
Explicit persistent work can instead use `background=true`. It returns a managed
session after a bounded initial observation rather than waiting for server exit.
Running is process liveness, not readiness; the model must check the reported
local URL before claiming that a server is ready.

Session actions share the existing tool and permission gate:

- `status` takes the returned `session_id` and optional `output_offset`.
- `stop` releases the owned process tree and returns its cleanup result.
- `list` recovers current runtime-owned IDs without starting a command.

Status, stop and list omit `command` and `workdir`. They cannot select a PID or
another runtime's process. Start approval binds the exact command, canonical
working directory, interpreter, launch mode, initial wait and lifetime. Control
actions require their own exact approvals under the existing user preference.

Each runtime can own four active sessions and retain 32 bounded session records.
Sessions default to one hour, with an explicit maximum of eight hours. They end
on stop, expiry, natural parent exit, runtime/profile shutdown or app exit.
Windows job ownership releases the session's owned descendants with their owner.
IDs are held in memory and never adopted from stale history after a restart.
Runtime shutdown closes session owners even if executor shutdown fails. Monitor
errors still close owned processes; process-close cleanup also runs when querying
the exit status fails.

Output is continuously drained into a rolling 64-KiB buffer. Status returns up to
8 KiB with absolute byte offsets, the next offset, available-more and lost-prefix
information. A verbose server stays running instead of dying at the foreground
output bound. Cancellation during the initial observation cleans up the new
session. Existing interrupted/unknown-outcome approval and journal guards remain.

Both prompts explain managed server starts, status/stop/list, HTTP readiness,
lifetime reporting and bounded package-root discovery within the provided
project. Temporary `project.inspect` previews retain their existing lifecycle;
inspection of an already running managed server does not take its ownership.
Model routing, sampling, context policy, accepted profiles and user settings
are unchanged.

## Qualification

Necessary native qualification passed **205 distinct focused checks** across
shell sessions, ordinary shell execution, project verification/inspection,
current-task completion, provider tools and coding guidance. Coverage includes
PowerShell and cmd HTTP servers surviving the launch call, subsequent foreground
commands, log paging and overflow, bounded capacity, startup failure/cancellation,
lifetime expiry, exact approvals, runtime isolation, idempotent stops, app
shutdown, monitor/exit-query errors and release of owned descendants while an
unrelated process survives. Actual browser click, text and scrolling checks
passed against a managed server, which remained available after inspection.

The initial native run passed 61 checks and exposed two fixture assumptions:
Windows locks an active process's working folder, and the other fixture checked
bare PIDs immediately after termination. Fixtures now test terminal folder
renames and bounded cleanup checks against captured process identities. The
corrected new-session run passed all 16 checks; subsequent
qualification includes the browser and error-cleanup additions.

A real cloud run used the accepted `gpt-6-luna` profile, actual streaming SDK,
production hybrid/runtime and the user's authorized `orsi_website` project:

```text
Start the npm server for C:\Users\yaboy\Desktop\orsi_website
```

```text
Is it still running? Check it without starting another server.
```

```text
Stop the server you started.
```

The qualified run discovered the nested package root, started Vite, and completed
the three turns in 5, 4 and 3 model requests respectively. Independent HTTP probes
returned 200 after start and after the later status turn. Exactly one managed
session existed throughout; status did not relaunch it. Stop confirmed all owned
processes released. Every turn retained its reviewed answer and had zero protocol
failures. Transport resources closed and raw conversation/journal files were
removed. The final cleanup-error hardening was subsequently rechecked natively.

Two earlier live attempts completed the start in 9 and 11 requests but failed
the harness's URL extraction: Vite inserts ANSI color sequences inside its URL.
The harness now removes those sequences before its independent probe; the three
prompts and production model policy were not changed to pass that gate. Those
attempts remain separate from the successful three-turn qualification. Reports
under ignored `state/persistent-shell-live-20261011/`,
`state/persistent-shell-final-20261011/` and
`state/persistent-shell-qualified-20261011/` retain only hashes, counts and status
metadata. The existing authorized key stayed in memory and was not recorded.

Source-edit and dependency-install calls were excluded from the live harness.
Test servers were stopped. Full-suite, local-model and eight-hour soak qualification
were not run, following the request for necessary tests only.

Preserve content-free refs/worktree/config evidence under
`state/backups/persistent-shell-sessions-20261011/` and prior main at
`archive/2026-10-11/main-before-persistent-shell-sessions`. Commit, fast-forward
local main and remove only the merged feature branch. Preserve other worktrees,
historical tips and remote branches; do not publish.
