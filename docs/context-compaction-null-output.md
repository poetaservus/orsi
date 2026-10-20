# Null-output context compaction, 20 October 2026

## Reproduced defect

An older failed capability receipt may legitimately have `output: null`. Once
ordinary projection still cannot fit the request, the deeper compaction branch
previously called `.get('source_retired')` on that null output. This raised
`AttributeError` and reached the generic context-recovery failure stop after
otherwise successful work.

The new focused null-output regression reproduced that exact exception on the
unchanged recovery implementation. Its omitted-output control passed. The fix
checks that output is a dictionary before inspecting the retirement marker.
Existing source-retirement behavior and original failed receipts remain intact.

## Bounded change

- Null and absent outputs survive pressure-driven compaction without losing
  failed receipts, error envelopes, call arguments, pairing or user requirements.
- Recovery reports fixed stages (`schema_reserve`, `budget`, `projection`,
  `compaction`) through an optional runtime observer. It does not alter admission,
  projection sizes, compaction selection or request content.
- Optional strict terminal metadata records the stage and a fixed exception
  category. The profile logging allowlist retains those categories without
  exception messages, tracebacks, source, paths or raw request data.
- An unexpected recovery exception retains a generated answer visibly as an
  unverified proposal. The service returns incomplete completion metadata rather
  than reducing this specific failure to a plain error string. The terminal task
  remains stopped; this is not an accepted completion or permission to replay.
- Ordinary non-fitting budgets continue to produce `CONTEXT_LIMIT`; unrelated
  internal errors retain their previous behavior. Older saved outcomes remain
  loadable without the optional diagnostic field.

## Focused verification

Final selections are disjoint: **31 passed** in the three focused modules and
**7 passed** in the related preservation selection, **38 checks total**.

```
runtime/python/python.exe -m pytest -q -o addopts= -p no:cacheprovider
  tests/test_context_compaction_null_output.py
  tests/test_context_failure_reporting.py
  tests/test_context_recovery.py
  --basetemp=state/test-tmp/context-null-focused-3
```

The seven selected preservation checks cover interrupted-review proposals,
completion-review approval restrictions and fallback, existing model budgets,
later presentation failures, stale-review save/reload and worker stop reporting.
Their repository-local temporary directory is
`state/test-tmp/context-null-preservation-4`.

The combined runtime regression performs a real rejected edit, a fresh read,
exactly one successful edit, a saved-source read, four large independent source
reads, proven deeper compaction, a subsequent answer and a current ready completion
review. It asserts `context_compactions > 0`, unchanged failed receipts in the
model request, complete original durable source results and conversation reload.
All eight settled calls remain; only one edit succeeds. The fixture uses an
explicit synthetic 24,000-token context and scripted model. Earlier fixture sizes
correctly encountered protected-context or approval-diff limits; no production
limit was changed to accommodate them.

Direct cases cover both local and OpenAI-context admission branches with null and
omitted outputs, fixed observer stages and a genuinely unfit protected request.
Failure-injection cases cover safe exception categories, logging privacy,
retained approvals/settled edits, visible unverified proposals and saved outcomes.
Whitespace validation passes.

No full suite, live API/model qualification, browser or user-project run is made.
This fixes the reproduced compaction defect; it does not establish the exact
exception from the historical encrypted incident. Screenshot accounting, image
transport caps, token limits, prompts, routing, model profiles, sampling, approval
policy and user settings remain unchanged. The running app is preserved and needs
a restart to load the repair.

## Local integration

`codex/context-compaction-null-output` starts from local main `5dcbb21`. Preserve
that tip as `archive/2026-10-20/main-before-context-null-output`, commit the bounded
change, fast-forward local main and remove only this merged feature branch.
Other worktrees, historical/unmerged refs and remote refs remain intact.
