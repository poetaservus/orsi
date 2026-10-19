# Workflow reproduction fixes, 19 October 2026

The investigation established two deterministic defects behind the reported
workflows: image edits expressed without the word “image” missed native image
generation, and a failed Excel verification read could deny earlier confirmed
changes. Subsequent native verification also established an asynchronous
descendant-exit race in worker cleanup. The fixes preserve the original
reproduction prompts.

## Changes

* Image intent recognizes sunglasses/glasses and photographic adjustments such
  as blur and camera settings when a source image is available. Existing code,
  written-output, analysis and negation exclusions remain. Follow-ups use the
  current visual task; explicitly submitted sources retain priority.
* Excel read failure wording now describes the failed read alone. Turn-local
  reporting retains confirmed applied edits and save receipts for the affected
  session. Failed, unchanged and unknown writes do not establish applied edits.
  An unfinished verification still ends incomplete.
* Word uncertain-operation feedback exposes the existing allowlisted failure
  stage, category and HRESULT, and states that changes may already be present.
  It does not retry the operation or reinterpret an uncertain result as success.
* Encrypted personal diagnostics retain sanitized provider stream events and
  request timing/token measurements, instead of replacing them with generic
  diagnostic records. Raw errors, headers, credentials and conversation contents
  are excluded and inputs are revalidated at the storage boundary.
* Owned capability workers pin the processes in their job before termination,
  verify membership, and wait for the pinned process objects to signal before
  reporting release. Native evidence demonstrated that zero active job
  accounting alone could precede a descendant's completed exit. The process
  inventory retains the existing 16-process bound and no unrelated process is
  terminated. API contracts were checked against Microsoft's
  [IsProcessInJob documentation](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob).
* The existing local-stop explanation is added to all 45 UI source catalogs and
  the 44 non-English compiled catalogs. The Hungarian integrity record tracks
  the addition without changing its pending native-review status. The stale
  routing test now expects the established local-stop exception while retaining
  its durable receipt, terminal-count and follow-up assertions.

No model profiles, sampling settings, context policy, core prompts, acceptance
prompts or user settings are changed.

## Focused verification

* Image selection: 94 passed, including a review correction that keeps explicit
  new photos with blur/bokeh independent of earlier images. Three actual composer/service/SDK image turns at
  Luna Medium completed: initial image 17.266 s, exact sunglasses follow-up
  15.813 s, exact attached blur/focus/compression request 16.047 s. Source hashes
  establish both retained-source and submitted-source continuity. The resulting
  synthetic portraits were visually checked for sunglasses and blur; the amount
  of compression was not quantified. The encrypted installed Photography body
  was not exported; the skill-name routing boundary was checked separately.
* Office reporting: 34 checks passed, including the formerly failing actual
  memory-backed edit followed by an injected native read failure. A further
  focused Office selection passed 79 with one opt-in gate skipped. These
  selections overlap and are not summed.
* Two independent compact native Word compositions, with and without page
  numbering, passed readback verification and released the owned Word process.
* Provider/profile diagnostics, routing and vault selection: 90 passed,
  including storage-boundary privacy tests.
* Native cleanup, shell and project selection after the descendant-exit fix:
  121 passed. This includes the existing preview process-disappearance assertion
  and new failure-injection checks for zero job accounting with an unsignaled
  child. Thirty real native preview probes independently confirmed process exit.
* Root native language/routing selection initially passed 91 with one catalog
  insertion-order failure. The catalog order was corrected; the affected
  maintenance/routing recheck passed all 26 tests. No test assertion was removed.
* The complete packaging module passed all nine tests after restoring the
  catalogs' original Windows line endings. The prior full run exposed this
  introduced working-tree formatting error: Git export converted the edited
  LF catalogs to CRLF and the existing exact-byte assertion correctly failed.
  Its isolated failure and corrected module run are retained separately.
* The exact compact Word diagnostic request passed through the real composer,
  service, SDK and native Word bridge in 59.25 s (11 provider requests), at Luna
  Medium with the repository Typesetter body. Composition, render/review, save
  and model completion succeeded. Independent verification preceded cleanup;
  reopening the saved fixture confirmed its title, paragraph and single page.
  The owned Word and bridge were released. The encrypted installed skill body
  was not exported or assumed equivalent.
* The npm start request, with only the path changed to the complete disposable
  project copy, completed in 36.422 s (10 completed provider requests). HTTP 200
  was independently observed after 18.125 s, and the final answer confirmed the
  server without unrelated visual inspection. Source files were unchanged and
  owned processes/port released. This replay used Office disconnected and four
  local plaintext skills, rather than exporting the six encrypted profile
  skills. It does not prove the historical intermittent scope drift repaired.

