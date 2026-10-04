# OpenAI cloud Phase 3.2: context, caching and numeric measurements

Implemented on `codex/cloud-openai` in the isolated cloud worktree. Main remains
at `b22b904f792f2d393b7e1ccc19ed483e86d0baf4`. The original checkout/settings,
accepted profiles, prompts, routing, permissions, tool limits and sampling stay
unchanged. Both profiles remain unqualified pending Phase 4.

## Context and cache handling

The cloud context counter now sees original structured messages. It estimates
Responses input items directly, counting provider replay once, handling UTF-8
bytes and reserving opaque encrypted evidence separately. The final request also
checks the selected profile's input allowance with its existing output/safety
reserves before sending. Estimates are offline admission heuristics, not exact
provider counts or a tokenizer for decrypted reasoning.

Fitting cloud histories remain unchanged, preserving reusable prefixes. Under
pressure, enabled context recovery can excerpt large capability results with
the existing explicit omission markers, original-output digest and untrusted
content notice. This changes only the request projection: original settlement
and durable evidence remain complete. Provider output items, encrypted reasoning,
phase fields, argument strings, call IDs, user requirements and system policy
stay intact. Disabled recovery performs no projection. Protected content that
still cannot fit stops admission; the cloud selector no longer silently
truncates an oversized user task. Local context behavior is preserved.

The same model's complete output items and growing history continue to be
appended through stateless replay. Cache routing stays automatic. No cache key,
retention override, prewarming request, provider compaction request, background
response or server conversation is introduced. Normal turns make no extra API
calls for token counting or recovery. `store: false` and disabled truncation
remain unchanged.

These choices follow [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching),
[conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
and [token counting](https://developers.openai.com/api/docs/guides/token-counting).
OpenCode's existing pinned Responses protocol supplies inclusive usage-accounting
patterns; OpenAI documentation and `openai==2.54.0` govern the actual fields.

## Measurements

Completion metadata now retains cache-read, cache-write and reasoning token
subsets when supplied. Missing/invalid detail counts stay unknown; explicit zero
stays zero. Cached input occupies context, and reasoning is already part of
output tokens, so neither is subtracted from or added again to the totals.
Measured context occupancy is invalidated by a model switch even when the
profiles have equal application limits.

Each SDK operation records queue wait, transport duration, time to first valid
stream event, time to first visible text delta, HTTP attempts and a fixed outcome.
Duration includes SDK retry delays and stream cleanup. Tool-only responses have
no first-text measurement. Interruptions retain observed timings with unknown
token usage. Successful/incomplete/cancelled completion metadata survives durable
conversation storage. HTTP failures also have a numeric log/last-request record.

Reports contain counts, elapsed milliseconds and fixed status labels only: no
keys, input/output text, paths, tool arguments, response/request/call IDs, prefix
hashes, reasoning summaries or ciphertext. Metrics do not alter request content,
cache configuration, retry ownership or sampling.

## Verification

Focused regression: **300 passed** in 19.77 seconds, including the existing
cloud, tool/replay, streaming, context, completion, agent and conversation tests.
New checks cover pressure-only recovery, original settled-output preservation,
atomic protected evidence, Unicode/cipher reserves, direct oversized requests,
cache/reasoning subsets, invalid/missing counters, numeric-only logs, reused
connection-pool hooks, retry attempts, cancellation timings, persistence and
equal-limit model switches. No acceptance prompts were changed.

The first full run recorded **1,656 passed, one failed, 49 skipped and 15
subtests passed** in 227.87 seconds. The failure was the existing Skill Settings
worker timeout also recorded during Phase 3.1. Its isolated UI/efficiency recheck
passed **68 tests and five subtests** in 21.11 seconds. The failed run is retained
separately. The 49 skips comprise 18 legacy cloud-pool live gates, 24 opt-in
local-model/live UI gates and seven host symlink checks.

The repeated full suite passed **1,657 tests and 15 subtests**, with **49
skipped**, in 214.91 seconds and no failures or errors. Preservation checks
confirmed that main, the original checkout and configuration, and all 43
historical branch/tag/remote references remained unchanged.

Live Luna used the accepted default profile and the already authorized key and
fixture metadata. One stat completed, exact output replay continued, two
responses survived reopening, and no-tool chat executed zero extra calls. Every
completed operation made one HTTP attempt. Client and transport-thread release
passed. The separately cancelled synthetic response retained partial text,
observed timing and unknown usage.

| Completed operation | Input/output/total tokens | Cache reads/writes | Duration / first text (ms) |
| --- | --- | --- | --- |
| Fixture stat request | 3009 / 73 / 3082 | 2940 / 66 | 3734 / unknown (tool only) |
| Result continuation | 3303 / 11 / 3314 | 3006 / 294 | 1453 / 1328 |
| Reopened no-tool chat | 3333 / 7 / 3340 | 3300 / 30 | 890 / 718 |

These are individual observations, not a latency guarantee or controlled
before/after benchmark. Cache availability is provider-dependent. Reasoning
counts were zero and no reasoning items were returned, so encrypted reasoning
remains deterministically tested rather than live-qualified.

A **separate diagnostic** used the official input-token-count endpoint on the
same first fixture request: **3009 actual input tokens versus 6097 estimated**.
This confirms that this sample was admitted conservatively; it does not prove
an exact or universal bound for other text, tool schemas or encrypted evidence.
The endpoint is not called in normal app turns. Broader calibration, Sol access,
model qualification, packaging and migration cleanup remain Phase 4 work.

Ignored results are under `state/test-artifacts/cloud-phase32/`. The key was read
only in memory. Durable replay is confined to the isolated fixture conversation;
content-free reports contain only its counts and verification outcomes.
