# Luna output-budget adjustment, 4 October 2026

This records the initial 16,384-token adjustment and its historical checks.
The later [maximum-output update](cloud-openai-max-output.md) supersedes the
active Luna allowance with 128,000 tokens and records its separate verification.

A user frontend-generation request stopped before executing its incomplete tool
call. Content-free diagnostics recorded `finish_reason=length`, 5,750 input
tokens, exactly 4,096 output tokens, zero reasoning tokens, one request and zero
settled calls. Its API request lasted 30.813 seconds. This was the configured
output limit, rather than the 90-second timeout or a model-access error.

OpenAI's [token-counting guidance](https://developers.openai.com/api/docs/guides/token-counting)
explains that output limits cover generated tokens beyond visible reply text.
File content sent as native tool arguments must fit that output allowance. The
[Luna model contract](https://developers.openai.com/api/docs/models/gpt-6-luna)
allows a larger output than this application's inherited 4,096-token cap.

Only the versioned cloud budget is adjusted:

| Setting | Before | After |
| --- | --- | --- |
| Luna output reserve | 4,096 | 16,384 |
| Luna application context | 32,768 | 45,056 |
| Luna input budget | 28,672 | 28,672 |
| Cloud request timeout | 90 seconds | 180 seconds |

The input budget remains unchanged; context grows by exactly the additional
12,288-token output reserve. The shared request deadline allows longer generation
while retaining a finite timeout. Sol's profile remains unchanged. Prompts,
routing, sampling, context estimation/projection, retry count, tool behavior and
permissions remain unchanged. Truncated calls still cannot execute. Neither
profile is marked qualified.

## Verification

Focused checks: 193 passed. New real-SDK fixture checks exercise a complete large
native write call, the checked-in budget/deadline, and rejection of incomplete
calls even with the larger cap. Existing native tools, streaming, cancellation,
model selection, context and qualification checks also passed.

A separate live synthetic fixture completed a native write with **9,110 output
tokens**, followed by a completed 16-token final response. Its two request inputs
were 9,981 and 19,327 tokens. One exact fixture-path write approval was granted;
all 220 supplied HTML sections were written. The model omitted the requested
final newline: 33,483 bytes were written versus 33,484 requested. Thus the live
check's byte-for-byte assertion failed even though both responses completed and
all HTML lines matched. That failed assertion remains in the original report;
it is separate from the verified output-cutoff fix and is not a qualification
pass. No prompts or sampling settings were changed to hide the omission.

The live fixture switched to Sol and back to Luna without clearing its history,
verified each profile's effective limits, and released the session key, SDK
client and owned transport thread. It did not make a Sol request or resolve
Sol's existing API permission blocker.

The existing full suite recorded **1,700 passed, 1 failed, 49 skipped and 15
subtests passed**, in 233.96 seconds. The failure was
`test_enter_previews_local_file_then_install_refreshes_picker_without_restart`:
the Skill Settings install worker exceeded its test wait. An isolated recheck
recorded 6 passed and the same failure. A source snapshot of pre-change commit
`2dc6963` also reproduced that failure with 6 passed. Its implementation and test
are unchanged in this bounded budget fix. The full suite is not reported as
passing; the unrelated pre-existing worker issue remains open.

Reports are under ignored `state/test-artifacts/cloud-output-budget/`. Prior
Phase 4.1/4.2 live evidence describes the old profile; this adjustment does not
promote it to qualification of the new budget. Main and the original application
remain preserved. Restart the separate test app to load the new versioned limits.
