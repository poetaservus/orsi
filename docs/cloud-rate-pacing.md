# Cloud rate pacing, 6 October 2026

After cloud's step allowance was raised to 32, the user's normal app still
stopped with `provider_rate_limit` / `rate_limit_exceeded`. The new step budget
was active. The user reports 200,000 tokens per minute and 500 requests per
minute for the active cloud model. Local main `e05aee4` is the starting point
for the bounded `codex/cloud-rate-pacing` change.

Content-free logs for the reproduced run record 21 completed API operations
from 19:50:50 through 19:51:30 and the next operation failing at 19:51:31.
The completed operations total 307,890 input tokens, 1,913 output tokens and
309,803 total tokens; 289,520 input tokens were cached. From agent start to the
last completed operation is about 44 seconds. These are API usage counters,
not a full-price billing estimate. No transcript, file contents, arguments or
credential is included in this record. Increasing the step allowance cannot
prevent a provider token-rate failure or undo completed request usage.

The [OpenAI rate-limit guide](https://developers.openai.com/api/docs/guides/rate-limits)
documents numeric request/token capacity and reset headers, the impact of large
output allowances on rate admission, and the restriction against replaying a
stream after consuming output. The [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
confirms that cached input still counts toward token rate limits.

## Implementation

The Responses adapter now paces each HTTP attempt inside its existing owned
async request runner. A rolling minute ledger reserves estimated input plus
its existing safety margin and the full configured output allowance. A terminal
usage record settles the reservation to the actual total,
including cached input and reasoning. Unknown/interrupted usage retains its
reservation. Each attempt is counted; failed retry attempts retain their reserve.
Completion/interruption refreshes the reservation's minute window so output
from a long-running stream does not disappear from rate accounting immediately.

The adapter also reads only allowlisted numeric request, token and project-token
limit/remaining/reset headers. Insufficient capacity waits until the reported
reset; valid server limits supersede local bootstrap limits. Missing headers use
the minute ledger. Unsupported/malformed header values and request identities
never enter the log. Only fixed resource names, numeric capacity and wait seconds
are logged. Pacing can make a large-output-budget workflow slower. A request
larger than the known token capacity stops locally before spending tokens.

The user's reported Luna limits are stored in ignored
`state/cloud_rate_limits_v1.json`, loaded at startup. This is machine-local
account state; `config/cloud.json` and its accepted model profiles are unchanged.
The optional typed configuration supports limits for other installations/tests;
older configuration remains valid. Switching models preserves each model's debt
and refreshes hooks for the current model. Key replacement starts a new pacing
ledger and releases the previous transport.

The existing request deadline includes rate waits. Stop, shutdown and key
replacement cancel a wait without sending another request or leaking the owned
SDK thread/client. SDK pre-stream retry ownership is unchanged. A started stream
is never retried or replayed by this change; incomplete tool calls remain blocked.
Cloud stays at 32 steps and local at 24. Prompts, tool permissions/behavior,
routing, model sampling, context projection, output allowances and deadlines
are unchanged.

## Verification

The final unrestricted focused check passed 301 tests in 26.73 seconds. Tests
use real SDK parsing with mock HTTP/SSE transport, synthetic usage and an
advancing test clock. The reproduced 21-operation usage pattern finishes with
rate waits and the original 128,000 output allowance. A 32-step agent completes
31 distinct tools exactly once and produces its final answer on request 32.
All three header buckets, account-state loading, legacy config, model switching,
oversized admission, unknown usage, long-stream retention, deadline and cancellable resource release
are covered. A partial rate-limited stream remains a single request with its
reservation retained. Existing input-boundary and acceptance prompts are intact.

The initial new check exposed the SDK wrapping an admission-hook error as a
connection failure. Initial admission was moved before SDK dispatch; retry-hook
admission preserves its original safe error category. An initial broad command
named a nonexistent test file and collected none. Another broad run recorded
265 passes and an input-boundary failure because account-specific bootstrap
limits had temporarily been placed in accepted configuration. They were moved
to ignored account state without changing the input contract or its test.
A new agent test then used the wrong result field in its assertion; correcting
that test-only assertion confirmed the successful 32-step run. Final focused
confirmation includes all these cases.

The first full unrestricted run passed 1,952 tests and 15 subtests, with 49
existing skips and no failures in 281.64 seconds. A subsequent review tightened
input plus output headroom and retained capacity for a minute after long streams;
the final 301-test focused confirmation includes these changes. Final full-suite
confirmation initially recorded 1,953 passes, one unchanged Windows folder
rename access-denied failure, 49 existing skips and 15 subtests in 297.45
seconds. `test_skill_discovery.py::test_entry_limit_rejects_entire_scope_before_any_skill_read`
fails at the temporary-folder rename, after its discovery assertions pass.
Its unrestricted recheck together with all pacing checks passed 49 tests in
8.22 seconds. No skill-discovery implementation or test was changed. Fresh full
unrestricted confirmation passed 1,954 tests and 15 subtests, with 49 existing
skips and no failures in 248.54 seconds, including the previously failing
folder-rename case. All runs use repository-local basetemp; JUnit evidence is
retained under ignored `state/test-artifacts/`. A content-free startup snapshot
at `state/diagnostics/cloud-rate-pacing-effective.json` confirms Luna's 500 RPM,
200,000 TPM, 1,050,000 context, 128,000 output, cloud 32/local 24 and no created
API transport. No paid API request,
key creation/rotation or live model qualification run is made for this change.
Deterministic tests cannot prove that external clients sharing an account will
stay within its limits; server headers reflect capacity outside this process
only when received. Skipped live gates remain separate from passed checks.

## Integration and recovery

Pre-change refs, worktree map and a verified complete-history bundle are under
ignored `state/backups/cloud-rate-pacing-20261006/`. Preserve prior main at
`archive/2026-10-06/main-before-cloud-rate-pacing`, commit the bounded verified
change, fast-forward local main and remove the merged local feature branch.
User conversations, keys and runtime selection are preserved. Other active
worktrees and remote refs are unchanged. Restart `orsi.cmd` to load the new
adapter and account limits.
