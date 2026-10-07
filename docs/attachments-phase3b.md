# Attachment input: phase 3B local vision

Local image input is enabled for the explicitly selected **Qwen3-VL 4B Instruct Q4_K_M**
and its verified matching F16 projector. The default 14B remains a text/tool model.
Choose the vision model in settings, then use +, image paste or file dropping.
The app never switches models or selects a skill because an image was attached.
Local mode permits one combined file/image per outgoing message; later messages may
attach additional sources, subject to context and transport bounds.

PNG, JPEG, WebP and still GIF work in chat and native agent mode, including image-only
messages, follow-ups, reopened snapshots, archives and paired native tool continuations.
Existing document extraction also works on the vision model. Animated images,
image-only PDFs and embedded Office/PDF visuals remain unsupported by document extraction;
attach a still image separately for visual reading. Cloud attachment sending remains phase 4.
The vision model's existing experimental file-editing qualification is unchanged.

## Qualified resources

The existing model matches Qwen's official release byte for byte. The downloaded projector
is an ignored local resource; configuration records its identity rather than committing weights.
Both are Apache-2.0 resources from
[Qwen's official release](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/tree/1cd86afb9a95c410a6038ab3b40d8b578c892266):

| Resource | Bytes | SHA-256 |
| --- | ---: | --- |
| `Qwen3VL4BInstructQ4KM.gguf` (official `Qwen3VL-4B-Instruct-Q4_K_M.gguf`) | 2,497,281,664 | `66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a` |
| `mmproj-Qwen3VL-4B-Instruct-F16.gguf` | 836,180,256 | `256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331` |

Other checkouts need the matching projector in `models/` from the
[pinned download](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/1cd86afb9a95c410a6038ab3b40d8b578c892266/mmproj-Qwen3VL-4B-Instruct-F16.gguf).
The catalog/native adapter verify both hashes/sizes and compatible Qwen3-VL merger metadata
before starting inference. Identity caches include size, modification and creation timestamps.
Changed resources are reverified; missing/altered/incompatible resources fail a requested
switch before saving selection. Projectors are not selectable language models.

The existing pinned llama.cpp **b9976/e3546c794** provides
[inline image input and native image token counting](https://github.com/ggml-org/llama.cpp/blob/e3546c794/tools/server/server-context.cpp).
The adapter passes `--mmproj`, `--image-max-tokens 4096`, and `--no-mmproj-offload` on CPU.
The catalog adds **1,468 MiB** for projector/encoder memory to the existing reserve before
resolving context. Sampling, tool catalog/permissions, routing and default 14B targets are unchanged.

## Input handling and accounting

The conversation worker reads verified app-owned still-image copies and decodes them into
orientation-correct lossless PNG transport, without resizing, cropping or OCR. This avoids
differences between Qt's supported formats and native decoding. Composer thumbnails honor
orientation too. Original bytes/SHA-256/references remain immutable in ignored state;
conversation JSON never stores data URLs. Transient caches expire before the next worker
admission. Retained originals are verified; images decode when history is projected.

Native user content contains typed text/image parts. Image bytes/display filenames never
enter system/tool/skill policy. Scoped trusted guidance identifies already-supplied visuals
as source material. Protocol validation rejects remote URLs, paths, invalid encodings,
unknown fields and images in privileged roles. Existing permission gates still protect tools.
The Python local backend remains explicitly unqualified for image input.

Source and lossless PNG transport each have a **16 MiB per-image** ceiling, in addition to
preparation's **40 million pixel** bound. Encoded native requests are bounded to **64 MiB**.
Binary transport has its own ceiling; existing transcript limits still cover all message text
and structured calls/results. Oversized/invalid sources fail visibly and never disappear silently.
Unsupported model/mode checks preserve the composer draft.

Context selection counts projected images while keeping source-reference turns atomic.
The pinned `/v1/chat/completions/input_tokens` route counts actual image patches without
encoding images or generating a reply. Counting uses an idle owned server and never starts
one; actual worker admission/explicit model switching prepares it. Cache keys are hashes only.
Offline/failed counts reserve the enforced 4,096-token image ceiling plus 64 wrapper tokens
per image, alongside text and normal output/schema/safety reserves. Structured tool history
keeps the existing serialized-text estimate; overall admission remains an estimate with
headroom rather than exact native tool-template accounting. Current oversized attachment
turns stop intact. Existing recovery compacts permitted assistant/tool text while preserving
image parts, user requirements and native call/result pairing.

## Verification

Focused checks passed **235 tests in 12.26 seconds**: prepared formats, original pixels/bytes,
image-only and multiple turns, document/image coexistence, reopen/archive replay, manual
skill/model behavior, native continuations with recovery on/off, current-turn overflow,
corruption/cancellation, inline schema restrictions, separate binary/text limits, native
count transport and hash-only caches, offline patch bounds, GUI gating/dispatch, projector
identity/metadata failures, memory reserves and GPU/CPU launch flags. Existing document,
protocol, runtime, context, default-model and UI checks are included.

The real GPU gate passed shape/color order, different images across turns, follow-up recall,
reopened/archive recall, PNG/JPEG/WebP/still-GIF input and actual `filesystem.stat` followed
by image reading with the unchanged production twelve-tool catalog. Ten completions finished
normally; the native tool request used `tool_calls`, followed by a `stop` continuation.
The real **14B → vision → 14B** switch checked server-reported context **16,384** and reply
reserve **4,096**, unchanged 14B sampling, unchanged versioned profiles/user selection,
GPU allocation within the memory guard and released owned servers. Observed allocations
were **9,873 / 6,097 / 9,873 MiB**, below estimates **11,827.21 / 7,653.91 / 11,827.21 MiB**.

The separate real CPU vision gate passed in **19.89 seconds** with server-reported context
**4,096**, reply reserve **1,024**, CPU model/projector placement, correct synthetic visual
interpretation and released owned process. This qualifies bounded CPU image chat; the smaller
context may reject larger sources/full tool catalogs. Content-free summaries are in ignored
`state/test-runs/vision-live-2/` and `state/test-runs/vision-cpu-live/`.

The first GPU run passed all visual/history/format checks but stopped at an incorrect test-only
host-policy constructor before the tool gate. Correcting that fixture and rerunning unchanged
requests passed. Restricted-shell attachment tests hit Windows ancestor-handle denials;
native checks are separate product evidence. Optional live gates remain separate from the
passed vision gates.

The first full native run had **2,187 passes, 52 skips, two failures and one teardown error**
in **264.70 seconds**. One startup fixture used the older optional-field shape; startup now
treats vision configuration as optional. The other failure/teardown was an existing skill Git
installer temporary-directory cleanup denial. The second full run had **2,188 passes, 52 skips
and one failure** in **255.32 seconds**: a native skill-reference fixture's immediate rename
hit Windows access denial. Neither skill installer nor reference-reader implementation was
changed. The startup/installer/image recheck passed **147 tests in 24.01 seconds**; the complete
unchanged reference-reader/installer handle-release groups passed **133 tests in 17.73 seconds**.
Direct native image-counter boundary checks also passed **44 tests in 1.92 seconds**.

The final full native regression passed **2,189 tests and 15 subtests, with 52 optional
skips and no failures, in 259.39 seconds**. Fifty skips are existing optional gates;
the two new GPU/CPU vision gates were run and passed separately above. Dependency,
compilation and whitespace checks passed. Pre-change Git history is preserved in the
verified ignored bundle `state/backups/local-vision-input-20261007/all-refs-before.bundle`;
prior main is tagged `archive/2026-10-07/main-before-local-vision-input`.
