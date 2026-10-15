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

As inspected on 16 October 2026, the qualified live surface is a bounded edit
surface, not a complete document-generation/typesetting engine. Recheck current
schemas rather than treating this dated summary as permanent API documentation:

- `replace_text`: an exact, completely read uniform range inside one paragraph.
- `insert_after`: plain text appended inside that same paragraph; no new paragraph.
- `apply_style`: a completely read paragraph; discovered targets are `Normal`,
  `Heading 1`, `Heading 2`, `Title`, and `Subtitle`. Direct formatting is preserved.
- `edit_table`: text matrix replacement for an existing fully read qualified
  fixed rectangular table; no creation, resizing, merging, or table redesign.
- Saving is separate and governed by the host's exact save/Save As policy.

Do not infer new-document creation, font/margin editing, native lists, section
creation, images, headers/footers, TOC creation, or rendering from those actions.
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
