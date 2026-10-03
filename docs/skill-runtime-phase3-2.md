# Skill Runtime check-in — Phase 3.2

Date: 3 October 2026. Starting integration revision: `a22cf11`.
Implementation branch: `codex/skill-selection`.

## Implemented

`ConversationService` now selects zero or one skill before an ordinary model
turn when its registry contains skills. Explicit session activation takes
precedence and skips the selector entirely. `/skill <name>` keeps its existing
exact-name command behavior; `/skill` clears it and permits automatic selection
on the next task. Commands themselves make no model requests.

Automatic choices apply to the current turn, including its agent model steps,
and are reevaluated from the next user task. The previous automatic choice is
never implicitly carried forward. New sessions clear choices and measurements;
selection is not restored from saved conversations. `active_skill` returns a
detached definition. Explicit activation resolves through the current registry;
automatic activation uses the snapshot resolved after routing. A catalog change
that removes the selected name or changes its description before resolution
rejects the result. A changed body with unchanged metadata uses the current body.

`automatic_skills_enabled=False` disables routing for comparisons or callers
while preserving explicit activation. Its default is true. This does not add a
settings-file schema, persistent user selection or UI switch.

## Selection boundary and failure behavior

`SkillCandidate` exposes only `name` and `description`. The pure routing input
contains the sorted metadata catalog and current user task in one JSON user
message, preceded by a fixed selection protocol. There are no instruction bodies,
paths, arbitrary metadata, previous conversation messages or tool definitions.
The existing inference adapter performs one tool-free request. No embeddings,
keyword routing, extra model or model-profile change is introduced.

The only accepted output is a JSON object containing exactly `skill`, with either
null or one exact catalog name. Unknown names, multiple choices, duplicate keys,
extra keys, non-JSON/fenced text, non-finite values and incomplete completions all
yield no selection. The protocol favors no selection for ordinary conversation,
unrelated coding, discussion of skill names and ambiguous requests.

The whole catalog/request is rejected rather than truncated above 128 candidates
or 64 KiB of JSON input. Responses are limited to 4,096 characters. Admission
uses the existing effective context limit, output reserve and safety buffer.
An empty catalog or rejected input makes no selector request. Invalid responses,
model errors and safely stopped timeouts allow the ordinary answer to continue
without skill guidance. Diagnostics use fixed reason codes without raw output.

The selector deadline is 120 seconds, with cancellation polled every 50 ms.
Timeout/cancellation invokes the adapter's existing cancellation hook and waits
up to two seconds for completion. If timeout cannot stop the request, the current
turn aborts instead of starting answer generation concurrently. An adapter without
effective cancellation can leave its daemon request running until that adapter
returns; native Qwen uses the existing cancellable server adapter.

The selected body uses the unchanged Phase 3.1 renderer and priority policy,
appearing once in the system message. Automatic guidance that cannot fit with
the complete current task and existing reserves is dropped. Explicit activation
retains its existing context-limit error contract. Tool catalogs, approval/path
policy, sampling and conversation context selection are unchanged. Malicious
skill instructions cannot grant runtime permissions.

`service.skill_selection` records name, fixed reason, selector request count,
estimated input tokens and actual input/output tokens when supplied by the
adapter. These describe the latest selection, separately from the existing
answer-generation counters and context meter. Routing adds one physical request
per nonempty-catalog automatic turn even when the result is no skill; explicit
activation and empty catalogs avoid that cost. Bodies and responses are not saved
to diagnostics or durable conversation messages.

## Fixed evaluation and integration

`tests/fixtures/skill_routing.py` fixes 44 requests and expected outcomes before
live evaluation: 8 frontend, 8 SQL, 8 Python, 6 ordinary conversation, 4 ambiguous,
6 unrelated coding and 4 skill-name mentions. Forty are obvious skill/no-skill
cases, with a 90% release threshold. All four ambiguous cases expect no skill.
The evaluation prompts and outcomes were not tuned in response to live results.

The three-mode comparison uses the unchanged request
`Redesign this React landing page.` with no skill, explicit activation and
automatic activation. Its synthetic frontend fixture requires a fixed
`FRONTEND-GUIDANCE:` prefix and a concise design suggestion. This checks native
prompt construction and influence; it is not an upstream TasteSkill import or
compatibility claim. Real TasteSkill compatibility remains Phase 5.1.

## Verification

