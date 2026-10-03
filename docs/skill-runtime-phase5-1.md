# Skill Runtime Phase 5.1 — unchanged TasteSkill compatibility

## Result

**Import compatibility passes; complete model/workflow compatibility does not.**
The existing HTTPS installer accepted all 13 upstream instruction files without
editing them. The current default `design-taste-frontend` body is 22,305 native
Qwen tokens. Its complete request with the configured 12-tool catalog needs an
estimated 32,320 tokens, exceeding the measured 16,384-token context. Explicit
activation is safely rejected before generation; automatic oversized guidance
is dropped. A standalone full-bundle routing case also selected an image skill
for a code-oriented SaaS task. These failures are retained, not patched away.

This branch is validation only: fixtures, tests, an explicit audit utility and
this checkpoint. No application/runtime source, model profiles, sampling,
context policy, routing, tools, permissions, launcher or user settings changed.
The user requested deferring the unrelated fixes until the skills are finished.
The starting local `main` revision is `71fd745`; the bounded branch is
`codex/tasteskill-compatibility`.

## Upstream import and preservation

The upstream project identified by its
[official documentation](https://www.tasteskill.dev/docs) is
[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill). Its current default
is the experimental v2 skill, with legacy v1 separately named. This checkpoint
pins revision `ce26fc25c0e5e8cab638f883de62d9a86ee5e45b`; it does not silently
substitute the smaller v1 for the current default.

The production `GitSkillInstaller` downloaded the public repository into an
owned temporary clone, enumerated its tree, read raw blobs and installed into
isolated ignored storage. Read-only observation captured original object IDs,
paths, hashes and byte counts without changing returned Git data. Results:

| Import observation | Result |
| --- | --- |
| Discovered instruction files | 13 |
| Parsed/accepted instruction files | 13 |
| Rejected instruction files | 0 |
| Installed instruction files | 13 |
| Unsupported metadata | None; all 13 contain name/description only |
| Exact installed bytes verified | Yes, all 13 |
| Combined upstream instruction bytes | 302,340 |
| Remaining temporary clone entries | 0 |

The retained test fixtures are byte-exact upstream `SKILL.md` files under
`tests/fixtures/tasteskill/skills/`. Their manifest records the upstream commit,
Git blob IDs and SHA-256 hashes. The upstream MIT license is retained, and a
fixture-local `.gitattributes` disables line-ending conversion so Windows
checkouts preserve these hashes. These are untrusted test data, never contributor
instructions. No npm installer, shell script, hook, dependency install or
executable resource ran.

No skills were installed into the user's normal global catalog. Live checks use
isolated model-selection, conversation, journal and skill storage under
`state/test-artifacts/skill-phase5-1/`. Pinned instruction fixtures are also tested
offline through the existing local installation/reinstall/removal transaction.
No TasteSkill-specific parser exception, skill rewrite or instruction truncation
was introduced.

## Native sizes

These are actual `/tokenize` measurements from the owned Qwen 14B native server,
not byte-based guesses. File tokens include frontmatter; body tokens describe
the unchanged instructions before JSON rendering and core/tool overhead.

| Skill | File bytes | File tokens | Body tokens |
| --- | ---: | ---: | ---: |
| brandkit | 15,992 | 3,779 | 3,685 |
| industrial-brutalist-ui | 8,456 | 1,989 | 1,926 |
| gpt-taste | 7,857 | 1,895 | 1,817 |
| image-to-code | 36,442 | 7,820 | 7,699 |
| imagegen-frontend-mobile | 40,326 | 8,872 | 8,742 |
| imagegen-frontend-web | 36,854 | 8,285 | 8,154 |
| minimalist-ui | 7,901 | 2,072 | 2,034 |
| full-output-enforcement | 2,592 | 569 | 523 |
| redesign-existing-projects | 15,060 | 3,416 | 3,367 |
| high-end-visual-design | 10,561 | 2,655 | 2,597 |
| stitch-design-taste | 11,851 | 2,817 | 2,763 |
| design-taste-frontend-v1 | 21,195 | 5,240 | 5,174 |
| design-taste-frontend | 87,253 | 22,371 | 22,305 |

Both owned model audits selected an effective 16,384-token context and a
4,096-token output reserve using the existing hardware-aware policy. This is
the measured test instance, not a claim that the user's existing running app
uses the same effective window. Earlier diagnostics reported 8,192 tokens there.
No configured limit, automatic hardware choice or runtime selection was changed.

## Fixed automatic-routing evaluation

The five frontend requests are the roadmap's unchanged stimuli. Five unrelated
requests were fixed in `tests/fixtures/tasteskill_cases.py` before evaluation.
Task-specific acceptable frontend names were likewise fixed before model calls.
All 13 unchanged upstream names/descriptions participated; no instruction bodies
were submitted to the selector.

| Request | Standalone full-bundle choice | Assessment |
| --- | --- | --- |
| Build a SaaS landing page. | imagegen-frontend-web | Fail: image generation instead of frontend implementation |
| Redesign an existing dashboard. | redesign-existing-projects | Pass |
| Create a minimal portfolio. | minimalist-ui | Pass |
| Create an intentionally dense industrial interface. | industrial-brutalist-ui | Pass |
| Improve this generic AI-generated page. | redesign-existing-projects | Pass |
| Why is this Python function throwing TypeError? | None | Pass |
| Hello. | None | Pass |
| What is 17 times 23? | None | Pass |
| Explain a SQL inner join. | None | Pass |
| How do I undo the last Git commit without losing my changes? | None | Pass |

Result: **9/10**, with **4/5** appropriate frontend choices and **5/5** unrelated
requests receiving no skill. This does not repeat the synthetic three-skill
Phase 3.2 catalog; that earlier success did not qualify this larger upstream
bundle. No selector prompt or acceptable outcome was changed after observing
the failure.

## Matched enabled/disabled review

Each task started from isolated state and the same synthetic index file. The
style comparison deliberately enabled only the existing `filesystem.stat`
capability in both modes. This isolates instruction influence without allowing
upstream scripts or dependency installation. It is **not** a completed frontend
build or full-production-catalog workflow acceptance. A separate production
catalog probe follows below.

| Task | Without: visible words | Automatic: visible words | Effective automatic skill |
| --- | ---: | ---: | --- |
| SaaS landing | 147 | 88 | None: selected guidance dropped for context |
| Dashboard redesign | 42 | 52 | redesign-existing-projects |
| Minimal portfolio | 57 | 120 | minimalist-ui |
| Dense industrial interface | 38 | 266 | industrial-brutalist-ui |
| Improve generic page | 19 | 74 | redesign-existing-projects |

The automatic SaaS turn independently reran selection and then recorded
`skill_context_limit`. Its pre-drop name was not retained in that turn's final
selection record, so it is not assumed to match the standalone image-skill
choice. Both explicit default-skill probes separately proved context rejection.
Four smaller specialist bodies were retained in their answer requests. All ten
style-comparison responses completed; completion alone does not mean a frontend
artifact was built.

Manual text/code observations:

- Dashboard/improvement replies shifted from general questions to requesting
  project paths and outlining an audit. This is consistent with the redesign
  guidance, but no actual project audit occurred in these short stimuli.
- The portfolio reply reflected the specialist's utilitarian palette,
  typography and structure. It proposed a layout rather than delivering code.
- The industrial reply changed from a refusal to a complete inline HTML example
  with sharp borders, dark neutrals, red accent, display typography and a noise
  filter. It contained only three metric cards, so it did not convincingly
  satisfy the requested dense interface. Referenced fonts were not loaded, and
  a large fixed minimum heading size creates a mobile-overflow concern that
  still needs rendering verification.
- The disabled-mode refusals about producing interfaces are not fixed here.
  They are observations of the existing prompts/model in this restricted test
  profile, not evidence that skill importing broke file tools.
- The longer enabled industrial answer mostly consists of code. Visible word
  counts alone cannot establish excessive verbosity or superior design quality;
  the sample is too small for that claim.

Review replies are separate synthetic artifacts, not content in baseline
diagnostics. The extracted industrial example is at
`state/test-artifacts/skill-phase5-1/manual-review/industrial-automatic.html`.
Browser security rejected its `file://` URL. No alternate browser surface,
local-server workaround or security bypass was attempted. Therefore manual
**rendered visual review remains unverified**; the observations above are
text/code review only. No visual quality pass is claimed.

The main audit made 29 physical generation requests, reporting 48,457 input
tokens and 8,859 output tokens, including selector calls and tool follow-ups.
These are cumulative audit costs, not one-turn context usage or visible reply
length. Metrics and fixed reason codes are at
`state/test-artifacts/skill-phase5-1/model-audit/live-summary.json`; no instruction,
request, reply or credential body is stored in that summary.

## Production catalog and native tool calling

A separate matched probe used the configured **12-tool** production catalog and
unchanged Qwen profile/sampling. Only the fixture's host-read scope was narrowed
to its isolated portable root; every write/launch approval was denied. User
configuration files and real host authority were untouched. Both modes saw the
same native tool definitions, verified by a matching serialized-schema hash.

The unchanged probe was: `Use filesystem.stat to inspect index.html and report
whether it exists.`

| Mode | Estimated complete request | Native stat result |
| --- | ---: | --- |
| Without skill | 8,260 tokens | One successful call; completed |
| Explicit minimalist-ui | 10,523 tokens | One successful call; completed |
| Explicit design-taste-frontend | 32,320 tokens | Context rejection before generation; no call |

All use the measured 16,384-token window, 4,096-token output reserve and unchanged
existing safety allowance. The schema reserve was 2,748 tokens. Thus native tool
calling works with an admitted unchanged specialist; the current default cannot
reach the tool stage. The default body also fails the narrower stat-only request
at 29,573 estimated tokens. Neither result is solved by removing a minor metadata
field or by the three design dials.

The production probe's first command finished its model work and released the
owned server, then exited with a validation-utility `KeyError` while printing a
summary field that belongs only to the style audit. The reporting projection was
corrected and covered by both-mode/content-isolation tests. The saved completed
native results were then summarized successfully with `--report`; no model
response, product behavior or failed qualification was changed by that repair.

Production metrics are at
`state/test-artifacts/skill-phase5-1/production-tool-audit/production-tool-summary.json`.
Both owned Qwen validation servers exited. No unrelated process was stopped.

## Deterministic verification and reproduction

The pinned tests check all 13 file sizes, SHA-256 hashes and Git blob IDs; parser
acceptance; exact body preservation in the priority wrapper; byte-exact batch
installation/idempotence/removal; and safe automatic-drop/explicit-reject behavior
for the large unchanged default. These check import and runtime boundaries, not
semantic model quality.

Final focused command:

```text
runtime/python/python.exe -B -m pytest tests/test_tasteskill_compatibility.py tests/test_skill_git_installer.py tests/test_skill_git_process.py tests/test_skill_installer.py tests/test_skill_selection.py tests/test_skill_activation.py -p no:cacheprovider --basetemp .pytest-tmp-tasteskill-focused-final --junitxml=state/test-artifacts/skill-phase5-1-focused-final.xml
```

Result: **230 passed** in 25.00 seconds. An earlier focused checkpoint passed
229 tests before the final report-mode checks and fixture-test cleanup.

Final full command:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-tasteskill-full-final --junitxml=state/test-artifacts/skill-phase5-1-full-final.xml
```

Result: **1,359 passed, 58 skipped, 15 subtests passed** in 162.06 seconds. The
intermediate full checkpoint passed 1,358 tests, 58 skips and 15 subtests in
201.10 seconds, before the final report-mode checks and fixture-test cleanup.
The 58 existing skips are 7 host-dependent symbolic-link tests and 51 opt-in
live-model/cloud/UI gates. They remain separate from the explicit TasteSkill
audits; no skipped gate is counted as a pass. Dependency consistency,
authored-file whitespace checks and all 13 Git-filtered upstream fixture hashes
also passed. The full staged whitespace check flags original trailing spaces in
upstream instruction files, including Markdown hard line breaks. Those bytes
are deliberately retained; the upstream fixtures are not reformatted to silence
the warnings. No repository-wide whitespace rule was changed.

Explicit model audits:

```text
runtime/python/python.exe -B -m tests.tasteskill_live_validation
runtime/python/python.exe -B -m tests.tasteskill_live_validation --production-tools
runtime/python/python.exe -B -m tests.tasteskill_live_validation --report state/test-artifacts/skill-phase5-1/production-tool-audit/production-tool-summary.json
```

The audit utilities report observations and `qualification_passed: false`; a
completed audit is not a passed qualification gate. Live Qwen validation is
explicit and not run by ordinary pytest collection. No cloud provider or API key
was used. Ignored artifacts contain only synthetic test sessions; user
conversations were never loaded. Native checks use repository-local pytest
temporary paths and an unrestricted Windows shell.

## Generic gaps and next step

No generic parser or file-format capability is missing for this pinned import.
Runtime interoperability is limited by whole-body context admission for large
instructions and imperfect semantic routing across overlapping frontend/image
descriptions. Those are generic capacity/routing/qualification issues, not
TasteSkill-specific parsing exceptions. Asset-dependent or package-installing
upstream workflows are also beyond this instruction-only runtime's authority.

Configuration overrides are not justified by these results. They would not make
the default body fit or repair the routing error. Phase 5.2 remains conditional;
no override engine, persistent dials or altered upstream file was added.

The context-window issue, routing miss, incomplete visual/workflow qualification,
Qwen punctuation observation and prior intermittent Windows regressions remain
on the final verification/fix list, consistent with the user's request to finish
the skills work before addressing them together. This checkpoint records Phase
5.1's successful import and failed broader qualification honestly.
