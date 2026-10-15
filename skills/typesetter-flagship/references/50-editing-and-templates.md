# 50 — Existing documents, templates, and review features

Read before editing, template application, redlining, or formatting preservation.

## Inspect before selecting a route

Determine which content, styles, relationships, and review features must survive.
Inspect sections, headers/footers, numbering, fields, hyperlinks, bookmarks,
comments, tracked revisions, controls, drawings, and embedded objects as relevant.
Use a working copy or the host's guarded live-edit workflow. Do not replace the
source by default or migrate it through a library that cannot preserve its features.

Record only the evidence needed for the edit; do not put document contents or
personal metadata in diagnostic logs. Keep original documents and authorized
working copies in the intended locations. Do not change global Word settings.

## Preserve the correct layer

Word text can span runs with different formatting and relationships. A visible
phrase is not necessarily one XML node. Map the intended match, its occurrence,
and formatting before replacing it. Avoid raw string replacement across the ZIP
or rewriting an entire paragraph solely because a phrase crosses runs. Preserve
unaffected runs, links, fields, and anchors; use a capable route or explain the
limitation. Do not remove paragraph/cell markers to imitate a merge.

Applying a paragraph style can leave direct formatting intact. That may be
necessary to preserve emphasis; it may also explain why a restyle has little
visual effect. Clear only in-scope overrides through supported operations.
Do not claim a global typography redesign from changing style names alone.

## Treat templates as structured documents

A template can encode roles, themes, numbering, page geometry, section linkage,
and reusable content. If it contains a required shell, build from a copy of that
shell and replace intended variable regions. If the request is only style
matching, map semantic roles rather than blindly transplanting style IDs.
Resolve dependent styles, numbering IDs, media, and relationships together.
Do not graft incompatible parts without validating the resulting document.

Keep required boilerplate, clause numbering, deliberate blank pages, and brand
assets. Remove sample content only from intended replacement regions. Check
for stale placeholders and duplicated sections after filling. Do not create a
permanent brand-profile system unless that was requested.

## Review features need explicit handling

Preserve existing tracked changes and comments unless the task says otherwise.
Do not accept/reject revisions, flatten comments, or simulate tracked changes
using colored text. A redlining request needs a route that can create genuine
revision structures and preserve their attribution appropriately. If unavailable,
provide a clearly identified comparison/review within scope. Do not claim native
redlining or bypass a guarded host's unsupported-document refusal.
