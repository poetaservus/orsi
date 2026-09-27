# O.R.S.I. OpenCode-inspired reliability action plan

Original plan: 2026-09-24; failure review updated 2026-09-26

Accepted runtime baseline: Phase 1, `dc2d092` on local `main`

Status: Phase 1 source baseline restored; a narrow activation/routing recovery is recorded below. Both Phase 2 attempts rejected and undone; Phase 2 branch deleted. Future Phase 2 implementation awaits a new user instruction.

## Delivery tracking

This ledger is updated on each phase branch so reviewers can see the inherited baseline, current
work, verification state, and the next branch point without consulting a separate tracker. A phase
branch is created only after the preceding phase has merged to `main`.

| Phase | Branch | Status | Verification and handoff |
| --- | --- | --- | --- |
| Phase 0 | `codex/phase0-context-measurements` | Complete; merged to local `main` | Created from `main` at `4a4e819`. Added one shared numeric budget for selection, admission, diagnostics, and the GUI; content-free provider usage logging; and all five deterministic regression scenarios. Verification: 619 passed, 44 skipped; full suite passed again on 2026-09-26. Follow-up code review found no new blocking issue. User confirmed successful Phase 0 review on 2026-09-26. Fast-forwarded local `main` to `05512fc` before creating Phase 1. |
| Phase 1 | `codex/phase1-compact-edit` | User approved; source restored; recovery verified in fixture | Runtime baseline `dc2d092`. Deterministic suite at delivery: 674 passed, 46 skipped; local Qwen read/edit fixture passed. The user reported a better context window and approved Phase 1. The rollback snapshot omitted the edit enable flag. The subsequent user-reported failure required the narrow activation/routing recovery below; restoring the commit alone did not restore the requested behavior. |
| Phase 2 | `codex/phase2-paged-text-reads` (deleted) | Failed twice; rolled back; not accepted | First attempt: `894cc0e`, followed by `30d40c5`; rebuild: `f165f58`. The user reported worse context usage, longer thinking, and a refusal to edit an existing file. Both attempts had unresolved live gates despite passing deterministic suites. The user explicitly rejected Phase 2 and requested rollback; local `main` was restored to `dc2d092` and the Phase 2 branch deleted. See the failure review and retry gates below. |
| Phase 3 | `codex/phase3-tool-result-projection` | Not started | Create only after Phase 2 merges. |
| Phase 4 | `codex/phase4-model-aware-context` | Not started | Create only after Phase 3 merges. |
| Phase 5 | `codex/phase5-rolling-compaction` | Not started | Create only after Phase 4 merges. |
| Phase 6 | `codex/phase6-context-overflow-recovery` | Not started | Create only after Phase 5 merges. |
| Phase 7 | `codex/phase7-registry-materialization` | Not started | Create only after Phase 6 merges. |
| Phase 8 | `codex/phase8-invalid-call-feedback` | Not started | Create only after Phase 7 merges. |

Branch update rule:

1. Mark the active phase in progress when its branch is created and record the exact `main` commit.
2. Record material implementation checkpoints and deterministic test results as they land.
3. Before review, update the row with remaining manual or live-model gates.
4. Mark the phase complete only after merge, then create the next phase branch from updated `main`.
5. A passing deterministic suite is necessary but insufficient. Do not label a phase ready for
   acceptance while a required ordinary-prompt live gate fails. Record conditional diagnostic
   successes separately, and do not change a failing acceptance prompt to obtain a pass.

### Phase 2 failure review — 2026-09-26

The user rejected both implementations. Their observations take precedence over the earlier
"ready for review" label. The rollback is complete; this document update changes the future plan,
not the accepted runtime. The abandoned commit IDs above are diagnostic references, not approved
starting points; they may eventually be pruned after branch deletion.

Evidence comes from the user's reports and screenshot, the recorded tests in this conversation,
the abandoned implementations and their notes, and inspection of the restored Phase 1 code.
Historical test numbers below are records of those runs, not newly rerun measurements.

