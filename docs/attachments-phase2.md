# Image and file input: phase 2 composer and preparation

## Delivered behavior

The composer + button opens a file picker. Local mode chooses one combined file
or image per message; cloud mode can select multiple without a small frontend
count cap. The folder button retains its placeholder behavior. Files can also
be dropped onto the window/input, pasted as local file URLs, or captured from an
image clipboard. Ordinary text and remote links continue to paste as text; remote
content is never downloaded by this input path.

An attachment row expands above the existing composer input. Each muted card has
its name, preparation status, removal action and either an image thumbnail or a
document label. Ready images show their dimensions. Documents explicitly show
text-only preparation, with full limitations in the tooltip. Removing the last
attachment restores the original compact composer. The input text remains editable
while attachments prepare.

File copying, clipboard PNG encoding, hashing, decoding and extraction run on a
dedicated Qt worker thread. Results enter the GUI in selection order. Further
cloud selections queue behind the active batch; removing a pending entry cancels
its work. New session clears/cancels the draft. Window close cancels preparation
and waits for the thread to unwind instead of destroying a running QThread.
Switching a multi-file cloud draft to local preserves the selection and asks the
user to remove extras; it never silently discards files.

An attachment-only message can travel through the worker/service contract when
an adapter is capable. User bubbles and restored history show attachment filenames.
Production adapters remain gated in this phase. Pressing Send with prepared inputs
shows an inline availability message and retains the text, selected skill and
attachment draft. It does not ask for credentials or issue inference. Actual local
and cloud input, native tool continuations and live qualification are phases 3/4.
Text-only messages retain their existing send behavior.

This describes the phase 2 checkpoint. [Phase 3A](attachments-phase3a.md) now enables
local text-document sending and native tool continuations; vision and cloud remain gated.

## Preparation contract

`AttachmentProcessor` consumes phase 1's verified immutable copies, never the live
original file. It returns a frozen `PreparedAttachment` with the reference,
`ProcessedAttachment` record and optional QImage thumbnail. Only the GUI converts
the QImage into a QPixmap. Thumbnails do not replace or reduce the original input.
The processed record is stored atomically as `prepared_v1.json` alongside the
snapshot. It is versioned and bound to the original attachment ID and SHA-256.
Original bytes and extracted text stay in ignored local state; they are not
diagnostic/baseline data. Cache absence or corruption reports a fixed error and
leaves the original available for preparation again.

Supported preparation:

| Input | Prepared material | Explicit limitations |
| --- | --- | --- |
| PNG, JPEG, WebP, static GIF | Validated image dimensions and thumbnail | Requires a later vision adapter; no OCR claim; animation is rejected |
| Text/code, CSV, TSV, JSON and related formats | Literal text and line endings | UTF-8 or BOM-marked UTF-16/32; binary and undecodable files are rejected |
| PDF | Selectable text, separated by page | No OCR or visual chart reading; textless pages are flagged; encrypted PDFs are rejected |
| DOCX | Main document paragraphs, runs and table text | No page layout, headers, comments or embedded visuals |
| PPTX | Text in presentation order and speaker notes | No slide design or embedded visuals |
| XLSX | Sheet names, cell coordinates, stored values and formulas | No calculation, formatting interpretation, charts or images; dates retain stored numeric values |

PDF extraction uses pinned `pypdf==6.19.0`. Its documentation explains why selectable
text extraction cannot read scanned images and why page content streams require
memory limits: [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
Office preparation reads package XML with pinned `defusedxml==0.7.1`, rejects entity
expansion and external relationships, and never extracts archive entries to disk.
There is no macro, formula, Python/code execution, network fetch or skill activation.
Image validation and scaled preview decoding use the existing Qt runtime:
[QImageReader](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QImageReader.html).
Both dependency manifests include the new parsers, and both were installed into
the repository-local portable runtime for verification.

Preparation has explicit processing guards: 2,000,000 extracted characters,
40,000,000 image pixels, 64 MiB encoded PDFs, 2,000 PDF pages, 32 MiB per Office
component/PDF page content stream, 128 MiB total declared unpacked Office data,
and 10,000 Office entries. Oversized inputs fail visibly rather than being silently
truncated. These are current client processing guards, not cloud API allowances;
phase 4 must distinguish native upload capacity from extraction/preview capacity
when implementing maximum supported cloud admission. Passwords, unsupported
legacy/macro Office formats and OCR remain outside this phase.

## Verification

Final focused native checks: **150 passed and five subtests passed in 13.26 seconds**.
The 49 new preparation/composer cases exercise actual document bytes, PDF text and
encryption, OOXML relationships/order, speaker notes, spreadsheet coordinates and
formula retention, image formats/thumbnails/animation, malformed/binary inputs,
processing bounds, cache integrity, clipboard and local URLs, drop events,
local/cloud counts, queued selections, cancellation, new sessions, shutdown,
adapter gating, attachment-only dispatch, draft/skill retention and ordinary text.
Existing UI, phase 1 foundation and manual skill tests also passed.

The initial cloud batch test timed out at ten seconds because `QTest.qWait` in its
polling helper starved the Python worker. A separate run using Qt's actual application
event loop prepared twelve files in **0.281 seconds**. Replacing that helper's wait
with Qt event processing plus a short GIL-releasing Python sleep fixed the harness;
the selected files, expectations and model acceptance prompts were unchanged.

The actual application was rendered at 1280 × 800 with image/document cards and
its unavailable-send hint, and the screenshot was inspected. Unnecessary geometry
refreshes on individual preparation results were removed. Dependency and Git
whitespace checks passed. Full native regression passed **2,119 tests and 15
subtests, with 49 existing skips and no failures, in 251.16 seconds**.

No live model or paid API requests were made. Live attachment qualification remains
deferred to the provider phases; contract doubles do not claim production support.
