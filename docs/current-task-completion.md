# Current requests and completion review

This bounded local change starts from `dd2da89` on
`codex/current-task-completion`. Each agent turn now receives a separate task
frame with the literal current request, applicable standing requirements and
historical work. Earlier cleanup tasks cannot take the current request's place.
The frame and recovery guidance are temporary model context; original user
messages, saved goals and tool receipts remain the durable evidence.

Before returning a proposed final answer, the runtime asks the selected model
to compare that answer and the current turn's actual work against every requested
change. A strict, turn-scoped review returns `ready`, `continue` or `blocked`.
Only `ready` accepts the original proposed answer. A diagnosis, plan or unrelated
answer that leaves requested work undone continues within the same turn. A
concrete blocker returns an unfinished outcome with remaining work; its goal
stays stopped. The review is retained with the saved outcome and survives reload.
Older histories without reviews remain readable.

The comparison is a model assessment, not an independent behaviour test.
`behaviour_verified` remains false. Internal review JSON is excluded from visible
answers and provider answer replay. New agent turns normally require one extra
model request before returning an answer; this uses the existing step, request,
context, cancellation and timeout budgets. Invalid or mismatched reviews stop
unfinished within the existing format-failure limit. Native tool and constrained
text fallback adapters use the same review gate.

Known rejected edits that need fresh source cannot finish or be classified as
blocked merely because a read or corrected patch is necessary. Recovery continues
in the current turn, with the read received before constructing the patch.
Already-present text can still finish without another mutation. Missing or
inaccessible source and denied approval retain their existing boundaries. The
review grants no read, write, execution or approval authority.

Only runtime task framing, completion/recovery handling, documentation and
focused test scripts change. Acceptance requests, core prompts, routing, tool
contracts, model profiles, sampling, context-selection policy and user settings
are preserved. Historical scripted tests supply an explicit ready review for
their previously completed candidates; the new coverage tests script positive,
negative, blocked and invalid assessments independently.

Verification uses synthetic files and repository-local test directories. The
initial sandbox run denied native Windows file operations; its failures are
separate from native test results. No full suite or live model/provider gate is
run, following the request to run only necessary tests.

Final focused native qualification passed 478 tests with one host symbolic-link
skip in 57.63 seconds. The subsequent source-evidence recheck passed 133 tests
with the same skip in 14.29 seconds, including one additional regression for a
failed fresh read after an earlier already-present check. Together these cover
479 distinct passing tests. The earlier cancellation timing miss passed unchanged
in the final combined run. Native SDK transport checks use synthetic responses;
they are separate from unrun live provider and local-model qualification.

Pre-integration refs and worktree metadata are preserved under ignored
`state/backups/current-task-completion-20261011/`. User settings and runtime
selection were not edited; the four other worktrees and historical/unmerged tips
remain unchanged. Local integration follows `AGENTS.md`: preserve prior main,
commit this bounded change, fast-forward local main and remove only this merged
feature branch. No remote publication is authorized by this request.