| Finding | Evidence and confidence | Consequence for the next attempt |
| --- | --- | --- |
| Normal use regressed | The user reported worse context than Phase 1, then approximately four prompts filling the window and longer thinking even when requests completed. First-attempt notes record a successful CSS fixture peaking at 14,666/16,384 estimated budget, including reserves. There was no matched Phase 1/Phase 2 multi-turn measurement with the same files, history, and effective settings. | Treat the regression as real; its exact token and latency causes remain unquantified. Establish the comparison before changing code. |
| Activation and tool visibility were confused with paging | The restored configuration omits `filesystem_edit_text_enabled`. First-attempt notes report whole-file writes and later activation of compact edits. The router does not recognize “add” in the screenshot request. These are inspectable integration gaps, including gaps inherited from Phase 1; the screenshot alone does not prove the complete configuration of that particular run. | Record effective flags and advertised tools at runtime. Resolve any prerequisite activation/routing defect as a separate, measured change rather than silently folding it into paging. |
| Too many variables changed together | The attempts changed read behavior, prompts, edit activation, tool selection, follow-up handling, and, in the rebuild, defaults from 16 KiB/200 lines to 4 KiB/100 lines. First-attempt notes also record 633 extra characters in the full read prompt before a later reduction. | Isolate changes and measure total request cost. Smaller pages can cause more tool calls and duplicated history; smaller excerpts alone do not prove lower context use. |
| Live paging was unreliable | First-attempt notes record requested offsets 4001 and 4002 producing attempted sequences `[4001, 4002, 4001, 4002]`, `[4001]`, and `[4001, 4002, 4001]`. The rebuild twice reached the 4,096-token output ceiling before a line-1201 tool call. | Test correct calls, stopping behavior, and the final answer. Separate output exhaustion from input-context overflow; the former is not fixed by claiming the latter. |
| The acceptance test was weakened | The rebuild's deterministic suite passed with 696 passed/48 skipped. A synthetic prior conversation plus the screenshot follow-up edited a disposable file successfully. A later paging test passed only after adding `/no_think`; that changed the conditions and did not establish ordinary-prompt reliability. | A cue-assisted result is a diagnostic control, not a replacement for the failing user-facing test. One successful synthetic workflow does not reproduce the user's session or establish repeatability. |
| Tool history and catalog size are coupled | Phase 1 exposes all available tools for some short confirmations and retains definitions for historical calls. Restricting history to the preceding turn during the rebuild caused “The initial model transcript is invalid” failures in folder-creation and listing/metadata follow-ups. Restoring historical definitions fixed those failures. | Do not trim definitions independently of retained call/result history. Any redesign must preserve valid transcript groups and the existing authorization boundary. |
| Paging added costs beyond returned text | Complete-line pages changed the old byte-boundary behavior. Full-file hashes required scanning the file for every page; the rebuild used separate page and digest reads. Windows path-stat and descriptor-stat comparisons required care about timestamp representation. | Specify compatibility, I/O, versioning, and boundary behavior before implementation; measure these costs and test mutation/timeout behavior. |

The most defensible explanation is a combination of integration weaknesses and insufficient
acceptance discipline. Paging was introduced into a system with configuration and routing gaps,
while context overhead and model behavior were changing at the same time. Passing capability
tests demonstrated local correctness, not a better application. We do not have evidence that
paging itself is inherently unsuitable, or that the model alone caused the regression. In
particular, output truncation before a tool call does not establish how all generated tokens were
spent or prove that the new schema and prompts were unrelated.

#### Establish a reproducible baseline before retrying

1. Start from the accepted Phase 1 runtime at `dc2d092`, plus any explicitly accepted later
   documentation or prerequisite changes. Do not restore or cherry-pick the abandoned Phase 2
   implementation wholesale. Keep a recoverable reference to the accepted runtime.
2. Record the actual launcher and checkout path, running process/revision, model file identity,
   loaded context and output limits, temperature, effective feature flags, and relevant environment
   overrides. The restored configuration specifies a 16,384-token context and 4,096-token maximum
   response. Do not confuse code supporting a tool with the running application enabling it.
3. Restart the application after switching versions/settings and start a fresh chat for each
   comparison. Use identical disposable copies of the same fixtures for both versions. Exercise
   `C:\Users\yaboy\Desktop\orsi_test\ORSI.cmd` and the development launcher separately;
   launching a different copy or reusing an old process is not a valid comparison.
4. Capture at least three runs per version of each required live workflow, including one continuous
   session of at least six user turns containing edits, a clarification, and follow-up requests.
   Record minimum/median/maximum latency, separating cold startup and approval wait from generation.
   Record request budget components before each model call, provider input/output usage and finish
   reason when available, tool call counts, repeated calls, returned bytes, and the GUI meter after
   each turn. Include schemas, prompts, wrappers, results, and retained history. Keep ordinary logs
   content-free; record fixture identities and expected outcomes in the test report.
5. Reproduce the reported workflows: the Documents/website CSS request, followed by normal continued
   work; and proposed JavaScript followed by “great, please add the javascript to the script.js file”.
   Use the exact wording quoted under Phase 2 below. If the original files or preceding conversation
   are unavailable, label synthetic substitutes and do not claim an exact session reproduction.
6. If baseline configuration or routing already prevents these workflows, record that as a
   prerequisite failure. Implement and review a narrowly scoped prerequisite separately, then
   establish a new accepted comparison point. Do not change the protected Phase 1 baseline while
   merely diagnosing, or use prerequisite fixes as evidence that paging improved it.
7. Set numerical context and latency tolerances from these measurements before implementation.
   Require no unexplained increase in peak request budget or tool calls for small-file workflows
   that do not need paging. An improvement must not depend on enlarging the context/output limits,
   changing the model, adding special prompt cues, or silently resetting the chat mid-workflow.

#### Phase 1 recovery after the rollback

