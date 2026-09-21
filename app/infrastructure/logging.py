from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_path: Path) -> None:
    """Configure bounded UTF-8 application logs without recording conversation content."""
    if not isinstance(log_path, Path):
        raise TypeError("The application log path must be a pathlib.Path.")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
