# Skill Runtime check-in — Phase 3.1

Date: 3 October 2026. Starting integration revision: `6681c5b`.
Implementation branch: `codex/skill-activation`.

## Implemented

`ConversationService.activate_skill(name)` explicitly selects one registry skill
for the current session. `active_skill` returns its current detached definition,
and `deactivate_skill()` clears the selection. A successful activation replaces
the previous selection; a missing/invalid name preserves it and raises a
structured `SkillActivationError`. Activation/deactivation cannot occur while
the service is replying or after shutdown.

The chat command `/skill <name>` activates that exact catalog name. `/skill`
alone deactivates it. The whole remaining argument is the name; there is no quote
syntax or inline task suffix. Ordinary mentions of names or `/skill` inside a
message do not activate anything. Commands return a local acknowledgement without
inference, tools or durable model history. Names in acknowledgements are bounded
and JSON-escaped. Existing UI workers display the acknowledgement normally.

The selection lasts across turns, clears on `new_session()` and is not restored
from saved conversations. Each request resolves the name through the authoritative
registry. Reloaded definitions apply on the next request. If the selected skill
is removed/rejected, a model turn fails closed until the user selects an available
skill or clears it; a previously loaded body is not silently reused. Once an agent
turn starts, its composed system message remains fixed across its model steps.

## Prompt construction and priority

The pure `with_active_skill()` renderer preserves the complete existing core
prompt, then adds a fixed instruction-priority policy and one labelled
`ACTIVE SKILL` section. Its JSON payload contains only `name` and `instructions`.
Descriptions, arbitrary metadata, source paths, resources and executable files
are not included or interpreted. Newlines, delimiters and controls in untrusted
names/bodies are escaped so they cannot create new message roles or section lines.
The original instructions remain recoverable exactly from the JSON string.

The priority policy states:

```text
Security/runtime restrictions and O.R.S.I core instructions remain binding
User instructions
Applicable project instructions
Active skill guidance
Model defaults
```

The existing system message remains first, including capability/permission
restrictions. The skill is labelled optional, lower-priority instruction data
inside a controlled section. The current user task stays a separate user message.
No automatic selector, new capability, project-instruction loader, installer or
configuration-override interpreter is introduced.

Prompt priority guides the model; runtime permissions, exact approvals, enabled
tools, schema validation and path policy remain enforced by the existing code.
The adversarial tests deliberately make the simulated model request forbidden
operations even with the skill active, rather than assuming the model will obey
the priority prose.

Without an active skill the renderer returns the exact existing core prompt and
ordinary request selection remains unchanged. Active skills use the existing
context accounting and recovery machinery, so their full section is counted and
protected as part of the system message. A skill-specific admission check rejects
a request if the complete skill/core and current user task cannot fit alongside
the unchanged tool-schema, output and safety reserves. Skill instructions cannot
displace/truncate the current task to obtain admission. Such turns record a
`context_limit` outcome, without sending an inference request.

## API

```python
service.activate_skill("design-taste-frontend")
service.run("Design this interface.")
service.deactivate_skill()
```

In chat, send `/skill design-taste-frontend`, then send the task. Send `/skill`
to clear it. The registry must already contain the skill; activation does not
discover directories or install anything.

## Tests

Focused checks used unrestricted native Windows handles and repository-local
temporary storage:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_activation.py tests/test_skill_activation_live.py tests/test_skill_registry.py tests/test_skill_discovery.py tests/test_skill_loader.py tests/test_skill_parser.py tests/test_personality.py tests/test_context_budget.py tests/test_context_recovery.py tests/test_conversation.py -p no:cacheprovider --basetemp .pytest-tmp-skill-activation-focused
273 passed, 3 skipped in 10.92 seconds
```

All 28 new deterministic activation checks passed. Coverage includes API/command
activation, replacement/clearing, missing/invalid names, busy/closed guards,
session/reset/reopen behavior, no automatic activation, unchanged inactive
prompts, chat/agent/conversation/recovery prompt placement, exact user retention,
one section per physical request, repeated turns, metadata exclusion, registry
reload/rejection, context accounting and admission, malformed renderer inputs,
malicious delimiter encoding, approvals accepted/denied, strict argument
validation, unadvertised shell-tool rejection and read-root enforcement. Native
call/result history remains valid; skill bodies are not written into durable
conversation messages.

Initial focused failures were new-test assumptions: the write target was inside
the fixture's protected application root, and assertions looked for retained
calls in the outcome instead of the store's separate call list. The fixture and
assertions were corrected to exercise the actual contracts. Security, tool
behavior and existing acceptance prompts were not changed to pass those tests.

The full unrestricted regression suite passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-activation-full --junitxml=state/test-artifacts/skill-phase3-1-regression.xml
1157 passed, 57 skipped, 15 subtests passed in 155.05 seconds
0 failed; 0 error records
```