The user subsequently reported “implement this into my style.css” receiving another false
inability-to-edit answer. Inspection of the saved conversation confirmed that wording; a direct
router check advertised only `filesystem.stat`, and the effective compact-edit flag was false.
The working tree recovery enables the already approved Phase 1 compact-edit capability and adds
file-targeted “implement/apply/add/append/insert” routing, with the legacy writer as a fallback
only when compact editing is unavailable. Phase 1 reader, model settings, and history handling
remain unchanged. Prompt corrections discovered in the next real-file reproduction are described
below. This is a prerequisite recovery, not a new Phase 2 attempt.

Verification: 681 tests passed and 46 skipped, including an opt-in local Qwen run using shipped
configuration, a synthetic prior CSS suggestion, and the exact “implement this into my style.css”
follow-up. It read a disposable stylesheet, performed an approved compact edit, and preserved
unrelated CSS without a reasoning-mode cue. This is not a claim of visible manual UI acceptance
or reproduction of the user's original stylesheet. Six idle ORSI model servers with absent
parent processes were also cleared; one retained approximately 9.6 GB of working-set memory.
Their contribution to earlier latency is unmeasured. Keep this recovery separate from any future
paging comparison and obtain the user's real-workflow confirmation before treating it as accepted.

#### Subsequent failure: ambiguous header edit — 2026-09-26

The user then reported the ordinary follow-up “add a gradient in the header in style.css” stopping
after 139.9 seconds with the identical-call limit. The saved conversation starts with “there is a
folder in my documents called website list the items there\\”. Logs show a successful listing and
read, then rejected attempts before any edit reached approval/journaling. The budget still had
space; this was not a demonstrated context-overflow failure. Preparation errors and rejected
arguments were not persisted, so the original repeated call's exact contents cannot be recovered
from those logs alone.

An isolated reproduction copied the actual 4,892-byte, 319-line stylesheet to a disposable Desktop
fixture and used both ordinary prompts, shipped settings, and the local Qwen model. It exposed an
invalid write path, then a 26-character declaration matching 12 locations. The model eventually
gave manual editing instructions despite having identified the correct header block. No file
bytes changed. The earlier tiny, seeded-conversation live test did not cover this failure.

Inspection found conflicting full-prompt instructions: reads were restricted to explicit read
requests despite edit guidance requiring a source read; and “After a write result ... do not call
another capability” included preflight validation rejections. The recovery now permits the source
read needed for an edit, stops after a **successful** write, and directs correction of
`invalid_arguments` rejections before an edit. Exact-edit schemas specify the absolute read-result
path and a unique excerpt including surrounding context (a CSS selector for a single CSS rule).
Ambiguity feedback explains that no edit happened and asks for a corrected, specific excerpt;
it no longer suggests an all-occurrences edit without the user's matching request.

The first corrected actual-file run still proposed two ambiguous excerpts (8 matches, then 2),
but recovered to one unique header block and completed after one approval. Byte comparison proved
that only that block changed, including preservation of content beyond the default read's line
limit. The edit turn took 109.7 seconds: latency remains a limitation, not a claimed improvement.
The original website was never modified by these diagnostics. Three more idle model servers with
absent parents were cleared before testing; automatic orphan cleanup remains future work.

Regression coverage now includes a rejected ambiguous edit followed by a corrected approved/denied
edit, plus opt-in real-model listing-to-header-edit workflows with repeated declarations, content
beyond 200 lines, and LF/CRLF variants. The first expanded suite had 685 passes, 46 skips, and one
live LF failure: the model's replacement dropped the header's closing brace despite successful
tool execution. The CRLF variant passed. The unchanged byte-preservation assertion exposed this;
an executor success alone is not a valid acceptance gate. Replacement guidance now explicitly
requires retaining unchanged declarations and closing braces, with a complete-rule example in
the argument schema. Keep approval binding, exact matching, repetition limits,
model settings, and Phase 1 read behavior intact. User acceptance through the launcher remains
pending; do not promote Phase 2 or declare the baseline restored solely from a fixture pass.

Final full-suite rerun with that replacement guidance: **686 passed, 46 skipped** (294.26 seconds),
including the original CSS follow-up and both unchanged LF/CRLF gradient workflows. The tests
verify an actual approved compact edit and preservation of every byte outside the target rule;
approval denial and ambiguous-edit correction remain covered separately.

The final real-file-copy rerun with the same code also passed: 94.0 seconds for the gradient turn,
two rejected ambiguous excerpts followed by one unique approved header edit, all unrelated bytes
preserved, and the original Documents stylesheet unchanged. This confirms recovery in that
workflow, not elimination of model latency or general acceptance of every editing request.

### Phase 0 follow-up verification — 2026-09-26

- Reviewed commit `53c3296` against `4a4e819`, covering budget selection and admission,
  per-step agent enforcement, GUI projection, and provider completion diagnostics. No new
  blocking issue was identified in this review.
- The full deterministic suite passed with:
  `runtime\python\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\Users\yaboy\Desktop\orsi_phase0_review_20260926`.
- Test fixture placement matters: mutation tests deliberately reject targets inside the
  application directory and AppData. Initial runs in those locations hit the expected protected-path
  denials; the passing run used the separate Desktop directory above. Do not weaken path policy
  to accommodate test fixtures.
