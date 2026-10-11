# Live completion-loop repair

This bounded change starts from local main `afc4e14` on `codex/live-completion-loop`.

The previous recall repair addressed unstable history pages. A live reproduction
with the user's authorized `Desktop/orsi_website` source exposed a separate
completion-state bug. After streaming a summary, completion review called a
read tool. The runtime cleared the proposed answer unconditionally. It then
treated the review's ready JSON as another proposed answer and started another
review, eventually stopping at the identical-call guard.

The runtime now keeps the proposed answer through review reads and evaluates
the assessment against that answer. A normal revised answer after review tools
gets its own check. Writes and execution during review invalidate the old
answer's coverage and require an updated answer before completion. A misplaced
assessment during resumed work is a bounded format error, never a user answer.
Known denied or unresolved edits still override positive model assessments.
Cancellation, approvals, source recovery and existing work budgets remain active.

Conversation streaming receives an explicit review-phase signal. Review text
and empty tool previews cannot erase the visible summary; provider activity
shows “Checking completion…” during the check. Standalone assessment messages
are excluded from durable provider replay. An interrupted check preserves the
summary as unfinished partial text, without exposing partial assessment JSON.
Observer cleanup and phase state are scoped to each user turn.

## Verification

The acceptance prompt, project, model profile, sampling, routing and context
settings remained unchanged. The prompt retained its original spelling:

```text
please read this project and sumarize it to me

C:\Users\yaboy\Desktop\orsi_website
```

All three live runs used the existing `gpt-6-luna` profile through production
`ConversationService`, the actual OpenAI SDK and streaming adapter, real local
read receipts and durable turn handling. The API key was read privately from
the user-authorized file and was not logged or copied into the checkout.
Source transfer to the OpenAI API was explicitly authorized. Test permission
rules confined reads to the target project and denied mutation/execution
approval requests.

| Live run | Model requests | Capability attempts | Outcome |
| --- | ---: | ---: | --- |
| Before repair | 38 | 35 | Repeated identical call; unfinished |
| After repair, fresh chat | 11 | 23 | Summary completed; ready review |
| After repair, another fresh chat | 16 | 22 | Summary completed; ready review |

Both repaired runs had zero protocol failures, zero assessment JSON previews,
ordinary summaries as their final answers and released API resources. The
content-free reports are under ignored `state/live-completion-before/`,
`state/live-completion-after/` and `state/live-completion-after-repeat/`.
Raw live conversation/provider replay files were removed after the runs.

The final focused native run passed **210 tests**. Coverage includes the exact
answer → review tools → ready sequence, multiple evidence reads, immutable recall
pages, revised answers, routine edits, denied approvals, malformed assessments,
interrupted checks, constrained text fallback, existing limits, provider replay,
conversation persistence, streaming and scroll position. A real SDK/SSE test
holds a review stream open while the actual chat widget retains its summary,
then checks completion and streaming in the next user turn. A synthetic app
appearance check confirmed readable text and completion status without overlap;
its screenshot is ignored `state/live-completion-preview.png`.

Sandbox handle restrictions were rerun in an unrestricted native shell. One
pre-existing startup test expected a configuration from before the four
verification/context features already enabled on main. Its expected dictionary
was updated; production configuration did not change. The full suite and live
local-model gates were not run, following the request for necessary tests only.

Content-free Git preservation evidence is under ignored
`state/backups/live-completion-loop-20261011/`. Preserve prior main at
`archive/2026-10-11/main-before-live-completion-loop`, commit the verified change,
fast-forward local main and remove only the merged feature branch. Other
worktrees and historical/unmerged tips remain intact. No remote publication.
