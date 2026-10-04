# OpenAI cloud Phase 2.2

Implemented on `codex/cloud-openai`, following Phase 2.1 commit `6233806`.
Local main stays at `b22b904f792f2d393b7e1ccc19ed483e86d0baf4`. The original
working application and its settings are preserved. No merge or push is part
of this phase.

## Response evidence and continuation

Requests remain stateless (`store=false`) and do not use `previous_response_id`.
The SDK request explicitly includes `reasoning.encrypted_content` for compatibility;
current [OpenAI reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning)
says stateless responses already return encrypted reasoning by default. Complete
supported output items are preserved in their original order, with item IDs,
function call IDs and argument strings, encrypted reasoning, summary fields,
message contents and assistant `phase`. This follows the
[manual conversation-state contract](https://developers.openai.com/api/docs/guides/conversation-state).

`OpenAIReplay` stores immutable JSON evidence with a version and model/response
identity. Each output is limited to 64 items and 8 MiB; existing conversation
storage remains limited to 64 MiB. Supported items are assistant messages,
function calls and encrypted reasoning. Unknown, malformed, duplicate-ID,
unfinished or unencrypted reasoning items fail safely before tool execution.
Model identity binds to the requested profile, including when an API alias
resolves to a dated snapshot. Iterable tool catalogs are snapshotted once.
Tool calls still cross Phase 2.1's strict JSON/schema and exact-ID boundary.
Replay evidence must agree with the neutral calls and visible assistant text.
It is private conversation state, excluded from model/result representations,
visible messages and content-free diagnostic reports.

The existing conversation store saves accepted provider output before permission
evaluation or execution. A failed save stops the turn and further attempts in
that session. The existing journal, approvals, domain validation and sequential
executor remain authoritative. Completed allowed/denied calls return their
validated result envelope under the original provider call ID. Accepted calls
never become executable merely because they appear in saved response evidence.

In-memory continuation and restart reconstruction replay complete batches once,
then append their matching results. Text-only responses also retain reasoning
and assistant phase across turns. If execution stops partway through a batch,
the complete provider output remains durable evidence, while a later user turn
receives only settled neutral pairs and the stopped outcome. Unsettled calls
are not submitted or automatically resumed. Disabled capabilities use the
existing bounded settled-result summaries without replaying their raw batch.

OpenAI metadata is opt-in when rebuilding cloud history and is stripped for local
requests, including explicit local fallback and the constrained text adapter.
Switching cloud models between user turns uses neutral history for output created
by another profile. A model change during a tool continuation is rejected.
Switching back retains the original durable OpenAI items and effective limits.
Versioned profiles, sampling defaults and accepted prompts are unchanged.

Selected turns remain atomic for context admission. Ciphertext contributes to the
conservative size/token estimate. Context recovery preserves a replay transcript
and its paired results untouched; if it cannot fit, admission stops. Provider-aware
context/cache optimization remains Phase 3 work, as do streaming, transport
cancellation and retry changes. Neither model is marked qualified.

## OpenCode reference

The already pinned `907b3bc518fa48e90e8ec24dd327d13eee71c36c` Responses protocol
was inspected for reasoning/provider-metadata lowering. Its existing hash remains
in `docs/opencode-reference.lock.json`; no upstream revision changed. OpenAI's
complete-output preservation contract takes precedence. Python adaptation and
MIT attribution are recorded in `THIRD_PARTY_NOTICES.md`.

## Verification, 4 October 2026

- Focused affected regressions: **242 passed** in 13.88 seconds.
- Final model-alias/catalog and OpenAI adapter recheck: **127 passed**.
- Initial full suite: **1,604 passed, 49 skipped, 15 subtests passed** in
  220.50 seconds, before the final alias/catalog fixes.
- Final full suite on the committed implementation: **1,606 passed,
  49 skipped, 15 subtests passed**. No failures or errors. It used normal
  Windows access and repository-local `--basetemp .pytest-tmp-c22j`.
  Reports remain ignored under `state/test-artifacts/cloud-phase22/`.

The existing live/qualification skips are separate from deterministic passes.
The preservation audit confirmed original main/configuration and all 43 prior
branch, remote and tag refs are unchanged. The original checkout is clean.

Deterministic checks use the real pinned SDK with mock HTTP transport and the
actual existing permission, journal, conversation and context implementations.
They cover exact item order/IDs/argument bytes/phase, encrypted reasoning,
pre-execution persistence, denied/approved/awaiting calls, interrupted batches,
crash recovery, corrupt/oversize evidence, history tampering, model/mode switches,
private-state redaction, context admission and client release.

Live Phase 2.1 follow-up: after the user's explicit fixture path/metadata approval,
the original filesystem/no-tool smoke passed before these implementation changes.
See [its recorded results](cloud-openai-tools.md).

Live Phase 2.2: the same filesystem and no-tool acceptance prompts passed using
a separate in-memory Luna medium-effort diagnostic profile. This did not change
the chosen default profile or saved model selection. One stat call completed and
reported the correct size; its exact output replayed through continuation. Two
provider responses survived reopening the conversation, and the subsequent
no-tool request replayed all prior output without executing another tool. Client
release passed. The provider returned **zero reasoning items**, so this is live
output/restart evidence, not live encrypted-reasoning qualification. Encrypted
replay is verified deterministically; Sol's earlier account permission failure
and broader live/model qualification remain outstanding Phase 4 gates.

| Request | Input/output/total tokens | Result |
| --- | --- | --- |
| Fixture metadata request | 3009 / 73 / 3082 | one completed native call |
| Matching result continuation | 3309 / 11 / 3320 | exact prior-output replay, correct size |
| Reopened conversation, no-tool chat | 3339 / 7 / 3346 | all prior output replayed, zero new calls |

Only counts, pass/fail values, completion kinds and usage are in ignored
`state/test-artifacts/cloud-phase22/live-smoke.json`. Durable item evidence belongs
to the isolated fixture conversation, not baseline reports. The key was read from
the authorized existing file in memory and never copied or printed.
