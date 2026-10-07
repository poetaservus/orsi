# 30 — Failure semantics, resource ownership and resilience

Read for files, transactions, external requests, retries or shutdown behavior.

## Make failures meaningful

Catch an exception where the code can recover, translate it into the boundary's
contract, or record the outcome. Catch the specific expected exception. At an
application boundary, a broad `Exception` handler may report and terminate safely;
it must not fabricate success or conceal programming errors. Do not broadly
catch `BaseException`: cancellation, interruption and exit need their semantics.

Chain translated failures with `raise DomainError(...) from exc` for internal
diagnosis; sanitize public messages independently. Do not log a failure at every
layer. Separate invalid input, missing resources, transient dependency failures,
permission failures and unknown external outcomes.

For batches, choose all-or-nothing versus partial success deliberately. Returning
per-item outcomes is useful when partial completion is allowed; silently dropping
failed items or always continuing is wrong when atomicity is required.

## Own cleanup

Use `with`, `async with`, `try/finally` and `ExitStack` for resources whose lifetimes
end with the operation. Put cleanup immediately around successful acquisition:
if acquisition itself fails, the context manager's exit method has not run.
Do not depend on garbage collection to release locks, files or connections.

Preserve the original failure if cleanup also fails; expose meaningful cleanup
failure rather than a blanket `except: pass`. Close generators, streaming clients
and subprocess pipes when their consumers stop early. A shutdown path must stop
accepting work, settle/cancel owned work, release resources and report what remains.

## Preserve stored data

Validate and serialize before replacing the accepted value. A same-directory
temporary file followed by `os.replace` avoids exposing a partially written file
where the filesystem supports atomic replacement. This is not a complete locking,
permissions, multi-file transaction or power-loss durability solution. Define
those policies separately. Keep recoverable state when a save fails.

The following Python 3.11+ example targets an application-owned file in a trusted directory,
under a single-writer contract. It does not create parent directories or safely
handle an attacker changing the directory. Permissions of the replaced file
require a separate policy.

```python
import json
import os
import tempfile
from pathlib import Path


def save_json(path: Path, value: object) -> None:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".save-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException as primary:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                primary.add_note("temporary file cleanup also failed")
        raise
```

The broad catch here only performs cleanup and re-raises the original exception,
including cancellation/interruption. It never converts failure into success.

## Retry only when repetition is safe

Classify failure and idempotency before adding retries. A lost response after a
payment, message send or file mutation may mean the operation already happened.
Use supported idempotency keys or reconcile the external outcome; do not blindly
replay. Do not retry invalid credentials, permanent validation failures or user
cancellation. Know the client's existing retry behavior to avoid layered retries.

Bound attempts and total elapsed time, apply backoff/jitter where relevant, honor
numeric server retry guidance, and use a monotonic deadline. Each attempt must
fit the remaining budget. Retry waiting must be interruptible. Never sleep while
holding a lock needed by cancellation or other work.

Connection/read timeouts and overall deadlines differ; configure both where
appropriate. Treat bounded concurrency, queue limits and backpressure as part of
resilience rather than launching more tasks whenever the service is slow.

For concurrent lifetimes read [50](50-concurrency.md); for trust and containment
read [70](70-security-and-data.md); verify failures with [40](40-testing.md).
