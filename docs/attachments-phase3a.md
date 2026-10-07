# Attachment input: phase 3A local text documents

The + composer can now send local text/code files, CSV/TSV/JSON and related text formats,
selectable-text PDFs, DOCX, PPTX and XLSX. Local mode allows one combined attachment
per outgoing message. Each later message may have another file, subject to the active
context window. Attachment-only requests and follow-ups work in chat and native agent mode.
Both the owned llama-server adapter and the Python llama.cpp adapter opt into this support.

Preparation retains phase 2's text-only limitations: no OCR, chart/image/layout reading,
formula execution or recalculation. Extraction warnings travel with the document text.
PDFs containing no selectable text fail before inference; mixed PDFs retain readable pages
and warnings for unread pages. Empty text files remain explicit empty sources. Images still
require [phase 3B's qualified vision model/projector](attachments-phase3b.md), now implemented.
Cloud input remains gated until phase 4,
including follow-ups in a chat with local attachments. Switching back to local resumes use
of retained references. No implicit cloud/local fallback discards attached material.

## Input and admission

Original user text and immutable references remain in conversation JSON; original bytes and
prepared text stay in ignored local state. For the model, each attachment becomes a JSON
record in its owning user message, with ID, filename, SHA-256, extraction summary, warnings
and full text. The surrounding label identifies attached source material as data without
permissions or instruction authority. Names/source contents never enter the system prompt,
tool catalog, skill activation or host-root configuration. Skills remain manually selected.
These labels guide the model; they do not guarantee that arbitrary models resist prompt injection.
The existing capability validation, permission gates and approval requirements remain in force.

The service clears its text cache at turn start, then loads and verifies references on the
conversation worker with cancellation. Foundation-era snapshots without prepared caches
are prepared from their app-owned copies; corrupt existing caches fail visibly. Old PDF
caches lacking readable-page counts are regenerated from verified original copies. Original
selected paths are never reopened. New session clears the cache; archives and reopened
conversations resolve the same immutable stored sources.

A scoped counting adapter renders the full source representation through the existing
backend tokenizer/accounting path. Filenames or reference sizes are never substitutes for
document content. Budget components include source labels, warnings and existing reply,
tool-schema and safety reserves. The native adapter uses its existing idle-server tokenization
and offline UTF-8 estimate; this remains an estimate with wrapper headroom, not a new exact
native chat-template counter. Python llama.cpp uses its existing GGUF template/tokenizer.

Context selection operates on reference-bearing messages while counting rendered text.
This preserves atomic attachment turns: an oversized current attachment stops visibly and
is retained as a stopped turn, rather than sending a truncated file or omitting the request.
The existing policy for older history/recovery remains unchanged. Only selected messages
are rendered before transport. Native tool continuations keep that rendered user message
and paired call/result history; they do not re-inject duplicate document bodies.

The composer shows specific unsupported-input errors and retains text/selection for image
and cloud gates. A known local capability hint makes these preflight checks independent
of heavyweight model loading. Actual document verification/extraction and token admission
run on the conversation worker. Worker-time failures such as context overflow appear as
stopped turns; broader retry/draft recovery belongs to phase 5.

## Verification

Focused native checks passed **160 tests in 15.18 seconds**. The 28 new deterministic
cases cover actual text/code/CSV/JSON/PDF/Office bytes, attachment-only/empty files,
local per-message counts, multiple files across turns, follow-ups, reopening and archives,
native paired tool continuations with recovery on/off, source/skill/host-policy separation,
complete-source token counting, current-turn overflow and atomic older-turn selection,
corrupt/missing snapshots and caches, legacy PDF cache upgrades, scanned-PDF rejection,
image gating without model loading, cloud switch/fallback guards, cancellation, both real
adapter transport boundaries, and Qt composer dispatch/draft preservation.

The opt-in accepted 14B live smoke passed **in 57.67 seconds** using isolated synthetic
files and the existing production catalog. It verified text input, plain follow-up,
reopened-history recall, selectable PDF input, and a real `filesystem.stat` call followed
by a response using the attached document. Its six physical requests reported input
counts of **833, 884, 914, 1,135, 3,837 and 4,157 tokens**. The agent requests advertised
the production twelve-tool catalog; the first finished with `tool_calls`, the continuation
with `stop`. Actual context was **16,384**, output reserve **4,096**. Versioned profiles
were unchanged, the test-owned native process exited, and dependency/whitespace checks passed.
Only numeric metadata and fixed outcomes enter the live summary; no keys or source contents
are copied into diagnostics. Synthetic conversation evidence stays in ignored test state.

The first live smoke used a restricted one-tool test catalog. All four document/recall
checks passed, but the model answered from the attachment and declined the requested stat
without an exact path, so that continuation gate failed. Rechecking with the app's existing
production catalog and isolated acknowledged read scope passed the **unchanged tasks**.
No acceptance prompt, routing, tool implementation, sampling or context policy was changed
to obtain that result; the restricted-catalog failure remains separate evidence of model behavior.

Final full native regression passed **2,147 tests and 15 subtests, with 50 skips and
no failures, in 316.34 seconds** after the context-outcome classification cleanup.
The initial full run also passed the same totals in 336.25 seconds. Of the skips,
49 are pre-existing optional live
gates and one is this phase's opt-in smoke (run separately above). Native vision, cloud
attachments, per-model live matrices and visual/OCR interpretation are not qualified by
these checks.

A subsequent generic “read this PDF” request revealed that the model could still look for
the original filename despite successful extraction. The
[attached-document grounding repair](attached-document-grounding.md) adds scoped trusted
source guidance and verifies the natural request with both synthetic and actual PDFs.
