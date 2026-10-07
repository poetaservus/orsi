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
| 1A | Separate image model, size, quality and format settings | 58 focused; 2,297 full-suite tests and 15 subtests passed, 58 checks skipped |
| 1B | Native tool, image streaming events, image-only responses | 115 focused; 2,307 full-suite tests and 15 subtests passed, 58 skipped; live generation blocked by account access |
| 2A | Original-resolution storage and assistant association | 76 focused; confirmation passed 2,307 full-suite tests and 15 subtests, 58 skipped |
| 2B | Chat and viewer editing from original sources; settings dialog | 61 focused; 2,310 full-suite tests and 15 subtests passed, 58 skipped; live edit blocked by image-model access |
| 3A | Cached grainy drifting placeholder | 51 focused tests and 5 subtests; confirmation passed 2,312 tests and 15 subtests, 58 skipped; synthetic visual reviewed |
| 3B | Aspect ratio, fade, thumbnails, viewer and save | 76 focused tests and 5 subtests; 2,314 full-suite tests and 15 subtests passed, 58 skipped; synthetic UI and viewer reviewed |
| 4A | Failure, cancellation, manual retry and deduplication | 136 focused tests; confirmation passed 2,328 full-suite tests and 15 subtests, 58 skipped |
| 4B | Acceptance, application restart and live verification | 139 image checks and 157 startup/native checks passed; final confirmation passed 2,332 tests and 15 subtests, 58 skipped; live generation, restart, edit and transport release passed |

On 7 October 2026 the authorized account could retrieve GPT-6 Luna, while
GPT-6.1 Sol and the queried image model IDs returned 404. Model catalog access
does not prove tool access. Two small native image requests through GPT-6 Luna,
using GPT Image 2.5 Flare and GPT Image 1 respectively, returned HTTP 403 with
`model_not_found`. No image was produced. These are failed live access checks,
not deterministic failures. Keys, provider bodies and prompts are absent from
the diagnostic reports.

The final application-pipeline live gate on the same date passed generation,
restart and editing through GPT-6 Luna with GPT Image 2.5 Flare at low quality.
It produced an actual image, retained its original bytes across reopening,
edited that source, and released the transport worker. This supersedes the
earlier access probes for application acceptance; catalog retrieval and the
earlier standalone requests were insufficient evidence of native tool access.
The earlier failures remain recorded separately. The content-free final summary
is retained under `state/image-generation-live-final/summary.json`.
The live gate passed again after binding reuse; its confirmation is retained at
`state/image-generation-live-confirm/summary.json`. The actual saved result was
also reopened and visually inspected in O.R.S.I.'s chat and fullscreen viewer.

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

Phase 4B's first full run recorded 2,328 passed and three Skill Settings install
worker timeouts. The nine-test recheck and a separate scheduling experiment each
recorded seven passed and two timeouts; an isolated thread-stack diagnostic also
timed out. No passing full suite is inferred from these failed runs. The worker
was actively rebuilding Windows DLL function bindings during protected reads.
The same snapshot code handles original image attachments. A controlled 1,000-call
benchmark took 0.032 seconds normally but 15.0 seconds during Qt's timed wait.
Reusing the immutable binding table reduced both measurements below 0.01 seconds.
File identities, opened handles, permissions, snapshot verification, acceptance
prompts and test deadlines remain unchanged. The 184-test native snapshot/UI
recheck passed with default scheduling, with four unsupported symlink checks
skipped. Final confirmation runs are recorded separately below.

The next default-scheduling full run passed the Skill Settings group, but
recorded 2,329 passed, two unrelated native rename/cleanup failures and one
related cleanup teardown error. These remain failed results. The complete
discovery/Git-installer groups passed in the subsequent 157-test startup/native
recheck. This recheck also verified the actual application bootstrap: chats
containing generated images resume after restart so their originals are visible
and editable; the existing non-image startup and explicit New Session checks
continue to pass. No acceptance deadline or prompt was changed.

The final complete run, including application restart restoration and binding
reuse, passed 2,332 tests and 15 subtests in 416.90 seconds with default thread
scheduling. Its 58 skips comprise 51 opt-in legacy-cloud/local-model/live-capacity
qualifications and seven unsupported symbolic-link scenarios. They are distinct
from the passed native image live gate. Exact skip reasons are retained in
`state/image-4b-final-suite.txt`; failed runs and native rechecks remain alongside
it. All eight implementation subphases were verified and integrated into main.

Image generation has no automatic POST retry, even when chat SDK retries are
configured. A started image stream is never replayed. Its mainline output budget
is bounded at the lesser of the existing profile allowance and 4,096 tokens;
image size/quality/format remain separate tool options. Chat request budgets and
sampling are unchanged. Corrupt/incomplete/duplicate results never enter assistant
history. Decoder handles are explicitly released before failed-draft cleanup.

## Using the feature

Select cloud mode and a compatible Responses model. Open **Settings → Image
generation…** to choose the separate image model, size, quality and format. The
dialog stores runtime choices in `state/image_generation_v1.json`; it does not
alter the accepted chat profile. The account must have access to the selected
image model.

Ask to draw, create or edit an image, or use `/image` followed by a prompt. Image
analysis continues through the existing chat path. A generated image can be
edited with a follow-up such as “make the background darker”; reopening the chat
restores its originals and preserves that source for the next edit. Click a
result to open the fullscreen viewer, choose this image or all images for a
follow-up, or save the original encoded file.
Conversations containing generated images resume on application restart.
Use New Session to clear the conversation when you want to start again.

The placeholder uses cached visual layers and a 14-second drift cycle, pauses
when hidden, and fades into the decoded image over 650 ms. Stop and failed
requests leave a clear inactive frame and restore the prompt for manual retry.
An image POST is never automatically retried or replayed after streaming starts.

## Opt-in live gate

Run `runtime/python/python.exe tools/verify_image_generation.py --key-file
<local-key-file> --output state/image-generation-live`. Only the first line of
the key file is used. This makes a small low-quality image request, reopens the
saved chat, edits the original, and checks transport release. The summary holds
only statuses, counts and failure categories. It excludes credentials, provider
bodies, prompts and image bytes. The private local chat and attachment store
hold the actual artifacts. A failed generation skips restart/edit checks and
returns a failing exit status.
