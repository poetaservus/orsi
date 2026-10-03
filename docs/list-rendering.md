# List marker rendering

The screenshot's large dots and tight spacing came from the default Qt list painter, rather
than the generated Markdown. At the actual 18-pixel Saira response font, Windows measurements
showed 28-pixel font line spacing and a 4-pixel space advance. Qt uses one third of the integer
line spacing for a bullet diameter (9 pixels) and a single space advance for the gap. Its marker
centering follows font height, rather than the visible capital-letter height. See the
[Qt list painter source](https://github.com/qt/qtbase/blob/6.10/src/gui/text/qtextdocumentlayout.cpp).

The renderer now paints ordinary unordered markers at approximately 4.2 pixels with a 7-pixel
gap at that font size, centered against the first line's capital-letter height. Sizes scale
with the text font. A per-block marker override suppresses the default drawing while preserving
the native list object, indentation, text layout and original Markdown. Numbered and task-list
markers retain native rendering. Wrapped lines keep the native hanging indent, and nested
lists keep their existing indentation. Inline references, selection and copying remain text.

Native Windows preview and focused checks covered narrow/wide wrapping, nesting, numbering,
task markers, selection and source copying at multiple font sizes. The focused run passed
39 tests and 5 subtests. A before/after preview is saved locally under ignored
`state/list-markers-windows-preview.png`.

The full suite recorded 848 passed, 4 failed, 54 skipped and 15 subtests passed. All four
failures originated in Windows access-denied errors during atomic journal/history replacement,
including a cancellation result that became an internal failure when journaling failed. The
affected cancellation, edit-preview, special-path and read-answer groups passed their isolated
five-test recheck. The full-run failures remain recorded; persistence was not modified here.

This is a presentation change with no changes to inference, model profiles, prompts, tools or
authorization. Model workflow qualification was not repeated; the feature remains on
`codex/list-marker-spacing` for review and is not promoted as a fully qualified model baseline.
