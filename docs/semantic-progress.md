# Semantic progress and attention notifications, 21 October 2026

## Chronological progress correction (current)

The progress timeline, Technical details and working counter now share one
compact task group. On completion or failure, that group stays above the
finished counter and answer. A later request receives its own disclosure, so
opening earlier details cannot show the new task's log. Question-only turns
also retain their progress before the next message. Resetting the conversation
clears the transient groups.

Progress rows use 4-pixel layout gaps. Compact progress text uses 110-percent
line spacing and sizes to its document without an extra 4-pixel allowance.
Normal answer typography is unchanged. This corrects the earlier spacing change,
which left separate progress rows subject to the conversation's 40-pixel gaps,
and the ordering change, which placed the final answer before its disclosure.
Regression checks measure visible geometry through real worker delivery,
including completion, failure, expanded details, narrow windows and the next
request. Scripted model replies drive actual file metadata tools; they do not
qualify live-model narration or native Office editing.

`codex/progress-narrative` starts from local main `da2329b`. The user clarified
the desired view with a screenshot: a running account of the work, with muted
operation summaries between task-specific paragraphs. This supersedes the
single rotating sentence as the primary progress surface described below.

The view is now enabled by the application's normal startup default, including
`ORSI.cmd`, `ORSI_TEST.cmd` and direct Python startup. Restart the app normally
to use it; no special launcher or environment setup is required. An explicit
`ORSI_ENABLE_SEMANTIC_PROGRESS=0` retains the earlier display. No saved user
preferences are migrated or rewritten. The launcher-specific enablement from
`67530bc` was corrected on `codex/progress-normal-startup`.

Normal-startup verification passes **60 focused checks in 19.58 seconds**, with
no failures or skips. The real worker timeline runs without a feature override;
an explicit opt-out still delivers the legacy status. Approval-free writes keep
their raw detail inspectable. Notifications, streaming and inline approvals are
included. Evidence is under ignored `state/progress-normal-startup-focused.xml`
with repository-local temporary/cache directories. No full-suite or live-model
qualification is claimed for this default-selection correction.

The view contains normal public assistant text accompanying accepted native
tool-call responses, followed by summaries of operations after their receipts
settle and are retained. Consecutive operations coalesce into labels such as
`Read files`, `Updated files`, and `Ran commands`. Failed operations use
`Tool attempt stopped` and do not masquerade as successful edits or checks.
These summaries never interpolate arguments, document contents or tool output.

One scoped presentation instruction permits occasional short public paragraphs
alongside native calls. It replaces the existing prohibition on such prose only
when the view is enabled. The instruction asks for concrete findings, changes
and next steps, distinguishing plans from verified results. It preserves the
exact JSON fallback contract. Routing, tools, authorization, retry and completion
decisions, model profiles, sampling, context limits and acceptance prompts are
unchanged. There are no additional model/API requests for narration; ordinary
responses may contain more public output text within their existing budget.

`AgentRuntime` emits commentary after native-response validation and before
tool execution. The callback uses the existing safe observer helper, so a broken
display cannot stop work. `ConversationService` emits operation summaries only
after durable settlement. `ConversationWorker` correlates the events; the
existing GUI thread receives them through queued slots. Completion assessments,
private reasoning, raw provider internals and speculative tool results are not
sources of paragraphs. Commentary itself does not complete a task or notify.

`app/ui/progress_timeline.py` renders paragraphs with the existing safe Markdown
widget and plain operation captions. Earlier entries remain visible when the
task finishes or stops, preceding the normal final response. Each task retains
up to 40 entries of at most 4,000 characters per paragraph; the view retains at
most 20 task timelines. Event deduplication is bounded. New sessions clear these
transient views. They add no extra conversational/model-history messages; native
assistant text already retained by the normal tool transcript remains intact.
The old phase sentence is a fallback when no public commentary is available.
Approval and stop notices still appear immediately. Raw technical details and
the strict attention policy from the first integration remain available.

