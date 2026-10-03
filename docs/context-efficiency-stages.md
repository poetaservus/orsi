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

## Stage 4: measured recovery and revision-bound qualification

Recovery remains **off** in the accepted configuration. The existing projection
preserves user requirements, exact arguments, scoped call/result pairing and
durable raw results. It projects large results before compacting older assistant
material under pressure; it stops rather than dropping protected requirements.
Its on/off acceptance arms now use the same provider-specific accounting as the
application. `--experiment-only` compares recovery on/off on identical candidate
source and prompt hashes, with fixed live cost/success thresholds. It can report
an experimental pass but **cannot qualify rollout** or replace the accepted-source
comparison.

The preserved live qualification harness is now versioned in
`app/infrastructure/qualification.py` and `tools/live_qualification.py`.
The ordinary, long-code, read/edit/clarify/follow-up, cancellation/next-task and
model round-trip prompt templates remain unchanged. Every chooser profile must
run all five workflows twice. The report binds revision, source, prompts,
effective flags, model bytes/profiles, sampling and runtime binaries. Required
missing/skipped/failed cells, incomplete outcomes, changed limits, process leaks,
unverified file bytes or a failed full regression block qualification. Routine
workflow costs count every physical request; missing usage stays unknown.

`python -m tools.verify_live_qualification --report <report>` is read-only. It
changes no branch, build, model selection or remote. No automatic promotion or
feature activation was added. A deterministic pass with legacy skips cannot
substitute for any required live cell.

The frozen accepted source `0c58c13` completed **20/30 live cells** (14B 9/10,
3B 5/10, VL 4B 6/10); all owned servers exited. These failures are retained as
baseline observations, not retrospectively certified as a qualified build.
The candidate matrix and recovery experiments write content-free counters under
ignored `state/`; their separate synthetic fixture histories contain validation
content. All final live results must be reported separately from unit-suite passes.

Stage-four full regression passed **920 tests and 15 subtests**, with **54 skipped
legacy live checks**. Gate tests explicitly reject replacing any of the 30
required live cells with skipped or deterministic evidence. Final live candidate
results are recorded in `state/context-stage-candidate-matrix.json`; recovery
off/on experiments and the numeric summary remain separate ignored artifacts.

## Follow-up prompt correction after live evidence

The first candidate at `b3cf936` passed 19/30 live cells (14B 8/10, 3B 5/10,
VL 4B 6/10), despite passing the 920-test regression. It is explicitly **not
qualified**. All owned servers exited. The 14B's failed edit workflow produced
the exact expected bytes, but first attempted a stale excerpt and required a
semantic correction. Its post-cancellation metadata request invented a Desktop
prefix and correctly returned not-found for that wrong path. Clarification itself
passed. Raw traces and unsuccessful outcomes remain preserved.

A separate prompt-only correction restores two explicit contracts: pass supplied
read/metadata paths verbatim (let the runtime resolve relative paths), and obtain
a fresh excerpt before each edit after a mutation. No tool behavior, permission,
sampler, context limit, prompt template or acceptance assertion is changed to
turn these failures green. The unchanged full matrix must run again for this
new revision. The first candidate's evidence remains in
`state/context-stage-candidate-matrix.json`; the retest uses a separate artifact.

The corrected full-local shared prompt is **4,909 bytes**, versus 17,345 for the
accepted full prompt (71.7% smaller). Its full regression passed **920 tests and
15 subtests**, with **54 skipped legacy live checks**. The retest report is
`state/context-stage-corrected-matrix.json`; live success must be judged from that
report independently of the deterministic pass. Across successful paired routine
cells only, the first candidate used 52.5% of baseline request tokens; its failed
or unmeasured work was excluded from savings and it still could not qualify.
