# Phase 5.2: configuration override assessment

Phase 5.2's conditional assessment is complete. Persistent configuration overrides
are **deferred**: the existing user-message path already changes TasteSkill's
design dials on the default 14B model, without changing installed instructions.
There is no demonstrated material benefit from adding a configuration engine.
This closes the conditional step, not the broader TasteSkill qualification gate.

The roadmap says to add overrides only after confirming they materially improve
real TasteSkill use, and explicitly forbids building a generic engine beforehand.
Both pinned upstream versions already describe conversational overrides. V1's
baseline section says to adapt the values to explicit chat requests; v2's
baseline section likewise directs overrides through conversation. Neither file
needs a fork. A future requirement to save per-skill defaults across independent
conversations would be a reason to revisit this decision; this assessment does
not introduce that requirement.

## Native evidence

The unchanged upstream `design-taste-frontend-v1` at revision
`ce26fc25c0e5e8cab638f883de62d9a86ee5e45b` was installed in isolated audit storage.
Its instruction body is 5,174 native tokens. The default
`Qwen314BQ4KM.gguf` ran with the accepted **16,384 context / 4,096 output** limits
and the existing production catalog of **12 tools**. User settings, model profiles,
sampling, routing, prompts, admission policy, permissions and application source
were not edited. Reads were confined to a synthetic home; write/launch approvals
were denied.

All four cases used the same SaaS metrics design-plan task, fixed before inference.
Only the requested dial prefix changed. Each ran in a fresh session on the same
conversation service with explicit v1 activation.

| Case | Effective variance / motion / density | Applied design choices | Result |
| --- | --- | --- | --- |
| Default | 8 / 6 / 4 | Asymmetric grid, animated, normal spacing | Passed |
| One chat override | 8 / 1 / 4 | Asymmetric grid, static, normal spacing | Passed |
| Three chat overrides | 2 / 1 / 9 | Symmetric grid, static, dense | Passed |
| Fresh session after overrides | 8 / 6 / 4 | Asymmetric grid, animated, normal spacing | Passed |

Manual text review corroborated the plan fields. The low-motion answer described
static elements. The dense answer specified a strict 12-column grid, 1px
separators, monospace metrics, and no cards or animations. The two baseline answers
described asymmetric grids and animated interactions. These are design plans,
not rendered websites or proof of complete frontend workflow quality.

Each response completed without truncation or tool calls. Every physical request
contained exactly one active-skill section with the exact original body and the
same tool-schema digest. Installed and fixture files remained byte-exact; the
model configuration file remained unchanged. The owned model server exited.
Four physical requests used **37,017 input tokens and 2,108 output tokens**.
No smaller model or cloud provider was substituted.

The upstream v2 default still has a 22,305-token instruction body, before core
instructions, schemas and the output reserve. It cannot fit this 16,384-token
profile. Configuration overrides would not resolve that limitation. The existing
whole-body admission policy remains intact. See the
[Phase 5.1 report](skill-runtime-phase5-1.md) for context admission, routing and
visual/workflow qualification gaps; the
[default 14B repair](default-14b-context-fix.md) separately records the fixed
ordinary-chat and smaller-skill capacity problem.

## Use the existing path

For an installed v1 skill, activate it with `/skill design-taste-frontend-v1`,
then include the desired dials in the request, for example:

```text
For this design use DESIGN_VARIANCE: 2, MOTION_INTENSITY: 1,
and VISUAL_DENSITY: 9. Plan a SaaS metrics page.
```

The upstream dial range is 1 through 10. These are conversational instructions,
not validated application configuration. Starting a new chat clears prior
conversation instructions; activate the skill again to use its baseline.
Simply omitting the override in the same chat is not a removal mechanism because
earlier user instructions may remain in its context.

The roadmap's six override-engine tests apply **if implemented**. Default,
single/multiple adjustments and fresh-session restoration were observed here.
Invalid-value rejection, unknown-setting rejection and removal of a persistent
configuration are **not applicable**: there is no configuration parser, storage
or removal API. The audit's strict answer checks are measurement safeguards, not
new runtime validation. We do not claim that the model rejects invalid chat dials
deterministically.

## Verification and scope

Only these authored files were added:

- `tests/tasteskill_configuration_validation.py`: explicit, repeatable native audit;
  it is not collected as a live test by ordinary pytest.
- `tests/test_tasteskill_configuration_validation.py`: prevents malformed answers,
  missing cases, incomplete responses or changed native evidence from passing.
- `docs/skill-runtime-phase5-2.md`: decision, evidence and limits.

Reproduction:

```text
runtime/python/python.exe -B -m tests.tasteskill_configuration_validation
runtime/python/python.exe -B -m pytest tests/test_tasteskill_configuration_validation.py tests/test_tasteskill_compatibility.py tests/test_skill_activation.py tests/test_default_14b_context.py -p no:cacheprovider --basetemp .pytest-tmp-phase5-2-focused --junitxml=state/test-artifacts/skill-phase5-2/focused.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-phase5-2-full --junitxml=state/test-artifacts/skill-phase5-2/full.xml
```

The focused checks passed **73 tests** in 6.84 seconds. The full suite passed
**1,392 tests and 15 subtests, with 58 skipped**, in 194.31 seconds. The existing
skips are seven host-dependent symbolic-link checks and 51 opt-in live-model,
cloud or UI gates; they are not counted as passes. The explicit four-case native
audit above is separate from those skips. Dependency consistency and authored-file
whitespace checks also passed. Native verification used an unrestricted Windows
shell with repository-local temporary files. Ignored `state/test-artifacts/skill-phase5-2/`
contains the content-free `live-summary.json`, test reports, and separate synthetic
answer artifacts for manual text review. No user conversations or keys were read
into the report.

The next roadmap step is 6.1, skill-runtime diagnostics. It has not been started.
