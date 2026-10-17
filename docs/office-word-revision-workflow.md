# Word revision workflow and finalization, 18 October 2026

Bounded branch `codex/word-revision-workflow` starts from clean local main
`a862446`. That Word save fix is retained. Only essential checks are authorized;
no remote operation, user-document edit, model/profile change or full-suite run.

## Demonstrated cause and evidence limits

The reported save, later edits and final authoring conflict do not establish that
the document required more rewriting. The exact historical tool arguments and
model findings were not supplied; private conversation history was not decrypted.

The execution path is `AgentRuntime` -> journaled `OfficeCapability` -> connection
mutation preparation -> `LiveOffice`/`WordEdits.prepare` -> approved native write.
`word_compose` requires all cursor fragments of a complete authoring snapshot.
Layout reads do not supply that document state; render snapshots live separately.
A successful save clears native authoring snapshot authority. Before this change
there was no Word-specific continuation state binding inspection, correction and
save evidence to one content revision. General call fingerprints included fresh
snapshot IDs and therefore could not identify semantic revision cycles.

The isolated native gate reproduces the wrong-layout-snapshot rejection before
any write, then succeeds with a complete fresh authoring read and one composition.
It also demonstrates a justified correction, clean review/save/completion, and a
closing-model-response failure that preserves the successful save receipt. This
establishes the contract/control-path gap, not the exact historical model choice
or the editorial quality of the user's already-produced document.

## Bounded implementation

`WordWorkflow` uses the existing normalized native package signature. Body,
formatting, sections, pictures, headers and footers participate; transport IDs and
Word's volatile revision identifiers do not define a new content revision.
Complete authoring authority, rendered-page coverage, delivered image coverage,
findings, checked requirements and save receipts are tracked separately. Applied
edits and observed external revisions invalidate current inspection/save evidence.
Saves also clear advertised authoring authority. Historical successful receipts
remain in settled tool results; evidence includes recent receipt IDs and a count.

The Word-only `office.word_review` contract records a current revision, observed
defect, page/location, unmet user requirement and requirements checked. After
initial composition, including a no-op composition, another edit requires concrete
recorded defects. Empty/blank findings or a clean review cannot authorize another
rewrite. A correction pass consumes its authorization. Every page is inspected
again afterward, covering affected pages and downstream reflow conservatively.
Vague cosmetic improvement alone grants no correction authority.

Returning to the same semantic revision is detected independently of read IDs.
Repeating a correction for that revision and the same normalized unmet requirement
set is blocked, even if defect wording changes. A distinct observed requirement
can justify further work; there is no new edit-count cap. This does not claim
semantic equivalence detection for arbitrarily paraphrased user requirements.

Visual evidence never becomes authoring authority. Wrong snapshot feedback asks
for a complete fresh authoring read only for a justified replacement; no settled
edit is replayed. Current clean review must precede the final save. The runtime
then directs completion and rejects unsupported/stale/failed-image review attempts.
A failed initial write also cannot earn completion. Blocked outcomes retain their
original status/errors and explain current review/save evidence locally, including
when the closing model response fails.

The existing Word PDF export/rasterization and image delivery path is used, not a
new screenshot system. Chunk coverage must be complete and match the current
revision; runtime review additionally requires that every page image actually
entered this model's transcript. Layout/page counts alone cannot qualify. Models
without image support receive an explicit unverified outcome. Synthetic legacy
adapters without native packages/pixels retain their older receipt path and cannot
claim native review qualification.

Word tool descriptions were compacted to accommodate the review contract inside
the unchanged schema budget. The accepted manifest is updated; maximum selected
Word projection is 22,399 bytes / 7,995 reserve tokens, below 22,500 / 8,100.
Excel's tool set, input definitions, edits, saves and runtime behavior remain
unchanged. Shared retry budgets, routing, context policy, model settings, core
prompts and acceptance prompts are unchanged.

## Essential verification

- Combined deterministic selection: **225 passed**, no failures/skips, 58.73 s.
  It covers Word authoring/save, contracts, bridge/runtime/conversation, rendering,
  Office read renewal, approvals and unchanged Excel edits/catalog behavior.
- Final focused workflow/save selection: **33 passed**, no failures/skips, 5.79 s.
  Four checks added after the combined run cover failed initial writes, save after
  clean review/no-op composition, cleared authoring authority after saving, and preservation of a known save when
  subsequent revision evidence cannot be captured.
  There are **229 distinct deterministic checks** across these selections.
- The 15 workflow checks cover wrong evidence, image transfer/delivery, fresh native
  and transport identifiers, alternating revisions, 30 distinct necessary
  corrections, stale inspection/save invalidation, clean completion, and retained
  saves after a closing failure or a post-save evidence failure. Existing `a862446` save regressions remain passing.
- Separate real Word/production SDK/stdio/STA/executor gate: **1 passed**, 37.17 s,
  with one test-owned two-page DOCX. Exactly two compositions occur: initial Draft,
  then the explicitly observed title correction to Final. Both page images reach
  the scripted vision model; clean review is followed by save and completion with
  no third rewrite. A separate closing failure retains its save receipt and precise
  report. Reopen confirms title/pages. Owned bridge, scratch and Word process exit.
- Manifest/budget verification, compilation and whitespace checks pass.

The first restricted-shell bridge attempt stalled in startup/shutdown; ordinary
Windows permissions passed those boundaries. Initial contract assertions needed
the new read-tool count/classification. The first native fixture lacked image
input token accounting and failed before finalization; its teardown also reported
RPC errors. The corrected fixture then passed. These are retained as investigation
failures, not hidden or relabeled product/live-model passes.

Evidence is under ignored `state/word-workflow-*.xml` and
`state/word-workflow-contract.json`. Native synthetic artifacts are under the
repository-local `.pytest-tmp-word-workflow-native-qualified/` directory. Findings
and completion are scripted; no paid/live model acceptance or full suite was run.
Image delivery is verified, but actual model judgment, arbitrary requirement
paraphrases and historical article quality remain unqualified. Neither
`Desktop/computers.docx` nor the historical article task was opened or modified.

Pre-integration refs/worktrees and a verified complete-history bundle are under
ignored `state/backups/word-revision-workflow-20261018/`. Prior main is retained at
`archive/2026-10-18/main-before-word-revision-workflow`. Commit the bounded change,
fast-forward local main, and remove only this merged local feature branch. Preserve
other worktrees, historical/unmerged tips, settings and all remote refs.
