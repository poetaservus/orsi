# Deep test and legacy-code audit, 18 October 2026

Five retired definitions and their unused translation source are removed. Three
reproduced failure modes are repaired: runtime-free chat, admitted agent picture
binding and owned inference cleanup after polling errors. The full native suite
records **4,480 passed, 53 failed, 79 skipped and 15 passing subtests**. The suite
is not clean: localization coverage, Word guidance/test drift, an obsolete local
stop expectation and two unexplained native failures remain explicit below.

## Scope and method

Baseline: clean local `main` at `220263c`, active checkout `Desktop/orsi_test`.
Work is bounded to `codex/deep-test-audit`. Three independent subagent reviews
covered reachability, assertion value, and lifecycle boundaries. The primary
review reproduced findings and owns the edits and verification.

The static inventory covers **526 tracked Python files**, including **247 app
modules**. Test inspection covers **232 test modules / 2,221 original test
definitions**; parametrization produces more collected cases. Ignored runtime,
state, copied worktrees and old pytest trees are excluded from code searches.
Definitions were checked against qualified imports, aliases, attribute/string
dispatch, entry points, documentation and migration history. A low reference
count alone was not accepted as proof of dead code.

No tests were deleted, newly marked skipped, weakened or rewritten to accept failed behavior.
Acceptance requests, prompts, routing, model profiles, sampling and context
policy are unchanged. The model-profile loader cleanup below removes a callerless
wrapper, not a profile or selection behavior.

## Bugs reproduced and repaired

### Plain chat crashes before inference

Baseline `ConversationService._run_chat_turn` resolves `office.image_register`
through `self.agent_runtime`, although runtime-free chat is a supported path.
The picture-binding block introduced by `45c4240` dereferences `None` before
calling the model. Existing conversation, encrypted-history and skill activation
checks reproduced the failure: **16 failed / 54 passed** in the initial focused
selection. The blocked worker-event assertion has the same cause: inference is
never entered. These are useful integration tests, not obsolete chat coverage.

The binding now runs in `_run_agent_turn`, after admission and before dispatch.
Plain chat does not need an Office capability registry.

### Agent turns cannot discover admitted picture attachments

The same misplaced block never executes for agent turns. A real
`ConversationService`, real `AgentRuntime`, unconnected `OfficeConnection`,
temporary attachment store and scripted attachment-capable model reproduce the
problem without native Office or a provider request: the admitted PNG is denied
by `picture_source`. Existing lower-level picture tests manually bind their
sources, so they could not detect this missing production wiring.

The new service-level regression fails on the original placement. It checks
source availability **inside model dispatch**, follow-up access, rejection of an
unattached image and an attached non-image document, and rebinding/exclusion of
prior sources on the first dispatch of a new session. The original permission
boundary remains in force.

An intermediate post-fix trial exposed an incomplete scripted test double: it
returned ordinary text to a completion-review request. The fixture now uses the
existing `ready_review_for` helper. Production review policy was not changed.

### Failed polling leaves owned inference handles open

`app.inference.owned_process.OwnedProcess.close` previously called `poll()` before
releasing its finalizer. A failure in either `WaitForSingleObject` or
`GetExitCodeProcess` raises with both handles still open and the ownership
finalizer still armed. `LlamaServerInferenceEngine._stop_process` reaches this
method even when termination itself fails.

Both synthetic Windows API cases fail before the repair. The repaired `finally`
path releases the job and process handles, retains the polling error and marks
the owner terminal. The parameterized regression checks the original Windows
error, both handles closing exactly once, inactive finalization, terminal polling
and harmless repeated close. Existing real process/job tests remain intact.

### Baseline localization defect remains open

`ui/chat.py` acquired `ui_text("Task stopped locally before completion.")` in
`fdba4a1`, but all 45 catalog sources omit that phrase. Reconstructing the source
inventory with the original `main` Settings module and original Git catalog blobs
proves the same gap at `220263c`; this is not a consequence of the audit cleanup.
The visible stop explanation falls back to English and catalog validation fails.

