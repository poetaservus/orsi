# Semantic progress and attention notifications, 21 October 2026

`codex/semantic-progress` starts from clean local main `d049878`. This is the
first bounded integration of the Desktop semantic-progress handoff. The actual
application uses **PySide6**; its existing Qt stack and execution engine remain
in place. No prompts, routing, model requests, tool behavior, retries, completion
policy, model profiles or user preferences are changed.

## Behavior and rollout

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

## Integration map

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

## Exact attention policy

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

## Verification

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

## Deliberate limits and next acceptance

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
