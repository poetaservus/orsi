# Office routing and stream compatibility, 21 October 2026

## Scope and reproduction

The Word report has a deterministic routing cause. The opening "Open and edit"
instruction was not recognized, Markdown obscured the primary task, and a later
"Create ... photograph" requirement selected image generation before the Office
agent could run. The exact reported prompt is retained unchanged in the new
routing regression fixture and is checked again after conversation persistence.

The Excel screenshot proves `unsupported_event`, but does not preserve the exact
rejected event. The installed SDK and official Responses event reference include
`response.queued`; the old parser rejected it. This is a confirmed compatibility
gap, not retrospective proof that queued caused the reported incident. The old
generic interruption path also falsely implied that an Excel tool call existed
when only answer generation or completion review might have been interrupted.

References: [Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events)
and [API compatibility](https://developers.openai.com/api/reference/overview#backwards-compatibility).

## Changes

Routing establishes an affirmative editable-document deliverable across the
request before interpreting subordinate photography instructions. Classification
normalizes Markdown and preserves literal Office filename cues as data, while
quoted instructions, fenced source and negated document operations remain data.
Document nouns used as modifiers in explicit image requests remain visual;
document topics such as a spreadsheet of sprite coordinates remain document work.
Image-to-editable-document transformations use the agent. Explicit `/image` still
wins, and genuine visual requests work with Word selected. The UI prediction and
worker share the same decision. A semantic presentation selector cannot override
established document intent. The original prompt and attachment bytes are not
rewritten.

The stream parser accepts a bounded queued lifecycle notification only after
creation, with matching identity, queued status, empty output, valid sequence and
before activity. In-progress lifecycle messages are checked too. Unknown output,
bad identity/sequence, invalid terminals and existing resource limits still stop
safely. No stream is automatically reconnected or replayed. A terminal response
is required before function calls can execute.

Optional completion metadata distinguishes reply, completion review and image
generation, and records whether a function call was actually observed. Stream
interruptions have a distinct protocol category. Only observed calls receive the
tool-generation explanation; interrupted reviews retain the proposed answer and
report task completion as unverified. Terminal-only unfinished calls are accounted
for without dispatch. Older histories missing these fields remain readable.

Encrypted-profile logging now retains revalidated structured route and turn
records. Stream diagnostics contain approved public event names or bounded
fingerprints for unknown identifiers, counters, request phase and random local
turn/request correlations. Only the diagnostic labels cross owned model thread
boundaries; unrelated context variables are not propagated. Both native and
constrained fallback review requests keep their phase through the SDK thread.
The existing 200-event cap remains. No prompts, document contents, filenames,
credentials, raw provider payloads or exception text are added to diagnostics.

## Focused verification and limits

Only the directly affected routing, stream, reporting and diagnostic checks plus
selected existing recovery/history regressions run. All pytest temporary paths
are repository-local and the cache is disabled. No full suite, live API/model,
native Office editing, image generation or user-profile decryption is performed.
SDK HTTP responses are mocked; Office entry uses an owned synthetic stdio bridge.
That bridge releases its worker after the test.

The restricted Windows environment blocked asyncio's local socket-pair creation
before mocked HTTP could begin. Those stalled runs were stopped; unrestricted
focused runs are the qualification evidence. No product workaround was added for
the sandbox limitation. An integration run found the spreadsheet-of-sprites
routing regression; the fix preserves the unchanged existing expectation. New
service-correlation fixtures were corrected to use the supported production
catalog and the actual retained-answer presentation behavior.

Final selected checks cover:

- The unchanged Word prompt, real service/SDK routing, Office capability entry,
  source preservation, explicit images, quoted/negated instructions and mixed
  requests.
- Queued text and function streams, exactly-once execution after terminal receipt,
  malformed lifecycle messages, cancellation/limits, unknown events and image
  endpoint boundaries.
- Reply versus review interruption, forbidden review calls, terminal-only calls,
  saved-history reload, native/fallback thread correlation, sanitization and
  bounded diagnostic retention.
- Existing filesystem and Office recovery, completion-review tool restrictions,
  denied prerequisites and null-output context compaction.

The final combined selection passes **355 checks in 47.80 seconds**, with no
failures or skips, using `state/test-tmp/office-routing-stream-final`.

These checks prove route selection and stream/receipt handling, not the quality
of a native Word magazine layout. Entirely non-English document commands continue
through the existing semantic selector unless document intent is established by
the deterministic classifier. Other unknown event types still stop safely. The
exact historical Excel event remains unknown; the repaired diagnostics make
future incidents distinguishable.

## Integration

Work starts from local main `efafc96` on
`codex/office-routing-stream-compatibility`. Keep diagnostics, stream/reporting
and routing in separate commits. Preserve prior main at
`archive/2026-10-21/main-before-office-routing-stream`, fast-forward local main
after verification and remove only the merged feature branch. Settings, model
profiles/sampling, context policy, core/acceptance prompts, Office execution
rules, historical/unmerged refs, other worktrees and remote refs stay intact.
The running app and user documents are untouched; restart Orsi to load the fix.
