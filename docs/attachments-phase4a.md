# Attachment input: phase 4A native cloud transport

Cloud mode accepts multiple supported file/image drafts through +, dropping and image paste.
Native OpenAI Responses inputs contain verified source bytes, never just a display filename.
PNG, JPEG, WebP and still GIF use `input_image`; text/code, PDF, DOCX, PPTX, XLSX and CSV/TSV
use `input_file`. PDF processing includes selectable text and page visuals, including scanned
pages. Other documents supply text rather than embedded charts/images. Native spreadsheet
processing may summarize only the first 1,000 rows per sheet; guidance and draft warnings make
this limitation explicit. Local extraction, manual model/skill selection and the one combined
local attachment per outgoing message remain unchanged.

## Source and continuation contract

The existing immutable snapshot store remains authoritative. Source metadata, size and SHA-256
are verified before native transport; the original selected path is never reopened. Ordered
references remain in durable conversation JSON and agent transcripts. Only selected transport
requests become inline base64 data. Native user input retains source order through follow-ups,
reopened histories, archives and paired native call/result continuations. Provider response
items/encrypted reasoning retain the existing model binding and replay protections.

Attachments are source material under the user role. They do not activate a skill, grant file
or tool permissions, become system instructions, or change the selected model. The shared native
transcript validator permits raw references only when explicit native attachment tool support
is enabled. Local/generic adapters still reject those references until their established local
source projection. Existing tool permissions, journal authority and incomplete-call rejection
remain in force. Attachment failures never trigger a fallback that drops source material.

Cloud file preparation verifies the source without local text extraction. It does not overwrite
or create an empty local prepared cache, preserving later local document reads. Image thumbnails
use existing validated Qt still-image decoding. Actual bytes remain the original snapshot.
Inline transport, disabled response storage and stateless replay avoid durable provider file IDs
and Files API uploads; no upload resource cleanup or credential persistence is introduced.

## Context, pacing and cancellation

The UI/context meter remains offline. Document byte size and image dimensions provide estimates;
compressed-document extraction is not claimed to have an exact offline token mapping. The worker
uses the pinned SDK's Responses input-token count endpoint with the same native source input,
reasoning settings and strict tool schemas as generation. The actual count, profile input ceiling,
existing output reserve and safety buffer gate generation. No base64-as-text token count is used.

The counting request runs through the owned cancellable async transport and account request
pacing. Its result is not generated model output. Actual generation tokens determine the existing
generation reservation. Count failures/invalid counts, cancellation, altered snapshots and size
limits stop before generation; a started generation stream retains existing interruption rules.
Errors and request measurements omit keys, source bytes, filenames/paths and response bodies.
The API key supplied for qualification was read from the user-authorized file's first line only
and held in memory; it was not copied into the repository, settings or reports.

Current documented transport ceilings are enforced: each file below 50 MB, files combined at most
50 MB, at most 1,500 images, and at most 512 MB JSON payload. Existing snapshot/image pixel guards,
offline admission, active profile limits and account rate limits can be stricter. These are boundary
guards, **not a claim that maximum capacity is qualified**. Phase 4B remains responsible for actual
maximum-capacity qualification and refinement. Phase 5 remains broader context/recovery, cleanup
and end-to-end lifecycle verification.

## Official source basis

- [File inputs](https://developers.openai.com/api/docs/guides/file-inputs): native base64 input,
  document types, PDF page processing, non-PDF visual limits and spreadsheet augmentation.
- [Images and vision](https://developers.openai.com/api/docs/guides/images-vision): native still
  image inputs and current image/request ceilings.
- [Counting tokens](https://developers.openai.com/api/docs/guides/token-counting): exact multimodal
  input counts using the same input format as Responses generation.

The existing OpenAI SDK version, cloud model profiles, reasoning/sampling, default local mode,
local GPU/CPU behavior, context recovery policy and runtime step budgets are unchanged.

## Verification

Expanded native deterministic checks passed **326 tests** in **16.301 seconds**, covering native
SDK request shapes, exact original bytes, offline accounting without network/base64 work,
multiple sources, follow-ups/reopening/archives, real native tool continuations, allow/deny/ask
permissions, source tampering, cancellation, unsupported types and request bounds. The existing
cloud replay/context tests and local document/image regressions passed in that group.

Initial deterministic failures exposed optional admission delegation to thin test adapters and
a composer ordering fixture still intercepting the former local extractor. Optional delegation
was corrected, and that fixture now delays native cloud preparation. New fixture errors were
corrected without changing acceptance prompts or production tool policy.

The first live batch recognized images, PDF/text/CSV and a scanned PDF; its minimal parser-only
Word fixture lacked OOXML package declarations, so OpenAI could not extract its text. The fixture
was completed with content types/root relationships; source recognition, follow-up and reopened
recall then passed. The subsequent fixture bootstrap lacked authority matching the production
full-local-read flag. Fixture read authority is now explicitly scoped to its own portable root,
retaining the production catalog/limits and unchanged acceptance requests. No user files were read
or uploaded for these gates.

Final real-cloud qualification passed in **122.078 seconds** on the unchanged default
`gpt-6-luna` profile: seven synthetic sources, scanned-PDF visual reading, two differently
colored images across turns, follow-up/reopened/archive recall and actual `filesystem.stat`
followed by source-aware continuation. The fixture used all **12 production capability
definitions**, actual **1,050,000 context** and **128,000 output reserve**. The four turn records
measured input tokens **1,275 / 1,406 / 1,445 / 4,063**, output tokens **50 / 16 / 16 / 16**,
with one actual native capability call in the restored turn. Owned SDK transport/client resources
were closed and the engine's session key cleared. The ignored numeric-only summary is at
`state/test-runs/cloud-attachments-live-3/test_native_cloud_sources_foll0/live-summary.json`.
This qualifies the default cloud profile for these attachment cases; it does not qualify account
access to the other cloud profile, maximum capacities, or existing unrelated live gates.

Final full native regression passed **2,221 tests and 15 subtests**, with **53 optional skips**,
zero failures/errors, in **278.479 seconds**. The new cloud live gate is opt-in and passed
separately; the other optional skips retain their prior qualification status. Compilation,
dependency consistency and Git whitespace checks passed. No accepted profiles, runtime selection
files, user skills, original conversation files or API credential files were modified.
