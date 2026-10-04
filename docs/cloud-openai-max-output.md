# Luna maximum output allowance, 4 October 2026

This records the maximum-output change and its original verification. The later
[maximum-input update](cloud-openai-max-input.md) expands the active cloud input
budgets separately; the output allowances recorded here remain current.

The user's normal cloud app reached the 16,384-token output limit during native
tool generation. Content-free diagnostics recorded 6,012 input tokens, 16,384
output tokens, zero reasoning tokens and an incomplete response after 85.609
seconds. Its tool call was correctly withheld from execution.

The user requested the highest supported output allowance. OpenAI's
[Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna),
retrieved on 4 October 2026, specifies 128,000 maximum output tokens and a
1,050,000-token context window. One million output tokens in a single Luna
response is unsupported; the context window is a separate combined budget.

| Setting | Previous | Current |
| --- | --- | --- |
| Luna output allowance | 16,384 | 128,000 |
| Luna effective application context | 45,056 | 156,672 |
| Luna input allowance | 28,672 | 28,672 |
| Shared Responses request deadline | 180 seconds | 1,800 seconds |
| Maximum stream events | 65,536 | 262,144 |
| Maximum accumulated stream event bytes | 32 MiB | 64 MiB |

The application context grows by exactly the output allowance increase. Explicit
Responses profiles now reserve the entire requested output allowance, including
when it exceeds half the effective context. This keeps the existing input budget
and 256-token admission margin consistent with the actual request. Local and
legacy context accounting retain their existing half-context clamp.

The finite 30-minute deadline covers connection, SDK retries and stream reads.
Stop still cancels the active request immediately. The larger stream bounds
allow token-sized deltas beyond the old event cap without removing protocol
bounds or checks for valid sequence, identity and successful terminal completion.
Incomplete tool calls remain unexecutable.

Sol's profile, qualification flags, prompts, routing, reasoning, temperature,
retry count and tool permissions are unchanged. The native file-write limit is
still 65,536 UTF-8 bytes and 1,000 lines per call. A larger model output allowance
does not enlarge that separate file-write capacity or guarantee a complete answer.

## Verification

All 247 focused checks passed, including the OpenAI adapter, native tools,
streaming, cancellation, replay, selection, qualification contracts and affected
context tests. A typed-SDK stream fixture completed 128,000 separate text deltas
and accepted its successful terminal event; excessive continuation still fails.
The checked-in request uses the full 128,000-token cap and 1,800-second deadline.
Oversized input is rejected with the complete output reserve accounted for, and
an incomplete native tool call at the maximum cap remains rejected.

Two short synthetic live Luna requests completed with the actual wire setting
`max_output_tokens=128000`; each generated five output tokens. An isolated real
Qt selector switched to Sol (32,768 context / 4,096 output) and back to Luna
(156,672 context / 128,000 output), preserving the fixture conversation and
verifying the exact output reserves. The SDK client, owned request thread and
in-memory key were released; no local model process was created. These checks
verify that the API accepts the configured cap, not a live 128,000-token generation
or a fresh qualification pass. The user's conversations and runtime selection
were not replaced with fixture state.

The normal embedded runtime's SDK transport/pin/cleanup check also passed with
OpenAI 2.54.0 and Qt 6.11.1. Content-free reports and test results are retained
under ignored `state/test-artifacts/cloud-max-output/`.

The full Windows regression passed 1,704 tests and 15 subtests in 239.574
seconds, with 49 existing skips and no failures. The previously intermittent
Skill Settings worker test passed in this run. Skipped live/local-model/host
gates remain skips; earlier qualification failures are not relabeled as passes.

## Integration and recovery

The bounded change starts from local main `a4aba0c` on
`codex/cloud-max-output`. Before edits, configuration copies and ref/worktree
maps were preserved under ignored `state/backups/cloud-max-output-20261004/`;
the all-ref recovery bundle was independently verified. The merged local feature
branch is removed after fast-forwarding main. Other active checkouts and the
detached cloud test checkout retain their existing heads and independent state.
