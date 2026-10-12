# Composer model and reasoning selection

The chat composer now has a text row and a lower control row, with an inactive
microphone placeholder at the left, existing attachment controls, model and
reasoning selectors, and Send/Stop at the right. Existing settings selectors
stay synchronized. The image viewer keeps its compact input layout.

The model selector uses the configured cloud profiles and installed local
models. Cloud reasoning choices are limited to each model's supported efforts.
The choice applies to the next request, including native tool requests and
completion assessments. Controls cannot change a running response. Local mode
has no cloud reasoning control.

Reasoning preferences are saved per model in ignored
`state/cloud_reasoning_selection_v1.json`, alongside the existing model
selection, or in the corresponding encrypted personal-profile state. Existing
model selection files and versioned profiles are preserved. No selection is
changed automatically. Unsupported saved choices are rejected without rewriting
the file; a failed save retains the previous effective choice. Locking a
personal profile revokes access to cached effective settings.

Effective requests send `reasoning.effort`. Enabling reasoning omits temperature;
returning to the configured effort restores that profile's sampling settings.
Context and output limits retain the selected model profile's values. A changed
effort does not inherit a profile's qualification claim. No prompts, tools,
completion rules or routing policy are changed in this branch.

Supported choices and parameter compatibility were checked on 13 October 2026
against the official [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[API deployment guidance](https://developers.openai.com/api/docs/guides/deployment-checklist).

## Verification

On `codex/composer-model-reasoning`, based on verified local main `aae279a`,
the final necessary native run passed **246 tests**, with no failures, errors
or skips, in 27.383 seconds. Results are under ignored
`state/composer-reasoning-final.xml` and `.log`; temporary files were kept in
the checkout. Tests cover composer interaction, attachments, skill selection,
image inspection, existing model selection, API input budgets and replay, plus
the new reasoning selection and encrypted preference lifecycle.

Actual runtime switches away and back preserved history and effective limits.
Captured SDK request bodies verified selected reasoning for text and native
tool calls, compatible temperature omission/restoration, and owned SDK runner
shutdown. These requests used synthetic responses, not the live API.
Rendered previews were reviewed at 1280x800 and 760x600.

The initial restricted run exposed an outdated geometry expectation and
Windows file-handle restrictions. The expectation was updated for the requested
taller composer; the final native run passed the attachment and handle checks.
The full suite and live repair/model qualification were not run, as the user
requested only necessary tests. This change provides reasoning selection;
it does not establish that higher reasoning resolves the reported repair loops.

The prior main tip is preserved at
`archive/2026-10-13/main-before-composer-reasoning`. The unmerged
`codex/scroll-behavior-acceptance` branch is retained separately. No other
worktree or remote branch is changed.
