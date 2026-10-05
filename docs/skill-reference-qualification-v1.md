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

That is 50 required cells, with additional setup function requests for change
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
no forbidden or unrelated calls, matching package/version follow-up evidence,
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
fail-closed report gate and Phase 3/4 regressions. Final deterministic and live
results will be recorded here after their completion. Unattempted, unavailable
and failed live checks remain distinct from passed deterministic tests.
