# Isolated context-efficiency work

The user-accepted starting state is `0c58c13`, preserved on
`codex/list-marker-spacing`. Work takes place on `codex/context-efficiency-stages`.
Neither `main` nor the remote is promoted by these experiments. Runtime model
selection and the accepted model profiles remain unchanged.

## Stage 1: display occupancy separately from admission

The header uses the latest physical request's reported total tokens (or input plus
output when both are reported). It never sums a turn's multiple requests. Without
provider usage it shows the projected next input with `~` to indicate an estimate.
The tooltip separately shows the next request's admission budget, answer reserve,
safety margin and remaining capacity. Admission still uses the complete budget.

Measurements are scoped to the session and backend revision. Starting another
request clears stale usage; missing usage, a new session, mode changes and model
switches require an estimate until a new request reports usage. Returning to the
previous model does not restore an old measurement. Persisted legacy completion
metadata has no reliable model provenance, so reopened history uses an estimate.
Partial responses retain measured usage without changing their incomplete status.

Validation: focused UI/conversation/budget/completion/lifecycle checks passed,
plus 19 lifecycle/model-selection checks. Full regression results are recorded
separately; skipped live tests are not qualification. This stage changes display
accounting only: prompts, tools, context policy, sampling and limits are unchanged.

The full run recorded 851 passes, three Windows `WinError 5` atomic-save failures,
54 skipped live checks and 15 passed subtests. Rechecking the three affected test
groups reproduced one journal replacement failure. This is not a green full run
and provides no permission to promote the candidate. A separate bounded persistence
fix precedes further context changes.
