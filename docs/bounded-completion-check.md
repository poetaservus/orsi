# Bounded completion checks

This change starts from local main `c45f42f` on `codex/bounded-completion-check`.

The preceding fix retained a proposed answer through review tool calls, but
still let completion review gather evidence and perform work indefinitely up
to the general turn limits. The new report showed a summary followed by an
identical-call stop and a malformed directory cursor during that check.

A fresh live run with the exact screenshot prompt reproduced the completion
stall: the summary appeared on request 7, then the checker kept reading until
request 37 stopped at the identical-call guard. This run did not reproduce the
specific malformed cursor; that case is covered by deterministic regressions.

## Contract

Completion checking is now an assessment-only phase. It compares the current
request and standing requirements with the proposed answer and settled evidence,
then returns ready, continue with concrete remaining work, or blocked with a
reason. A continue assessment resumes the normal work loop in the same turn,
with its existing permissions, approvals, recovery rules and budgets. Reads,
corrected edits and project verification remain available in that work phase.

The OpenAI Responses adapter sends `tool_choice="none"` for assessment while
retaining the capability definitions needed to validate and replay settled
calls. Normal work still uses automatic tool selection. Hybrid, lazy and
cloud-to-local fallback adapters preserve the review boundary. The runtime also
rejects every tool proposal during assessment, before permission handling,
execution, settlement or provider replay. Rejected proposals and invalid
assessments share the existing consecutive format-failure budget: two attempts
in the current configuration. They cannot start a directory-cursor retry loop.

An unsuccessful check leaves the goal unfinished and retains the proposed
summary as incomplete partial text, with an explicit failure notice. Internal
review output remains hidden from streaming and standalone provider replay.
Directory cursor validation is unchanged; malformed cursors are not silently
accepted. Acceptance prompts, routing, sampling, model profiles and context
policy are unchanged.

The provider setting follows the official [Responses API tool-choice contract](https://developers.openai.com/api/reference/resources/responses/methods/create).

## Verification

The live acceptance prompt was unchanged from the new screenshot:

```text
read this project and summarize please

C:\Users\yaboy\Desktop\orsi_website
```

All runs used the existing `gpt-6-luna` profile, the actual OpenAI SDK/SSE
adapter, production runtime/conversation handling and real project reads.
The user authorized reuse of the key file and transfer of this project's source.
The key was read privately and was not copied or logged. The harness confined
reads to the authorized project and denied mutation/execution approvals.

| Live run | Model requests | Capability attempts | Result |
| --- | ---: | ---: | --- |
| Previous main, direct cloud adapter | 37 | 50 | Summary, then repeated-call stop |
| Repaired direct cloud adapter | 7 | 21 | Summary completed; one assessment |
| Repaired app hybrid wrapper, fresh chat | 7 | 18 | Summary completed; one assessment |

Both repaired assessments used disabled tool selection and returned ready in
one request, taking approximately 1.2 and 3.3 seconds. Both runs had zero
protocol failures, zero assessment JSON previews, ordinary summaries as final
answers and released API resources. Content-free reports are under ignored
`state/bounded-review-before/`, `state/bounded-review-after/` and
`state/bounded-review-hybrid/`. Raw live conversation/provider replay files were
removed after each run.

Qualification passed **354 distinct focused checks**: 351 in the main focused
run, followed by three successful rechecks after fixture corrections. Coverage
includes native and text-fallback assessment violations, the malformed cursor,
write-approval isolation, same-turn reads/edits after continue, known blockers,
budgets, immutable recall paging, cloud/lazy/hybrid/fallback delegation, real SDK
wire requests and provider replay, interruption, streaming and scrolling.

The main run exposed two older fixtures that also failed in an isolated process
loading unchanged main production modules in memory. One expected 12 built-ins
before the two project tools were added; the other omitted the existing
completion-assessment response. Their expectations were corrected without
changing their acceptance prompts or permission/persistence assertions. The
third correction enabled required metadata support in a new list-tool fixture.

The actual chat widget was inspected during a held assessment stream and in a
follow-up turn. An app appearance check using synthetic text confirmed that a
failed assessment retains the readable summary with a clear incomplete notice;
the screenshot is ignored `state/bounded-review-unfinished-preview.png`.
The full suite and live local-model gates were not run, following the request
for necessary tests only. Configuration was preserved and no website edits or
remote publication were performed.

Content-free integration evidence is under ignored
`state/backups/bounded-completion-check-20261011/`. Preserve prior main at
`archive/2026-10-11/main-before-bounded-completion-check`, commit, fast-forward
local main and remove only the merged feature branch. Other worktrees and
historical/unmerged branch tips remain intact.
