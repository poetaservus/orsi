# Separate cloud step budget, 6 October 2026

The user requested the maximum supported step allowance for cloud mode while
keeping local mode at 24. The bounded `codex/cloud-max-steps` change starts from
local main `36e2df4`.

The existing agent contracts support at most 32 steps, model requests and
capability calls per turn. Cloud now selects `runtime_limits.cloud_max_steps=32`
from the versioned agent configuration; local retains `runtime_limits.max_steps=24`.
Older configuration without the new field defaults to 32 for cloud. Values above
the supported maximum are rejected. This does not expand the underlying 32-step
contracts or remove finite limits.

`AgentRuntime.effective_max_steps` follows the active backend mode at the step
guard. Switching cloud to local and back applies 32, 24 and 32 without replacing
the configured local limit or resetting conversation history. Direct Responses
and legacy cloud adapters identify their mode explicitly. The temporary skill
reference runtime shares the same model/configuration and follows the same
effective budget. Content-free diagnostics log only the selected mode and step
count at the start of an agent run.

Prompts, tool authority/behavior, routing, sampling, context/model profiles,
reference paging, deadlines and API retry/rate-limit policy are unchanged.
The other existing 32-request/call ceilings can still stop a turn; API rate
limits remain independent. Cloud can complete a final answer on request 32 after
31 tool calls, and stops before request 33 after 32 tool calls.

## Verification

The final native focused checks passed 168 tests. A real hybrid mode switch with
isolated scripted backends completes cloud on step 32, stops local after step
24, and completes cloud on step 32 after switching back. Outcomes and settled
calls survive reopening the saved synthetic conversation. Another run stops at
32 without sending request 33. Direct cloud adapters and both cloud/local skill
reference runtime copies use the correct budget. Legacy configuration remains
readable and an unsupported cloud budget is rejected.

The first focused invocation named a nonexistent test file and collected no
tests. The next boundary check had a test-harness assertion reading settled
calls from the stripped saved outcome instead of the turn's separate journal;
the assertion was corrected without changing runtime behavior. A sandboxed
reference suite then recorded 37 native installation/handle failures and 129
passes; these environment restrictions are separate from product failures.
The unrestricted 168-test focused confirmation passed. Full unrestricted
Windows confirmation passed 1,937 tests and 15 subtests, with 49 existing skips
and no failures in 237.32 seconds. Both runs use repository-local basetemp and
retain JUnit results under ignored `state/test-artifacts/`. Existing live
API/local-model qualification gates remain unrun and are not counted as
deterministic passes. No model request is sent to an external API by these checks.

## Integration and recovery

The exact previous agent configuration, pre-integration refs, worktree map and
verified complete-history bundle are preserved under ignored
`state/backups/cloud-max-steps-20261006/`. After verification, commit the bounded
change, fast-forward local main and remove its merged local feature branch.
The prior main is also preserved at
`archive/2026-10-06/main-before-cloud-max-steps`. User runtime selection and
conversations/settings are preserved; other active worktrees and remote refs
are unchanged.
