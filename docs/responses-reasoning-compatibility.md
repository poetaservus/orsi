# Responses reasoning-content compatibility

With reasoning enabled, a valid completed OpenAI Responses result can contain
a reasoning item with `content: []`. The installed SDK 2.54.0 declares optional
`content` as a list of `{type: "reasoning_text", text: string}` parts. ORSI's
strict replay validator omitted this documented field, so a valid result failed
before tool execution with "OpenAI returned an invalid Responses payload."

Accept and validate that optional field, preserving every supported item for
stateless replay. Reasoning content remains private evidence; it is never
assistant text. Existing encryption, field/type checks, completed-item checks,
identity checks and storage-size limits remain enforced. Tool schemas,
permissions, prompts, routing, profiles and sampling are unchanged.

References: [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
and [reasoning replay guidance](https://developers.openai.com/api/docs/guides/reasoning).

## Verification

- A live synthetic Luna Medium probe reproduced the exact malformed-response
  error before the fix: a completed reasoning item with empty `content` failed
  replay validation while its function call decoded successfully. The same
  prompt passed after the fix. No tool executed in these schema probes.
- A live Luna Medium read/summary run completed against three generated
  synthetic project files: three successful reads, five provider responses,
  four reasoning items with `content`, a nonempty counter-project summary,
  successful history reopening, unchanged source and released transport.
- 264 affected deterministic native Windows checks passed, using repository-local
  `state/responses-reasoning-final-temp`. They cover SDK decoding, tool execution,
  exact replay and persistence, legacy histories, private-reasoning visibility,
  malformed evidence, streaming, context budgeting, composer selection and
  turn outcomes. The full suite was not run under the requested necessary-test
  scope. The first deterministic reproducer failed with the same reported error
  before changing the validator.

Live probes used the previously authorized credential and synthetic inputs
only. The isolated probe used a 2,048-token response cap; accepted model profiles
and user preferences were not changed. Content-free live metadata is under
`state/responses-reasoning-probe/` and
`state/responses-reasoning-summary/result.json`. Deterministic results are in
`state/responses-reasoning-final.log` and `.xml`. No user profile or project
contents were read or transmitted by these probes.

The bounded branch starts at `f30a597`. Preserve prior main as
`archive/2026-10-13/main-before-responses-reasoning-compatibility`, commit,
fast-forward local main and remove only the merged feature branch. Preserve
earlier unmerged branches and other worktrees. No remote publication.
