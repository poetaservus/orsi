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
            root = Path(__file__).resolve().parent.parent
        paths = cls(root, root / "config", root / "models", root / "state")
        for directory in (paths.config, paths.models, paths.state):
            directory.mkdir(parents=True, exist_ok=True)
        return paths


PATHS = RuntimePaths.resolve()
