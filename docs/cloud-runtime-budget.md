# Cloud work budget and progress retention

The bounded `codex/cloud-runtime-budget` change starts from local main `0ff7bff`.
The reported cloud failure used every one of the configured 32 model steps and
32 requests. There were also separate 32-call and 32-record ceilings. Raising
only the step setting would have exposed those other ceilings next.

## Behavior

Cloud turns default to 128 steps, 128 model requests and 256 capability calls.
The three cloud settings have matching finite validation ceilings. Local turns
retain 24 steps, 32 requests and 32 calls, with the existing 32-step local ceiling.
The active backend selects all three budgets, including skill-scoped runtimes.
Older configuration files continue to load; explicit smaller cloud step limits
remain respected. Cloud request/call settings default independently when absent.

Durable outcomes, settled/recovered calls and Responses evidence accept the
corresponding larger counts. Completion history allows 129 records: the 128
physical requests plus one preplanned tool step that uses no model request.
Existing history loads without
migration. The existing transcript, conversation-byte, context, cancellation,
approval, repeated-call and malformed-response boundaries still apply.

Cloud guidance permits the existing maximum of seven independent metadata checks
in one response, with separate authorization, execution and journaling for every
call. Other calls remain single. Discovery stays within the user's requested
scope and may reuse settled evidence. Model profiles, sampling, routing and
context recovery policy are unchanged. Acceptance prompts are unchanged.

When a cloud step, request or call budget is reached, the outcome remains a
stopped turn. A deterministic progress summary counts successful operations
and reports unsuccessful operations separately. It does not claim that the task
is complete, include file content or perform another model request. The chat
shows a paused-task notice instead of a raw exception. That notice is retained
in completion metadata for restored messages.

The user can send a continuation in the current conversation; settled results
are available to the next turn. There is no automatic replay or automatic extra
API spending at a budget stop. Explicit fresh-session behavior is unchanged.
Restart O.R.S.I. to load the revised code and accepted runtime settings.

## Verification

Final native Windows focused regression passed **246 tests** in **87.76 seconds**:

- A cloud task completed 40 metadata operations and its final response in 41
  requests, beyond the old cutoff; persisted completion history reopened safely.
- A real cloud/local/cloud backend switch applied each mode's three budgets.
- A cloud pause retained 128 settled results and 128 Responses records, made no
  request 129, reopened safely and requested again only on explicit continuation.
- A synthetic batched reader exercised the 256-call ceiling and durable history.
- Real native seven-call metadata batches retained every independent result.
- Thirty-three separately approved edits completed in 34 requests, preserving
  CRLF, unrelated bytes and an untouched file; all approvals were consumed.
- An approved edit followed by a small cloud-budget pause remained known after
  store restoration; the follow-up issued no second edit or second approval.
- Independent step/request/call limits and over-ceiling validation were checked.
- A preplanned tool step plus native-to-text fallback reached the full 128
  physical-request budget and safely serialized all 129 completion records.
- The worker emitted the paused summary through its finished signal, and the
  restored GUI message displayed the paused notice.

Focused evidence is in ignored `state/pytest-cloud-runtime-final-focused.xml`,
using repository-local `state/pytest-cloud-runtime-final-focused/` temporary files.
Final full native regression passed **2,414 tests and 15 subtests** in
**422.06 seconds**, with **58 separately recorded skips** and no failures or
errors. Those skips comprise 51 opt-in live model/provider/UI gates and seven
host-dependent symbolic-link checks. Full evidence is in ignored
`state/pytest-cloud-runtime-final-full.xml`, with repository-local
`state/pytest-cloud-runtime-final-full/` temporary files.

The initial full run passed 2,412 tests and 15 subtests with 58 skips, but
`test_repository_limits_reject_before_copy[bytes]` failed and errored during
temporary Git-folder cleanup (405.54 seconds). All 60 existing skill Git installer
checks passed on the native focused rerun. No installer code was changed.

Live provider gates are **not run**. Verification uses scripted models, synthetic
Responses evidence, real temporary Windows file operations and native Qt.
The user's credential file and runtime selection state were not modified.

The verified complete-history recovery bundle contains 104 refs and preserves
ref/worktree identities under ignored
`state/backups/cloud-runtime-budget-20261008/`.

Preserve prior main at `archive/2026-10-08/main-before-cloud-runtime-budget`;
after full regression, commit, fast-forward local main and remove only this
merged local feature branch. Other worktrees and remote refs are outside the change.