The existing localization selection reports **47 failed / 26 passed**: 45 exact
catalog checks and two Hungarian maintenance checks blocked by the same coverage
gap. The required phrase needs a separate translation/review update. No source is
added to a fallback list and no validation assertion is weakened to hide it.

## Other full-suite failures and follow-up evidence

All six additional failed cases were rechecked unchanged with fresh disposable
fixtures and unrestricted Windows access: **four failed / two passed**.

| Case | Evidence and classification |
| --- | --- |
| `test_office_word_compose_validation.py:298` | The old default-body-width and header/footer-margin guidance disappeared from the tool description in `be5d21d`; cross-field constraints remain enforced but are not expressed by the individual schema bounds. This is a contract-guidance gap. Its four control-character negatives also use obsolete `pages` input against the live `sections` schema: a clean `pages` plan fails too. These negatives do not prove their intended payload checks. Separate pure checks pass a live-shaped positive control and reject all four bad controls at their intended pattern paths. |
| `test_office_word_compose_validation.py:361`, corrected branch | The script exhausts its responses. Direct synthetic tracing proves one dispatch and one approval after the invalid initial call. Its successful receipt supplies no `word_workflow`, so the current finalization guard correctly requests more evidence and the three-response fixture cannot finish. This is fixture drift, not proof correction dispatch fails. Model requests, approval and settled-result shapes were captured without prompt/document contents. Do not bypass verification or relabel unverified work completed to fix it. |
| `test_office_word_compose_validation.py:392` | Exact uppercase `COMPLETE body` wording is stale; the current description still requires replacement of all content. The substantive provider/schema break-only rejection assertions pass before the obsolete wording assertion. Preserve those assertions when updating the wording check. |
| `test_routing_diagnostics.py:288` | The test expects `IncompleteResponseError`; `fdba4a1` deliberately introduced distinct `AgentStoppedError` for local recovery stops. Baseline main has the same branch. Logs and durable counts prove repeated-call status, three semantic corrections, five settled calls, two successes and three failures. No diagnostic loss was observed. The stale expectation prevents the later follow-up/no-replay assertions running; update the expected type while retaining those checks in a separate bounded repair. |
| `test_project_verification.py:88`, cancellation | The full run observes the child's PID still present after cancellation. The PID file **does exist**; this is not an initial readiness failure. The isolated case passes unchanged. Shared runtime cleanup terminates the job, waits and checks zero active processes, while the assertion retains only an integer PID. Existing evidence cannot distinguish a live survivor from PID/object-visibility races. This remains an unexplained native cleanup assertion failure; it is not labeled a sandbox failure or a proven surviving child. A retained process handle/creation identity would resolve the ambiguity. |
| `test_vault_engine.py:351`, local profile | The full native run receives `WinError 5` renaming a disposable vault after lock. The isolated case passes unchanged. Static review finds scoped lease/directory-pin closure but no captured handle-holder identity or clear leaked owner. Rename denial is proven; its cause remains unresolved. A passing recheck does not erase the original failure. |

The Word contract/progress implementation and its original tests, shared process
owner, project verification implementation and vault engine are unchanged from
baseline main. The audit does not repair these additional cases by changing
prompts, completion policy, timeouts or existing assertions. Word guidance and
test-contract repairs, and identity-bound native diagnostics, remain follow-up
work. Two independent reviewers verified the classifications; synthetic Word
evidence is in `compose-evidence-proof.json` under the ignored audit directory.

## Legacy definitions removed, with replacement evidence

