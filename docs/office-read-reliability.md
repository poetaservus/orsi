# Office read reliability, 18 October 2026

Started from clean local main `2a0c399` on `codex/office-read-reliability`.
This bounded change repairs the three native/shared failures reproduced under
ignored `state/office-mcp-investigation/` and retains safe read-failure diagnostics.

## Changes

The shared reader now yields a cursor page after approximately two seconds of
work. It always returns progress before yielding, retains the same Excel snapshot
and exact continuation state, and still respects requested item/character bounds.
This leaves headroom inside the unchanged production 10-second transport deadline.
It does not retry a call or discard snapshot coverage. A single hung native call
still follows the existing bounded shutdown path.

The shared page builder measures normalized `ReadResult`/`ReadItem` output,
including serialized defaults such as `word_workflow: null`. The 16,384-byte
ceiling is unchanged. Provisional construction is only for size measurement;
completed results still pass the existing strict server/client validation.
The accepted Office manifest and schema budgets are unchanged.

Word runs its existing native package preflight before taking a revision guard,
and workflow revisions use that same guard. Empty native package parts therefore
materialize before the baseline, rather than invalidating a read halfway through.
Complete-package, text, formatting and retained-anchor comparisons remain active.
Unsupported edit anchors retain their read-only fallback and gain no write
authority. Revision review/save completion safeguards remain active.

Read timeout/worker-stop and unexpected read transport/validation failures now
emit the existing profile-persisted diagnostic event with fixed categories and a
bounded timeout number. No cell values, target names, IDs, paths, raw exceptions
or conversation contents are added to diagnostics.

## Focused proof and checks

Seven new deterministic/stdio cases fail before the fix: two packed byte-boundary
cases, a simulated slow read, two preflight/real-change cases, workflow revision
alignment and durable timeout reporting. The first red run also encountered one
missing basetemp-parent setup error; a separate pre-fix timeout rerun confirms
the diagnostic failure. Both original reports remain under ignored
`state/office-read-reliability/`.

Only focused checks run, as requested:

| Selection | Passed | Failures / skips |
| --- | --- | --- |
| New regressions, cursor/foreign-change guards, manifest/budget | 16 | 0 / 0 |
| Existing save/review, restoration, Unicode, diagnostics and worker cleanup | 12 | 0 / 0 |
| Native 1,000-cell Excel read and Excel/Word/PowerPoint read/session baselines | 4 | 0 / 0 |

These are **32 distinct passing cases**. The native Excel case uses the default
10-second deadline, requests up to 1,000 cells per call, and reads all 1,000
synthetic values exactly once across 13 pages with one snapshot. Pages take
437–2,156 ms including host preparation/execution. The previously failing first
native Word read now passes. Native fixture and bridge release are verified;
the final unrestricted process inventory contains no Office/MCP helper process.

Evidence: `focused.xml`, `guards.xml`, `native.xml`, `native.log`,
`verification.json`, and the native case's `native-read-diagnostics.json` under
the repository-local native basetemp. No full suite or paid/live-model request
is made. User documents and settings remain untouched.

COM/RPC cleanup diagnostics (`0x800706be`, `0x800706ba`, `0x80010108`) still appear
from the existing native test's application shutdown. They are retained in the
log; this result is not described as diagnostic-free. The broader audit's unrelated
localization/routing/native blockers remain outside this fix. Attribution of the
original screenshot's exact call still requires its turn diagnostics.

Prior main is preserved at
`archive/2026-10-18/main-before-office-read-reliability`. Commit the bounded
change, fast-forward local main and remove only its merged feature branch.
Other worktrees, historical tips and remote refs remain untouched.
