# O.R.S.I. robustness audit — 1 October 2026

## Finding

O.R.S.I. has useful separation between models, capabilities, permissions, and execution. Its
Windows authorization and crash-journal boundaries are substantial. The central reliability
problem is the lifecycle around them: provider completion information is discarded, normal
provider output is sometimes rejected, successful tool results disappear from conversation
history after a failed turn, and growing tasks have no context-recovery path. A new feature can
change generation limits, prompt cost, or tool visibility and expose those weaknesses without
breaking any individual capability test.

The model chooser introduced a concrete reduction in the effective 14B profile. It did not
introduce all the older lifecycle problems. This investigation does not establish that the
desktop process itself crashes; the supplied screenshot and recent logs show failed or
incomplete conversation turns.

## Scope and verified baseline

- Checkout: `C:\Users\yaboy\Desktop\orsi_test`.
- Branch: `codex/local-model-chooser`; HEAD `b2f4e3eabd323e63ec6059765f133ca1012a0bf7`.
- On entry, the only tracked modification was `config/model.json`. It was preserved.
- Committed 14B configuration: 16,384 context tokens, 4,096 output tokens.
- Effective saved configuration: 8,192 context tokens, 2,048 output tokens. Its KV estimate also
  changed from 262,144 to 163,840 bytes per token.
- Existing regression suite outside the restricted shell: **724 passed, 52 skipped, 5 subtests
  passed**, 113.81 seconds. The first restricted run had 70 failures; an identical filesystem
  module passed all 29 tests outside that restriction. Those initial failures are environmental,
  not evidence of product regressions.
- Ten diagnostic cases reproduced with synthetic model responses and disposable metadata
  fixtures. No live model generation, cloud API requests, or application configuration changes
  were needed.
- Application source was left unchanged. This report and ignored diagnostic artifacts are the
  investigation outputs.

## The screenshot: a supported causal chain

The log records a request at `2026-10-01 20:28:39,137` and its completion at
`20:29:45,495`: **66.358 seconds**, which rounds to the screenshot's **66.4 seconds**. The
completion has `finish_reason=length`, 3,070 input tokens, and exactly 2,048 output tokens
(`state/orsi.log:1334–1335`). There is no following protocol-failure warning for that completion.
The timing strongly associates this log event with the screenshot, although the log intentionally
does not retain generated content and cannot prove its exact text.

The matching implementation path is reproducible:

1. The chooser creates a fresh automatic profile and sets output tokens to
   `min(4096, selected_context // 4)` (`app/settings/local_models.py:137–159`). The documentation
   records 8,192/2,048 for this machine's 14B switching check. Switching back to the same model
   does not restore its previously accepted manually configured 16,384/4,096 profile.
2. `normalize_native_chat_completion` treats `finish_reason=length` as truncation **only if**
   message normalization has already failed (`app/inference/protocol.py:393–417`). Valid-looking
   text loses the finish reason and becomes an ordinary successful text response.
3. `AgentRuntime` completes on that text (`app/agent/runtime.py:453–482`). There is no continuation
   of partial code or indication that output capacity was exhausted.
4. The renderer recognizes only code fences with a closing delimiter
   (`app/ui/chat.py:23–51`). An unfinished fence becomes a plain-text label, including the visible
   opening backticks. Ordinary text is deliberately rendered without Markdown formatting.

This is output-budget exhaustion, not evidence of input-context overflow: the provider input
was 3,070 tokens in an 8,192-token context. Raising the output limit alone is not a complete repair;
larger code can exhaust 4,096 tokens too. The renderer needs to display partial code correctly,
and the execution layer needs to preserve and report incomplete completion state.

## Ranked architectural findings

### 1. Completion state is lost, and truncation handling is inconsistent — high

`ModelResponse` has mutually exclusive text/calls/failure fields but no finish reason, usage,
partial-output state, or reasoning parts. Adapters log usage and then discard it from the outcome.
Text ending at the provider limit is accepted as complete. A length-ended call whose missing
closing brace can be repaired is also accepted as a call. A call with an unfinished string becomes
`OUTPUT_TRUNCATED` and stops immediately, without a recovery attempt.