- Visible checks of `ORSI.cmd` and `ORSI_TEST.cmd` remain unverified. This review session had no
  native Windows UI control. The user subsequently approved advancing to Phase 1; no automated visible launcher result is claimed.
- User confirmed successful Phase 0 review on 2026-09-26 and authorized moving to Phase 1. This approval supersedes the pending pre-merge gate; it does not claim an automated visible launcher check was performed.

## Objective

Adopt the OpenCode patterns that address O.R.S.I.'s remaining context and tool-call reliability
limitations while preserving O.R.S.I.'s local-first Windows design, exact approvals, fail-closed
execution, protected-path policy, and small auditable capability catalog.

This plan deliberately excludes broad cloud-provider compatibility. The intended future cloud
target is one OpenAI API integration, optimized and tested for a small explicit model set. O.R.S.I.
does not need OpenCode's 75-provider adapter layer, Models.dev dependency, dynamic provider package
installation, or provider-specific compatibility matrix.

## OpenCode patterns being adapted

1. Prefer compact edits or patches over whole-file replacement.
2. Page large reads with explicit offsets and continuation metadata.
3. Bound every model-visible tool result through one central projection layer.
4. Preserve full oversized results outside model context and retrieve them in bounded chunks.
5. Track input, output, tool-schema, and safety reserves per active model.
6. Compact old conversation history into a structured rolling summary while keeping recent turns.
7. Attempt one compaction-and-retry when a provider rejects a request for context overflow.
8. Let enabled tools come from the trusted registry and permission configuration rather than a
   natural-language keyword router.
9. Represent invalid tool calls as non-executable structured feedback so the model can correct
   itself without losing tool-call continuity.

OpenCode remains a reference, not a dependency. Before implementation begins, pin the exact
OpenCode commit being consulted and record it in `docs/opencode-reference.lock.json`.

## Invariants that must not change

- Model output is untrusted and cannot grant permission or execute an operation.
- All arguments pass strict schema validation before permission evaluation.
- Writes and application launches require exact, expiring, single-use approval.
- Approval is bound to the capability, canonical arguments, target resource, target identity, and
  trusted preview.
- Interrupted, uncertain, or unjournaled mutations are never replayed automatically.
- No general shell, arbitrary process execution, dynamic plugin loader, MCP runtime, or auto-approve
  mode is introduced by this work.
- File contents and model responses remain absent from ordinary logs.
- Compaction summaries never preserve an approval as valid authorization.
- Existing whole-file writing remains available for new files and intentional replacement, but it
  stops being the preferred method for modifying an existing file.
- Every phase lands separately with a clean tree and passing deterministic tests.

## Recommended implementation order

The order intentionally reduces context pressure before adding summarization. Compact edits and
paged reads solve the most common causes at their source; compaction then handles long sessions.

### Phase 0 — Establish measurements and regression scenarios

Goal: make context pressure observable without logging conversation or file content.

Implementation:

- Add a provider-neutral context budget record containing only numeric counts:
  - model context limit;
  - system-message tokens;
  - conversation tokens;
  - structured tool-history tokens;
  - capability-schema reserve;
  - requested output reserve;
  - safety buffer;
  - total estimated request tokens and remaining tokens.
- Expose the same calculation to the GUI context meter and diagnostics so displayed and enforced
  values cannot drift.
- Record finish reason and provider-reported input/output usage when available; continue excluding
  generated text and file contents.
- Create deterministic fixtures for:
  - the 195-line CSS workflow that previously truncated;
  - a file larger than 1,000 lines;
  - repeated search/read results across a long conversation;
  - a request whose full tool catalog is near the context boundary;
  - a simulated provider context-overflow rejection.

Likely code areas:

- `app/conversation/context.py`
- `app/conversation/orchestrator.py`
- `app/inference/diagnostics.py`
- `app/ui/context_window.py`
- context and conversation tests

Exit criteria:

- One calculation drives request admission and the GUI meter.
- Diagnostics explain where tokens were spent without exposing content.
- Baseline tests reproduce the remaining limitations without executing unsafe mutations.

### Phase 1 — Add compact existing-file edits

Goal: stop requiring the model to reproduce an entire file for a small or medium modification.

Implement `filesystem.edit_text` with an intentionally narrower first version:

- Arguments:
  - exact absolute path;
  - exact `old_text` to replace;
  - exact `new_text`;
  - `replace_all`, defaulting to false;
  - expected content SHA-256 from the preceding read, when available.
- Reject an empty `old_text` for existing files.
- Without `replace_all`, require exactly one match. Reject zero or ambiguous matches.
- Initially support UTF-8 text only, preserving BOM and line endings where present.
- Generate a bounded trusted diff for the approval dialog.
- Bind approval to the original file identity, expected digest, exact replacement, and resulting
  preview.
- Recheck identity and digest immediately before writing.
- Use the existing pinned-parent and atomic-replace path, then verify the final digest.
- Return a small result containing path, additions, deletions, and final digest—not the whole file.
- Update model guidance so `edit_text` is preferred for existing files and `write_text` is preferred
  for new files or deliberate full replacement.

