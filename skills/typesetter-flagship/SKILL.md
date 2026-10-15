---
name: typesetter-flagship
description: >-
  Design, create, edit, restyle, repair, and review Microsoft Word documents
  and editable .docx deliverables: reports, proposals, briefs, letters, manuals,
  manuscripts, and template-based documents. Use for typography, page composition,
  semantic styles, tables, figures, pagination, preservation, and document visual
  QA with anti-slop and anti-premium-slop judgment. Not for plain chat copy,
  spreadsheet dashboards, slide decks, or PDF-only design unrelated to Word.
license: MIT
metadata:
  version: "1.0.0"
  author: O.R.S.I.
---

# Typesetter — O.R.S.I. Flagship

Make Word documents that feel authored for their subject and reader, remain
editable, and hold together across pages. Give typography, composition, and
content equal attention. Anti-slop should produce better design, including
expressive design when appropriate; it must not force every brief into a plain
memo or an interchangeable luxury report.

## Priority order

1. User purpose, requested scope, and existing work to preserve.
2. Content truth, completeness, exact wording where required, and source fidelity.
3. Document integrity, editability, and supported operations.
4. Reading order, hierarchy, navigation, and useful page composition.
5. Legibility, accessibility, and the requested brand or publication conventions.
6. Pagination, rendering compatibility, and reliable saving.
7. Distinctiveness and visual craft.

Host instructions, permissions, and approvals remain authoritative. This is an
instruction package; it supplies no Word bridge, renderer, library, or new tools.

## 1. Establish the document brief

Inspect the actual source/template and advertised capabilities. Distinguish new
creation, content editing, formatting-only work, template application, repair,
and critique. Identify reader, purpose, document genre, language, required
content, expected length, page size, delivery format, and target reading context.
For existing work, inspect styles, sections, tables, fields, and review features
before selecting an editing route. Read 60 before a write or file-generation
decision; do not promise page design that the available tools cannot perform.

Infer routine design choices from the brief and existing document. Ask only for
missing information that materially changes the result. A formatting request
does not authorize rewriting claims, removing caveats, accepting revisions, or
replacing the user's template. Preserve intentional direct formatting and
structural relationships; content is not disposable material for a layout.

## 2. Set three dials

Infer these on a 1–10 scale; use them as judgment guides, not a questionnaire:

- `design_variance`: freedom to depart from a template or conventional composition.
- `editorial_depth`: permitted intervention in wording and organization.
- `visual_density`: useful information per page at the intended reading size.

A formatting-only request has low editorial depth even when design variance is
high. A dense technical manual can have excellent craft. A short board brief may
need an immediate recommendation rather than a cover. A commissioned editorial
report can support expressive type and imagery. No dial implies extra pages,
mandatory illustrations, or permission to alter factual content.

## 3. Read references progressively

For substantial new work, start with 00 and 20, then 10 when defining typography.
For a narrow task, start with its matching reference. Read further only for the
next actual decision; do not load every file in advance.

| Decision or task | Reference |
| --- | --- |
| Purpose, source coverage, scope, document contract | [00 — Foundations](references/00-foundations.md) |
| Styles, fonts, paragraph rhythm, language | [10 — Typography and styles](references/10-typography-and-styles.md) |
| Art direction, page composition, anti-slop, premium-slop critique | [20 — Composition and taste](references/20-composition-and-taste.md) |
| Tables, figures, captions, numerical presentation | [30 — Tables and figures](references/30-tables-and-figures.md) |
| Page/section breaks, headers, fields, long-document flow | [40 — Pagination and navigation](references/40-pagination-and-navigation.md) |
| Existing documents, templates, revisions, preservation | [50 — Editing and templates](references/50-editing-and-templates.md) |
| Live Word versus file generation, tool limits, save behavior | [60 — Word implementation](references/60-word-implementation.md) |
| Accessibility, compatibility, final artifact and handoff | [70 — Accessibility and delivery](references/70-accessibility-and-delivery.md) |
| Completion review, rendered inspection, evidence | [80 — Review and evidence](references/80-review-and-evidence.md) |
| Evaluating this skill against representative briefs | [85 — Evaluation cases](references/85-evaluation-cases.md) |
| Genre-specific structure and useful visual treatments | [90 — Document patterns](references/90-document-patterns.md) |
| Research, provenance, licenses | [99 — Sources and license](references/99-sources-and-license.md) |

O.R.S.I. hosts: request canonical paths from the active package's
`skill.read_reference` inventory. Respect returned version and continuation
fields. Finish relevant excerpts before relying on them; do not invent missing
guidance or search the user's drive for package files. Other hosts can read
these relative Markdown paths normally.

## 4. Form a compact document contract

Resolve reader/purpose, content coverage, editable structure, intended page
geometry, type hierarchy, visual direction, preservation constraints, and
verification route before substantial changes. Summarize these only when useful.
Choose a specific compositional idea from the subject: a comparison-led brief,
an illustrated field guide, a typographic essay, or a compact working memo.
Decide what deserves emphasis and what should stay quiet.

Use the user's template when supplied. For an unconstrained new design, make
visible choices in hierarchy, title treatment, rhythm, tables, and imagery
where relevant. A different accent color alone does not satisfy a redesign.
Read 20 for positive design options and recognizable failure patterns.

## 5. Build the whole document

Use native paragraphs, semantic heading styles, lists, tables, captions, and
fields where supported. Design the style system before applying repeated
formatting. Keep layout in flow where practical, so future edits can reflow.
Do not build pages from spaces, repeated blank paragraphs, text screenshots,
or floating boxes that fracture reading order.

Preserve qualifications, exact figures, sources, and required sections. Never
invent quotations, references, certifications, endorsements, metrics, or
confidentiality labels to make a document seem substantial. Use lists for real
enumerations and numbering for actual sequences or referable clauses. Keep
generic promotional prose and duplicated summaries out of newly authored text.
For formatting-only work, flag textual issues without silently rewriting them.

Check real page transitions, long headings, table continuations, captions, and
headers/footers. A polished first page does not establish a finished report.
Apply 40 and 50 as needed. A refusal from the live host is not permission to
circumvent it through a different execution route.

## 6. Verify in bounded passes

Read 80 before substantial completion. Inspect content/structure and actual
rendered pages when available; collect defects, fix them in a coherent batch,
then confirm affected pages and downstream flow. Continue only for observed
blocking defects rather than speculative cosmetic churn.

Keep proof categories separate: valid OOXML is not visual QA; a PDF preview is
not evidence of editable Word structure; an inserted field is not an updated
TOC; an in-memory edit is not a saved artifact. State material unavailable
operations and checks precisely. Deliver the useful supported result without
calling a text patch, mockup, or plan a fully typeset Word document.

## Definition of done

From a distance, the document has a coherent hierarchy and visual identity.
At reading size, text, tables, figures, and page transitions are comfortable.
On close inspection, content is faithful, structure is editable, required
features survive, and the requested artifact has been saved and checked to
the extent reported. Deliver the file or review with a brief account of actual
changes, verification, and material limits.
