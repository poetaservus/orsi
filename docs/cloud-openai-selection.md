# OpenAI cloud Phase 4.2: selection and migration review

The migration remains on `codex/cloud-openai`. Main, the original application's
configuration and runtime state remain preserved.

## Defaults and selection

GPT-6 Luna remains the cloud default. Startup remains local where a local model
is available; cloud-only installations use the available cloud mode. Existing
cloud disclosure and session-key handling remain in place. Automatic local
fallback remains disabled. Accepted profiles, sampling, context policy, prompts,
routing and tools are unchanged.

Settings now shows the model selector for the active mode. Cloud mode offers
GPT-6 Luna and GPT-6.1 Sol, their effective context/reply limits and qualification
status. The controls fit the existing settings panel at the minimum window size.
Selection does not make a request or establish model access. API permission errors
still surface without silently substituting another model.

Cloud selection goes through the conversation's execution lock. A response must
finish or stop before switching; closed services reject selection. Successful
switches refresh the hybrid's effective limits and context identity, invalidate
the previous physical-request context reading, and preserve conversation history.
Only the selected ID is saved to ignored `state/cloud_model_selection_v1.json`.
A failed save preserves the previous profile and restores the selector.

Baseline diagnostics now include allowlisted cloud profile settings and effective
limits, without keys or conversation/file contents. Shared cloud error types move
to `app/inference/cloud_errors.py`; existing legacy imports retain the same class
identity. The Responses backend and hybrid no longer import errors from the
legacy transport implementation.

OpenAI's [Responses migration guidance](https://developers.openai.com/api/docs/guides/migrate-to-responses)
and the [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) model contracts
were checked on 4 October 2026. Existing stateless item replay and profile-specific
reasoning parameters remain unchanged.

## Verification and remaining gate

The initial focused run passed 185 tests and 5 subtests. After adapting visibility
to the fixed settings-panel height, the final UI/selection/shutdown run passed
48 tests and 5 subtests. Checks cover persistence/reopening, busy/closed/local
rejection, history preservation, save failure, effective limits, actual SDK
request parameters, context-meter invalidation, diagnostics and client cleanup.
The final existing suite passed 1,699 tests and 15 subtests, with 49 skips, in
220.30 seconds using repository-local temporary storage and an unrestricted
Windows shell. Skipped live gates remain separate from deterministic passes:
18 legacy cloud-pool gates, 24 opt-in local-model/live-UI gates and 7 host symlink
checks. An earlier full run before the panel-visibility adjustment also passed
1,699 tests and 15 subtests with 49 skips in 218.91 seconds.

The final synthetic live UI check selected Luna → Sol → Luna using the existing
authorized key. Both Luna requests completed with known usage (717 and 770 total
tokens); Sol returned a permission error. Both profiles applied their actual
32,768-token context and 4,096-token reply limits; the conversation survived each
switch. The fixture accepted the real cloud disclosure once, saved only the model
ID, and released the session key, SDK client and owned transport thread on close.
This was a targeted selection check, not a rerun or promotion of Phase 4.1's full
60-cell acceptance matrix.

Legacy-provider deletion remains conditional on passing verification in the
agreed Phase 4.2 plan. The Phase 4.1 gate is still blocked by Sol access, so the
legacy configuration/transport and their tests remain available until that gate
passes. Both profiles remain `qualified=false`. Phase 4.2's defaults and UI work
are implemented; its final legacy deletion is pending that external gate.

Machine-local reports are under ignored `state/test-artifacts/cloud-phase42/`.
See [Phase 4.1 qualification](cloud-openai-qualification.md) for the retained
acceptance failures and blocked cells.

The subsequent [Luna output-budget adjustment](cloud-openai-output-budget.md)
supersedes Luna's limits and the timeout recorded above. This page retains the
original Phase 4.2 measurements rather than presenting them as evidence for the
new profile.
