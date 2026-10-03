# Phase 6.1: skill observability

Skill discovery, routing, explicit activation, deactivation and admitted injection
now appear in the existing rotating `state/orsi.log`. This is a bounded addition
to the current runtime, with no new configuration, UI, provider calls or logging
infrastructure. Smaller open-source skill acceptance testing is deferred at the
user's request; model profiles and context policy are unchanged.

## Events and fields

New records use the `app.runtime.skills.diagnostics` logger at INFO and start
with `[skill]`, followed by one JSON object. The existing project-override record
remains available from `app.runtime.skills.discovery`.

| Event | Meaning |
| --- | --- |
| `discovered` | A valid skill is in the effective catalog after scope precedence and duplicate rejection. |
| `load_error` | Discovery rejected an entry or scope; only its stable error code, scope and location hash are retained. |
| `catalog_error` | An unexpected registry refresh failed and cleared the catalog. |
| `activated` | Explicit API or `/skill` activation succeeded; this alone does not mean injection. |
| `deactivated` | API, `/skill` or a successful new-session reset cleared a selection. |
| `activation_error` | Explicit selection failed or its active definition disappeared. |
| `router` | The conversation router returned a validated decision, fallback or cancellation. |
| `rejected` | Existing context admission rejected explicit guidance or dropped automatic guidance. |
| `injected` | Skill instructions are in an admitted prompt handed to the chat or agent answer runtime. |

Known definitions include their bounded, JSON-escaped name, `global`/`project`
source, exact instruction-body SHA-256, body byte count, and labelled token-size
estimate. Activation/injection records identify `explicit` or `automatic` use.
Router and failure records use allowlisted result/error codes; arbitrary labels
become `unknown`. There is no untrusted metadata/version serialization: the body
hash identifies the instruction revision actually used.

`token_size_estimate` is the rounded-up character count divided by four, labelled
`token_measurement: character_estimate`. It is informational and never changes
admission. Injection also records `system_message_tokens` from the existing
request budget, which includes core instructions and the skill wrapper. That
number is not an isolated body-token measurement. No extra tokenizer/model
request is made to produce either field.

Injection hashes are extracted from the already-rendered request snapshot. A
concurrent catalog reload cannot cause the replacement body's hash to be reported
for an older prompt. If the original definition can no longer be matched, source
is `unknown`; the submitted name/body hash remains accurate. Injection describes
the handoff, not successful model completion or every subsequent tool-loop request.
Reading the context meter does not emit an injection event.

## Privacy and behavior

These records never serialize user messages, descriptions, instruction bodies,
metadata, model responses, exception messages, paths, tool arguments or hidden
reasoning. DEBUG does not enable content logging. Names are the intentional
metadata exception: they are capped at 128 characters and controls are escaped
to prevent forged lines. Rejected files are correlated through a location hash,
not a visible path. No file is reread merely to generate a diagnostic hash.

The existing log rotation remains 2 MiB with three backups. Prompts, routing
rules, tool definitions/permissions, sampling, model limits, registry precedence,
installation behavior and upstream files are unchanged. The added registry
`project_root` accessor is read-only and performs no filesystem access.

## Verification

Focused verification passed **183 tests** in 7.92 seconds. It covers discovery and
project precedence, structured load failures, explicit API/slash activation,
automatic chat/agent injection, fallback decisions, cancellation, missing active
files, context rejection and fresh-session reset. It also checks bounded names,
INFO/DEBUG privacy, persisted rotating-log privacy, and snapshot hashes across
catalog reloads. Matched runs with diagnostics disabled/enabled have identical
tokenizer calls, model requests, prompt contents, tool definitions, selection
results and model limits. Existing 14B context checks passed unchanged.

The full suite passed **1,410 tests and 15 subtests, with 58 skipped**, in
194.77 seconds. The existing skips are seven host-dependent symbolic-link checks
and 51 opt-in live-model, cloud or UI gates; none is counted as a pass. Dependency
consistency and authored-file whitespace checks also passed. Manual inspection of
the persisted synthetic debug log confirmed the three expected lifecycle records,
their body hash/source and no prompt, body, reply or path content.

Native Windows handle checks use an unrestricted shell and repository-local
temporary files. An initial sandboxed read of that test directory was denied;
the unrestricted inspection succeeded. This was a sandbox limitation, not a
runtime or test failure. No new live-model or cloud inference was run;
deterministic checks are separate from live acceptance.

```text
runtime/python/python.exe -B -m pytest tests/test_skill_diagnostics.py tests/test_skill_discovery.py tests/test_skill_registry.py tests/test_skill_activation.py tests/test_skill_selection.py tests/test_default_14b_context.py -p no:cacheprovider --basetemp .pytest-tmp-phase6-1-verified --junitxml=state/test-artifacts/skill-phase6-1/verified-focused.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-phase6-1-full --junitxml=state/test-artifacts/skill-phase6-1/full.xml
```

Changed files are the new diagnostics module and its tests, small hooks in skill
discovery/registry and conversation orchestration, and this report. The next
roadmap step is 6.2, extension-boundary documentation; it has not been started.