The diagnostic confirms all three branches. The existing
`test_truncated_structured_output_stops_without_a_pointless_retry` explicitly expects immediate
termination. Retrying the identical request with the identical budget would indeed be ineffective;
what is missing is a distinct recovery policy, such as a smaller edit, an available larger output
reserve, or an honest partial result. Partial tool arguments must never execute just because
they can be made syntactically parseable. Normal schema validation and approvals still apply in
the current implementation; this finding does not claim they are bypassed.

### 2. Valid provider behaviour is classified as malformed — high

`normalize_native_chat_message` rejects any nonempty assistant text alongside tool calls
(`app/inference/protocol.py:452–456`). A response such as “I will inspect the file” with a valid
metadata call is therefore rejected before execution. This restriction is a product protocol
choice, not a requirement of the permission boundary. Presentation text can remain untrusted
while structured calls are independently validated and approved.

Mixed batches of different capabilities are also rejected (`app/agent/runtime.py:526–561`),
although the executor already runs sequentially. Those calls could instead be validated and
settled in order. The current maximum of two protocol failures is cumulative across the whole run;
it does not reset after a successful step. Two separated mistakes in a long task exhaust it.

Provider call IDs are additionally required to be unique across the entire retained transcript
(`app/inference/protocol.py:287–333`). IDs reused by a provider in separate turns produce an invalid
transcript. The runtime's new-ID set is scoped to one run, so it does not prevent that later
history conflict. Internal identity should include the owning assistant message/turn.

### 3. A failed turn loses evidence of completed work — high

`_run_agent_turn` collects tool results into a local `turn_trace`. `run` adds that trace to
`_agent_history` only after `_run_agent_turn` returns successfully
(`app/conversation/orchestrator.py:133–137,173–208`). A later timeout, cancellation, context stop,
or protocol failure prevents that return. Completed operations remain in the crash journal, but
their arguments/results are missing from the model's next-turn history. The journal contains
privacy-safe hashes and lifecycle fields; it is not a replayable conversation transcript.

The diagnostic performs one real metadata read, then injects output truncation. The journal
records success, the user sees “No computer action was taken,” and the next model request has
no tool trace. The same retention structure surrounds approved mutations. This audit did not
perform a mutation to demonstrate it.

The failure message should describe the unfinished step and any earlier completed actions. The
trace needs to survive unsuccessful turns, with explicit terminal state. Cancellation in the
middle of a batch also needs per-call settlement, rather than observation only after the batch.

### 4. Context management stops growing tasks instead of preserving their progress — high

Before each model step, the runtime calculates context cost and returns `CONTEXT_LIMIT` if it
does not fit (`app/agent/runtime.py:960–986`). It never projects older results to smaller summaries,
compacts the active task, or recovers after a provider overflow. The diagnostic and existing
`test_agent_refuses_a_continuation_that_exceeds_the_context_budget` both demonstrate a tool
succeeding and its result preventing the next model request.

Across turns, selection drops whole older groups. If an oversized latest user message is a
single text message, selection keeps its **suffix**, potentially discarding the task's leading
requirements (`app/conversation/context.py:75–125,328–354`). It can therefore report a fitting
budget while the original task definition is absent.

Historical capability names are gathered from the entire in-memory history, even if their turns
are subsequently excluded from the selected context (`orchestrator.py:368–399`). Old tools thus
continue costing schema/prompt space. Production llama-server counting uses an estimate and
serialized internal tool history rather than the exact native request. In the screenshot-associated
request the estimated input was 4,480 tokens versus 3,070 provider input tokens. The estimate is
not proof of a context error, and the displayed remaining budget does not establish output room.

Large-output handling bounds JSON and returns a preview; it does not provide OpenCode's general
saved-output retrieval mechanism. Text reads currently have byte/line limits but no page offset.
These are additional limits on long workflows, not reasons to remove bounded output.

### 5. Tool visibility still depends on hand-written phrasing — medium/high