Focused unrestricted Windows checks used repository-local temporary storage:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_selection.py tests/test_skill_selection_live.py tests/test_skill_activation.py tests/test_skill_activation_live.py tests/test_skill_registry.py tests/test_skill_loader.py tests/test_skill_parser.py tests/test_skill_discovery.py tests/test_conversation.py tests/test_personality.py tests/test_context_budget.py tests/test_context_recovery.py -p no:cacheprovider --basetemp .pytest-tmp-skill-selection-focused
332 passed, 4 skipped in 17.92 seconds
```

All 59 new deterministic checks passed, covering strict output/input boundaries,
context admission, provider failures, incomplete responses, timeout/cancellation,
metadata isolation, empty catalogs, explicit precedence, per-turn reevaluation,
disable/reset behavior, stale catalog rejection, oversized-body fallback, exact
user retention, unchanged full twelve-tool definitions, valid native history,
and enforced write approval despite malicious automatically selected guidance.

An earlier focused run hit an access-denied error in an unchanged Windows
registry handle-release test. Its isolated unrestricted recheck passed, and the
final focused run passed it. Initial new-test fixture/assertion mistakes were
corrected without changing product permissions or acceptance prompts.

The full unrestricted regression passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-selection-full --junitxml=state/test-artifacts/skill-phase3-2-regression.xml
1216 passed, 58 skipped, 15 subtests passed in 194.37 seconds
0 failed; 0 error records
```

Skips are separate evidence: 7 actual symbolic-link creation checks and 51
opt-in live-model/cloud/UI gates. The Phase 3.1 and 3.2 Qwen gates are separately
run below; the other 49 live gates remain unverified by this phase. Dependency
consistency (`pip check`) and whitespace checks passed. The existing pytest cache
remains disabled; temporary directories and content-free reports stay under
ignored repository-local state.

## Actual Qwen results and cost

The corrected native Qwen routing/integration gate passed all 44 fixed cases:
40/40 obvious cases (100%, above the 90% threshold) and no activation for 4/4
ambiguous cases. All three frontend modes passed selection, style influence,
section count, unchanged native tool definitions and valid completed history.
The exact requests submitted to Qwen were inspected in memory; diagnostic
artifacts contain only counts, reason codes, expected/selected names and hashes.
No request, reply, instruction body or credential is persisted in these snapshots.

| Frontend mode | Physical requests | Skill sections in answer | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| Without skill | 1 | 0 | 922 | 453 |
| Explicit | 1 | 1 | 1,072 | 413 |
| Automatic | 2 | 1 | 1,348 | 719 |

Automatic totals include a selector request costing 276 input and 139 output
tokens, then an answer request costing 1,072 input and 580 output tokens. These
are measured native token counts, including provider-reported generation usage;
they are not estimates of visible reply length. Output differences are one-run
observations, not evidence of equal answer length or comparative quality.

Effective limits were 8,192 context tokens and a 4,096-token output reserve in
this run. The versioned profile's target remains 16,384; the existing automatic
hardware-aware selection chose the lower effective window. No model profile,
sampling or persistent user selection was changed. The owned server exited.

The initial live run also matched all 44 routes, then failed a test assertion
that mistakenly required the last message of the completed conversation to be
the user request. Completed history correctly ended with the answer. The test
now captures the actual answer-generation payload and separately validates
completed history. Product prompts and fixed evaluation stimuli were unchanged.
The first run remains a failed integration run, preserved separately at
`state/test-artifacts/skill-phase3-2-live-first-run.json`.

Final content-free routing, per-request usage and frontend-mode diagnostics are
at `state/test-artifacts/skill-phase3-2-live.json`. The combined live test report
is `state/test-artifacts/skill-phase3-2-live-final.xml`.

```text
ORSI_RUN_SKILL_SELECTION_LIVE=1
ORSI_RUN_SKILL_ACTIVATION_LIVE=1
runtime/python/python.exe -B -m pytest tests/test_skill_selection_live.py tests/test_skill_activation_live.py -s -p no:cacheprovider --basetemp .pytest-tmp-skill-selection-live-final --junitxml=state/test-artifacts/skill-phase3-2-live-final.xml
2 passed in 363.26 seconds
```

The existing Phase 3.1 smoke separately passed ordinary greeting, explicit style
and user-priority suppression with unchanged acceptance requests and tools.
Its baseline now includes the additional selector request; explicit turns still
skip routing. Both owned validation servers exited. Strict final punctuation
continues to be recorded separately from the priority assertion:
`exact_user_output_matched: false`. This later smoke selected an effective
16,384-token context with the same 4,096-token output reserve through the
unchanged hardware-aware policy.

## Files changed

- `app/runtime/skills/selection.py`
- `app/runtime/skills/__init__.py`
- `app/conversation/orchestrator.py`
- `tests/fixtures/skill_routing.py`
- `tests/test_skill_selection.py`
- `tests/test_skill_selection_live.py`
- `tests/test_skill_activation.py`
- `tests/test_skill_registry.py`
- `docs/skill-runtime-phase3-2.md`

Existing registry/activation assertions now inspect the final answer request,
allowing the additional metadata-only selector request. Their acceptance tasks
and expected answer-prompt contents are unchanged.

## Known limits and next phase

The live routing set qualifies this fixed three-skill English catalog on Qwen
14B only, not arbitrary catalogs, languages, smaller models or broad agent
qualification. Skill loading/discovery remains Windows-only. There is no
persistent active-skill badge, installer, resource execution or configuration
override support. Qwen's previously recorded strict trailing-punctuation issue
is separate from routing and is not fixed by this phase.

Next: Phase 4.1 — local installer. Do not begin until this checkpoint is accepted.