Eight operation captions extend the Hungarian pilot through its existing
optional translation context. Other catalogs use the established English
fallback. Existing translations and pending native-review status are preserved.

Verification for this correction:

- Six focused cases pass, including real tool execution/settlement
  order, display failure isolation, public commentary, GUI-thread delivery,
  bounded grouping, final retention and absence of extra model requests. The
  prompt case covers both local and cloud batching guidance.
- The affected existing progress/streaming selection passes 22 checks.
- The broader focused selection records **195 passed and one failed** in 46.98
  seconds, with no skips. The failure is the unchanged
  `test_schema_errors_have_a_separate_cumulative_semantic_budget`. An isolated
  process loading the committed `da2329b` runtime reproduces the same expected
  `semantic_correction_limit` versus actual `completed` assertion. That test
  exercises the runtime directly without the new commentary observer or prompt
  option. Its recovery policy and assertion are preserved; the selection is not
  reported as fully passing.
- Final affected narrative/UI/notification/theme selection: **86 passed in
  31.95 seconds**, no failures or skips. Selections overlap and must not be
  added together.
- Full-size and narrow synthetic renders were inspected against the supplied
  reference. Evidence is under ignored `state/progress-narrative-*.xml`,
  repository-local temporary directories and `state/progress-narrative-*.png`.
  An initial GUI test override omitted Qt slot registration; it was corrected
  to observe the actual registered receiver, which confirms GUI-thread delivery.

No full-suite run, live model/API qualification or real Word/Excel workflow is
claimed. Natural paragraph frequency depends on the model emitting public
commentary; JSON-only fallback and commentary-free providers still show factual
operation summaries. Rich progress is transient across app restarts. Manual
acceptance remains useful for the actual long Word/Excel tasks and chosen model.

Preserve prior main at `archive/2026-10-21/main-before-progress-narrative`, commit
the bounded correction, fast-forward local main and remove only its merged
branch under `AGENTS.md`. Preserve the running user app, other worktrees, user
settings and all unrelated historical/unmerged/remote refs.

## Original phase-only implementation (historical)

`codex/semantic-progress` starts from clean local main `d049878`. This is the
first bounded integration of the Desktop semantic-progress handoff. The actual
application uses **PySide6**; its existing Qt stack and execution engine remain
in place. No prompts, routing, model requests, tool behavior, retries, completion
policy, model profiles or user preferences are changed.

### Original behavior and rollout

Sentence-based progress is opt-in while the real Word/Excel acceptance flows
remain pending. Start the development launcher from PowerShell with:

```powershell
$env:ORSI_ENABLE_SEMANTIC_PROGRESS = '1'
.\ORSI_TEST.cmd
```

Omit the environment override to retain the existing progress display. The
override is process-local and does not migrate or rewrite saved preferences.
The attention-policy corrections below apply with either progress display.

The working area shows one deterministic sentence. Ordinary changes coalesce
over a 12-second minimum interval. A single-shot Qt timer releases only the
latest already-observed phase; elapsed time never invents a milestone. Questions,
approval requests, cancellation and terminal handoffs bypass this delay. Streaming
answer text cannot overwrite the semantic phase. The existing timer, spinner,
question/approval composer, image preview and final response remain in place.

Raw activity is retained in collapsed **Technical details**, as plain text, with
at most 100 entries of 512 characters each. It remains inspectable after the
latest task finishes and clears on a new request or history reset. This is
transient UI history, not a new persistence system. Existing execution records
remain authoritative.

### Original integration map

- `app/conversation/orchestrator.py`: optional observer at actual preparation,
  execution, completion-review and history-saving boundaries. Observer exceptions
  are isolated by the existing safe callback helper. `turn_status` exposes the
  retained outcome after service cleanup; early control commands cannot inherit
  the previous request's status.
- `app/ui/worker.py`: correlates phase events with a fresh task/run pair for
  each submitted request and captures the final attention decision after
  `service.run()` settles. These IDs are transient UI request IDs, not invented
  durable conversation turn IDs.
