# Small open-source skill validation, 3 October 2026

The unchanged Anthropic `brand-guidelines` skill works when explicitly activated
on the existing Qwen 3B profile. Automatic activation works for the CSS task but
misses the font-only task. Qwen 14B selected its existing CPU fallback, where the
full tool catalog cannot fit even without a skill. This is a validation result,
not a runtime repair or a claim of general compatibility.

Only tests, the pinned upstream fixture and this report are added. Application
code, core prompts, selector prompts, sampling, model profiles, context policy,
the user's selected model and global skill catalog are unchanged.

## Source and installation

- [Upstream skill](https://github.com/anthropics/skills/blob/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/brand-guidelines/SKILL.md)
  and its [Apache-2.0 license](https://github.com/anthropics/skills/blob/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/brand-guidelines/LICENSE.txt).
- Revision: `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`.
- SKILL.md: 2,235 bytes; body: 1,915 bytes. This is about 39 times smaller
  than TasteSkill's default 87,253-byte file.
- Native tokenizer: 528 file tokens, 466 body tokens on both tested models.
- The `license` metadata is preserved as inert metadata. No scripts, assets,
  references, font installation or third-party libraries are needed by this test.

The existing HTTPS installer scanned the public repository and installed its 20
skills into ignored, isolated test storage. The chosen skill matched the original
Git blob exactly. All 20 temporary catalog entries were then removed; zero clone
temporary entries remained. Only this Apache-licensed skill and its license were
retained as versioned fixtures. The separate model catalogs each contain just
`brand-guidelines`, installed through the existing local installer.

The fixture manifest records source revision, Git object ID, byte counts and
SHA-256 digests. Local Git attributes preserve the upstream bytes. Install,
identical reinstall and removal passed; the installer stores only SKILL.md.

## Frozen requests and controls

`tests/simple_skill_live_validation.py` fixes these requests before inference:

1. CSS: "Using Anthropic's brand guidelines, reply with CSS only: define custom
   properties for all seven brand colors, set h1 font-family with its fallback,
   and set body font-family with its fallback. Do not create files or use tools."
2. Fonts: "What are Anthropic's official heading and body fonts and their fallback
   fonts? Reply with just two short lines. Do not use tools."
3. Existing tool acceptance request: "Use filesystem.stat to inspect index.html
   and report whether it exists."

Each branding request runs in a fresh conversation without a skill, with explicit
activation, and with automatic selection. The tool request runs without and with
explicit activation. Five unchanged unrelated requests from the earlier audit
cover Python, a greeting, arithmetic, SQL and Git; selection should return no match.

All model runs retain all 12 production tool definitions. Only fixture authority
is scoped: reads stay inside each isolated test directory, and write/launch
approvals are denied. The same model profile and sampling apply to every mode
within each model comparison. The second model uses its existing profile and
does not switch the application's selected model.

CSS content checks require all seven expected color values in actual custom
property declarations and the expected heading/body font families with fallbacks
in their respective CSS rules. Font content checks require all four expected
font names. These checks do not claim rendered visual quality or strict response
format compliance. Synthetic responses were also inspected as text.

## Live results

| Check | Qwen 14B | Existing Qwen 3B (`model.gguf`) |
| --- | --- | --- |
| Effective context / output reserve | 4,096 / 1,024 | 16,384 / 4,096 |
| Unrelated requests select no skill | 5/5 | 5/5 |
| Explicit CSS content | Blocked by context | Passed |
| Automatic CSS content and activation | Blocked by context | Passed |
| Explicit font content | Blocked by context | Passed |
| Automatic font content and activation | Blocked by context | Failed: `no_match` |
| Native stat, without / explicit skill | Both blocked | 1 successful call in each |
| Exact skill body injected once per answer request | Not exercised | Passed |
| Identical 12-tool schema across answer requests | Not exercised | Passed |
| Owned validation server exited | Yes | Yes |

The 3B controls without a skill used incorrect colors/fonts. Explicit activation
corrected both content checks. Automatic CSS selected `brand-guidelines` and
produced the same correct CSS. Automatic font selection returned valid `null`
(`no_match`), so the body was never injected and the answer again used incorrect
fonts. This is a selection miss, not truncation or a skill-size failure. The
explicit font answer included the correct names but used one line rather than
the requested two, so complete prompt compliance is not claimed.

All eight 3B conversations completed without truncation. The tool schema digest
was identical across its ten physical answer requests, including tool follow-ups.
Five answer requests contained exactly one byte-preserving instruction section;
the remaining five contained none. Seven selector requests had no tool catalog.
The 3B run used 17 physical requests, 40,325 input tokens and 713 output tokens.

On 14B, all eight answer workflows were rejected before answer inference. Seven
selector requests completed using 1,724 input tokens and 264 output tokens.
Both unrelated selection and valid branding selection were possible, but selected
branding bodies were dropped with `skill_context_limit` before the agent request
also failed. No native tool call or final branding answer was exercised on 14B.

The 14B run selected the accepted profile's CPU fallback. A separate read of GPU
memory reported 16,384 MiB total and 11,358 MiB free during that run; those figures
are consistent with insufficient memory under the existing 14B memory guard.
No other application or model process was stopped to improve the test result.

For the stat request, the unchanged full-catalog admission budget was:

| Budget | Qwen 14B fallback | Qwen 3B |
| --- | ---: | ---: |
| Without skill | 5,188 | 8,260 |
| With skill | 5,811 | 8,883 |
| Effective context | 4,096 | 16,384 |

The serialized skill section adds 623 tokens to this admission estimate. The
baseline alone exceeds 14B's fallback limit. Shrinking the skill therefore cannot
resolve that run's context failure. Context/runtime and automatic-selection
repairs remain deferred as requested.

## Verification and artifacts

Focused checks: **91 passed** (fixture integrity/license, native local installation,
activation, selection, and report handling for blocked requests).

Final full regression: **1,363 passed, 58 skipped, 15 subtests passed**. Native
checks ran with repository-local temporary directories. The 58 skips comprise
seven host symbolic-link cases and 51 opt-in live gates; they are separate from
the two explicitly run model audits above. No deterministic failures occurred.

Reproduce the unchanged tests with:

```powershell
runtime/python/python.exe -B -m tests.simple_skill_live_validation
runtime/python/python.exe -B -m tests.simple_skill_live_validation --model-id model.gguf --root state/test-artifacts/simple-skill/qwen3b-audit
```

Use fresh artifact roots for additional independent live runs. `--report PATH`
refreshes derived summary fields without starting a model. Empty answer evidence
is reported as unexercised, rather than as verified injection or tool behavior.

Ignored artifacts under `state/test-artifacts/simple-skill/` include:

- `import-summary.json`: HTTPS import and cleanup evidence.
- `model-audit/live-summary.json`: 14B context-blocked run.
- `qwen3b-audit/live-summary.json`: 3B activation and tool results.
- Each audit's `runs/*/review-answer.txt`: isolated synthetic answers for review.
- `focused-final.xml` and `full-final.xml`: deterministic regression evidence.

Summary files retain counts, fixed test identifiers, model/skill identities and
hashes, status and outcome flags. Synthetic response text stays in separate ignored
review files. No keys, user conversations or user file contents are captured.
