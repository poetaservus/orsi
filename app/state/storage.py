from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStore:
    def __init__(self, path: Path): self.path = path; self._lock = RLock()
    def load(self, default: Any = None):
        with self._lock:
            try: return json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError: return default
    def save(self, value: Any):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
