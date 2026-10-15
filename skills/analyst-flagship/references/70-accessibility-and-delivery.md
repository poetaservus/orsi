# 70 — Readability, accessibility, and delivery

Read when the dashboard will be used, saved, shared, printed, or handed off.

## Design for the actual Excel reading surface

A worksheet is not a responsive web page. Choose a useful working area for the
intended laptop/desktop window and normal reading size. Smaller screens may need
a compact summary with reachable detail, rather than a giant canvas scaled down
until nothing is readable. Do not enforce a universal 75% zoom or a fixed width.

Inspect title and axis wraps, legend overlap, slicer captions, row labels, large
values, footnotes, and long category names. Allow expected expansion without
covering adjacent values. Keep units and selected context readable together with
the data they explain. A chart that only works full-screen at one zoom is fragile.

Keep source/detail sheets convenient to navigate. Freeze relevant headings or
identifier columns when the range needs scrolling and the tools support it.
Do not hide every supporting sheet or disable normal worksheet navigation to
imitate a standalone app. Preserve the user's existing view conventions where
appropriate.

## Accessible structure and color

Use clear sheet names, logical reading order, descriptive headings, labeled
controls, and proper tabular headers. Avoid merged cells across data regions;
they complicate reading, sorting, filtering, and navigation. A limited title
merge is a separate decision, not a reason to merge every KPI area.

Use readable contrast for labels, values, axes, and control states. Check pale
gray footnotes and colored text against the real background. Pair good/bad,
actual/target, and selected/unselected colors with explicit text or other cues.

For meaningful charts, include descriptive titles, axis/series labels, and
alternative text where the host supports it. Keep an accessible data table or
exact-detail route when the visual alone would obscure values. Do not claim
screen-reader or keyboard verification from a screenshot.

Choose fonts that exist in the target environment and preserve usable fallbacks
when relevant. Avoid requiring a font download or custom theme installation for
ordinary business use. Newness of a typeface is not an accessibility benefit.

## Locale, units, and formats

Keep stored numeric/date types separate from display conventions. Display the
currency and scale unambiguously. Format entity counts as whole numbers; allow
fractional quantities only when the unit supports them. Use appropriate monetary,
rate, and date precision. Do not add mixed currencies without a valid conversion
basis. Keep zeros, negative amounts, missing values, and unavailable comparisons
distinguishable.

Use labels and number formats rather than turning numeric cells into strings
just to append a suffix. Keep exact amounts available where reconciliation is a
user task. Verify long translated labels or non-Latin text where they occur;
do not change the language of the workbook without a reason.

## Print and export only when needed

For a requested printed/PDF view, set a suitable print area, page orientation,
margins, and repeated headings where supported. Check page breaks and final text
size. Fit-to-page is not successful if it creates unreadably small labels. A
multi-page detail report can be better than a compressed one-page dashboard.

Preserve existing print settings during unrelated edits. Do not add a PDF,
slide deck, screenshot pack, website, or macro workflow merely because dashboard
delivery sometimes includes one. An image is supplementary when the requested
deliverable is an interactive workbook.

## Saved state and maintenance

Save with a sensible active sheet, visible workbook window, selected context,
and useful view when the tools allow it. Do not leave test selections, temporary
rows, or an accidental empty sheet as the opening experience. Preserve macros
and the appropriate file extension when applicable.

For a maintained dashboard, provide concise source/period definitions, refresh
instructions, and any material compatibility limits. Place them in the workbook
or handoff where the user needs them; avoid a lengthy manual for a simple file.
Never label a live-clock timestamp as verified refresh time.

## Handoff with evidence

State the saved file location or the identified live workbook, the main result,
and the checks actually completed. Separate calculation, filter/refresh, visual,
preservation, and save/reopen evidence. Name unfinished requested features or
unavailable verification without claiming they passed.

For critique-only work, give prioritized findings tied to specific sheets,
ranges, or visuals and their effect on the reader. Do not silently turn critique
into a rebuild. For completed edits, explain only material design or analytical
decisions and relevant limitations.