`select_turn_capabilities` is a regex router. It does not execute commands or authorize actions,
but it decides which tools the model can see. The ordinary request “Build a Pygame shooter and
save it on my Desktop as shooter.py” advertises only `filesystem.stat` in the diagnostic. The
writer exists and is enabled but is unavailable to that request. Compound tasks can similarly
need tools that their initial wording never exposed.

If the model returns prose rather than taking the requested action, ordinary assistant text is
generally accepted as a completed run. Production does not seed `required_calls` from an accepted
task plan. This is not solved by adding another special-case phrase each time.

`docs/status-report.md` still says there is no production regex router and that each turn receives
the complete enabled catalog. That description is stale. `ARCHITECTURE.md` describes the current
scoped router more accurately. Conflicting documentation makes baseline diagnosis harder.

### 6. Model and release qualification do not protect the accepted baseline — high process risk

The chooser validates architecture, metadata and tool-template markers, then checks server
startup. Those checks establish format/load compatibility, not task reliability. It exposes the
VL 4B model as **experimental**, and its documentation honestly records failed follow-up edit
acceptance. Those known failures should define its qualification status, rather than be treated
as proof that every model supported by the chooser behaves equivalently. The screenshot-associated
configuration is the 14B model; the VL failures do not explain this particular response.

The chooser writes its generated settings into the same tracked `config/model.json` that
describes the working baseline. A clean source commit and a previously passing default profile
therefore do not describe the actual running configuration after model switches. The UI shows
the new limits in Settings, but switching does not carry an accepted per-model profile back.

The default suite's live-model acceptance tests are opt-in and skipped. Many deterministic tests
use scripted completions and verify safe stopping, not successful completion of realistic tasks.
No tracked CI workflow or packaging acceptance runner enforces the documented live gates.
`docs/opencode-context-reliability-action-plan.md` already records two rejected Phase 2 attempts
with green deterministic suites and unresolved live gates. It prescribes repeated unchanged
ordinary-prompt workflows and continuous-session acceptance, but that discipline is not enforced
by the normal test/build path.

### 7. A display refresh can prevent failure cleanup — medium/high

`MainWindow._done` refreshes the context meter before clearing the busy state and displaying the
result (`app/ui/main_window.py:917–934`). That refresh calls the service's context calculator
without exception isolation (`main_window.py:1329–1340`). Counting can initialize a lazy backend
and fail; `LazyInferenceEngine` also remembers initialization failures. An error in this display
path therefore escapes before controls are released or the original error is shown.

A method-level diagnostic with a failing context-meter double confirms this ordering. This is
a credible way for a request failure to leave the app looking stuck; it is not evidence that it
caused the supplied screenshot. Essential cleanup should run even if an optional display
calculation fails, and presentation refreshes should not initiate model loading.

## OpenCode comparison

