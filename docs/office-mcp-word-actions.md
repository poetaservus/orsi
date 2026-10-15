# Office MCP phase 5: insertion, paragraph styles and table edits

This bounded change starts from main `3d984d7` on
`codex/office-word-actions`, 16 October 2026. It completes the three pending
Word actions through the existing cloud-only connection, permissions, actual
review UI, production stdio, native readback, owned recovery and separate
saving. The [initial replacement record](office-mcp-phase5.md) remains the
historical milestone. PowerPoint editing is still phase 6 work.

## Supported actions

Every patch contains one action and needs complete cursor coverage of the
exact attached document and target. Existing macro/protection/AutoSave,
unsupported-structure and local `.docx` save policies continue to apply.

| Action | Qualified scope |
| --- | --- |
| `replace_text` | Existing nonempty uniform body-text range within one paragraph |
| `insert_after` | Append nonempty plain text after a fully read uniform body-text range, inside the same paragraph; retain its character properties; resulting range at most 4,096 UTF-16 units |
| `apply_style` | Complete paragraph text, including mixed runs; choose `Normal`, `Heading 1`, `Heading 2`, `Title` or `Subtitle` from `office.read` with target `styles`; preserve direct run formatting and direct paragraph properties |
| `edit_table` | Replace the exact text matrix of an existing, fully read fixed-layout rectangular table; at most 64 cells and 8,192 combined UTF-16 text units; each cell has one ordinary paragraph; changed cells must have uniform formatting |

`office.read` with `tables` returns bounded table discovery and usable
`table:index` read targets. Reading that target returns paged structured JSON:
row/column counts, the complete text matrix, native cell-text coordinates and
coordinate units. Discovery and ordinary flattened document text do not
authorize table edits. All pages of the structured target must be read first.

Table dimensions, grid, widths, cell properties, paragraph properties, style
dependencies and unrelated content remain guarded. Empty cells can be filled
or cleared; unchanged mixed-format cells are preserved. Merged, nested,
irregular, AutoFit and multi-paragraph cells are outside the supported table
subset. Rows, columns and tables are not created or deleted by this action.
Paragraph/cell/control markers remain forbidden in supplied text. Insertion
does not create paragraphs. Custom styles can be restored from an owned edit;
the five discovered built-in styles are the qualified style-change targets.

## Native guards and preservation

The existing snapshot, approval digest and single-use guard bind each action's
exact arguments and state. Word table and cell collection wrappers do not
provide stable COM identities on this host. Table guards instead retain the
native table range and every cell range, checking their exact body-story
positions, parent document, table selector, complete structure and content.
Native qualification confirms that deleting/recreating an identical table
cannot inherit an earlier snapshot's authority. Insertions before targets and
later content/format changes still require fresh reads and approval.

Word's table cell-end sequence appears as CR + BEL in returned text but occupies
**one native character position**. Text-range endpoints exclude that whole
marker. Table writes run in row-major order, check the complete current state
before each write and admit only the approved patch's preceding text-length
transitions. Every cell write is read back against its expected intermediate
state. The final table is verified again. Recovery reverses the owned text
changes with the same guards and refuses later user edits.

Style assignment can reset direct paragraph formatting. The adapter assigns
the exact existing native style, then reapplies the approved paragraph
properties and direct text runs from a native-captured XML packet. The original
paragraph marker remains in place. Readback must match the requested paragraph
style, preserved direct formatting, text and unchanged style definitions.
Word's proven first-use removal of `semiHidden` gallery flags on a style and
its linked character style is excluded from the formatting fingerprint. Style
names, links, locks and all rendering properties remain exact; focused checks
confirm that font and style-link changes still invalidate the dependency guard.
Only the partial-range export's materialized inherited-font representation is
treated as derived; the full paragraph's native properties remain exact.
Explicit references to the default paragraph style and its native omission
normalize to the same captured definition. Custom-style restoration is
qualified through the production bridge.

Text/cell packets accept escaped caller text only. Native XML supplies all
formatting; section/header/footer parts and unrelated relationships are
excluded. Snapshot, guard and recovery memory limits are unchanged. Partial,
uncertain and misverified actions remain blocked and journal review-gated,
with no automatic retry or rollback. Saving remains separate and binds the
new source identity after Save As. Stop reports now use “Word edit” for all
four actions rather than describing every action as a replacement.

## Essential verification

The final focused selection passed **301 checks in 109.62 seconds**, without
failures, errors or skips (`state/word-actions-essential-final.xml`). It covers action
payloads and bounds, complete pagination, permission and exact approval,
stale-state/recovery rejection, partial/misverified outcomes, stdio execution,
history/replay, existing Word reads, shared connector behavior and Settings.
The actual Qt approval matrix includes all three new actions, saved/unsaved
documents and approval ON, denial and OFF. Earlier selections overlap this
final group and are not added to its count.

The final native selection passed **two gates in 98.56 seconds**, without
failures, errors or skips (`state/word-actions-native-qualified.xml`). One exercises
the new actions through displayed review panels and production stdio; the
other reruns the existing replacement/preservation gate. They qualify insertion
and restoration with Unicode/XML literals, changing and restoring a custom
source paragraph style through all five advertised targets while preserving
mixed runs and direct spacing,
structured table pagination, empty-cell writes/clearing, unchanged mixed cell
runs, cell formatting, later-edit restoration refusal, merged-table refusal,
identical-table recreation refusal, save/reopen, follow-up edits after Save As,
unrelated headers/body/tables and focus preservation.

The new combined COM gate invokes the displayed panel's own approval decision
handler. Real keyboard shortcuts are checked independently for every new action
in the saved/unsaved Qt matrix. Earlier combined offscreen-focus attempts
cancelled before dispatch; they are preserved separately. Earlier native
findings corrected default-style assignment, direct paragraph formatting,
table-export trailing paragraphs and cell-marker units. Failed fixture
journals were retained; retries used new synthetic documents and journals.

Both final diagnostics confirm bridge release, zero provider requests and no
forced fixture termination. The pre-existing user Word process remained open;
only positively identified test-owned instances were closed. Caught Windows RPC
notifications during native shutdown remain in the log and are not described
as a diagnostic-free shutdown. No user document or private setting was changed.
Saved style/table approval screenshots were also visually inspected.

The full eight-tool schema measures **14,271 UTF-8 bytes / 5,141 offline reserve
tokens**, below unchanged 14,500/5,300 ceilings. The seven-tool live projection
measures **12,687 / 4,565**; Word-only measures **5,252 / 2,039**. Manifest,
compilation and whitespace checks pass. These are offline schema estimates,
not provider billing or latency measurements.

The full suite, live provider/model behavior, visual document design, maximum
table-capacity performance and physical second-host qualification were not
run. Essential focused tests only follow the user's instruction. Prompts,
model sampling/routing/context policy and accepted model profiles are unchanged.

Inventories are retained under ignored
`state/backups/office-mcp-word-actions-20261016/`. Prior main is preserved at
`archive/2026-10-16/main-before-office-word-actions`. Commit, fast-forward local
main and remove only this merged local feature branch; preserve other worktrees,
historical/unmerged tips and remote refs.
