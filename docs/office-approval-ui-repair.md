# Office approval UI repair, 15 October 2026

Excel edits were reported as denied by permission policy even though no approval
prompt appeared. The workbook's ordinary Desktop path passed the host write
policy, and read-only diagnosis found a writable, unprotected workbook. The
actual rejection happened in `create_inline_approval`: its fixed presentation
catalog did not recognize any Office mutation and immediately resolved the
request as denied.

This bounded change starts from local main `9d0dfc2` on
`codex/office-approval-ui`. It adds review panels for the three supported Excel
mutations: `office.excel_edit`, `office.revert` and `office.save`. They reuse the
existing localized Apply, Restore and Save titles. Saved-document reviews show
the canonical resource path plus the operation preview. Unsaved-document reviews
show the trusted preview without requiring a nonexistent filesystem path.
The bridge preview now includes the workbook title before its bounded cell/range
or save description. Preview text is displayed literally in read-only controls.

The UI only presents an existing approval; it grants no new permission. The
original approval manager, exact argument/document binding, guarded preflight,
single-use consumption, cancellation and execution journal remain authoritative.
Office reviews require a nonempty preview. Unknown actions, unimplemented
Word/PowerPoint mutations and ordinary file operations missing their required
resource remain rejected. Tool approval OFF keeps its existing exact automatic
authorization path. Prompt wording, schemas, manifests, model settings, routing,
context policy, filesystem protections and user preferences are unchanged.

## Verification

Before the repair, all **six** saved/unsaved edit/restore/save presentation cases
failed by silently denying the approval. The final focused Windows selection
passed **96 checks in 51.31 seconds**, without failures, errors or skips.

The new tests cover the actual window, conversation service, permission rules,
MCP SDK/stdio bridge, production Excel control adapter and journal with a
synthetic Excel backend. Saved workbook fixtures live outside their synthetic
application root and use the normal production write policy without overriding
it. For saved and unsaved workbooks, the tests verify:

- Approval ON displays the workbook and range before dispatch; Enter authorizes
  one edit and consumes exactly one approval.
- Esc rejects the edit without dispatching it or changing cells.
- Approval OFF performs the same authorized edit without displaying a panel.
- Readback confirms the synthetic values, and editing does not implicitly save
  the synthetic workbook file. Closing the test window releases the owned bridge.

Edit, restore and save presentation, malformed/unknown actions, existing inline
reviews, approval preferences, Office guards/recovery and conversation catalogs
are also checked. The synthetic review screenshot
`state/office-approval-panel.png` was visually inspected. All 45 existing UI
catalogs still validate; no translation sources or compiled catalogs changed.
Compilation and whitespace verification are recorded with final integration.

The full suite used Qt's Windows platform, normal Windows permissions and
repository-local `state/pytest-office-approval-full`. It completed **4,153 tests
and 15 subtests successfully**, with **63 skips and three failures**, in
**1,595.18 seconds**. It is not recorded as a clean full-suite pass. Two unchanged
test-only Qt activation deprecation warnings remain. The three failures were:

- Git output-limit cleanup still observed its owned output filename immediately
  after deletion.
- The isolated skill CLI reported a generic storage I/O failure after successful
  repository inspection.
- The missing-encrypted-profile native startup probe exited before writing its
  report.

Both complete affected modules were rerun unchanged with normal Windows
permissions and a separate repository-local temporary directory. All **68 checks
passed in 68.92 seconds**, including the three failures. Their implementation and
test files have no changes in this repair. The failures were not reproduced and
their underlying cause remains unresolved; they are retained as intermittent
full-run failures, not silently converted to passed checks. All Office approval
and conversation checks passed in the full run. The 63 skips include opt-in
live provider/model/Office gates and unavailable symbolic-link checks.

Evidence is retained under ignored state:

- `state/office-approval-before.xml` and `.log`
- `state/office-approval-focused.xml` and `.log`
- `state/office-approval-full.xml` and `.log`
- `state/office-approval-followup.xml` and `.log`

No real workbook cells were read or changed during diagnosis, and no live
provider request was made. The opt-in live model/Office and second-host gates
remain separate from the automated regression suite. Cell background/fill colors
remain outside the current Excel contract, which supports values, local formulas,
number formats, bold and italic.

Restart ORSI after integration, reconnect Office, select the workbook and click
Use document before retrying. With Tool approval ON, the supported edit now
reaches the composer review instead of being silently rejected.

Content-free ref/worktree inventories are retained under
`state/backups/office-approval-ui-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-approval-ui`, commit the verified change,
fast-forward local main and remove only its merged feature branch. Other
worktrees, historical/unmerged tips, private settings and remote refs remain intact.
