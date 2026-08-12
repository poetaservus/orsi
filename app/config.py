from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"Configuration must be an object: {path}")
        return value
    except FileNotFoundError:
        if default is not None:
            return default
        raise
