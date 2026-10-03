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

## Persistence prerequisite

Atomic state replacement now retries only Windows errors 5, 32 and 33, for at
most 900ms, using the same already-flushed bytes. No filesystem tool action is
replayed. Permanent denial still propagates and the journal remains fail closed.
Fault-injection checks verify exact bytes, bounded exhaustion and immediate
propagation of unrelated errors. The full regression run passed **860 tests and
15 subtests**, with **54 skipped live checks**. The repeated continuous-session
failure passed with this fix. These results do not constitute live qualification.

## Stage 2: one shared native-tool policy

Agent requests now use the shared compact policy at every context size. Tool
descriptions and strict argument schemas still come from the unchanged registry;
there is no phrase-based filtering and no change to permissions or sampling.
The policy retains personality, latest-user intent, path scope and relative-path
rules, untrusted-content handling, external approvals, exact edits, failure
honesty and stopping on unknown mutation outcomes. Chat-only prompts are unchanged.

For the full local catalog and current home path, the system prompt decreases
from **17,345 to 4,631 UTF-8 bytes**, with the existing heuristic estimating
**4,609 versus 1,430 tokens**. These are prompt-size measurements, not measured
total task savings. Historical full-prompt generators remain available for
baseline comparison; inference uses the shared policy.

Six historical tests asserted duplicated prose inside the submitted prompt.
Their functional assertions remain intact. The text assertions now verify the
shared policy and authoritative native tool descriptions/argument schemas.
The live acceptance prompt suite is unchanged, including code, clarification,
file-byte verification, cancellation and model round trips, repeated per profile.

Stage-two full regression: **861 passed, 54 skipped, 15 subtests passed**.
Live qualification remains separate and pending; a deterministic pass cannot
promote this branch.

## Stage 3: provider-specific estimates

The local schema reserve now counts the exact projected native function JSON
submitted to llama-server, rather than runtime-only validation annotations.
When its owned server is already idle, content is tokenized with that model's
`/tokenize` endpoint, with a 500ms deadline and bounded response size. Literal
special-token-looking content is counted as text. Counting never starts or
duplicate-loads a model. Only SHA-256 keys and integer counts are cached, with a
128-entry bound; no content, credentials or token IDs enter diagnostics/cache.

Unavailable, busy, timed-out or malformed tokenizer responses retain byte-based
fallback estimates. Wrapper allowances, answer reserve, safety margin and the
accepted model limits are retained. These remain estimates of a request, not an
exact application of every native chat template. Invalid provider counters cannot
weaken admission. Both initial selection and subsequent agent steps use the same
provider-specific schema accounting, including recovery projections.

The pinned tokenizer contract is documented in the
[llama.cpp b9976 server API](https://github.com/ggml-org/llama.cpp/blob/e3546c794/tools/server/README.md#post-tokenize-tokenize-a-given-text).

Offline full-catalog schema reserve decreases from **4,388 to 3,912 estimated
tokens**, while retaining all 12 definitions. Stage-three full regression passed
**872 tests and 15 subtests**, with **54 skipped live checks**. An earlier run's
30ms timeout-start assertion failed while live model tests were running; all 32
runtime checks and the full suite passed when rechecked without that contention.
Neither the timeout nor its assertions were relaxed.
