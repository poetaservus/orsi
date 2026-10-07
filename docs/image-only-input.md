# Image-only input, 7 October 2026

An image-only message could receive a generic claim that the assistant could not
access or interpret the picture. The reported turn retained one valid image
reference, no written request and no selected skill. A fresh production request
sent the original picture as native visual input to Qwen3-VL 4B with the vision
projector, 12 advertised tools, GPU offload and a 16,384-token effective context.
There was no missing-image transport failure in those checks.

Fresh runs on the previous code also succeeded, so the exact reported refusal
was not reliably reproduced. The prior attachment policy did not specify what
to do when the user supplied only an image. This change addresses that ambiguity
and the model's inappropriate connection between visual input and filesystem
access limitations; it does not claim deterministic control over model replies.

Local and cloud attachment guidance now share a visual-intent instruction. An
image without accompanying text continues a clearly established conversation
task. With no established task, the assistant briefly describes the visible
content and asks what help the user wants. Images remain untrusted source
material. Their contents cannot activate a skill or authorize a computer action.
Explicit prompts, image bytes, user message text, tools, routing, sampling and
model profiles retain their existing behavior. Guidance is transient and does
not rewrite saved messages or thumbnails.

## Verification

- The original picture was identified as a cat with bread in three repaired
  full-pipeline GPU runs, with zero tool calls. Three fresh runs before this
  change also identified it. Content-free measurements remain ignored under
  `state/image-only-check/`; user history, selection and profiles were unchanged
  and owned model processes exited.
- The new opt-in GPU gate passed: three empty-text synthetic image turns
  identified both visible colors, and a later empty-text image followed an
  established request about its left-hand color. No tools or skills were used.
- 145 focused regressions passed, covering local and cloud payloads, immutable
  image sources, source retention, attachment capacity, composer and viewer.
  Cloud payload checks use the real SDK with a simulated HTTP transport; no
  paid cloud model call was made. CPU verification was not used.

The full suite recorded **2,289 passed, one failed, 58 skipped and 15 subtests**
in **369.89 seconds**. Its unchanged Windows state-replacement retry test saw
four attempts instead of three. The first isolated native recheck passed that
test but recorded a separate skill-reader directory-rename denial (116 passed,
one failed). The fresh combined state/reader/registry recheck passed **all 117
tests** in **1.87 seconds**. The full suite is not labeled passing; both denials
remain explicit Windows verification evidence. Other opt-in live model/API
qualification gates are separate from these checks.
