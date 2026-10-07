# 80 — Evidence-led debugging and performance

Read for a reproduced failure, slow operation, excessive memory or unstable timing.

## Diagnose before changing

Record the trigger, actual result, expected result and environment. Follow the
real entry point and traceback. Reduce the failing case without removing the
behavior that causes it. Separate observations from hypotheses; confirm the
likely cause with a targeted inspection, trace or experiment.

| Symptom | Useful first evidence |
| --- | --- |
| Import/startup failure | Actual interpreter, installed version, import/entry path |
| Wrong result | Input/output contract, parsing, ordering, mutation, boundary cases |
| Freeze or late cancellation | Thread/event-loop state, blocking boundary, owned work |
| File unexpectedly unavailable | Permissions, open handles, path identity, timing |
| Repeated side effects | Retry layers, idempotency, ambiguous timeout outcome |
| Slow or memory-heavy operation | Representative profile, data size, allocation growth |

Do not change prompts, routing, dependencies and timeouts simultaneously to make
one test pass. Change the confirmed cause while preserving the acceptance input.
If a sandbox cannot perform native access, establish whether the same code works
with the required capability before classifying it as a product defect.

## Measure the user's workload

Define the metric: end-to-end latency, throughput, peak memory, UI responsiveness
or startup. Measure representative input and baseline in the actual environment.
Use `perf_counter` for elapsed intervals, `cProfile` for CPU call attribution,
`tracemalloc` for Python allocations, and a suitable external/native profiler when
the missing cost lies outside Python. A flat profile is evidence, not a verdict.

Compare like for like: same input, warmup/cache state, configuration and output
contract. Avoid a single run's noise or a microbenchmark that omits the real I/O.
Record what changed and whether the result remains correct.

## Improve the dominant cost

Start with algorithmic complexity, redundant work and I/O shape. Remove repeated
parsing or duplicate queries before rewriting expressions. Batch only within
real API/transaction limits. Reuse an owned connection/client when its lifetime
allows it. Stream large data when the caller does not need all results at once.

Avoid incremental copying, unbounded retained history and loading a whole file
only to inspect a prefix. A generator is not memory-efficient if its consumer
immediately materializes everything or keeps references indefinitely.

Cache only with a defined key, lifetime, size and invalidation rule. Consider
mutability, credentials, concurrent access and stale results. `lru_cache` can
retain arguments/results and is not a decorator for caching coroutine results.
Slotted records, vectorization, threads/processes and alternate serializers need
measured benefit and compatibility, not prestige.

## Make regression checks stable

Test exact results and meaningful resource bounds. For performance, prefer an
explicit benchmark environment and tolerances justified by noise. Do not make
ordinary tests depend on tiny wall-clock thresholds. For concurrency correctness,
use a synchronization event rather than an arbitrary sleep.

After a repair, run the smallest meaningful regression and required broader
checks. Once those pass, stop unless a new unresolved concern justifies another
experiment. Do not repeatedly tune code without evidence of improvement.

## Report what is known

State the cause established, the fix and evidence. An intermittent failure needs
honest uncertainty and preserved observations. Do not claim an optimization from
code appearance, or claim production performance from a synthetic tiny input.
When instrumentation is needed, prefer counts/timings/error labels over logging
private input, output, files or secrets.

For concurrency read [50](50-concurrency.md); for bounded verification read
[40](40-testing.md) and [95](95-review.md).
