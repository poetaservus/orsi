This bounded change starts from local main `3e6a9d0` on
`codex/office-mcp-phase4`. It adds Excel editing, guarded restoration and separate
saving to the existing live Office connection. The accepted v1 contracts and
manifests, model profiles, prompts, sampling, routing and context policy are
unchanged. Default startup remains disconnected; Word and PowerPoint remain
read-only.

A later conversation-level check exposed a missing Office-name entry in the
compact prompt validator. The [conversation repair and full-suite record](office-mcp-conversation-repair.md)
documents that integration fix and the broader regression qualification.

## User workflow and supported edits

In Settings > Models, choose Cloud mode, Connect, select an open Excel workbook
and click Use document. Read the intended cells before asking for an edit. The
six reviewed tools are `office.documents`, `office.attach`, `office.read`,
`office.excel_edit`, `office.revert` and `office.save`. Availability follows the
cached installed applications, rather than changing with individual requests.

Excel patches support literal values, local formulas, number formats, bold and
italic. The existing contract limits each patch to 16 changes and 1,000 total
cells. Targets are explicit worksheet/range pairs; overlapping changes in one
patch are rejected. Literal strings beginning with `=` stay literal text, empty
strings clear cells, and integers beyond Excel's 15-digit precision require text.
Boolean and numeric values remain distinct when checking conflicts.

The initial formula subset allows local cell/range references, arithmetic,
comparisons, quoted literals and these built-in functions:

`SUM AVERAGE MIN MAX COUNT COUNTA ROUND ROUNDUP ROUNDDOWN ABS IF IFERROR AND OR
NOT TRUE FALSE CONCAT CONCATENATE LEN LEFT RIGHT MID TRIM UPPER LOWER SUMIF
COUNTIF SUMIFS COUNTIFS DATE YEAR MONTH DAY`.

Absolute references are supported. Each reference must fit Excel's worksheet
bounds; rectangular references retain the 1,000-cell limit. Defined names,
cross-sheet/external references, DDE, UDFs and network functions are rejected.
The pre-edit formula must also fit this subset so supported restoration can
recreate it. Formula verification normalizes identifier case and spacing while
preserving quoted string case.

The adapter uses English automation locale 1033 for Formula2 and number formats,
including on the qualified Dutch Excel host. Writing a formula preserves the
approved number format even when Excel would inherit a referenced cell's format.
It calculates the affected formula cell, verifies the formula and supported
state, and captures its actual resulting value for subsequent conflict checks.
It does not promise to restore an old calculated value after dependencies change.

Writes require a writable, macro-free workbook with AutoSave off. Protected
sheets, merged cells, array/spill formulas, table cells, hyperlinks and mixed
rich-text bold/italic are outside the supported write subset. Cell strings and
formulas beyond the bounded 4,096-character recovery representation are not
editable. No application-wide event, calculation or alert setting is changed.
Production code does not create or quit Office applications or close documents.

## Exact authority and concurrency

The bridge retains complete cell state privately: value, formula, number format,
bold and italic. Excel read pages accumulate coverage under one snapshot, even
when a long cell requires multiple fragments. A cell is eligible for editing
only once its full read and private state agree. Snapshots bind to the exact
session/resource and retained worksheet COM identity. A similarly named or
focused workbook cannot substitute for it.

The host first applies the existing write policy to the selected source and,
for Save As, the destination. A private local resource then prepares an opaque
guard and digest over the exact arguments, document identity, expected cell
states or destination metadata. These controls and recovery contents stay out
of model tool definitions and content-free diagnostics. Approval ON/OFF follows
the existing preference; OFF still requires permission, validation and exact
single-use call authority.

After approval, the host revalidates the binding. The bridge consumes the guard,
preflights every cell before touching any cell, and checks each cell again
immediately before writing it. Changed content or supported formatting causes a
conflict. Successful edits consume their snapshot and invalidate its continuation
cursors. A conflict requires a fresh read and approval rather than silently
rebasing the requested patch.

Office COM provides no atomic transaction across cells. A user can still change
the workbook during a multi-cell operation. Once mutation starts, any failure,
partial result or verification mismatch is an uncertain outcome. The bridge
blocks further mutations, and the existing execution journal prevents automatic
replay. A proven pre-write conflict is a known failure and leaves the connection
usable. Cancellation before dispatch performs no write; cancellation, timeout or
disconnect after dispatch does not imply rollback.

