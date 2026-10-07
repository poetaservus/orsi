# Images inside sent messages

Image attachments appear above the user's text inside the bubble. One image has
a larger, rounded 280 × 180 preview; several images use ordered 112 × 96 miniatures
in one row. Four fit at the normal conversation width. Longer rows scroll
horizontally, and narrow windows resize the single preview. Images keep their
aspect ratio and orientation. Filenames and sizes are available on hover and
through accessibility names; document attachments retain their existing labels.

The same rendering applies to local and cloud messages, including restored and
archived conversations. It reads the existing immutable attachment snapshots,
without depending on the original file path or changing attachment admission,
inference, model selection, context accounting or serialized history.

Only exposed miniatures request decoding. A two-worker pool verifies each snapshot
off the GUI thread, then borrows its pinned read-only handle for Qt decoding. Handles
close after decoding, and a 32-entry cache retains only images bounded to 560 × 360
pixels. The existing 40-million-pixel source guard is respected. Clearing the chat
cancels queued work and ignores old completions. Missing, changed or undecodable
copies show a quiet filename fallback while preserving the message.

## Verification

Focused native checks cover actual image pixels after deleting the original,
image/file mixtures and ordering, long-row lazy loading and cache eviction,
resizing, unavailable source handling, stale worker completion, Windows handle
release, local sending, and normal/archive restoration. PNG, JPEG, WebP and still
GIF decoding and portrait aspect ratio passed. The actual app UI was rendered and
visually inspected with synthetic images; preview artifacts remain in ignored
`state/chat-image-preview-artifacts/`.

Initial test setup errors (a missing basetemp parent, a nonexistent test filename,
and one misplaced new assertion) were corrected before final verification.
Expanded focused checks passed 144 tests and five subtests. After the final visual
refinements, UI/composer checks passed 72 tests and five subtests; the format/cache
group then passed all 12 tests. The initial full run recorded 2,269 passed, one
unchanged native skill-reader directory-rename denial, 57 skipped and 15 subtests
in 337.12 seconds. All 73 skill-reader tests passed their isolated recheck.
Final full native regression passed **2,274 tests and 15 subtests**, with **57
optional skips**, zero failures/errors, in **330.37 seconds**. Integration is
recorded in [the Git workflow](git-workflow.md).
Optional live model/API gates remain skipped; this change only affects display.
No API credential or real user attachment was accessed. Compilation, dependency
consistency and Git whitespace checks passed.
