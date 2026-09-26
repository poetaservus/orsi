# O.R.S.I. OpenCode-inspired reliability action plan

Date: 2026-09-24  
O.R.S.I. baseline: `main` at `4a4e819`  
Status: Phase 0 merged locally; Phase 1 implemented and verified on its review branch

## Delivery tracking

This ledger is updated on each phase branch so reviewers can see the inherited baseline, current
work, verification state, and the next branch point without consulting a separate tracker. A phase
branch is created only after the preceding phase has merged to `main`.

| Phase | Branch | Status | Verification and handoff |
| --- | --- | --- | --- |
| Phase 0 | `codex/phase0-context-measurements` | Complete; merged to local `main` | Created from `main` at `4a4e819`. Added one shared numeric budget for selection, admission, diagnostics, and the GUI; content-free provider usage logging; and all five deterministic regression scenarios. Verification: 619 passed, 44 skipped; full suite passed again on 2026-09-26. Follow-up code review found no new blocking issue. User confirmed successful Phase 0 review on 2026-09-26. Fast-forwarded local `main` to `05512fc` before creating Phase 1. |
| Phase 1 | `codex/phase1-compact-edit` | Implemented; ready for review; default off | Created from local `main` at `05512fc` on 2026-09-26. Recorded the edit threat review before registration. Added exact replacement, coherent preview/digest binding, immediate pre-replace revalidation, atomic-write reuse, complete escaped diff approval, read digests, routing, and model guidance. Final deterministic suite: 674 passed, 46 skipped. Local Qwen 14B read/edit acceptance: 1 passed. Visible launcher/manual approval acceptance remains pending; the edit feature stays off in production configuration. |
| Phase 2 | `codex/phase2-paged-text-reads` | Not started | Create only after Phase 1 merges. |
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
turn.

Implementation:

- Extend `filesystem.read_text` with a one-based `offset_line` argument, defaulting to 1.
- Keep `max_lines` and `max_bytes` as hard upper bounds.
- Return:
  - `offset_line`;
  - first and last returned line;
  - `next_offset_line` when more content exists;
  - `eof`;
  - total file size;
  - content SHA-256 or a stable read-version digest.
- Ensure UTF decoding cannot split a code point at byte boundaries.
- Give the model a clear continuation hint when output is truncated.
- Preserve the same path policy, read acknowledgement, binary rejection, timeout, and cancellation
  behavior.
- Add explicit out-of-range behavior rather than silently returning misleading empty content.

Likely code areas:

- `app/capabilities/filesystem_read_text.py`
- `app/conversation/prompt.py`
- read capability and natural-language integration tests

Exit criteria:

- The model can retrieve lines after line 1,000 from a large file.
- Consecutive pages have no gaps or duplicated lines.
- A later edit can bind to the digest returned by the read.

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
  model-aware budget.
- If a future catalog becomes too large, use explicit configured capability profiles or families;
  do not return to free-form natural-language regex routing.
- Continue retaining tool definitions needed by an active tool transcript.
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
2. Read requested content beyond line 4,000 using successive pages.
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

## Rollout and branch strategy

- Implement each phase on its own `codex/` branch from an up-to-date `main`.
- Do not combine security-policy changes with context changes in one commit.
- Keep new capabilities disabled until their unit, policy, approval, execution, cancellation,
  recovery, integration, and live-model gates pass.
- Merge in this recommended order: measurements, compact edit, paged read, result projection,
  model-aware budgets, compaction, overflow recovery, registry materialization, invalid-call
  continuity.
- After every merge, test both `ORSI.cmd` and the development launcher before starting the next
  phase.

## Explicit non-goals

- Supporting arbitrary cloud providers or dynamically installed provider SDKs.
- Integrating Models.dev.
- Treating every OpenAI model as tool-capable without acceptance testing.
- Adding MCP, plugins, subagents, skills, a shell, or general process execution.
- Copying OpenCode's permissive defaults or `--auto` approval behavior.
- Adding fuzzy or heuristic edits before exact replacement is proven.
- Automatically replaying interrupted or uncertain writes.
- Restoring the history button or designing a history UI as part of context compaction.

## Recommended first implementation session

Start with Phase 0 and Phase 1 only:

1. Create a clean feature branch from `main`.
2. Add context-budget measurements and the large-CSS regression fixture.
3. Threat-model `filesystem.edit_text` before registering it.
4. Implement exact single-match editing with digest and identity binding.
5. Add approval, race, cancellation, atomicity, and real-model tests.
6. Stop for review before beginning paged reads or compaction.

This delivers the largest immediate reduction in context usage without introducing summarization,
provider changes, or broad new authority.
