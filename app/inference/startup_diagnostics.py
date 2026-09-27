"""Drain native stderr continuously; retain only allowlisted startup categories."""
from __future__ import annotations

import os
from threading import Lock, Thread


_PATTERNS = {
    "memory allocation failure": (
        b"out of memory", b"failed to allocate", b"cannot allocate memory",
        b"not enough memory", b"insufficient memory", b"paging file is too small",
        b"cudamalloc failed", b"error_outofmemory",
    ),
    "GPU initialization failure": (
        b"no cuda-capable device", b"cuda driver version", b"failed to initialize cuda",
    ),
    "model loading failure": (b"failed to load model", b"error loading model", b"invalid model"),
    "local port binding failure": (b"address already in use", b"failed to bind"),
}


class StartupDiagnostics:
    """At most 4 KiB per read plus a 128-byte overlap, never written to disk.

    Once healthy, stop classification but keep draining so stderr cannot block
    inference. Only fixed category labels cross this object's public boundary.
    """

    def __init__(self, read_fd):
        self._lock = Lock()
        self._capturing = True
        self._categories = set()
        self._tail = b""
        self._stream = os.fdopen(read_fd, "rb", buffering=0)
        self._thread = Thread(target=self._drain, name="local-server-stderr", daemon=True)
        try:
            self._thread.start()
        except BaseException:
            self._stream.close()
            raise

    def _drain(self):
        try:
            with self._stream:
                while chunk := self._stream.read(4096):
                    with self._lock:
                        if not self._capturing:
                            continue
                        sample = self._tail + chunk.lower()
                        for category, patterns in _PATTERNS.items():
                            if any(pattern in sample for pattern in patterns):
                                self._categories.add(category)
                        self._tail = sample[-128:]
        except OSError:
            pass
        finally:
            with self._lock:
                self._tail = b""

    def finish(self, *, wait=False):
        if wait:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._capturing = False
            self._tail = b""

    def failure_category(self, exit_code=None):
        # Give a terminated child's final stderr bytes time to reach the reader.
        if exit_code is not None:
            self._thread.join(timeout=0.5)
        with self._lock:
            for category in _PATTERNS:
                if category in self._categories:
                    return category
        if exit_code in {0xC0000017, 0xC000012D, 0xC000009A}:
            return "memory allocation failure"
        if exit_code == 0xC0000135:
            return "missing runtime library"
        if exit_code == 0xC0000005:
            return "native access violation"
        return "unclassified native startup failure"
