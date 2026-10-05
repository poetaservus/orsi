# Skill reference qualification v1 (Phase 5)

Date: 5 October 2026. Starting main: `05221dc`.
Implementation branch: `codex/skill-reference-qualification-v1`.

This phase evaluates the installed tiny Markdown pack through the actual local
llama-server and OpenAI Responses adapters, conversation service, reader,
executor and durable history. It does not change application prompts, sampling,
routing, context policy, tool implementations or accepted model profiles to make
failed cases pass. The frozen Phase 1 acceptance prompts and pack are unchanged.

## Matrix and evidence

`tools/skill_reference_qualification.py` runs two repetitions for all three shipped
local models and both configured cloud profiles. Each repetition covers:

- Explicit function generation, then its follow-up in the same session.
- The exact assertion task, unrelated arithmetic and disabled-reference task,
  each with fresh history.
- Automatic selection for the function and unrelated tasks, separately from
  explicit selection.
- A legacy single-file arithmetic skill.
- Package changes and switching to a legacy skill after establishing a real
  successful reference read.

That is 100 required cells, with additional setup function requests for change
and switch checks. The legacy skill uses a separate catalog, so it cannot skew
the original automatic-selection tasks. Every task reuses a frozen prompt;
there are no corrective retries or reworded prompts after a failed output.

The normal enabled tool catalog and run limits are retained. Host reads are
restricted to a disposable portable fixture, and every write/launch approval is
denied. The desktop key is read into memory only by the existing cloud adapter;
it is never copied into runtime settings, conversation prompts or reports. Each
backend uses isolated model-selection state. An external 180-second watchdog
cancels a test turn without changing the accepted model settings or output limit.

Native local models must match their configured bytes and target context/reply
limits; the harness also checks the loaded server's actual context. A constrained
memory resolution is recorded as unavailable for the accepted profile rather
than silently counted as a target-profile pass. All owned server processes and
cloud transport threads must exit. User configuration and runtime-selection
hashes must match their pre-run values.

Reports retain model identities, configuration hashes, request/token counts,
durations, reference identifiers, completeness flags, terminal statuses and fixed
error labels. Synthetic conversations remain in the ignored disposable workspace,
separate from the content-free summary. No key, document body, generated code,
provider payload or exception message is written to the report.

## Output and failure assessment

A function passes only after an isolated Python worker validates its AST and
checks below/inside/above/equal and negative bounds, then the exact reversed-bounds
exception. The worker permits one small function using only bounded syntax and
`min`, `max`, and `ValueError`; imports, filesystem operations, loops, recursive
calls and arbitrary call targets are rejected before evaluation.

Assertion output must contain the four exact frozen assertions and the reversed
bounds check. It must pass against the correct clamp and fail against incorrect
values, missing exceptions and wrong exception messages. These synthetic checks
run in a separate restricted worker with a three-second deadline, independently
of any model tool. The model is never asked to execute its generated checks.

Live qualification additionally requires the right successful document reads,
no forbidden or unrelated calls, no failed settled reader calls, matching package/version follow-up evidence,
completed durable terminal outcomes and a correct visible answer. Unavailability
must request the required content without fabricating a function. Stale/switch
checks distinguish permitted visible answer history from forbidden raw excerpts
and opaque provider replay. Missing, duplicated, skipped, failed or blocked cells
prevent qualification. Permission/authentication/quota errors block the remaining
cells for that provider profile rather than silently switching models.

This is qualification of the small reference feature, not promotion of the
application's broader model/workflow qualification flags. GUI layout and lifecycle
remain covered by existing deterministic checks; this live matrix exercises the
conversation service rather than driving a visible desktop window.

## Reproduction

Run against a committed, clean candidate using the bundled runtime and a new
ignored workspace. Supply an already authorized local key file; do not put its
contents into command arguments or tracked files.

```powershell
.\runtime\python\python.exe -m tools.skill_reference_qualification `
  --workspace state/skill-reference-live-v1 `
  --report state/skill-reference-live-v1-summary.json `
  --key-file C:\path\api.txt