After exact replacement is accepted, evaluate a separate `filesystem.apply_patch` capability for
multi-block edits. It must parse one constrained patch format, resolve every path before approval,
show a complete bounded diff, reject mixed-root patches, and apply atomically per file. Do not port
OpenCode's fuzzy matching in the first version; ambiguity must continue to fail closed.

Likely code areas:

- new capability under `app/capabilities/`
- `app/capabilities/catalog.py`
- `app/security/default_permissions.py`
- `app/security/write_policy.py`
- `app/execution/windows_filesystem.py`
- `app/conversation/prompt.py`
- approval, capability, integration, and real-model tests

Exit criteria:

- Editing a selector in a 65 KB CSS file does not require returning the entire file.
- A changed file between preview and execution is rejected.
- Zero-match and multi-match requests make no change.
- Approval shows the exact diff and remains single-use.

### Phase 2 — Make text reads pageable

Goal: allow the model to inspect any portion of a large file without placing the whole file in one
turn, while preserving the accepted Phase 1 editing and conversation behavior. This phase is
currently rolled back. The following is a future retry design, not authorization to implement it.

Scope and sequencing:

- Complete the baseline comparison and any separately accepted prerequisites above first.
- Build the paging capability and its deterministic contract first; integrate model guidance only
  after that contract passes. Measure schema and result overhead even at this first stage.
- Initially preserve the accepted no-offset read behavior and defaults. Make new paging behavior
  explicitly selectable during development. Decide and document how legacy partial-line reads
  coexist with complete-line pages before activation; adding an offset field does not by itself
  make those semantics compatible.
- Do not bundle edit activation, regex-routing expansion, catalog/history trimming, different
  model settings, or default-page reductions into the paging change. If one is necessary, isolate
  and review it as a prerequisite. The retired rebuild's 4 KiB/100-line defaults are an experiment,
  not a new requirement; choose eventual defaults from total workflow measurements.
- Keep full and compact prompt changes short. Measure their token cost with the same catalog as
  Phase 1, and avoid solving repeated-call behavior by accumulating more instructions.

Read contract and resource bounds:

- Extend `filesystem.read_text` with a one-based `offset_line` argument, defaulting to 1.
- Keep `max_lines` and `max_bytes` as hard upper bounds.
- Return:
  - `offset_line`;
  - first and last returned line;
  - `next_offset_line` when more content exists;
  - `eof`;
  - total file size;
  - a full-file content SHA-256, or a separately named and documented read-version token.
- Define whether each byte field describes source bytes, returned UTF-8 text, or total scanned
  bytes. Measure the serialized result envelope as well as the excerpt itself.
- For paged reads, preserve complete lines, code points, BOM handling, and original newline bytes.
  Consecutive pages must neither skip nor repeat a line. Define behavior for empty files, exact EOF,
  a missing final newline, and out-of-range offsets explicitly.
- If a requested line exceeds the page budget, return a bounded, actionable error. Increasing a
  limit must remain within its ceiling. Define how very long skipped lines are drained with bounded
  memory; a long line before the target must not silently corrupt the target's line number.
- Give a small continuation hint only when more content exists. More content being available does
  not mean the model should read it when the user's requested range is already satisfied.
- If every page computes a full-file SHA-256, measure the repeated I/O and enforce cancellation and
  scan deadlines on slow/large files. Avoid an unnecessary second full-file pass. If a cheaper
  version token is selected, never pass it as `expected_sha256`: when that optional edit argument
  is supplied, it must be a real hash of the complete source bytes. Define how an edit obtains
  that hash without trusting an excerpt.
- Detect file changes during a page read and between pages. Compare each Windows stat API with a
  compatible baseline; metadata equality is a change detector, not a hostile-writer snapshot.
  Never join pages from different paths or versions. Preserve the edit's own identity and digest
  checks regardless of read-side caching or versioning choices.
- Preserve the same path policy, read acknowledgement, binary rejection, timeout, and cancellation
  guarantees. Specify the extent of encoding/binary validation when only part of a file is scanned.

Conversation integration:

- Preserve needed historical tool definitions until their call/result groups are safely retired.
  Do not repeat the preceding-turn-only catalog change that broke transcript validation.
- Verify that short follow-ups retain the pending request, path, and needed tools. Any catalog
  reduction must pass “find folder -> yes -> list”, “create folder -> supplied path -> never mind”,
  and “list files -> metadata of first file -> and the second” regressions as well as edit workflows.
- Record all attempted page calls, not only successful executions. Repeated identical reads of an
  unchanged requested range and missed required pages both fail acceptance. A genuinely changed
  file or an explicit user reread remains valid; do not silently suppress it or replay mutations.
- Ensure the final answer contains all requested pages in order. A fallback renderer must not
  discard earlier pages, combine incompatible versions, or turn missing model calls into a claimed
  successful workflow. Rendering tests and model call-sequence tests are separate gates.

Likely code areas:

- `app/capabilities/filesystem_read_text.py`
- `app/conversation/prompt.py`
- `app/conversation/result_grounding.py`, only if multi-page display needs a narrowly scoped change
- read capability and natural-language integration tests

