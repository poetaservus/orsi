# Native Word report authoring and page inspection

Started from local main cdd7f5b on codex/word-authoring, 16 October 2026.
The active checkout's unfinished full-suite repair is preserved in place;
implementation and qualification use a separate checkout under ignored state.

## Product behavior

The new office.word_compose action replaces an explicitly approved ordinary
report with real Word body paragraphs, built-in heading styles, editable native
tables and page breaks. It can start with a completely blank document. Text
boxes, floating shapes and generated page images are never used as body text.

Typography supports a font family, point size, color, bold/italic, alignment,
paragraph spacing, line spacing and keep-with-next. Layout supports bounded
page dimensions and margins, primary headers/footers, and native PAGE/NUMPAGES
fields. Fixed column widths, a repeating table header, no split rows and a
printable-width check support stable KPI tables. Saving remains a separate
office.save operation with the existing new-destination Save As policy.

Read target=authoring returns paginated complete report content and layout.
Finish every cursor page before composition. Approval explicitly says that
ALL body and running-matter content will be replaced. Complete native XML,
page setup and running-matter snapshots bind the exact document and revision.
Foreign changes reject the write or owned restoration before dispatch.
Post-dispatch errors remain outcome_unknown and block further writes; there
is no automatic retry, ordinary Undo or speculative rollback.

Read target=layout returns native pagination and bounded table-width warnings.
Read target=render:first:last renders one to three full pages through Word's
print-quality PDF export and the pinned PDFium rasterizer. Continue over
all pages. These are document pages, independent of overlapping desktop windows.
Pixels remain in bounded bridge memory and travel through private chunked
resources with byte-count and SHA-256 checks. The PDF is a private temporary
export, deleted before returning. Each bridge has its own owned scratch folder,
which is reclaimed after worker exit/abort; replacement directories are never
deleted. Cleanup status is recorded separately if an external Word export still
holds a file during cancellation. The model receives the verified
pixels as untrusted visual evidence; unsupported vision and integrity failures
explicitly leave visual quality unverified.

## Bounds and compatibility

Composition supports one ordinary macro-free, unprotected local DOCX section,
at most 96 content blocks, 512 table cells and 24,000 supplied text characters,
within the existing 32-KiB argument envelope. Source XML has a one-MiB bound.
Pictures, floating shapes, notes, tracked changes, unsupported fields and
external relationships remain outside the authoring subset. Existing text
editing and table-cell contracts retain their scope. Rendering is a read
operation and has a separate eight-MiB source snapshot bound.

The Office catalog grows from eight to nine tools. Its reviewed schema ceiling
is 20,000 bytes / 7,200 offline reserve tokens. This measures the additive tool
contract; model profiles, context limits, sampling, prompts and permissions
retain their existing policies. Pillow 12.3.0 was already present in the portable
runtime and is now pinned for the MCP/Windows installation and relocation checks.
PDFium/pypdfium2 5.14.0 is installed from its official Windows wheel after
checking the publisher's SHA-256; its full license notices ship with the runtime.
PDF export is capped at 16 MiB and each image group at 2 MiB, with at most
three pages per call. Large pages can be rendered individually.

Word exports fresh revision identifiers and refreshes page-field display values.
Snapshot comparison excludes those caches while retaining field codes, their
typography, document content, structural properties, styles and dependencies.
The writer repaginates before updating total-page fields, then repaginates again.
Native page-metafile probes exposed stale totals, inactive-window running-matter
omissions and repeated-header paint caching. The final print-export path avoids
that preview API and verifies header text in the actual exported page content.

## Verification

The final affected selection passed **210 checks**, with **7 optional skips**,
in **117.47 seconds**. Three native Word gates passed in **167.84 seconds**,
covering replacement/insertion/style/table compatibility and the new complete
report workflow. The saved-source variant also passed in **70.92 seconds**;
its unique fixture name prevents selecting another process's unsaved Document1.
All owned Word processes exited, bridge workers released, and export scratch
folders were reclaimed without forced fixture termination. Existing native
fixture COM proxy cleanup emitted RPC diagnostics; these remain in the logs.

The report gate verifies an initially blank source, complete paginated reads,
approval denial, stale-source refusal, native heading styles and editable table,
three actual pages, correct PAGE/NUMPAGES fields, every exported page's header,
verified image delivery into a scripted model continuation, refusal to revert
foreign edits, complete report restoration, new-path Save As and reopen. The
DOCX contains genuine body text and a native table, with no text boxes. All
three printed page images were inspected for clipping, orphaned headings,
broken breaks, running matter and whitespace. A synthetic proof copy is retained
under the active checkout's ignored state/word-authoring-proof.

The full unrestricted run recorded **4,215 passed, 51 failed, 99 skipped**, and
**15 passing subtests**, in **1,369.47 seconds**. Fifty failing IDs exactly match
the prior cdd7f5b baseline: 47 language/Hungarian catalog failures, one login font
fixture and two settings dropdown cases. These belong to the preserved pending
full-suite repair. The additional unchanged skill-discovery entry-limit test hit
WinError 5 while renaming its released directory; its entire **32-test module
passed unchanged** on isolated unrestricted recheck in **0.74 seconds**. Its
full-run cause remains unresolved. No full run is claimed clean.

The 99 skips include opt-in Office/model/provider gates and browser checks whose
Playwright cache is absent from the isolated checkout. Native Word qualification
above is separate from those skips. The original acceptance prompt is unchanged;
no real provider-driven generation was run and no API credentials or requests
were used. The optional Typesetter reference is updated to describe current
contracts, with package version 1.0.1; it is not automatically installed or
activated. Core prompts, routing policy, sampling, model profiles and context
limits remain unchanged. Compilation, dependency consistency, manifest/budget
verification and whitespace checks passed.

Initial failed probes remain explicit under ignored state/word-authoring. They
led to native namespace preservation, explicit page-setup application, page-field
cache handling and package-relationship normalization. Native metafile previews
were rejected after visual/print differences; the shipped path uses Word's
fixed-format export. No early failure is relabeled passing.

## Primary API references

- [Word fixed-format export](https://learn.microsoft.com/en-us/office/vba/api/word.document.exportasfixedformat)
- [PDFium renderer distribution](https://pypi.org/project/pypdfium2/5.14.0/)
- [Word Range.InsertXML](https://learn.microsoft.com/en-us/office/vba/api/word.range.insertxml)
