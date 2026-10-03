"""Bounded retries for replacing already-flushed state, never for executing actions."""
from __future__ import annotations

import os
from pathlib import Path
from time import sleep


def replace_state_file(temporary: Path, destination: Path) -> None:
    # Windows scanners/readers can briefly deny replacement after handles close.
    # Retry the same immutable state bytes for at most 900ms. A permanent denial
    # still propagates: callers must retain their fail-closed persistence boundary.
    delays = (0.02, 0.04, 0.08, 0.16, 0.20, 0.20, 0.20)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(temporary, destination)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == len(delays):
                raise
            sleep(delays[attempt])
