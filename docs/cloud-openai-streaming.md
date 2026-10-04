# OpenAI cloud Phase 3.1: streaming, Stop and retries

Implemented on `codex/cloud-openai` in the isolated cloud worktree. Main remains
at `b22b904f792f2d393b7e1ccc19ed483e86d0baf4`. The original checkout, ignored
runtime settings, accepted profiles and acceptance prompts are preserved.

## Contract and implementation

The backend now requests `stream: true` through the pinned `openai==2.54.0`
async SDK. An owned event-loop thread and connection pool preserve the app's
synchronous inference interface. The pool is created lazily, reused between
requests, and released together with its thread on shutdown or key replacement.

[OpenAI's streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses)
defines typed Responses events. The bounded collector checks response identity,
event sequence, message parts and output-item identity; only a complete terminal
response goes through the existing text/tool/replay validators. Arguments and
item-done events never authorize execution. The same pinned OpenCode Responses
protocol supplies terminal-handling patterns; attribution and its original
revision remain in `THIRD_PARTY_NOTICES.md` and the reference lockfile.

Visible text/refusal deltas feed a temporary, throttled plain-text preview in
the existing chat view. Tool arguments, reasoning summaries, encrypted reasoning
and provider error bodies never reach that preview. Final text retains the
existing formatting, completion metadata, permission checks and durable replay.
Automatic skill-selection output is excluded from the preview.

Stop cancels the active async task and terminates its connection, including
pending headers, stream reads and SDK retry sleeps. It also prevents a cancelled
conversation from starting a request after context preparation. Repeated Stop
does not cancel stream cleanup again. Partial visible text survives cancellation
and reopening with an interrupted completion marker; incomplete calls never
execute or become replay evidence. An agent safety deadline remains `timed_out`.

[OpenAI's background guide](https://developers.openai.com/api/docs/guides/background)
specifies connection termination for synchronous responses. The cancellation
endpoint applies to background responses. This implementation keeps `store:
false`, stateless replay and disabled truncation; it does not enable background
responses or server-side conversation storage.

The SDK is the sole owner of retries before the stream opens. Existing
`max_retries: 0` stays unchanged; configured retries remain bounded at five, with
one overall request deadline covering connection, backoff and streaming.
A public async HTTP response hook prevents quota/billing 429 errors from being
retried. Authentication and invalid-request failures remain terminal. A started
stream is never reconnected or automatically replayed, and interruptions cannot
trigger local fallback. Missing terminal events, malformed streams and dropped
connections retain honest incomplete state with unknown usage; final terminal
usage remains authoritative. There is no additional model-pool retry loop.

## Verification

Focused final regression: **294 passed**, zero skipped, in 22.13 seconds. It uses
the real async SDK with mock HTTP/SSE transport and covers pending connections,
stream failures, early/repeated Stop, retry delays, quota exclusions, the overall
request deadline, thread/client release, final replay, tool gating, partial-text
persistence, agent deadlines and temporary UI previews. Existing tools, replay,
conversation, completion-state, agent and UI checks passed alongside these tests.

The first full run recorded **1,633 passed, one failed, 49 skipped and 15 subtests
passed** in 226.46 seconds. The failure was an existing Skill Settings worker
timeout. The isolated UI/streaming recheck passed **78 tests** in 23.12 seconds;
it also verified the preview's final theme styling. The first run remains
recorded as a failure rather than being relabeled as a pass.

Final full regression after the styling fix and isolated recheck: **1,634 passed,
49 skipped and 15 subtests passed** in 200.54 seconds, with zero failures or
errors. The post-verification preservation audit confirms main and the original
checkout/configuration remain unchanged, and all 43 preexisting branch, remote
and tag references retain their original revisions.

The 49 skips comprise 18 legacy OpenRouter pool live gates, 24 opt-in local-model
or live UI gates, and seven host symlink checks. They are separate from the
deterministic passes and the explicit live OpenAI smoke below.

Live Luna smoke used the approved existing key and fixture metadata only, with
the accepted default profile (`none` reasoning effort and temperature 0.1):

- One `filesystem.stat` call completed and reported the fixture's actual size.
- Continuation preserved exact call/result pairing and prior output replay.
- Two responses survived reopening; subsequent no-tool chat executed zero calls.
- Four nonempty text-preview updates arrived across the completed turns.
- A separate synthetic generation was cancelled after eight visible characters;
  it retained partial text and unknown usage rather than claiming completion.
- The SDK client and owned transport thread were released on shutdown.

Only counts, completion kinds, pass/fail results and token usage are in ignored
`state/test-artifacts/cloud-phase31/`. Keys and response contents are excluded
from diagnostics. Durable replay remains confined to the isolated fixture store.
Zero reasoning items were returned in this live smoke; encrypted replay remains
deterministically verified rather than live-qualified. Sol's earlier account
permission limitation and broader live qualification remain Phase 4 gates.
Both profiles remain unqualified. Context/cache policy and timing/token
instrumentation remain Phase 3.2 work.