I verified both the repository's reference revision
[`d870e22c70f27103016dcd479edcfebf86136d93`](https://github.com/anomalyco/opencode/commit/d870e22c70f27103016dcd479edcfebf86136d93)
and current upstream
[`aa481b8f5652f5576c55f914a64ed270e7daa7e0`](https://github.com/anomalyco/opencode/commit/aa481b8f5652f5576c55f914a64ed270e7daa7e0).
The following patterns exist in the pinned reference, not just in later upstream work.

| Concern | O.R.S.I. now | OpenCode reference pattern |
| --- | --- | --- |
| Provider outcome | One mutually exclusive text/call/failure response; finish metadata discarded | Streamed text, reasoning, tool and step parts; finish reason and usage retained |
| Text plus tools | Rejected as malformed | Separate text and tool events handled in one assistant message |
| Tool history | Kept for model continuation only after a successful whole turn | Pending/running/completed/error parts updated in session storage |
| Bad calls | Generic protocol feedback and two failures per run | Safe name repair and an invalid-tool result the model can correct |
| Context pressure | Admission check followed by terminal stop | Output pruning, summary compaction, overflow recovery and continuation |
| Tool visibility | Latest-turn keyword patterns plus historical names | Central catalog filtered by model and permission configuration |
| Output reserve | Chooser derives 1/4 of selected context, capped at 4,096 | Model output limit combined with a configured ceiling |
| Oversized tool output | Bounded JSON preview | Saved full output plus bounded preview and retrieval hint |
| Interrupted work | Safe journal exists; conversation trace can disappear | Session parts retain completed work and mark interrupted calls |

Primary source references:

- [Processor: streamed parts, stored finish/usage, compaction signal and cleanup](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/processor.ts).
- [LLM: streaming, invalid-call repair and abort propagation](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/llm.ts).
- [Compaction: pruning and summary lifecycle](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/compaction.ts).
- [Registry: model-aware catalog](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/tool/registry.ts).
- [Provider transform: model-aware output ceiling](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/provider/transform.ts).
- [Truncation: saved output and bounded previews](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/tool/truncate.ts).

OpenCode also has bugs and provider limits. Its presence does not prove automatic completion
of arbitrarily long code after every token cutoff. The useful comparison is its richer session
lifecycle, not a claim that adopting its framework makes every task succeed. O.R.S.I. can adapt
these mechanics in Python without replacing Qt or weakening its Windows permissions.

O.R.S.I. currently also lacks a general code-execution/test tool. It can generate code and edit
files but cannot independently run arbitrary generated programs to validate them. That is a
capability boundary to consider separately from the observed truncation defects.

## Repair order and acceptance requirements

1. **Freeze and identify the effective baseline.** Separate accepted per-model profiles from
   runtime user selection. Reconcile the 14B output/context downgrade with real available memory;
   do not simply force an unsafe context. Record revision, effective flags, model identity and
   limits in a content-free diagnostic snapshot. Test switching away and back.
2. **Preserve completion state.** Carry finish reason, usage and partial text through inference,
   runtime and UI. Never label length-ended text complete. Reject incomplete tool generation
   before syntax repair can turn it into an executable call. Render unfinished code fences as
   code with a clear incomplete indication. Ensure failure cleanup releases UI controls even if
   the context meter cannot refresh.
3. **Preserve every settled call and stopped turn.** Retain trace even when later steps fail.
   Introduce durable session/turn outcomes and message-scoped provider identities. Prove that
   a successful approved edit followed by a model failure remains known to the next turn, with
   no automatic replay of an unknown mutation.
4. **Normalize normal provider responses independently of authorization.** Allow text alongside
   validated calls and settle supported multiple calls sequentially. Define bounded recovery
   budgets that distinguish consecutive format failures, semantic corrections and total work.
5. **Add context recovery behind measured acceptance.** Project large results, preserve current
   requirements and exact call/result pairing, then compact only when needed. Remove phrase-only
   capability availability as the controlling source of task reachability. Compare total request
   costs and continuous-session success against the unchanged accepted baseline.
6. **Enforce qualification before promoting features.** Require the same long-code prompt,
   read/edit/clarify/follow-up session, cancellation followed by another task, and model round trip
   for each supported model/profile. Repeat live workflows, keep ordinary prompts unchanged,
   and verify actual file bytes and terminal outcomes. A green deterministic suite with skipped
   required live gates must not promote a build to the working baseline.

Each repair should be independently reviewable and use regression tests for the desired
behaviour. Avoid combining a new model, schema, routing heuristic, context policy and UI change
in one acceptance step. Restoring the previous token values is a useful controlled comparison,
not proof that the architecture has been repaired.

## Reproduction artifacts

- `state/test-artifacts/robustness-repro.py`: ten diagnostic checks, using current product
  modules and existing test fixtures. Its assertions intentionally describe existing defects;
  it is not a proposed production acceptance suite.
- `state/test-artifacts/robustness-repro.json`: observed outcomes.
- `state/test-artifacts/robustness-suite.txt`: successful unrestricted regression run.

Run the diagnostics from this checkout with
`runtime\python\python.exe state/test-artifacts/robustness-repro.py`.

The reproduction covers truncated code rendering, mixed valid calls, length-ended repaired
arguments, cross-turn call-ID reuse, hidden writer routing, lost latest-prompt requirements,
completed trace loss, cumulative protocol exhaustion, context exhaustion after a successful
tool, and UI finalization interrupted by a meter error. Exact user-session content and live-model
repeatability remain unverified in this audit.
