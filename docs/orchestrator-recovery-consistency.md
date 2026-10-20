# Coordinated inspection recovery, 20 October 2026

## Defect and bounded change

The repair guard previously replaced its required inspection receipt/read boundary
on every failed observation, while the project progress guard renewed source reads
only for bounded new evidence. Repeating the same defect could therefore demand a
read the repetition guard would block. Rejected edit proposals also consumed the
same repetition allowance as execution, even after their prerequisites changed.

One repair tracker now owns inspection admission and source-read renewal. Equivalent
failed observations on an unchanged revision share the original read boundary;
their runtime-owned receipts are accepted as equivalent evidence. A genuinely new
scope receives a matching bounded allowance, or an explicit exhausted-reassessment
result. Unresolved scopes accumulate and only matching successful assertions clear
them. Requested assertion values are part of the scope, so another option/text
value cannot clear a failed requested-value check. Proven settled project changes
renew the existing reassessment budget.

A separate turn-local repetition tracker permits one model-requested retry of a
preflight-rejected mutation after a complete current target read is received.
Contiguous original pages qualify; incomplete, failed, same-batch and invalidated
reads do not. Diagnosis/reversal prose does not create a different operation.
Approval, unknown-outcome, ordinary preflight, rollback, target-failure and global
work limits remain in force. No settled or uncertain mutation is replayed.

Browser inspection supports exact native `select_option`, verifies the retained
selected value and leaves resulting app behavior to its own assertion. Unsupported
action/element combinations are inspection errors. Real runtime problems alongside
those errors still establish a repair obligation. Desktop use is rejected.

## Reports and saved evidence

Stopped outcomes retain the proposed answer explicitly as unverified and identify
the actual undispatched repeated capability/count/prerequisite separately from the
latest settled failure. Diagnostic metadata contains identifiers and fixed reason
categories, never raw arguments or source bodies.

Completion reviews are anchored to their original settled-call prefix. Later tool
results mark an older assessment stale; saved conversations validate it against
that prefix and the corresponding delivered pixels. Current completion requires a
current review. Unknown pixels and inconsistent/missing anchors are rejected.
History/recall preserves stale assessments as earlier assessments rather than
reintroducing their remaining-work strings as current requirements. Existing saved
outcomes without the optional fields retain their previous validation behavior.

## Focused qualification

Only essential focused checks run; selections overlap and are not added:

- Initial affected regression selection: **161 passed** across recovery, project
  progress, bounded edits, current-task completion, completion review, evidence and
  stop diagnostics.
- Affected source-read/inspection/approval/paging recheck: **81 passed**, three
  native-named cases deselected for their separate native run.
- Final obligation/repetition/anchored-history selection: **70 passed** across
  `test_orchestrator_recovery_consistency.py`, `test_repair_loop.py` and
  `test_project_recheck_progress.py`, including the cases deselected above.
- Focused native selection: **21 passed** across native option selection, selector
  versus product failures, and unavailable-preview recovery.

The final combined workflow runs through real Chromium and an owned disposable
HTTP preview, with a scripted model: two prior reads; unavailable preview; a proposed
answer and continue review; failed app assertion; two rejected edits; fresh source
read; equivalent failed inspection; exactly one successful edit; saved source read;
passing option and app-text assertions; screenshot delivery; updated answer and
current ready review. Every owned inspection process is released. Local and cloud
runtime modes also pass the deterministic version of this sequence. Negative cases
retain genuine no-progress stops, wrong receipts, unresolved older scopes, partial
reads, denial/unknown outcomes and invalid review anchors.

Initial test-fixture mistakes (an unsupported timeout field, page arguments and
missing scripted image-token accounting) were corrected without changing production
capacity policy or acceptance prompts. An initial sandboxed browser run hit its
worker deadline; unrestricted focused runs pass. It is not called a product failure.
All final runs disable the pytest cache and use repository-local `--basetemp` paths
under `state/test-tmp/recovery-*`. Whitespace validation passes.

No full suite or live OpenAI/model qualification is run. Native checks use synthetic
HTML and scripted semantic assessments; they do not establish live-model visual
judgment or replay the encrypted historical incident. The exact old blocked proposal
has not been recovered. No API credential, user project, settings, accepted model
profile, sampling, context policy or core prompt is changed. The running app is
preserved and requires a restart to load the repair.

## Local integration

Branch `codex/orchestrator-recovery-consistency` starts from local main `c5b0d82`.
Preserve that tip at `archive/2026-10-20/main-before-recovery-consistency`, commit the
bounded change, fast-forward local main and remove only this merged feature branch.
Other worktrees, historical/unmerged refs and remote refs remain intact.
