# 50 — Async, threads, processes and cancellation

Read when overlapping work, UI responsiveness or worker lifetimes matter.

## Choose execution from the workload

| Work | Starting choice |
| --- | --- |
| Small sequential script | Synchronous functions |
| Many independent network operations with async clients | Asyncio |
| Blocking I/O inside an async/GUI application | Managed worker/thread boundary |
| CPU-bound Python work needing parallel speedup | Processes or measured native code |
| Existing framework event loop | Integrate with that loop's lifecycle |

I/O does not automatically require async. Threads may help blocking I/O; ordinary
GIL-enabled Python threads do not generally accelerate pure Python CPU work.
Native libraries and free-threaded builds have different behavior: inspect and
measure the actual runtime. `asyncio.to_thread` is not a universal CPU accelerator.

## Keep the event loop usable

Do not run blocking sleep, large CPU loops or synchronous clients in a coroutine
and call it non-blocking. Await async-native operations or offload the specific
blocking boundary. Do not call `asyncio.run()` inside an already running loop.
Use it at an owned application entry point; library functions expose awaitables.

Use `asyncio.TaskGroup` for related work on Python 3.11+ when a failure should
cancel siblings and propagate. It can raise an exception group; callers need a
deliberate error policy. If partial success is desired, collect per-item outcomes
explicitly. `gather` has different failure/cancellation behavior; do not assume
all siblings stop on the first failure.

## Bound concurrency and memory

A semaphore bounds active work but not the number of task objects created.
Creating a million tasks and waiting behind a semaphore still consumes memory.
For large or unbounded inputs, use a bounded queue and a fixed worker set. Bound
connections, buffered bytes and outstanding results, not just concurrent calls.
For finite moderate batches, a semaphore may be sufficient.

This Python 3.11+ example demonstrates structured ownership of two related jobs,
not a high-volume scheduler:

```python
import asyncio


async def increment(value: int) -> int:
    await asyncio.sleep(0)
    return value + 1


async def run_pair() -> tuple[int, int]:
    async with asyncio.TaskGroup() as group:
        first = group.create_task(increment(1))
        second = group.create_task(increment(2))
    return first.result(), second.result()
```

## Cancellation is an outcome

Allow cancellation to propagate after cleanup. Do not swallow
`asyncio.CancelledError` or retry a cancelled operation. Use `try/finally` for owned
resources. Establish whether a request stopped before a side effect, after it,
or with an unknown external result. Report partial progress honestly.

Cancelling an await of `to_thread` does not stop its underlying thread. A worker
needs cooperative cancellation and ownership until completion. Blocking clients
need timeouts; processes and subprocesses need a stop/wait/escalation policy.
Do not force-kill a shared process or terminate a thread as routine cleanup.

Protect shared state with an appropriate lock or single owner. Keep critical
sections small; do not hold locks across network operations or sleeps. Async
locks do not protect cross-thread access. Communicate through queues or a defined
handoff rather than mutating another thread's objects unpredictably.

## Desktop event loops

For Qt, widget changes happen on the GUI thread. Move appropriate worker objects
to their thread and send queued results/signals to the UI. A `QThread` object
itself lives in its creating thread; putting slots on it is not automatically
worker-thread execution. Do not assume `quit()` interrupts a long-running blocking
function. Define cancellation, worker completion and cleanup together. See
[90](90-applications.md) for application state and shutdown checks.

For timing/retry semantics read [30](30-errors-and-resources.md); verify
interruption and ownership with [40](40-testing.md).