## Guarded restoration

Verified mutations return an opaque recovery ID. Recovery retains only the
affected cells' before and verified after states in bridge memory; it does not
rely on Excel's ordinary Undo. Restoration requires a fresh complete snapshot
and exact equality with the recorded after state. Later user changes to any
affected cell reject the restoration before writing. Successful restoration is
itself verified and returns recovery for its own changed cells.

Disconnect/Refresh releases this memory and makes its recovery IDs unavailable.
No recovery content is written to baseline snapshots or diagnostics. Limits are
128 prepared guards and 64 retained recovery records, with 8 MiB bounds on
snapshot state, guards and recovery accounting. New edits stop at the recovery
limit; explicit reconnect starts a new session. Unknown outcomes never trigger
blind rollback.

## Separate saving

Editing does not save. `office.save` is a separate approved operation whose
preview states that it saves all current workbook changes, including other
unsaved changes already present. It binds the exact workbook and destination;
`Workbook.Saved` is not treated as a revision counter.

Existing attached workbooks use Save. Unsaved workbooks require an explicit
absolute Save As destination; the initial Save As subset creates a new `.xlsx`
file. Replacing an existing Save As destination is unsupported, even with the
contract's overwrite flag. This avoids changing global DisplayAlerts behavior.
Destination file metadata is checked again after approval. The host checks both
source and destination policies, and verification requires Saved, the expected
canonical path and the resulting file. Verified Save As refreshes the trusted
binding; old resource snapshots cannot authorize later edits under another path.

## Essential verification

The final focused deterministic/SDK/runtime/UI selection passed **134 checks in
64.94 seconds**, with no failures, errors or skips. Evidence is retained under
ignored `state/office-mcp-phase4-qualified.xml`. It includes:

- Patch, formula/value/format verification, complete paged snapshot coverage,
  exact worksheet binding, boolean/numeric distinctions and consumed cursors.
- Pre-write conflicts, later-change restoration rejection, partial/misverified
  writes and uncertain outcomes without replay or blind rollback.
- Actual MCP SDK/stdio execution through existing permission, approval ON/OFF,
  single-use authority, cancellation, crash-journal and source/destination paths.
- Existing read adapters, cloud exposure, connection controls, portable runtime
  pins/licenses/native imports and runtime relocation.

The opt-in native Excel selection passed **one gate in 12.01 seconds**, with no
skips (`state/office-mcp-phase4-live-qualified.xml`). A fixture-owned Excel
instance and two synthetic workbooks verify visible edits, unrelated cells and
focus preservation, literal text, local formulas and their calculated values,
basic formatting, conflict rejection, supported restoration, Save As, Save and
reopening the saved workbook. Disconnect preserves the open workbooks. Native
cancellation timing is covered by deterministic stdio fixtures rather than
interrupting a real user's Excel operation.

Caught Windows RPC notifications during native fixture shutdown remain in
`state/office-mcp-phase4-live-qualified.log`; they are not labeled clean shutdown
diagnostics. The fixture releases only its own instance and uses exact process
ownership for bounded cleanup. Final content-free diagnostics confirm bridge
release and no forced fixture termination. This is separate from production code, which
owns the bridge and preserves user Office processes. Preliminary fixture,
locale/format and assertion failures remain separate from the passing final
selection. Compilation and whitespace checks pass.

The actual six-tool projection measures **4,520 UTF-8 bytes / 1,795 conservative
reserve tokens**. The complete accepted eight-tool v1 manifest remains **7,390
bytes / 2,848 reserve tokens**, below its 9,000-byte / 3,500-token ceiling.
`state/office-mcp-phase4-budget.json` records a matching manifest and passing
offline budget. Local/disabled/unready Office exposure adds zero Office schemas.
These estimates do not measure billed provider usage.

No real document contents or credentials were used. The full suite, live cloud
acceptance/billing and physical second-host qualification were not run.
Word/PowerPoint editing and the complete phase 7 workflow remain later phases.
Essential focused tests only follow the user's explicit instruction.

Ref/worktree inventories are preserved in
`state/backups/office-mcp-phase4-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-mcp-phase4`, commit this bounded change,
fast-forward local main and remove only its merged feature branch. Other
worktrees, historical/unmerged tips, private settings and remote refs remain intact.