| Removed definition | Evidence and retained active behavior |
| --- | --- |
| `file_resolution._latest_user_text` | Its only caller was removed in `8d5e33d` when filename recovery became language independent. Current recovery derives scope from failed native lookup/read evidence. Remove the unused `re` import too. |
| `context.select_context_messages` | `53c3296` migrated orchestration to `select_context_request`, which returns the admitted messages and their exact budget. No remaining caller/import/export/dispatch was found. |
| standalone `context.estimated_context_tokens` | The same migration retired this wrapper. The distinct, active `ConversationService.estimated_context_tokens` remains and uses `context_budget`; same-spelling methods were resolved before removal. |
| `model_profiles.load_model_profiles` | Introduced in `28c2787`, with no tracked caller. `load_model_config` and `LocalModelCatalog` load and validate `LocalModelProfiles` directly. Remove its exclusive `load_json` import. |
| `SettingsDragStrip` | `302e182` removed construction when Settings became full-window. Main-window caption controls are reparented instead; the old panel movement APIs also disappeared. Remove its exclusive `ui_text` import, unused `QColor` import and retired catalog source. |

For four distinctive names, `git grep` against baseline `main` returns only their
definitions across app/tests/tools/packaging and entry-point documentation. The
fifth requires qualified resolution because the service meter has the same name.
History and the active construction paths support the removals independently of
test execution.

Meaningful retained checks cover exact context admission/budget agreement,
structured history and recovery, profile identity persistence and backend
replacement, extensionless filename disambiguation, Settings resize/draft
preservation and reparented caption controls. The focused selection runs those
paths after removal; no absence-of-symbol tests were added.

The first full run caught a missed build-time dependency in this cleanup:
localization extraction walks the UI's syntax tree. Deleting the unused class
also removes its `Move settings` source, making that retained catalog entry
surplus. The run was interrupted near 21% with 47 failure markers and no complete
JUnit result; it is not a completed or passing full run. Diagnosis found both the
audit-induced surplus and the pre-existing missing stop phrase described above.

The final cleanup removes only `Move settings` from 45 TS catalogs and regenerates
44 non-English QM files. Ordered message comparisons independently verify that
all **33,203** other messages and annotations are unchanged. Direct `QTranslator`
readback verifies all **32,466** remaining non-English translations and absence of
the retired phrase. The Hungarian fingerprint is updated for deletion only,
retaining prior maintenance and pending native review. The normal
`tools/ui_translations.py --compile` gate remains blocked by the missing stop
phrase; direct Qt compilation/readback is not reported as a clean validator pass.

## Tests and compatibility paths retained after investigation

* The two owned-process implementations are active. The inference owner and
  shared command/worker owner have different memory and cleanup policies.
  Similar native tests cover distinct code; consolidating them was not justified.
* The vault prototype is a documented, frozen phase-1 API with a benchmark CLI.
  Production vault tests also reject its incompatible format. Dormant production
  use does not justify deleting its tests or experiment.
* Compatibility dialogs, `_skill_blobs`, `ProfileSelection` and image-intent
  wrappers retain documented or test consumers of active behavior.
* `office_server`, `inspection_worker` and `launcher` have subprocess/shortcut
  entry points; ordinary imports are not their only reachability evidence.
  Qualification and benchmark modules also have executable consumers.
* Apparent tests without direct `assert` statements delegate to assertion
  helpers, unittest methods or executable documentation. No unconditional skip
  or xfail was found in the inspected test definitions.

One low-priority naming gap remains: the legacy
`test_image_settings_dialog_preserves_choices_and_busy_guard` checks persistence
but never enters a busy state. Active embedded-page checks in
`test_settings_panel.py` and service-level checks in
`test_image_generation_followup.py` exercise the busy guards separately. This
does not establish a product defect or justify deleting the persistence check.

Routing tests have measured value despite repetitive wording variants. The
unchanged **19-case** module passes normally. Three isolated in-memory AST
mutations are rejected: dropping the final catalog tool causes **16 failures**,
removing user-text validation causes **1**, and removing catalog validation
causes **2**. The route is called by the active conversation service. This is
targeted mutation evidence, not a suite-wide mutation score.

## Verification record

All pytest invocations use the bundled Python 3.12 runtime. Temporary roots are
repository-local and unique to each selection. Native runs use unrestricted
Windows access to avoid confusing sandbox restrictions with product failures.

