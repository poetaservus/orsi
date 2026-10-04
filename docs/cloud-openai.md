# OpenAI cloud migration

The migration stays on `codex/cloud-openai`, starting at local main
`b22b904f792f2d393b7e1ccc19ed483e86d0baf4`. The user's explicit instruction
is to leave main unchanged throughout all phases. This overrides the normal
fast-forward/branch-cleanup step in `AGENTS.md` for this migration.

## Four phases

| Phase | Sub-phase A | Sub-phase B |
| --- | --- | --- |
| 1: API foundation | Explicit OpenAI profiles, credential boundary and runtime selection | SDK Responses text adapter, completion/error/usage mapping and deterministic verification |
| 2: Native tools | Strict tool schemas, function-call IDs and validated outputs | Durable response-item/encrypted-reasoning replay and existing permission/continuation behavior |
| 3: Responsiveness and efficiency | Streaming, actual cancellation and one bounded retry owner | Context/cache handling and content-free latency/token measurements |
| 4: Qualification and migration | Unchanged acceptance workflows across modes/models, live qualification and packaging | Review default behavior, UI selection and legacy-provider removal after verification |

OpenAI documentation determines request semantics. OpenCode supplies useful
implementation patterns adapted to O.R.S.I.'s existing Python interfaces;
it does not override OpenAI's documented contract or O.R.S.I.'s permissions.
Existing acceptance prompts remain unchanged.

Current branch status: Phases 1, 2.1, 2.2, 3.1, 3.2 and 4.1 are implemented. Native tools now
support reasoning profiles and durable stateless output-item replay. Profile
defaults are unchanged and both models remain unqualified. The Phase 1-only
tool gate below is historical. See [native tools](cloud-openai-tools.md) and
[response-item replay verification](cloud-openai-replay.md) and
[streaming/cancellation verification](cloud-openai-streaming.md) and
[context/cache/measurement verification](cloud-openai-efficiency.md).
Phase 4.1 adds the separate [OpenAI acceptance and packaging gate](cloud-openai-qualification.md);
Luna passed 28 of 30 required cells, with both failures caused by the required
switch to inaccessible Sol. Sol's 30 cells remain blocked. Both profiles remain
unqualified. Phase 4.2 implements [defaults and UI selection](cloud-openai-selection.md)
and separates shared errors from the legacy transport. Legacy deletion remains
gated on successful qualification, which is still blocked by Sol access.

## Phase 1 implementation

`config/cloud.json` now selects the official Responses endpoint with two explicit,
immutable profiles. GPT-6 Luna is the user's chosen default. GPT-6.1 Sol is an
optional configured profile, subject to account access. Both remain unqualified.

| Setting | GPT-6 Luna | GPT-6.1 Sol |
| --- | --- | --- |
| Model ID | `gpt-6-luna` | `gpt-6.1-sol` |
| Effective application context | 32,768 | 32,768 |
| Input budget | 28,672 | 28,672 |
| Output reserve | 4,096 | 4,096 |
| Reasoning effort | `none` | `medium` |
| Temperature | 0.1 | omitted |

