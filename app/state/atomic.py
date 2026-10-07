"""Bounded retries for replacing already-flushed state, never for executing actions."""
from __future__ import annotations

import os
from pathlib import Path
from time import sleep


def _retry_windows_denial(operation, *, cancellation=None) -> None:
    # Windows scanners/readers can briefly deny replacement after handles close.
    # Retry the same immutable state bytes for at most 900ms. A permanent denial
    # still propagates: callers must retain their fail-closed persistence boundary.
    delays = (0.02, 0.04, 0.08, 0.16, 0.20, 0.20, 0.20)
    for attempt in range(len(delays) + 1):
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        try:
            operation()
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == len(delays):
                raise
            if cancellation is None:
                sleep(delays[attempt])
            else:
                cancellation.wait(delays[attempt])


def replace_state_file(temporary: Path, destination: Path) -> None:
    _retry_windows_denial(lambda: os.replace(temporary, destination))


def rename_state_directory(temporary: Path, destination: Path, *, cancellation=None) -> None:
    """Publish a flushed snapshot with the same bounded Windows-lock tolerance.

    Rename semantics remain unchanged; no overwrite or sharing flags are changed
    and the copy is not repeated. The caller retains filesystem pins.
    """
    _retry_windows_denial(lambda: temporary.rename(destination), cancellation=cancellation)
