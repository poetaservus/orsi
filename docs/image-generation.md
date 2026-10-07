# Native cloud image generation

This port uses the Responses API image tool through O.R.S.I.'s existing OpenAI
connection. Chat profiles, sampling, local model selection and acceptance prompts
are unchanged. Runtime image choices belong under ignored `state/`.

## Delivery and verification

Each subphase uses a bounded `codex/image-generation-*` branch from local main.
Focused checks precede a repository-local full suite. Live gates are recorded
separately and an unavailable account/model is never a passed image check.

| Subphase | Scope | Verification |
| --- | --- | --- |
| 1A | Separate image model, size, quality and format settings | 58 focused; 2,297 full-suite tests and 15 subtests passed, 58 optional gates skipped |
| 1B | Native tool, image streaming events, image-only responses | 115 focused; 2,307 full-suite tests and 15 subtests passed, 58 skipped; live generation blocked by account access |
| 2A | Original-resolution storage and assistant association | 76 focused; confirmation passed 2,307 full-suite tests and 15 subtests, 58 skipped |
| 2B | Chat and viewer editing from original sources; settings dialog | 61 focused; 2,310 full-suite tests and 15 subtests passed, 58 skipped; live edit blocked by image-model access |
| 3A | Cached grainy drifting placeholder | 51 focused tests and 5 subtests; confirmation passed 2,312 tests and 15 subtests, 58 skipped; synthetic visual reviewed |
| 3B | Aspect ratio, fade, thumbnails, viewer and save | 76 focused tests and 5 subtests; 2,314 full-suite tests and 15 subtests passed, 58 skipped; synthetic UI and viewer reviewed |
| 4A | Failure, cancellation, manual retry and deduplication | 136 focused tests; confirmation passed 2,328 full-suite tests and 15 subtests, 58 skipped |
| 4B | Acceptance and live generation/edit verification | Pending |

On 7 October 2026 the authorized account could retrieve GPT-6 Luna, while
GPT-6.1 Sol and the queried image model IDs returned 404. Model catalog access
does not prove tool access. Two small native image requests through GPT-6 Luna,
using GPT Image 2.5 Flare and GPT Image 1 respectively, returned HTTP 403 with
`model_not_found`. No image was produced. These are failed live access checks,
not deterministic failures. Keys, provider bodies and prompts are absent from
the diagnostic reports.

References: [image generation](https://developers.openai.com/api/docs/guides/image-generation),
[native image tool](https://developers.openai.com/api/docs/guides/tools-image-generation).

Phase 2A's first native full run recorded 2,306 passed and one failure in the
unchanged agent-runtime 30 ms cancellation test: the timer cancelled before its
blocked capability had started. An isolated recheck cancelled before model entry
instead. The complete 32-test runtime group then passed. These failures remain
recorded separately from the subsequent full-suite confirmation; runtime behavior,
the test and acceptance prompts were not changed to pass them.

Phase 3A's first native full run recorded 2,311 passed and one Windows access-denied
directory rename in the unchanged skill-reference-reader depth-limit test. This
is retained as a failed run; the placeholder and the reader implementation were
not changed to hide it. Native recheck and full confirmation are separate evidence.

Phase 4A's first full run recorded 2,327 passed and one unchanged Skill Settings
folder-preview install worker timeout. Its complete nine-test native UI group
passed on recheck. The failed full run is retained separately; neither the
existing worker nor its acceptance test was changed to pass the recheck.

Image generation has no automatic POST retry, even when chat SDK retries are
configured. A started image stream is never replayed. Its mainline output budget
is bounded at the lesser of the existing profile allowance and 4,096 tokens;
image size/quality/format remain separate tool options. Chat request budgets and
sampling are unchanged. Corrupt/incomplete/duplicate results never enter assistant
history. Decoder handles are explicitly released before failed-draft cleanup.
