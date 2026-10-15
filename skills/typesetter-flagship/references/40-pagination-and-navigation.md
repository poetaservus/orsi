# 40 — Pagination and long-document navigation

Read for multi-page documents, page-flow repair, TOCs, sections, or headers/footers.

## Keep the document in flow

Use paragraph spacing and pagination properties rather than blank lines to
place content. Keep headings with following text; use widow/orphan control
where supported. Reserve keep-together for appropriate short blocks. Applying
keep-with-next to all body paragraphs can produce huge gaps or unstable flow.
Inspect page endings and opening paragraphs after changes.

Use an explicit page break for an intended new page. Use a section break when
page geometry, orientation, numbering, columns, or header/footer policy changes.
Do not add section breaks after every heading. Odd/even starts can deliberately
create blank pages in a bound document; distinguish that convention from an
accidental empty page. Do not force every section onto a new page for drama.

Check repeated headers, footer distances, top/bottom margins, and the space
available to body content. Inspect first-page and odd/even variants, linkage
to previous sections, and page-number continuity. A landscape table must not
silently change all subsequent pages or detach their footers.

## Fields and navigation are functional features

Use logical heading levels for the navigation pane and a native TOC where
useful. Short letters and memos rarely need a contents page. Use real page
number, caption, and cross-reference fields when supported. Preserve bookmarks
and field relationships during edits. Do not type fake page numbers or cached
TOC entries and call them dynamic.

A DOCX library may insert fields without evaluating them. A request to update
fields on open is not proof of a refreshed TOC. When available, update through
the target application, repaginate, and verify entries and page references.
If unavailable, state which fields remain unverified or require refresh.

## Inspect transitions, not only the opening

Inspect all rendered pages for a normal deliverable: empty/near-empty pages,
stranded headings, broken tables, detached captions, clipped notes, bad font
fallback, and header/footer collisions. Pay particular attention to section
boundaries, long headings, tall rows, and the final page. For a very long file,
combine a whole-document thumbnail/contact-sheet pass with readable inspection
of representative and risk pages; disclose sampled visual coverage.

After fixes, rerender affected pages and downstream flow. Different fonts or
Word/LibreOffice versions can repaginate the file; qualify evidence by renderer.
Do not promise universal pagination from one PDF preview.