```

The tool returns a nonzero exit code if qualification fails. Selecting fewer
models or repetitions is available for diagnosis, but cannot produce a qualified
full-matrix report. Reports name the measured commit and hash application,
configuration, tests, harness and pinned runtimes. Documentation-only commits
can retain source-matching evidence; source or profile changes invalidate it.

## Results

The initial focused check passed 145 tests, including the generated-code worker,
fail-closed report gate and Phase 3/4 regressions. Initial full regression passed
1,910 tests and 15 subtests with 49 existing skips. The final gate/context-scope
check passed 37 tests, followed by a full confirmation of 1,912 tests and 15
subtests with 49 skips. An additional fallback-check correction and its regression
case passed all 38 gate tests. The first full run after this correction recorded
1,911 passed, 2 failed, 49 skipped and 15 subtests passed. Failures were an empty
PID file read in `test_parent_exit_kills_owned_child_and_descendant_only[True]`
and a native `WinError 5` directory-rename rejection in the depth-limit reader
case. Both tests and their implementations are unchanged. The process test
observes file existence before the writer has necessarily published its PID;
the rename denial's cause was not established. The isolated native/reader/gate
recheck passed 117 tests. The final full confirmation passed 1,913 tests and 15
subtests, with 49 existing skips, in 225.23 seconds; both previously failing
native cases passed. No test was skipped, relaxed or given a longer deadline
to conceal these results.

The full live matrix at candidate `789e011` finished all **100 required cells**:
**36 passed, 44 failed, 20 blocked**. Its original strict gate remains
**unqualified**. All owned resources exited and user settings were unchanged.

| Configured model | Passed | Failed | Blocked | Effective context / output reserve |
| --- | ---: | ---: | ---: | --- |
| Qwen 3 14B (`Qwen314BQ4KM.gguf`) | 6 | 14 | 0 | 16,384 / 4,096 |
| Qwen 2 3B (`model.gguf`) | 6 | 14 | 0 | 16,384 / 4,096 |
| Qwen 3 VL 4B (`Qwen3VL4BInstructQ4KM.gguf`) | 6 | 14 | 0 | 16,384 / 4,096 |
| GPT-6 Luna | 18 | 2 | 0 | 1,050,000 / 128,000 |
| GPT-6.1 Sol | 0 | 0 | 20 | 1,050,000 / 4,096 configured; live access blocked |

Every local model passed both repetitions of explicit unrelated arithmetic,
automatic unrelated arithmetic and legacy single-file use. None passed the
reference-dependent workflows reliably. All six explicit function cases skipped
the required behavior read. Five of six automatic function cases selected the
correct skill but still skipped that read; one 3B case reached a repeated-call
stop. All three models retrieved checks in at least one case, but the strict
read/output gate still failed. The 14B assertion cases recovered from an initial
failed read; this conservative gate counts a failed settled call as a failure
rather than claiming first-attempt reliable retrieval.

The local stale/switch cases could not establish their prerequisite successful
behavior read. They remain failed end-to-end gates, not evidence that the
runtime's scope protections were bypassed. Those protections passed the Phase 3/4
deterministic suite. Luna established real prior reads and passed all four live
stale/switch cells, as well as both repetitions of function generation, assertion
generation, grounded follow-up and automatic selection. Generated functions and
assertions passed their isolated behavior checks.

Sol's first actual request returned the adapter's `permission` error, with a
`model_unavailable` terminal status. The remaining 19 cells are explicitly
blocked and were not attempted. The same key worked for Luna; no key rotation,
fallback model or account-access change was performed. This is an access blocker,
not a passed Sol test or a local/network failure.

### Evaluator correction and cloud recheck

A separate synthetic disabled-reference review found that the wording matcher
did not recognize the typographic apostrophe in “can't.” The visible reply
requested the required reference, but the model also attempted
`filesystem.read_text`, which returned `not_found` inside the fixture. That host
fallback independently violates the reference boundary. The text matcher was
corrected in `866efed`, with a regression case; the app, model settings, tools,
prompts and fixtures did not change.

The original 100-cell report is preserved without editing scores or pretending
it was generated by the corrected evaluator. Its unavailable wording scores can
include this false negative. A fresh Luna-only, two-repetition recheck at
`866efed` again passed **18 of 20** cases. Both disabled-reference cells attempted
a forbidden non-reference fallback before completing their response. Thus the
remaining fallback failure is real despite correcting the text check. The
subset report is intentionally unqualified: it contains neither the complete
model matrix nor all passing cells. No partial report replaces full qualification.

Local evidence is bound to the original harness revision; the corrected cloud
subset has its own identity. The application, profiles and acceptance inputs
are byte-identical between these candidates. Neither run promotes existing model
qualification flags. Live results, unavailable gates and deterministic passes
remain separate.

### Retained artifacts and next work

Ignored, machine-local artifacts:

- `state/skill-reference-live-v1-summary.json`: original content-free 100-cell report.
- `state/skill-reference-live-v1-20261005/`: disposable installations and synthetic state.
- `state/skill-reference-luna-recheck-v1-summary.json`: corrected-evaluator cloud subset.
- `state/skill-reference-unavailable-review-v1/`: separate synthetic fallback review.
- `state/skill-reference-qualification-regression-text-final.xml`: retained earlier native test failures.
- `state/skill-reference-qualification-regression-confirm.xml`: final passing regression evidence.

The initial document incorrectly stated 50 cells; this record corrects it to
10 workflows × 2 repetitions × 5 models = 100. No test was omitted or added to
the live matrix by that documentation correction.

The next bounded repair should first address local models skipping required
reference reads and cloud models using ordinary file tools when the reader is
unavailable. Inspect the interaction between ordinary-question core guidance and
required skill lookup before changing prompts, routing or sampling together.
Repeat the frozen cases after a focused repair. Sol requires appropriate account
access before its cells can be qualified. This phase completes the qualification
audit and reproducible harness; it does **not** complete successful release
qualification of the reference feature.
