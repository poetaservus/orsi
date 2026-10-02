# Provider response normalization and recovery, 2 October 2026

Starting integration revision: `c2908f8f71dcc187d388db31c8e82bc8beb360c5`.
Bounded repair branch: `codex/provider-response-recovery`; fast-forwarded into local `main` after verification.

## Diagnosis and comparison

ORSI rejected ordinary assistant text alongside native calls as a mixed-response protocol error.
The runtime also rejected multiple calls unless one capability explicitly opted into that batch
size. Neither restriction established execution authorization. A cumulative format-error count
could terminate a long task even after successful intervening operations; argument-schema
corrections had no separate budget. Switching to constrained fallback could perform a second
model request without accounting for it independently.

OpenCode's [session processor](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts)
handles text parts and tool parts within the same assistant message, tracks each tool's state,
and persists each completion or error individually. This comparison uses the upstream source
read on 2 October 2026. ORSI keeps its existing sequential executor and exact approval policy
while accepting that ordinary provider response shape. It does not adopt OpenCode's concurrent
execution policy or increase model memory/output limits.

## Resulting contract

- Complete assistant text may accompany validated native calls. Its original whitespace is
  retained in continuation and durable traces, once on the first settled call of the response.
  Restored history still includes the text when tools are disabled. Constrained fallback conversion
  retains both the prior call and its accompanying text.
- Calls are processed in provider order, including different advertised capabilities. Each goes
  through its own registry/schema validation, resource policy, bound approval and journaled
  execution. Assistant prose cannot confer approval. No parallel execution is introduced.
- The existing 16-call response ceiling, 32-call turn ceiling, duplicate-call protection,
  transcript limit and unknown-mutation review barrier remain enforced. A terminal stop retains
  earlier settlements and does not execute later calls. A denied operation returns a denied
  result; subsequent calls still require their own authorization, as before.
- Incomplete generation is rejected before decoding/repair and never becomes executable.
  Malformed envelopes, duplicate IDs and unadvertised names remain rejected.
- Legacy `max_calls_per_batch` catalog metadata stays readable but no longer controls response
  acceptance. Existing configuration, capability visibility, acceptance prompts, model profiles,
  selection, sampling and permission rules were not changed.

## Recovery budgets

| Limit | Effective default | Meaning |
| --- | ---: | --- |
| `max_protocol_failures` | 2 | Consecutive format failures; valid response shapes reset the streak. The existing configuration key is retained. |
| `max_semantic_corrections` | 4 | Cumulative correction events: unknown catalog names, schema-invalid arguments, required-plan deviations, or runtime filename clarification. Valid intervening operations do not replenish this budget. |
| `max_model_requests` | 32 | Total inference-boundary request attempts, including native-to-constrained fallback and failed attempts. No reset after progress. |
| `max_steps` | 24 | Existing total loop-step bound, including seeded required plans. |
| `max_capability_calls` | 32 | Existing total submitted-call bound, checked before accepting a response's call set. |

The exhaustion event is retained and stops before another correction/model request or later
batch call. Tool/environment failures such as missing files and policy denial remain ordinary
settled results rather than malformed-response strikes. Filename clarification itself consumes
a semantic event. Existing timeout, repeated-call and transcript limits further bound work.
Provider-internal network retries/model-pool attempts retain their own existing adapter bounds;
`model_requests` counts runtime-to-inference invocations, not each internal HTTP request.

Durable outcomes record `model_requests`, `consecutive_format_failures`, and
`semantic_corrections`. Existing `protocol_failures` remains a cumulative rejected-response
statistic, including unknown-name responses; it is no longer the streak that controls stopping.
Older saved outcomes load with zero defaults for the added counters.

## Verification

Focused suite: **189 passed**. It covers independent approvals/denials in heterogeneous responses,
preserved text and results after a later model failure and restart, format-streak reset,
separate schema/name correction limits, bounded native-to-fallback requests, mid-batch exhaustion,
and the prior incomplete-generation and stopped-turn regressions.

Full suite: **796 passed, 54 skipped, 5 subtests passed** in 122.09 seconds. The skipped gates
include live local/cloud/UI acceptance and unsupported Windows symlink cases. No live provider
recertification was performed for this response/recovery repair.

A separate final metadata check encountered the previously observed intermittent Windows
`WinError 5` during the journal's atomic replacement, before capability execution. Its complete
65-test set passed on rerun. The full suite itself had no failures; the successful recheck does
not establish that the existing intermittent storage issue is fixed. Atomic-write retry policy
is outside this bounded response-normalization repair.

Content-free verification metadata is saved under ignored
`state/diagnostics/provider_response_recovery_verification_v1.json`. It contains revision IDs,
effective limits and test/proof counts, with no prompts, response text, file contents or credentials.
