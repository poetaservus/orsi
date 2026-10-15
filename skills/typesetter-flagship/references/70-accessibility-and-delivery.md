# 70 — Accessibility, compatibility, and delivery

Read when preparing the artifact for use, sharing, printing, or handoff.

## Preserve a usable reading path

Use semantic headings in logical order, native lists, meaningful hyperlink
text, and actual table headers where supported. Avoid merged/nested tables for
layout when a simpler in-flow structure works. Check reading order around
columns, images, and floating objects. Add useful alt text to informative
visuals and identify decorative images appropriately where supported.

Keep contrast sufficient at intended reading and print size; do not rely on
color alone for meaning. Test muted text, fine rules, and shaded cells on a white
page and, when relevant, grayscale. Accessible design can still have expressive
type, color, and imagery. Do not imply that a monochrome export or a font-size
threshold proves accessibility. Use the application's accessibility checker
when available and report material unresolved issues.

## Check the receiving environment

Confirm editable DOCX as the primary artifact when requested. Preserve other
formats only through an explicitly suitable workflow. Do not convert `.docm`
to macro-free `.docx` as incidental polish or assume legacy `.doc` conversion
is lossless. Preserve the original and qualify any authorized conversion.

Choose fonts and features for the target Word/renderer environment. Check
substitution and language coverage. Embedded fonts have licensing and tool
constraints; do not assume they are permitted or supported. A LibreOffice
preview establishes LibreOffice rendering. Native Word inspection is stronger
for a Word-targeted deliverable, but neither proves identical output everywhere.

## Deliver and report accurately

Confirm the intended destination, saved artifact, and reopen/readback when
supported. Live Word saving can persist unrelated outstanding changes; follow
the host's review and save semantics. Do not claim saving from edit success.
Do not overwrite another file or export extra formats merely for presentation.

A PDF can be an internal layout-check artifact; provide it as a deliverable
only when requested or useful within scope. Keep the editable DOCX available.
Do not present a flattened PDF/image as the requested editable document.

Briefly describe material changes and actual checks: content/structure,
rendered pages and renderer, field refresh, accessibility, and save/reopen as
applicable. Name incomplete categories without burying the result in a generic
checklist. Release only owned resources and leave the user's work accessible.
