from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    config: Path
    models: Path
    state: Path

    @classmethod
    def resolve(cls) -> "RuntimePaths":
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            root = Path(__file__).resolve().parents[2]
        return cls(root, root / "config", root / "models", root / "state")

    def ensure_directories(self) -> None:
        """Create writable runtime directories explicitly during application startup."""
        for directory in (self.config, self.models, self.state):
            directory.mkdir(parents=True, exist_ok=True)


PATHS = RuntimePaths.resolve()