- `app/runtime/semantic_progress.py`: small, bounded presentation coordinator;
  coalesces phases, rejects unrelated runs and accepts a terminal handoff once.
- `app/ui/main_window.py`: queued phase delivery to GUI-thread slots, cancellation
  and shutdown cleanup, stale-worker guards and one final presentation per run.
- `app/ui/chat.py`, `app/ui/status.py`: sentence templates, technical disclosure
  and preservation of the phase while streaming. Wording uses the existing
  optional UI translation context. The Hungarian pilot adds nine labels; its
  existing copy is preserved and native-speaker review remains pending.
- `app/ui/notifications.py`: central event allowlist and generic question banner,
  preserving existing notification enablement, foreground suppression, sound,
  native delivery and click-to-focus behavior.

### Exact attention policy (retained)

| Observed state | Desktop/sound attention, subject to existing preferences |
| --- | --- |
| Actionable approval displayed | Once for that open approval |
| Settled response with validated question metadata | One input alert; no completion alert |
| Retained completed outcome | One response/image result alert |
| Incomplete/limited/failed retained outcome or worker exception | One failure alert |
| User cancellation | None |
| Preparation, phases, raw activity, tool success, recoverable retries | None |
| Restored question/history, duplicate final, unrelated/late worker callbacks | None |

A successful tool receipt or an early proposed final answer cannot trigger
success. A returned partial answer with an incomplete or budget-limited outcome
produces failure attention even when the worker returns normally. Cancellation
is recognized from the retained outcome even when legacy cancellation text lacks
completion metadata. Banners contain fixed copy, never question text, paths,
arguments or provider errors.

### Original verification

- Focused affected regression selection: **184 passed in 96.63 seconds**, no
  failures or skips. Includes the new progress tests plus working status,
  notifications, streaming, local stops, questions, approvals, conversations and
  every existing GUI-language catalog check.
- Final affected logic recheck: **53 passed in 19.68 seconds**, no failures or
  skips, after tightening cancellation/shutdown and testing stale worker signals
  and the real coalescing timer.
- Final progress/theme recheck after visual correction: **55 passed in 9.47
  seconds**, no failures or skips. Selections overlap and are not added together.
- Synthetic full-size and narrow previews are inspected, including collapsed
  and expanded technical details. The first render exposed unstyled disclosure
  controls; theme-aware colors and alignment were corrected.
- The initial restricted selection stopped making progress after 11 checks and
  was interrupted. Native Windows access passed the affected checks; the
  restricted stall is not recorded as a product failure. Initial new-test
  failures concerned unsupported synthetic catalog and question fixtures; those
  fixtures were corrected to use the actual accepted boundaries.
- Evidence is ignored under `state/semantic-progress-*.xml` and the corresponding
  repository-local basetemp/cache directories. No live model/API, paid provider,
  native Office editing or full-suite run is claimed; the user requested focused,
  essential checks.

### Original limits and acceptance

The first integration uses coarse phases. It does not infer document/spreadsheet
milestones or claim that layout, formulas or checks passed from tool names.
Structured question metadata and actual approval requests identify required input;
unstructured prose is not guessed to be a new question. Other optional-language
contexts use their established English fallback. No crash-persistent notification
ledger or new task engine is introduced.

Before enabling semantic progress by default, exercise the unchanged 20+ minute
Word editorial flow with four images, then an Excel KPI flow with a recoverable
cloud error. Check actual phase provenance, raw detail access, responsiveness,
background question/resume behavior, and exactly one genuine terminal alert.
These live gates remain pending separately from passing deterministic checks.

After verification, preserve prior main as
`archive/2026-10-21/main-before-semantic-progress`, commit the bounded change,
fast-forward local main and remove only the merged feature branch, following
`AGENTS.md`. Other worktrees and historical/unmerged/remote refs remain intact.
The running user application is preserved and requires a restart to load changes.
