# Office Excel execution reliability, 18 October 2026

This bounded repair starts from clean local main `0acc369` on
`codex/office-mcp-reliability`. The reported screenshot is failure evidence;
its dashboard request is not treated as an instruction to alter dataset.xlsx.
All native qualification uses disposable, test-owned workbooks and no provider
requests. Historical incident arguments are unavailable, so the screenshot's
exact failing call is not claimed to have been recovered.

## Reproduced defects

- A valid native 200-cell values/number-format/bold/fill patch reaches the
  production ten-second execution cutoff after writing begins. The connection
  disconnects with an uncertain outcome. Existing native dashboard tests used
  explicit longer deadlines and much smaller cell patches.
- Preparation uses private MCP resource reads. Those were independently limited
  by both the host's short metadata deadline and the SDK's connection-startup
  timeout; increasing only the tool-call timeout does not repair large patches.
- Shared save/revert capability registrations are constructed before document
  selection. Caching their outer timeout preserves forty seconds even after
  selecting Excel. The first 1,000-cell qualification completed the edit, then
  exposed this exact forty-second restoration cutoff in its journal.
- An approved patch that formats a formula and changes its input can be applied
  correctly but fail verification against the old cached numeric result. Both
  cell orders reproduce. Restoring only the old comparison in memory makes both
  new regressions fail; the corrected comparison passes both edit and recovery.
- Excel writes were missing from the shared diagnostic allowlist and bridge
  collection. Native errors lost their stage and HRESULT behind a generic stop.
- A four-chart native test reproduces a plain line chart palette failure. Excel
  returns black for the unused series fill while the visible stroke correctly
  matches the requested color. Requiring that unused fill to match stops an
  otherwise valid dashboard operation. Both direct and real MCP gates reproduce.

## Repair

Excel edit/save/revert calls and their mutation-preparation controls receive a
bounded 240-second native allowance, covering the advertised 1,000-cell limit.
The outer executor accounts for binding, preparation, execution and cleanup
(500 seconds for Excel). Its allowance is computed at dispatch from the current
document selection rather than cached when the registry is built. SDK resource
reads no longer inherit the shorter initialization timeout; each private control
has its own bounded deadline. Ordinary metadata/read controls remain ten seconds,
Word's existing allowances remain intact, and explicit short test/host overrides
remain authoritative. These are maximum wait limits, not delays or retries.

Formula verification checks the expression and formatting while allowing the
calculated result to change after an input edit within the same approved patch.
Complete preflight comparisons still reject changes made before dispatch; literal
values remain exact. Approvals, snapshot coverage, recovery guards, cancellation,
and the prohibition on replaying uncertain writes remain in force.

Excel now supplies content-free stage/category/HRESULT/duration/outcome evidence
through the owning STA, MCP, bridge and existing profile logging sanitizer.
Cell-write and verification failures have specific messages. Native exception
text, document values, paths and credentials are not added to diagnostics.

Plain line-chart palettes now verify the visible stroke. Filled chart types still
require both fill and stroke to match. Regression checks reject a wrong visible
line and a wrong column fill; the native gate creates bar, column, line and
doughnut charts together.

## Qualification

Only focused checks are used. Evidence is retained under ignored
`state/office-mcp-reliability-*`. The initial native 200-cell failure, intermediate
maximum-size restoration failure and failed fixture assumptions remain separate
from passing results. The sandbox stdio attempt was interrupted and replaced by
unrestricted Windows checks; it is not called a passing run.

The corrected 200-cell native gate verifies exact values, formats, fill, recovery,
save and released owned Excel/bridge processes. Its entire gate took 106.31 seconds;
the edit including approval/preparation took 47.969 seconds and recovery took
35.156 seconds. This is correctness qualification, not a low-latency claim.

The final 1,000-cell gate passes at production settings, including exact readback,
restoration, save and released owned Excel/bridge processes. It takes 636.81
seconds in total: 243.125 seconds for the edit and 290.734 seconds for restoration,
including approval preparation and rechecking; save takes 0.625 seconds. The
240-second allowance applies independently to each preparation/native dispatch;
the outer execution budget accounts for both. The separate initial preparation
also precedes execution. Large native patches remain slow; no performance
improvement is claimed.

There are 158 distinct passing deterministic/owned-stdio focused checks: the
142-pass selection, the final 11-case reliability module and the 31-pass
capability/deadline selection overlap, plus four palette regressions. One opt-in native Word pagination gate
is explicitly skipped. The accepted manifest and portable runtime checks pass.

The dashboard gate uses production deadlines and checks four native chart types,
formula recalculation, linked KPI shapes, PivotTables, slicers, recovery, save and
reopen. The final real-MCP gate passes in 69.79 seconds. Its diagnostics confirm
every feature check and both owned Excel and bridge release, with no forced
cleanup. Windows emits `0x80010108` during final proxy release; the gate exits
successfully and the process-release checks are independently confirmed.

The two failing chart reproductions also recorded Windows COM/RPC cleanup
diagnostics and forced cleanup of their test-owned Excel process. Those failed
runs are retained separately and are not counted as passes.

The accepted MCP manifest, schema/token ceilings, model settings, prompts,
routing, sampling and context policy are unchanged. No full suite or live-model
dashboard acceptance is claimed. This repair does not add unsupported authoring
features, including native Excel sparklines or PowerPoint writes.

## Integration

Preserve prior main as `archive/2026-10-18/main-before-office-mcp-reliability`,
commit the bounded repair, fast-forward local main, and remove only the merged
feature branch. Other worktrees, settings, historical/unmerged tips and remote
refs remain untouched. Restart the running ORSI process to load the repair and
reconnect Office; existing uncertain operations are not silently retried.
