from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ProviderContentFilter(logging.Filter):
    """Keep raw SDK/HTTP debug bodies, headers and URLs out of ORSI's log file."""
    def filter(self, record):
        return not any(record.name == name or record.name.startswith(name + ".")
            for name in ("openai", "httpx", "httpcore"))


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
    handler.addFilter(ProviderContentFilter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
