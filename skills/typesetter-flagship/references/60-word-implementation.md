# 60 — Word implementation and capability boundaries

Read before live writes or file generation. Inspect current tool schemas and
the actual environment; this package does not install upstream engines.

## Select the supported route

| Route | Suitable use | Check before choosing |
| --- | --- | --- |
| Guarded live Word tools | Qualified edits to an attached document | Exact supported targets/actions, approvals, read coverage, save contract |
| Permitted file generation | New editable DOCX or authorized copy edits | Available library, feature preservation, output path, renderer |
| Review/text-only surface | Critique, recommendations, supported content edits | Deliverable limits and evidence available |

Do not silently downgrade a requested full Word design to a plain text patch.
Complete useful supported work and name the remaining limitation. Another
route may be used only when independently permitted and suitable; it must not
circumvent an approval denial or unsupported-document guard.

## O.R.S.I. live Word baseline

Recheck current schemas rather than treating this dated summary as permanent
API documentation. The 17 October 2026 report-authoring extension supports:

- `office.word_compose`: replace an explicitly approved ordinary report with
  native body paragraphs and heading styles, editable tables, page breaks,
  one/two equal native text columns with explicit spacing, continuous/new-page
  section transitions, column breaks, typography, page dimensions/margins,
  consistent headers/footers and continuous PAGE/NUMPAGES fields. Supply the
  complete `sections` plan; older `pages` and `blocks` calls normalize separately.
  Read `authoring` completely first, including every cursor page; blank documents
  are supported. The approval replaces all body and running-matter content.
- `office.read` with `layout`: native page count and bounded table-width checks.
  With `render:first:last`, inspect up to three complete rendered pages per call
  and continue until every page has been reviewed. Pixels are native Word output;
  page count alone does not establish visual quality. Correct concrete defects
  before separately saving the document. Use genuine paragraphs for report text.
- `office.image_register`: register an authorized local PNG/JPEG path, or an
  `attachment:` reference discovered with `office.read` target `assets`. The
  returned opaque asset freezes the exact bytes for the session. Use an image
  block with `asset`, `width_mm`, meaningful `alt_text`, optional editable
  `caption`, and truthful `credit`. Aspect ratio is retained. Maximum eight
  images, 256 KiB per file, 2048 pixels per side, four million decoded pixels,
  and one MiB total media. Tables and pictures must fit their containing column.
  Rendered inspection pages are not insertion assets. No remote image fetching.

The existing bounded actions remain:

- `replace_text`: an exact, completely read uniform range inside one paragraph.
- `insert_after`: plain text appended inside that same paragraph; no new paragraph.
- `apply_style`: a completely read paragraph; discovered targets are `Normal`,
  `Heading 1`, `Heading 2`, `Title`, and `Subtitle`. Direct formatting is preserved.
- `edit_table`: text matrix replacement for an existing fully read qualified
  fixed rectangular table; no creation, resizing, merging, or table redesign.
- Saving is separate and governed by the host's exact save/Save As policy.

Do not infer launching new documents, native lists or TOC creation from these
actions. Composition requires an attached ordinary document, at most 16
supported sections and a two-MiB native package snapshot. Ordinary embedded
inline PNG/JPEG pictures and equal one/two-column layouts are preserved through
capture and owned recovery. Floating objects, text boxes, linked pictures,
cropping/effects, running-matter pictures, active document grids and unsupported binary dependencies
remain outside the initial subset; do not discard them to bypass a refusal.
Existing review/field/drawing structures can make a document unsupported for
writes. Treat host refusals as boundaries. Complete all needed read pages, use
returned coordinates and units, and refresh state after an identity-changing
operation. Never calculate native Word positions from Python string lengths.

## File generation when independently available

Use an available DOCX library or OpenXML SDK suited to the task. Do not assume
Python packages, .NET, LibreOffice, render scripts, or shell access exist because
an upstream skill mentions them. Keep content in native structures and verify
relationships, style/numbering dependencies, and section behavior. XML schema
validation helps find package defects; rendering checks layout separately.

For OOXML work, keep units explicit: font sizes use half-points, ordinary page
dimensions use twentieths of a point, drawing dimensions use EMUs; automatic
line spacing uses a different scale. Use library unit helpers where available.
Never mix them by guessing. Check target-version support for advanced features.

Use task-owned temporary files and resources. Close only resources created for
the task; do not quit the user's Word session or kill unrelated processes.
Read [70](70-accessibility-and-delivery.md) before handoff and
[80](80-review-and-evidence.md) before a completion claim.