Skips are recorded separately: 7 actual symbolic-link creation checks and 50
opt-in live-model/cloud/UI gates. This is the previous 56 skips plus the new
opt-in Qwen activation smoke, which was separately run as documented below.
The 49 existing live gates remain unverified by this phase. The ignored full
report is under `state/test-artifacts/skill-phase3-1-regression.xml`.

Dependency consistency (`pip check`) and whitespace checks passed. Existing
acceptance prompts, model profiles and sampling settings are unchanged; the
existing unwritable pytest cache remains disabled.

## Actual Qwen and manual prompt inspection

The opt-in live smoke ran the accepted `Qwen314BQ4KM.gguf` profile with isolated
conversation/selection state and the existing native server and agent boundary:

```text
ORSI_RUN_SKILL_ACTIVATION_LIVE=1
ORSI_SHOW_SKILL_TEST_PROMPT=1
runtime/python/python.exe -B -m pytest tests/test_skill_activation_live.py -s -p no:cacheprovider --basetemp .pytest-tmp-skill-activation-live --junitxml=state/test-artifacts/skill-phase3-1-live.xml
1 passed in 29.28 seconds
```

Manually inspected the exact native request submitted to Qwen, displayed only
for this fixed synthetic fixture. Core personality, available-tool list and
external approval rules were first and intact; the priority policy followed;
one JSON skill section preceded the separate, unchanged current user task.
The JSON name/body matched the loaded definition exactly. The native tools were
identical before activation, after activation and for the user-priority request.

The three physical requests verified an ordinary greeting without the skill,
the same request with the skill's `Skill check:` prefix, and an explicit user
override suppressing the prefix/greeting. Effective limits remained 16,384
context tokens and a 4,096-token output reserve. The owned server exited.
No model profile, sampling setting or persistent user selection was changed.

The initial live run failed an additional strict punctuation assertion: Qwen
returned `USER-WINS` for the unchanged request `Reply exactly USER-WINS. Do not
add any prefix or greeting.` The skill prefix was correctly omitted. The final
smoke checks priority separately from punctuation and accepts either marker
with or without the final period. The user prompt and product prompts were not
changed between runs. The stricter observation remains recorded as
`exact_user_output_matched: false`; the initial run was not an exact-output pass.

Content-free live diagnostics are under `state/test-artifacts/skill-phase3-1-live.json`:
pass flags, prompt hash, request/section counts, effective limits, catalog equality,
the separate exact-output observation and owned-process release. No credentials,
responses or prompt/skill bodies are saved in that diagnostic snapshot. This is
a small style/priority smoke, not broad live-model qualification or TasteSkill
compatibility testing.

## Files changed

- `app/runtime/skills/activation.py`
- `app/runtime/skills/__init__.py`
- `app/conversation/orchestrator.py`
- `tests/test_skill_activation.py`
- `tests/test_skill_activation_live.py`
- `docs/skill-runtime-phase3-1.md`

## Known issues and limits

No known blocking runtime issue in Phase 3.1. Qwen's exact trailing punctuation
failed the stricter observation above. Safe skill discovery remains Windows-only.
Activation commands/selection are session-local and are not restored from history.
An oversized or rejected active skill blocks a model turn until cleared/replaced.
No visible persistent active-skill badge or automatic selection was added.

## Next

Phase 3.2 — automatic skill selection. Do not begin until this checkpoint is accepted.
