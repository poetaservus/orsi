# OpenAI cloud Phase 2.1

This change continues `codex/cloud-openai` from Phase 1 revision `435eea4`.
Main remains at `b22b904f792f2d393b7e1ccc19ed483e86d0baf4`; the original
working application and runtime configuration remain untouched.

## Native tool contract

The Responses adapter now advertises flat function tools with explicit strict
schemas. It converts optional properties to required nullable wire fields and
closes nested objects. Local references, nested arrays/objects, nullable unions
and enums are supported. Defaults and nonessential schema annotations are removed
from the wire copy. Unsupported structures fail before inference. Domain schemas
are not modified. This follows the [OpenAI function-calling contract](https://developers.openai.com/api/docs/guides/function-calling)
and [supported structured schemas](https://developers.openai.com/api/docs/guides/structured-outputs).

Synthetic nulls for optional non-nullable arguments become omitted domain fields,
so the existing Pydantic models apply their defaults. Genuine nullable fields
retain null. Shape/type checks occur at the adapter; value constraints remain
enforced by the existing capability models before permissions or execution.

Provider function names use O.R.S.I.'s existing bounded name mapping. Responses
`call_id` is retained exactly for `function_call` and `function_call_output`;
the output item's separate `id` and the harness's internal execution ID are not
substituted. Existing transcript validation checks complete result pairing and
harness scopes. The Responses boundary also rejects actual call-ID reuse across
those scopes. Tool results must be valid capability-result envelopes for the
matching capability, serialized as JSON strings.

The adapter accepts completed native calls, text, or text alongside calls.
Malformed JSON, unknown names, unsafe/duplicate IDs and invalid batches return
no executable calls. It performs no syntax or name repair at this native strict
boundary. Incomplete, cancelled or unfinished calls cannot execute. Refusals
remain visible; refusals mixed with calls authorize no execution. No protocol
outcome activates the legacy text-to-tool fallback. Usage/completion metadata
and content-free error handling remain intact.

The API can propose multiple calls; the existing harness executes them
sequentially with its current limits, approvals, permission rules and journal.
Schema context reserves now count the actual converted wire schema with the
existing conservative byte-based policy. No acceptance prompts, routing policy,
model sampling, model limits or qualification flags changed.

## Boundary with Phase 2.2

Native tools are enabled for profiles using reasoning effort `none`, including
the chosen Luna default. Reasoning-enabled profiles fail before any tool request.
If the provider nevertheless returns reasoning items alongside calls, the
adapter stops before execution. Opaque reasoning/item persistence and replay,
and preservation of complete provider response items, remain Phase 2.2 work.
Basic settled domain call/result history can already be reconstructed from the
existing conversation store. No server-side response storage or response-ID
chaining is enabled.

Both profiles remain unqualified. Sol's previously observed permission failure
has not been retried or changed in this sub-phase. Packaging and UI selection
remain later work; the SDK is still isolated under this worktree's `.testdeps`.

## OpenCode adaptation

The cloud reference remains pinned at
[`907b3bc518fa48e90e8ec24dd327d13eee71c36c`](https://github.com/anomalyco/opencode/tree/907b3bc518fa48e90e8ec24dd327d13eee71c36c).
The lock now also records inspected hashes for:

- `packages/llm/src/protocols/openai-responses.ts`
- `packages/core/src/github-copilot/responses/convert-to-openai-responses-input.ts`
- `packages/core/src/github-copilot/responses/openai-responses-prepare-tools.ts`

The flat tool and exact call/result pairing patterns are adapted in Python.
The protocol reference currently defaults to non-strict tools; O.R.S.I. instead
explicitly uses strict mode following OpenAI documentation. Attribution is in
`THIRD_PARTY_NOTICES.md`.

## Verification, 4 October 2026

- Final focused adapter/harness/protocol/context/completion/conversation checks:
  **210 passed**.
- Full suite with normal Windows access and repository-local
  `--basetemp .pytest-tmp-c26`: **1,576 passed, 1 failed, 49 skipped,
  15 subtests passed** in 222.02 seconds. The unchanged skill Settings test
  `test_enter_previews_local_file_then_install_refreshes_picker_without_restart`
  timed out waiting for its worker. The same timeout was observed during
  Phase 1; no skill Settings implementation changes are in this sub-phase.
- Isolated skill Settings group recheck: **7 passed**. This does not relabel
  the failed full-suite run as an all-pass result.
- All 12 built-in capability schemas compiled without changing their domain
  schemas. Real SDK requests intercepted by a mock transport verified request
  shape, exact call IDs, validated results and client release.
- Harness integration covered allowed, denied, awaiting-approval and approved
  calls; malformed/truncated batches; sequential multi-call execution; invalid
  arguments; journal state; persisted result history and usage. Existing
  acceptance workflows and prompts remain unchanged.

An initial filesystem live smoke was rejected before execution by automatic
approval review because it would export an absolute local path to OpenAI.
It was not retried or routed around that restriction. That live gate remains
unrun; permission to export local path metadata is needed before running it.

A separate live protocol smoke sent only synthetic strings and a pure echo
result, without filesystem paths, file content or host metadata. It passed a
native-call/result/text round trip and the existing no-tool chat prompt. This
is narrow transport evidence, not filesystem or model qualification:

| Request | Outcome | Input/output/total tokens |
| --- | --- | --- |
| Synthetic echo request | one native call | 74 / 34 / 108 |
| Echo result continuation | assistant text | 173 / 6 / 179 |
| No-tool chat | assistant text, zero calls | 71 / 7 / 78 |

The client was released. Only outcome kinds, counts, usage and pass/fail metadata
were saved in ignored `state/test-artifacts/cloud-phase21/synthetic-live-smoke.json`.
No key, call arguments, response text, conversation or filesystem content enters
that baseline report. The user's key was read in memory from the authorized
existing file and was not copied into the repository or runtime settings.