The application budgets are deliberately conservative. They preserve the previous
cloud output cap; they are not the vendor ceilings. The model pages retrieved on
4 October 2026 document a 1,050,000-token context and a 128,000-token output ceiling
for both profiles. Profile validation rejects unsupported model IDs/efforts,
impossible reserves and temperature when reasoning is enabled.
See the [Luna model contract](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Sol model contract](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[current model guidance](https://developers.openai.com/api/docs/guides/latest-model).

Only the selected model ID is persisted under ignored
`state/cloud_model_selection_v1.json`; selection never rewrites profiles. Corrupt
or unknown selections are rejected without replacing the saved file. Phase 1
exposes selection through the backend/catalog; Phase 4.2 adds the UI selector.
Startup still defaults to local mode with automatic local fallback disabled.

`OpenAIResponsesInferenceEngine` creates the SDK client lazily. Keys come from
`OPENAI_API_KEY` or the existing in-memory session prompt. The configuration cannot
contain a key or change the official endpoint. The dependency is pinned to
`openai==2.54.0` in both package manifests.

Text requests use `responses.create`, explicit model/reasoning/output settings,
`store=false`, `stream=false` and `truncation=disabled`. The adapter parses typed
message/output-text/refusal items, retains partial completion state and reports
actual SDK usage. Missing usage remains unknown rather than becoming zero.
Authentication, permission, quota, rate-limit, connection, timeout, context,
provider and malformed-response errors have fixed content-free messages/codes.
There is no model-pool failover; the SDK is the only retry owner and the initial
retry count is zero. Client closure is idempotent and clears the session key.
See [Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
and the [Python Responses request contract](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

Phase 1 supports plain text conversations and the existing text-based skill
selector. O.R.S.I.'s normal agent requests tools, so its cloud tool workflow is
not ready yet. The adapter rejects it before inference and before the existing
text-to-tool fallback can execute. Native function calls and opaque reasoning
replay are Phase 2 work. Streaming and in-flight cancellation are Phase 3 work.
`store=false` controls response storage; it does not claim account-level Zero
Data Retention.

## OpenCode reference

The independent cloud reference is pinned at
[`907b3bc518fa48e90e8ec24dd327d13eee71c36c`](https://github.com/anomalyco/opencode/tree/907b3bc518fa48e90e8ec24dd327d13eee71c36c).
`docs/opencode-reference.lock.json` records hashes of the three inspected files
without changing the older agent-harness reference:

- `provider/provider.ts`: choose the Responses API for OpenAI models.
- `session/llm/request.ts`: include sampling parameters only when supported.
- `provider/transform.ts`: disable server-side response storage.

The Python adaptation and MIT attribution are recorded in
`THIRD_PARTY_NOTICES.md`. Phase 2 will separately adapt response-item/tool replay
against the [official function-calling contract](https://developers.openai.com/api/docs/guides/function-calling).

## Verification, 4 October 2026

The isolated checkout is `state/cloud-openai-worktree` under the original checkout.
Its runtime junction reads the existing runtime without installing anything into
it. The new SDK and dependencies were installed only under this checkout's ignored
`.testdeps`; tests import application code from this checkout. No conversations,
runtime selection or working-app configuration are shared into this checkout.
This is a development checkout, not a newly packaged runnable distribution.

All refs and the original configuration were preserved in the original checkout's
ignored `state/backups/cloud-openai-phase1`. The Git bundle was verified. Main,
the original launcher and the user's current app state are preserved. No push,
merge, remote branch deletion or other active-worktree change is part of Phase 1.

- Focused foundation/regression run: **187 passed**.
- Launcher/final adapter recheck: **47 passed, 18 skipped**.
- Validation redaction and affected skill/Git/UI recheck: **114 passed**.
- First full run: **1,524 passed, 1 failed, 49 skipped, 15 subtests passed**.
  The failure was the isolated checkout's missing runtime link; that link was
  added and the launcher test passed its recheck. A prior sandbox collection
  failure was caused by denied access to SDK files; normal Windows access passed.
- Second full run: **1,505 passed, 20 failed, 49 skipped, 1 teardown error,
  15 subtests passed**. The long temporary path triggered Git's Windows path
  limit: an exact local reproduction reported `Filename too long` for a pack
  keep file. The affected skill/Git/UI checks passed in the 114-test recheck
  using a shorter repository-local temporary path; the teardown and UI timing
  failure are recorded separately rather than relabeled as passing that run.
- Final full regression with the shorter repository-local temporary path:
  **1,526 passed, 49 skipped, 15 subtests passed** in 197.64 seconds.

The final run used `--basetemp .pytest-tmp-c2` and saved its ignored XML report at
`state/test-artifacts/cloud-phase1/final-short-path.xml`. The legacy cloud matrix
collects 18 skipped cases for the two configured profiles, versus 27 for the old
three-model pool; this accounts for the nine fewer skips than the previous main
baseline. It does not mean nine live gates passed.

Tests exercise the real SDK through a mocked HTTP transport, not a substitute
SDK. Coverage includes exact request bodies, errors without body/key leakage,
refusals, partial and malformed responses, usage persistence, lazy startup,
model switching away/back, effective limits and released clients/local backends.
The existing OpenRouter live gate now explicitly rejects Responses configuration
so it cannot misreport qualification for the new profiles. Its acceptance prompts
and workflows are unchanged; existing skipped gates remain skipped.

Minimal live text requests used the user's supplied key in memory:

| Selected model | Result | Input/output/total tokens |
| --- | --- | --- |
| GPT-6 Luna | passed | 11 / 5 / 16 |
| GPT-6.1 Sol | permission failure | unknown |
| GPT-6 Luna, switched back | passed | 11 / 5 / 16 |

Requests used the checked-in effective 32,768 context and 4,096 output settings;
the SDK client was released. Only model IDs, limits, completion/error codes and
token counts were saved in ignored `state/test-artifacts/cloud-phase1/live-smoke.json`.
No key or response text was printed or stored in that report. The Sol request
reached the API but lacked permission; account/project/key access needs inspection
before its live qualification. The smoke checks are transport evidence, not the
Phase 4 acceptance matrix. Neither profile is promoted to qualified.
