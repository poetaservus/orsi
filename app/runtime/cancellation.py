from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock
from time import monotonic


class TaskCancelled(RuntimeError):
    """Raised at cooperative cancellation boundaries."""


@dataclass
class _CancellationState:
    event: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)
    reason: str = "The task was cancelled."


class CancellationToken:
    def __init__(self, state: _CancellationState | None = None):
        self._state = state or _CancellationState()

    @property
    def is_cancelled(self) -> bool:
        return self._state.event.is_set()

    @property
    def reason(self) -> str:
        with self._state.lock:
            return self._state.reason

    def wait(self, timeout: float | None = None) -> bool:
        return self._state.event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelled(self.reason)


class CancellationSource:
    def __init__(self):
        self._state = _CancellationState()
        self.token = CancellationToken(self._state)

    def cancel(self, reason: str = "The task was cancelled.") -> None:
        with self._state.lock:
            if self._state.event.is_set():
                return
            self._state.reason = str(reason) or "The task was cancelled."
            self._state.event.set()


class LinkedCancellationToken(CancellationToken):
    """Read-only token cancelled when any of its source tokens is cancelled."""

    def __init__(self, *tokens: CancellationToken):
        if not tokens or not all(isinstance(token, CancellationToken) for token in tokens):
            raise TypeError("Linked cancellation requires one or more cancellation tokens.")
        self._tokens = tuple(tokens)

    @property
    def is_cancelled(self) -> bool:
        return any(token.is_cancelled for token in self._tokens)

    @property
    def reason(self) -> str:
        for token in self._tokens:
            if token.is_cancelled:
                return token.reason
        return "The task was cancelled."

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is not None and timeout < 0:
            raise ValueError("Cancellation wait timeouts cannot be negative.")
        deadline = None if timeout is None else monotonic() + timeout
        while not self.is_cancelled:
            if deadline is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                interval = min(0.01, remaining)
            else:
                interval = 0.01
            self._tokens[0].wait(interval)
        return True
