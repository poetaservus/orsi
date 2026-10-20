# Completion review recovery, 20 October 2026

Bounded branch `codex/completion-review-recovery` starts from local main
`0881ba5`. The second supplied screenshot shows completed coding work followed
by `agent_review_invalid`, a different stop from the original semantic-correction
limit. The previous fix was present in the running checkout: the repository's
Python app launched after its changed source was saved. This was not established
as a wrong-checkout or pre-patch process incident.

## Reproduced defect and qualification gap

The previous live review schema required the model to reconstruct a receipt
ledger, including internal call IDs, outcome claims and screenshot references.
Even a reasonable task assessment could therefore exhaust both format attempts
after successful work. Validation failures were reduced to one generic stop;
their reasons were not retained by the encrypted profile's logging allowlist.

The previous scripted-model helper generated a perfect ledger from the prompt.
Those passing tests did not qualify a real model's ability to reproduce it. A new
regression with 72 successful project checks and an ordinary three-field ready
assessment reproduced the terminal format stop against the previous code.

The screenshot's exact rejected responses are not available. The encrypted user
profile was not bypassed or exported, and the original failure is not attributed
to a particular missing field. The defect and same terminal failure path are
independently reproduced below.

## Repair

The tool-disabled model review now returns only `goal_id`, `status` and
`remaining`. The strict cloud schema binds the current goal. Local text fallback
uses the same parser. Ready requires empty remaining work; continue/blocked
requires concrete remaining requirements. Malformed assessments still stop at
the existing limit, retaining the proposed report and settled work.

The runtime reconstructs the ledger from original current-turn receipts. It
keeps failed and stale checks, takes the latest observation of each owned shell
session, and distinguishes terminal execution from confirmed command success.
It does not fabricate server readiness, screenshot assessment or independent
behavioral verification. The semantic reviewer still assesses the request and
proposed answer against the transcript, receipt catalog, current scope and skips.

Durable outcomes mark the ledger's runtime origin; reopening recomputes and
checks its exact contents. Legacy model-origin assessments remain readable and
retain their prior validation. Unknown IDs, false passing/success/readiness
claims and screenshot delivery mismatches remain rejected. Successful receipt
bookkeeping is not proof of arbitrary task quality.

Rejected assessments retain fixed failure categories and counts, supply safe
correction feedback, and write allowlisted content-free encrypted diagnostics.
No response bodies, user paths, receipt IDs, conversation contents or keys enter
those diagnostics. A later presentation failure also retains settled work,
review evidence and review failure history. It is still a failed presentation,
not a completed turn.

Only review guidance/contracts, runtime ledger assembly, failure preservation
and related diagnostics/fixtures change. Execution permissions, approval,
cancellation, denial/uncertain-outcome safeguards, budgets, core/acceptance
prompts, routing, model profiles/sampling and context policy remain unchanged.

## Focused deterministic checks

No full suite was run. Native Windows runs with repository-local basetemp record:

| Selection | Result | Ignored report |
| --- | --- | --- |
| Completion recovery, current-task review, prior orchestrator regression, mocked OpenAI wire schema, profile diagnostics | 116 passed | `state/review-recovery-native.xml` |
| Agent runtime, mode limits, bounded edits and saved-history compatibility | 102 passed | `state/review-recovery-integration.xml` |
| Final changed review/diagnostic cases, including blocked reviewer tool calls | 66 passed | `state/review-recovery-final-named.xml` |
| Final recovery/persistence regressions, including later presentation failure | 13 passed | `state/review-recovery-persistence.xml` |

These selections overlap; counts are not added. Each final report has zero
failures/errors/skips. Earlier restricted-shell runs were interrupted after
stalling and are not clean qualification. An oversized-response test initially
used its entire input as a parameter ID, exceeding Windows temporary-path
limits; bounded test labels fixed that fixture error. The original red
regression and these incomplete/failed attempts remain separate evidence.

## Real model and native workflow

The user authorized reuse of their existing key file. It was read privately and
used in memory, without copying it into configuration, fixtures or reports.
Production `OpenAIResponsesInferenceEngine` and the configured `gpt-6-luna`
profile were used. Inputs were disposable synthetic fixtures, not user project
or conversation contents. Engines closed after every run.

| Controlled history | Previous code | Repaired code |
| --- | --- | --- |
| 81 shell/project receipts, current final build and test | Both attempts rejected; 392-character assessments, no provider truncation | First assessment valid `ready`; all 81 ledger entries reconstructed; 5.390 seconds |
| 80 receipts, final test stale after a shell command | Valid `continue` | Valid `continue`; all 80 entries retained; 6.156 seconds |

Reports are `state/completion-review-live-before-current/summary.json`,
`state/completion-review-live-after-current/summary.json`,
`state/completion-review-live-before/summary.json` and
`state/completion-review-live-after-stale/summary.json`. They retain categorical
outcomes, counts and timing, not response bodies. The exact baseline validation
message was not captured, so the comparison establishes rejection and recovery,
not a claim about a particular original rejected reference.

A real `ConversationService` workflow then edited HTML and a README in a
disposable sibling project, ran only its two immutable selected unittest checks,
and inspected a local preview using owned Chromium/server processes. The final
run recorded **completed**, **ready**, **zero format failures**, two successful
edits, both selected tests passed, and **one of one browser text assertions
passed**. It used nine model requests/seven settled calls in **23.172 seconds**.
Both file contents independently matched the requested outcome; the test file
hash was unchanged; the preview port released after shutdown. See
`state/review-workflow-live-20261020-assertions/summary.json`. The preceding
correctly configured run also completed with passing test/browser receipts in
27.625 seconds; its summary did not count browser assertions explicitly.

Earlier workflow attempts are not counted as successful gates: the first fixture
mistakenly placed the editable project under the protected application root,
correctly blocking writes; the next used module-name unittest loading with the
isolated embedded Python, causing import failure. Exact-file discovery ran the
same two unchanged tests successfully. No production permissions or test
assertions were weakened to correct these fixtures.

This is live model/API and native tool qualification of disposable workflows,
not a replay of the user's 18-minute session or a guarantee against every future
model assessment error. Screenshots remain observations requiring visual review.

## Integration and activation

Preserve prior main as
`archive/2026-10-20/main-before-completion-review-recovery`, commit the bounded
change, fast-forward local main, and remove only its merged feature branch.
Other worktrees, historical/unmerged refs, user settings and remote refs are
untouched. The running encrypted user app is preserved. Restart ORSI to load
this repair; already loaded Python modules do not reload from a Git update.