Required acceptance matrix:

| Scenario | Required evidence |
| --- | --- |
| “there is a folder in my documents called website. edit style.css there, change the background to charcoal and the font color to white” | Actual authorized changes, preserved unrelated bytes, appropriate approval, and measured context/call/latency behavior against the accepted baseline. Include both a small stylesheet and the 65 KB fixture. |
| Proposed FAQ JavaScript, then “great, please add the javascript to the script.js file” | Retain the relevant path and requested code; ask for genuinely missing information, then perform the approved edit. No false “cannot edit” claim when the tool is enabled, and no unrequested whole-file replacement. |
| A normal request for a range past line 1,000 and a multi-page range past line 4,000 | The model selects correct offsets and limits without the user naming tools, supplying JSON/offset syntax, or adding `/no_think`. All requested content is returned, with no missing or redundant page calls after the request is satisfied. |
| Consecutive pages and changed versions | Deterministic tests cover all supported encodings, LF/CRLF/CR, byte edges, empty files, EOF, long lines, malformed/binary text, cancellation, deadlines, and mutation. A later compact edit accepts the correct full-file hash and rejects a stale one. |
| Clarifications and continuing work | At least six user turns in one chat, including “yes”, a supplied path, cancellation of an intention, and edits following reads. No invalid transcript or loss of required tools; measure context growth at each turn. |
| Ordinary chat and small reads | No unjustified new tools or paging loops; functional behavior and measured cost stay within the predeclared baseline tolerances. |
| Launchers and approval UI | Run the actual ordinary and development launchers from the recorded checkout. Test accepted and denied edits with the real approval UI; a fixture callback proves runtime execution, not manual UI acceptance. |

Release decision:

- Pass the full deterministic suite and every required live workflow on at least three comparable
  runs using the intended shipped settings. Record exact revision/configuration and failed trials
  as well as successes. A skipped opt-in test is not a passed live gate.
- Compare cumulative and peak request budget, schema/result/history contributions, call counts,
  and generation latency with the accepted baseline. Record any remaining margin and variance;
  do not interpret a smaller default page or a single successful edit as a context improvement.
- Treat `finish_reason=length` at the output cap separately from an input-context rejection.
  A reasoning-mode cue, higher token cap, or model change may be tested diagnostically, but it
  requires its own reviewed behavior/configuration change before it can form a new baseline.
- If any ordinary-prompt gate fails, status remains **not accepted**. Stop feature expansion,
  isolate the cause, and either fix that cause with the same tests or revert the candidate. Do not
  move to Phase 3, merge, or declare readiness based on unit-test totals or cue-assisted success.
- The user's acceptance of the real workflow is required before replacing the approved Phase 1
  runtime. Keep rollback to the accepted runtime straightforward.

### Phase 3 — Centralize model-visible tool-result limits

Goal: prevent any capability result from unexpectedly consuming the context window.

Implementation:

- Add a `ToolResultProjection` boundary between trusted capability results and model transcript
  messages.
- Keep the original normalized result for the executor outcome and UI, while generating a separate
  bounded model projection.
- Apply global limits by encoded bytes, lines, and estimated tokens. Individual capabilities may
  choose stricter limits but never bypass the global ceiling.
- When a result is oversized:
  - include a bounded head or task-appropriate preview;
  - state exactly what was omitted;
  - retain the complete result in a private managed output store;
  - return an opaque result handle, never a freely chosen filesystem path.
- Add a read-only internal capability such as `runtime.read_tool_output` that accepts only the
  opaque handle plus offset/limit. It must not accept arbitrary paths.
- Give stored outputs a size cap, per-session ownership, short retention period, startup cleanup,
  and explicit deletion at session end.
- Store only hashes and lifecycle metadata in the crash journal. Do not journal full content.

Start with conservative O.R.S.I.-specific limits measured against the 16K local context rather than
copying OpenCode's 50 KB default blindly.

Likely code areas:

- new projection/output-store modules under `app/agent/` or `app/conversation/`
- `app/agent/runtime.py`
- `app/inference/protocol.py`
- `app/settings/agent.py`
- state cleanup and privacy tests

Exit criteria:

- A 100 KB synthetic tool result creates a bounded transcript message.
- The omitted section can be retrieved through the opaque handle in bounded pages.
- Handles cannot cross sessions, escape into arbitrary paths, or survive their retention policy.

### Phase 4 — Make context limits model-aware

Goal: calculate the usable request budget from the active model rather than one optimistic shared
number.

Implementation:

- Define a small checked-in model profile containing separate context, maximum input, and maximum
  output limits.
- For local GGUF models, read the native context metadata where reliable and confirm the context
  actually selected by `llama-server`.
- For the future OpenAI-only cloud backend, maintain an explicit tested OpenAI model profile. Do not
  add Models.dev or a generic provider catalog.
- Use the lower of configured, native, server-confirmed, and tested limits.
- Keep output reserve independent from input history budget.
- Distinguish input-budget exhaustion from generation reaching its output cap. Phase 2 produced
  the latter before a tool call; attributing it solely to model reasoning or solely to context size
  is unsupported without measurements. Any reasoning-mode or output-limit change needs ordinary
  workflow acceptance, not just a cue-assisted fixture.