| Check | Result |
| --- | --- |
| Original focused baseline: conversation, lifecycle, history compatibility, skill activation | 16 failed, 54 passed; retained as the chat-regression evidence |
| New owned-polling regression against original implementation | 2 failed; neither handle was released |
| New picture service regression against original placement | 1 failed; admitted image was unavailable at dispatch |
| Final focused selection, 16 modules | 273 passed, 2 opt-in Word gates skipped; 2 existing Qt deprecation warnings |
| Final explicit original-error assertion for owned polling | 2 passed |
| Retired catalog cleanup | 45 source deletions only; 33,203 remaining messages/annotations preserved; 44 QM files regenerated; 32,466 translations read back exactly |
| Existing GUI-language / Hungarian checks after catalog cleanup | 47 failed, 26 passed; baseline missing stop-message phrase remains |
| Six additional full-suite failures, fresh native recheck | 4 failed, 2 passed; failures and non-reproduction are classified above |
| Additional Word evidence, not a pytest pass count | Live-shaped positive control passes; four bad controls reject at the intended pattern paths; correction settles one invalid and one successful call with exactly one approval/dispatch |
| Agent lifecycle / routing checks | 8 / 19 passed; lifecycle overlaps the primary selection |
| Syntax parsing | All 526 tracked Python files parsed |
| `pip check`, `git diff --check` | Passed |
| First full run | Interrupted near 21%; 47 failure markers, no complete result; surplus/missing source diagnosis retained |
| Final complete existing suite, 4,612 collected cases | 4,480 passed, 53 failed, 79 skipped, 15 subtests passed, 2 existing Qt warnings; 1,609.97 seconds |

The **79 skips** are separate from failures and passing checks: **50** opt-in
live-model/provider cases, **18** opt-in native Office cases, **1** opt-in UI
case and **10** host/platform cases (eight symbolic-link restrictions and two
native-window platform cases). The run remains failed. JUnit counts 4,627 reports
because its total includes the 15 passing subtests; pytest collects 4,612 cases.

The first attempted focused command named a nonexistent test module and collected
no tests; it was corrected. Its pytest-cache access warning is environmental.
The later failing baseline ran with native Windows access and its application
exceptions are product evidence.

Ignored evidence lives under `state/deep-test-audit/`: JUnit results for the
baseline, red cases, focused checks and final full suite; both full-run logs;
content-free owned-handle comparison, baseline localization reconstruction,
ordered catalog/readback evidence and static scan. Focused passes overlap; counts are not
summed into a purported unique total. The static candidate scan is a heuristic
and is not a substitute for the qualified review above.

## Limits and remaining gates

This audit does not prove every remaining branch or test useful. It provides
tracked reachability/history review, selected failure injection and integration
checks. It does not supply a runtime line-coverage percentage or comprehensive
mutation coverage, and cannot establish unknown external imports of internal
application helpers.

Paid cloud/model acceptance, real model switching and opt-in native Office
document-quality gates have not run. These are separate from the deterministic
and ordinary native Windows tests. No user document, private settings, accepted
model profile, remote ref or other active worktree is changed.

Catalog validation is a demonstrated unresolved blocker: the required stop
message is missing in every language catalog. The Word guidance gap, three
stale Word test assumptions, stale diagnostic exception expectation and two
unexplained native failures above also remain. The low-priority legacy dialog
test-name overstatement remains; its active busy guards are covered elsewhere.
No complete full run is claimed clean while failures remain.

## Local integration and preservation

Prior main is retained at
`archive/2026-10-18/main-before-deep-test-audit` (`220263c`). Content-free ref and
worktree inventories are in the ignored audit directory. The bounded change is
committed, fast-forwarded to local `main` and only its merged feature branch is
removed under the repository workflow. Other worktrees, historical/unmerged tips,
remote refs and private settings are preserved. No remote action is performed.
