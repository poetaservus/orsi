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
| 2A | Original-resolution storage and assistant association | Pending |
| 2B | Chat and viewer editing from original sources | Pending |
| 3A | Cached grainy drifting placeholder | Pending |
| 3B | Aspect ratio, fade, thumbnails, viewer and save | Pending |
| 4A | Failure, cancellation, manual retry and deduplication | Pending |
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
