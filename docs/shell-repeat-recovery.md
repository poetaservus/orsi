# Shell output and preview recovery

The unchanged shell acceptance prompt against Desktop/orsi_website exposed four
problems in the production cloud path:

- PowerShell reported exit code zero for `Get-Location` and a file-object pipeline,
  but returned only a newline. Its deferred object formatter had not drained before
  the wrapper's explicit exit. The model retried the listing with other commands.
- Browser inspection attempted an unavailable preview. Recovery then launched a
  server in `shell.run` and inspected it after that call had stopped its descendants,
  causing repeated startup and navigation attempts.
- The completed test report was replaced by the last source read. The direct-read
  heuristic matched “show … a pipeline that”; execution had no report-preservation
  guard, unlike file mutations.
- Failed browser checks could trigger further completion retries even though the
  request called for a read-only report of passing, failing and unverified checks.

PowerShell now drains its object stream through `Out-Default` before returning the
native exit status. Shell receipts explicitly state that no background processes
are retained. Browser navigation failure without an owned server returns bounded
structured recovery: reuse an existing live preview or supply `server_executable`
and `server_arguments` in the same `project.inspect` call. The description also
explains this lifetime. The corrected call still needs its own exact approval.
Browser receipts distinguish `unavailable`, `failed` and `passed` and explain that
read-only reports should retain observed failures. They do not turn failing checks
into passing checks or authorize source edits.

Supporting reads now preserve shell/build/test/inspection reports, including
failures and denials. Explicit file displays append the source to the report;
ordinary direct-read requests retain their existing behavior.

The repeated-call limit, approvals, process ownership, model profiles, sampling,
agent prompts, routing, context policy and user settings are unchanged. This does
not add persistent shell sessions or fix source code in the test website.

## Verification

Only necessary tests ran: 105 distinct focused checks across shell execution,
project verification/inspection and report grounding passed. The object-output
regression and nine report-preservation cases failed before their fixes. Native
checks include Unicode, exit statuses, bounded execution, descendant cleanup,
browser references and interactions, unavailable-preview recovery and fresh
approval for the corrected server call. A new cleanup assertion was adjusted to
wait for Windows process termination, consistent with the existing native tests.

Live qualification uses the unchanged acceptance prompt, production default cloud
model and real native tools, with a 240-second harness deadline. The authorized
credential stays in memory. Content-free reports retain counts, hashes, statuses
and check outcomes; temporary conversation/journal bodies are removed. Early
incomplete runs include harness approval errors/denials and are not passing gates.
Two intermediate runs completed in 16 and 19 model requests, exposing the later
report replacement; those do not qualify final answer delivery.

After report preservation, a fresh live chat completed in 18 requests with the
reviewed answer intact. An additional run ended incomplete on a harness READ
permission denial; the exact blocked path was not retained, so it is neither a
qualified success nor a proven product defect. Another run exhausted semantic
correction during repeated browser-check attempts. Those results prompted the
explicit failed/unavailable distinction. The final fresh live run completed in
18 requests, preserved its reviewed report, and released all owned resources.
No passing run is evidence that every future model turn will avoid retry churn.

The website has no documented test script. Its build succeeds. Browser inspection
runs at desktop and mobile sizes and records failed scroll movement, passive-event
listener console errors and selector/interaction failures where present. These
are failed website checks, not passing visual qualification. Screenshots alone
do not establish complete visual correctness. The screenshot's exact terminal
repeated-call stop was not reproduced; live runs established the missing-output
and repeated-preview prerequisites above. The full suite and other model profiles
remain unrun, per the request for only necessary checks.

The branch starts from local main `1198acb`. Content-free preservation evidence is
under ignored `state/backups/shell-repeat-recovery-20261011/`. Retain prior main at
`archive/2026-10-11/main-before-shell-repeat-recovery`; commit and fast-forward
local main, then remove only the merged feature branch. Preserve other worktrees,
historical refs and configuration; no remote publication.