These are focused results, not a substitute for the full suite or live model
acceptance. Ignored evidence is under `state/`, including
`image-followup-fix-live/summary.json`, `fix-office-feedback.xml`,
`fix-office-compact-native.json`, `fix-focused-root-native.xml`, and
`fix-focused-root-final.xml`. Additional live evidence is
`state/fix-npm-medium-mainwindow-20261019-replay/report.json` and
`word-compact-api-1792413659232726900/summary.json` in this task's visualization
directory.

## Remaining incident limits

The earlier actual Word operation changed its synthetic document body and then
failed before a confirmed save. Its precise native plan/stage was not retained.
The compact native checks pass; the change improves truthful failure evidence
without claiming that this historical failure's cause was repaired.

The previous npm run started a working server but returned an unrelated final
answer. No deterministic rule causing that scope drift was established. No
prompt or verifier was weakened to make that run count as passing. The historical
provider streaming errors likewise remain unassigned to a specific cause unless
new provider event evidence establishes one.

The first full-suite attempt was deliberately stopped after the image review
correction, so the final run starts with all reviewed source changes present.
It is retained as a superseded partial run, not counted as a pass or failure.
The next complete native run (`state/workflow-fixes-final-full.xml`) recorded
4,575 passed, two failed, 82 skipped and 15 passing subtests in 968.55 s. Its two
failures are retained: the introduced catalog line-ending issue described above,
and `test_native_inventory_rejects_contract_violations_before_activation[depth-limit_exceeded]`
failing at the final directory rename with WinError 5. The complete reference
reader module subsequently passed all 73 tests unchanged. That does not establish
the earlier rename failure's cause or erase it.
Two direct native stress runs reproduced rename denials in 18/100 and 5/100
attempts. All 4,100 tracked snapshot handle closes succeeded in each run. Native
process handle enumeration found zero own file/directory handles beneath the
fixture immediately after each of the five second-run failures, before garbage
collection; the detector was checked against deliberately held file/directory
handles. This argues against a retained reader file handle, but does not identify
the cause of the rename denial. No product retry or weakened assertion was added.
Evidence is retained in `state/skill-handle-stress-20261019*/report.json`.
The subsequent confirmation run (`state/workflow-fixes-confirmation-full.xml`)
recorded 4,574 passed, three failed, 82 skipped and 15 passing subtests in
1,467.59 s. Packaging passed. Two failures were the same directory rename denial
(depth and reserved-name cases). The third was the browser-preview process
release assertion: inspection and release receipts passed, but the server PID
still existed immediately afterward. Its complete command module passed
unchanged in isolation; that alone did not resolve the failure.

A separate native probe pinned the server process before cleanup and proved its
object was still unsignaled despite the release receipt, then signaled within
the subsequent bounded wait. This reproduced on the first attempt; the original
evidence is `state/preview-release-probe.log`. After the ownership fix, 30 native
preview runs all passed inspection and had zero unsignaled or existing server
PIDs after close (`state/preview-release-probe-fixed.log` and
`state/preview-release-probe/report.json`). Neither the production assertion nor
the test was weakened to accept a running process.

## Final verification

The full native suite after the descendant-exit fix recorded **4,578 passed,
one failed, 82 skipped and 15 passing subtests**, with two existing Qt
deprecation warnings, in **1,503.66 s**. Evidence:
`state/workflow-fixes-owned-exit-full.log` and `.xml`.

The sole failure is the same depth-validation directory rename with WinError 5
in `tests/test_skill_reference_reader_v1.py`. Its cause remains unresolved;
the prior native handle investigation did not establish a reader handle leak.
The full suite is **not clean**. No assertion was weakened, no test disabled,
and no additional rerun was made simply to obtain a green result.

The original browser-preview cleanup test and the catalog packaging test pass
in this full run. Focused cleanup/shell/project verification also passed all
121 cases (`state/workflow-cleanup-focused.xml`), and all 30 native preview
probes confirmed process exit. Ordinary-suite skips remain separate from the
additional controlled live API and native Office qualifications above.

The original reported intermittent provider streaming failures, the older
live-profile Word confirmation failure and npm scope drift have not been
proven resolved. Current controlled live checks pass; their profile/skill
limitations remain explicit. General image-analysis latency was not established
as repaired by the image-edit routing fix.

The running user app is preserved; code changes take
effect in a newly started process.
