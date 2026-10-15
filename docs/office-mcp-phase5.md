# Office MCP phase 5: qualified Word replacement slice

Started from local main `33328c8` on `codex/office-mcp-phase5`, 15–16 October
2026. The initial vertical slice in phase 5.1 is implemented: exact text
replacement, actual approval UI, production stdio/native execution, readback,
guarded restoration and separate Save/Save As with reopen. Remaining Word
actions (`insert_after`, `apply_style`, `edit_table`) stay unavailable pending
their own bounded implementation and qualification. PowerPoint remains read-only.

## Supported workflow and boundaries

Connect in Cloud mode, select an open Word document, attach it and read the
intended body text. `document` discovers paragraph text targets without their
final paragraph markers; `text:start:end` uses native UTF-16 positions.
`selection` freezes the range in the selected document's window. Headers,
footers, notes and text boxes are outside body-read coverage; header selections
are rejected. Table text remains readable, with no table mutation authority.

`office.word_edit` accepts one nonempty replacement of one completely read
target, up to 4,096 UTF-16 units, within one ordinary body paragraph. The
containing paragraph must fit 8,192 units. Both the range and its underlying
paragraph runs must have uniform character formatting across the target.
Mixed surrounding runs are preserved. Paragraph/cell markers, control
characters, empty replacements, multiple changes and reserved actions reject
before dispatch. This deliberately avoids patch overlap and rebasing ambiguity.

Documents must be writable, macro-free, unprotected, non-final and without
IRM, AutoSave or tracked changes/revisions. Existing files must be ordinary
`.docx`. Main-story fields, hyperlinks, bookmarks and content controls are
unsupported. Snapshot exports reject embedded fonts, drawings, notes and more
than 16 sections. Header/footer dependencies must be bounded text without
drawings. These checks precede native XML export, whose byte ceiling is 256 KiB.
Unsupported targets remain bounded read-only views rather than edit anchors.
No application-wide Office setting is changed.

Editing leaves the document unsaved. Saving is a separate approved operation
that saves all current document changes. Unsaved documents require a new,
absolute local `.docx` Save As destination. Replacing an existing destination is
unsupported, including with `overwrite=true`. Source/destination policy,
destination metadata and exact document identity are checked. Save As updates
the trusted host binding; fresh reads authorize subsequent edits under the new
path. Production code never closes documents or quits Word.

## Exact coverage, preservation and recovery

Read pages share a snapshot and target IDs, even when one page contains several
fragments of the same target. Complete cursor coverage is required before any
edit. Every observed fragment and captured text/format state is rechecked on
continuation. Retained native ranges, exact positions, the body story, parent
document, full paragraph text/properties/runs and style/font/theme/numbering
dependencies bind the approved operation. Insertions before duplicate text,
formatting changes, stale snapshots and cross-session targets cannot retarget
the write. The adapter never resolves a fresh active selection during dispatch.

Private native OOXML supplies the existing text-run properties. Caller text is
escaped; caller XML is never accepted. Full paragraph properties are retained
explicitly. Section properties and unrelated package parts/relationships are
excluded from insertion. Native verification checks the exact intended text,
run formatting, paragraph state and dependency fingerprints. Partial-range
exports materialize inherited fonts differently from complete-paragraph
exports; each representation is preserved separately.

Verified operations return in-memory recovery. Restoration needs a fresh
complete covering read and exact equality with the owned after state. Later
manual edits reject restoration. Recovery is not ordinary Undo; disconnect
releases it. Limits are 128 snapshots/cursors/prepared guards, 64 recovery
records and separate 8-MiB snapshot/guard/recovery budgets, including fragment
metadata. Unknown native, partial or misverified writes block mutations and
remain journal review-gated, without automatic replay or rollback. Diagnostics
retain fixed stage codes, HRESULT numbers and mismatched field names only.

## Qualification

The essential connector/Word/Excel/approval/history/settings/protocol selection
passed **287 checks in 57.79 seconds**, with no skips or failures
(`state/office-phase5-essential.xml`). The separate connection/permission
selection passed **21 checks in 18.99 seconds**
(`state/office-phase5-connection-final.xml`).
The filesystem-report module passed **31 checks in 1.69 seconds** in an
unrestricted shell (`state/office-phase5-report-native.xml`). Its initial
sandboxed run left the source unchanged in one case; no product test or
assertion was weakened, and that failure remains in the earlier report.
The three final deterministic selections contain **339 checks** in distinct
modules; earlier overlapping runs are not added to that count.

The final native Word gate passed **one test in 30.92 seconds**, with no skips
(`state/office-phase5-native-final-safe.xml`). It runs the actual conversation
and approval window through the production bridge against isolated synthetic
documents. It qualifies Unicode and XML literal text, custom/inherited styles,
paragraph spacing, mixed surrounding runs, unchanged tables/headers and focus,
structural/tracked/protected/drawing refusals, an insertion before duplicate
text, approval-time formatting conflict, later-edit restoration refusal,
Save As, follow-up editing, Save and reopening. Deterministic UI cases cover
saved/unsaved approval ON, denial and OFF. Historical reserved Word evidence
replays original bytes/IDs while live decoding stays restricted to replacement.
Stop reports retain successful Word operations.

Native diagnostics confirm bridge release and no forced fixture termination.
Caught Windows RPC shutdown notifications remain in the native log; the log is
not represented as free of shutdown diagnostics. One failed diagnostic probe's
synthetic document was recovered after checking its exact PID, process creation
identity and fixture fingerprint; all other Word instances were preserved.
Earlier native formatting/import findings and uncertain journals are retained
under ignored `state/`; each retry used a new synthetic fixture and journal.
The actual approval screenshot was visually inspected. No user document was
changed and no provider request was made.

The accepted eight-tool catalog measures **14,112 UTF-8 bytes / 5,088 offline
reserve tokens**, under unchanged 14,500/5,300 ceilings. The seven-tool live
projection measures **12,528 / 4,512**; Word-only exposure measures **5,093 /
1,986**. The manifest matches; compilation and whitespace checks pass. These
are schema estimates, not billed usage or provider latency measurements.

The full suite, live provider/model behavior, document visual-design assessment
and physical second-host qualification were not run. Essential focused tests
only follow the user's explicit request. Instructions, model profiles, routing,
sampling, context limits and private settings were not changed.

Pre-change refs/worktrees/status are preserved in
`state/backups/office-mcp-phase5-20261015/`; prior main is retained at
`archive/2026-10-15/main-before-office-mcp-phase5`. Integrate the verified bounded
change by fast-forwarding local main and removing only its merged feature
branch. Other worktrees, historical/unmerged tips and remote refs remain intact.