- Include provider/tool wrapper overhead and capability schemas in every preflight calculation.
- Refuse impossible requests before sending them, with a useful context-specific message.
- Refresh the context meter immediately when switching local/cloud mode or model profile.

Likely code areas:

- `app/settings/model.py`
- future OpenAI cloud settings
- `app/inference/engine.py`
- `app/inference/llama_server_backend.py`
- `app/conversation/context.py`

Exit criteria:

- Context calculations use the active model's limits.
- Switching mode cannot leave the previous model's context limit in the UI or orchestrator.
- Tests cover input/output asymmetry and tool-schema overhead.

### Phase 5 — Add structured rolling compaction

Goal: preserve important old information instead of simply dropping older turns.

Implementation:

- Trigger compaction before a model request when the complete projected request exceeds the usable
  input budget.
- Preserve complete recent turns. Start with approximately 25% of the usable context, bounded to a
  sensible 2K–4K range for the current 16K model, and tune from measurements.
- Summarize only the older head into a strict structure containing:
  - user objective;
  - explicit constraints and preferences;
  - known paths and file identities/digests where still relevant;
  - completed read-only observations;
  - completed mutations as historical facts;
  - failures and their causes;
  - pending questions and unfinished work.
- Exclude secrets, approval IDs, valid authorization state, raw large file contents, and stale tool
  call IDs.
- Mark summarized file/tool content as untrusted data so prompt injection is not promoted into
  system instructions.
- Run compaction with no tools available.
- Use the active model initially so local mode stays fully local. A dedicated inexpensive OpenAI
  model can be considered later only within the single-provider design.
- Write a new checkpoint only after a complete valid summary is produced. If summarization fails or
  is cancelled, retain the previous active boundary unchanged.
- On later compactions, summarize the previous structured summary plus the newly retired turns.
- Keep compaction state separate from the visible chat UI; this work does not restore the history
  button or require cross-launch conversation history.

Likely code areas:

- new `app/conversation/compaction.py`
- `app/conversation/context.py`
- `app/conversation/store.py`
- `app/conversation/orchestrator.py`
- prompt-injection, cancellation, persistence, and long-session tests

Exit criteria:

- A 30-turn workflow retains its original objective and important paths after compaction.
- Recent turns remain verbatim and grouped with their tool traces.
- Failed compaction cannot erase or replace valid history.
- No approval becomes reusable through a summary.

### Phase 6 — Recover once from genuine context overflow

Goal: handle provider/server disagreement with local token estimates without loops or duplicated
side effects.

Implementation:

- Add a provider-neutral `CONTEXT_OVERFLOW` error classification distinct from output truncation,
  malformed calls, network failure, and timeout.
- A request may compact and retry once only when:
  - the provider rejected the request for context size;
  - no capability from that physical attempt executed;
  - no durable assistant response or partial mutation was accepted.
- Rebuild the entire request from the completed compaction checkpoint before retrying.
- A second overflow stops with a clear message; it never starts another compaction loop.
- Output truncation during a long write remains non-executable. Once compact editing exists, bounded
  corrective feedback may ask the model to use `edit_text` or a patch, but the truncated call itself
  is never repaired into an executable write.
- Record retry/compaction counters as metadata so the behavior is testable and diagnosable.

Likely code areas:

- inference error contracts and local/OpenAI adapters
- `app/conversation/orchestrator.py`
- `app/agent/runtime.py`
- compaction and replay-safety tests

Exit criteria:

- One simulated pre-execution overflow compacts and succeeds on the single retry.
- A second overflow terminates.
- An overflow after any mutation never replays that mutation.

### Phase 7 — Replace keyword-based tool visibility with registry materialization

Goal: prevent indirect or unfamiliar wording from hiding a capability the model needs.

Implementation:

- Materialize the model-visible catalog from enabled registry entries plus deterministic deployment
  and permission configuration, following OpenCode's registry approach.
- With the current small catalog, expose all enabled capabilities when their schemas fit the
  model-aware budget and the measured workflow retains sufficient headroom. The Phase 2 experience
  shows that fitting a single request is not evidence that a wider catalog is sustainable over
  several turns. Compare explicit profiles if advertising everything regresses that measurement.
- If a future catalog becomes too large, use explicit configured capability profiles or families;
  do not return to free-form natural-language regex routing.
- Continue retaining tool definitions needed by an active tool transcript.
- Design transcript conversion and catalog changes together. Removing old definitions while
  retaining their calls caused invalid-transcript failures in the abandoned Phase 2 rebuild.
- Keep the permission gate authoritative. Visibility does not imply authorization.
- Remove the keyword selector and its language-specific patterns only after indirect-phrasing and
  context-budget acceptance tests pass.

Likely code areas:

- `app/conversation/capability_routing.py`
- `app/conversation/orchestrator.py`
- capability registry and routing tests

Exit criteria:

- Indirect requests, typos, and non-English phrasing can still reach the correct enabled tool.
- The model never sees a disabled capability.
- Catalog size is fully included in the context preflight.

### Phase 8 — Normalize invalid calls into safe correction feedback

Goal: improve recovery across otherwise capable models without weakening validation.

Implementation:

- Keep the existing bounded capitalization, trailing-comma, and unambiguous-closing repairs.
- Represent unknown tool names, invalid JSON arguments, and schema validation failures as a
  provider-neutral synthetic invalid-tool result tied to the failed provider call when possible.
- Return only bounded validation details; never echo secrets or unbounded model content.
- Let the model correct the call within the existing protocol-failure cap.
- Output truncation, duplicate call IDs, repeated identical calls, and mixed prose/tool responses
  remain separate terminal or bounded-feedback cases.
- The invalid-tool path must have no permission class, no approval path, and no executor route.

Likely code areas:

- `app/inference/protocol.py`
- `app/agent/feedback.py`
- `app/agent/runtime.py`
- provider transcript conversion and malformed-call tests

Exit criteria:

- One repairable invalid call can self-correct and complete.
- Repeated invalid calls stop at the configured cap.
- No invalid call reaches permission evaluation or execution.

## Integrated acceptance matrix

Every phase must retain the existing deterministic suite. Before the complete project is promoted,
add and pass these end-to-end scenarios:

1. Read and minimally edit a 65 KB CSS file without returning the complete replacement.
2. Read requested content beyond line 4,000 using successive pages, from ordinary wording without
   tool syntax or reasoning-mode cues; stop when the requested range is complete.
3. Process a 100 KB tool result while keeping the model-visible projection bounded.
4. Continue a 30-turn task after one and then two compactions without losing the original goal.
5. Recover from one simulated request-context overflow and prove no capability ran twice.
6. Reject an output-truncated write without modifying the target.
7. Correct one malformed call through the invalid-tool feedback path.
8. Reach each enabled capability through indirect wording without keyword routing.
9. Deny changed-target, expired-approval, protected-path, reparse-point, UNC, and device-path cases.
10. Run the real larger local Qwen model through list, paged read, compact edit, search, copy, move,
    folder creation, and trash acceptance.
11. When the OpenAI backend is introduced, run the same matrix against each explicitly supported
    OpenAI model profile; do not infer compatibility from API success alone.
12. Repeat the exact reported CSS and JavaScript follow-up workflows in a continuous chat, comparing
    context growth, tool calls, latency, and real file outcomes with the accepted Phase 1 baseline.

## Rollout and branch strategy

- Implement each phase on its own `codex/` branch from an up-to-date `main`.
- Phase 2 has been rejected and its branch deleted. Create a future retry branch only after a new
  user instruction, from the accepted runtime plus separately accepted prerequisites. Planning
  changes do not authorize re-enabling the discarded implementation.
- Do not combine security-policy changes with context changes in one commit.
- Keep activation, routing, page defaults, and model-generation changes separately reviewable.
  Never use an unrelated integration fix to claim that paging reduced context pressure.
- Keep new capabilities disabled until their unit, policy, approval, execution, cancellation,
  recovery, integration, and live-model gates pass.
- Merge in this recommended order: measurements, compact edit, paged read, result projection,
  model-aware budgets, compaction, overflow recovery, registry materialization, invalid-call
  continuity.
- After every merge, test both `ORSI.cmd` and the development launcher before starting the next
  phase. Also run both before promotion; discovering a launcher/configuration mismatch only after
  merge is too late. Record any unavailable UI checks as unmet gates.

## Explicit non-goals

- Supporting arbitrary cloud providers or dynamically installed provider SDKs.
- Integrating Models.dev.
- Treating every OpenAI model as tool-capable without acceptance testing.
- Adding MCP, plugins, subagents, skills, a shell, or general process execution.
- Copying OpenCode's permissive defaults or `--auto` approval behavior.
- Adding fuzzy or heuristic edits before exact replacement is proven.
- Automatically replaying interrupted or uncertain writes.
- Restoring the history button or designing a history UI as part of context compaction.

## Next implementation session, when requested

1. Verify that the runtime still matches approved Phase 1 and read this failure review. Record any
   accepted changes since `dc2d092`; do not assume the deleted Phase 2 branch is a usable baseline.
2. Reproduce and measure the ordinary launcher workflows before creating a paging implementation.
   Confirm the effective edit flag, advertised tools, and fresh-process/fresh-chat conditions.
3. If a prerequisite fails, stop the paging work and prepare that prerequisite as a separate small
   change for review. Retest the same workloads before selecting the retry's comparison baseline.
4. Define the compatibility contract, digest strategy, and numerical regression tolerances from
   measurements. Record these decisions before changing defaults or prompts.
5. Implement the smallest selectable paging change on a new branch, then add only the necessary
   conversation integration. Run deterministic boundary tests and the unchanged ordinary-prompt
   live matrix; preserve failed evidence instead of weakening the test.
6. Stop for user review only when the required gates pass. If they do not, report Phase 2 as not
   accepted and keep the working approved runtime available. Phase 3 remains pending.
