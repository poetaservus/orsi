"""Bounded, content-free encrypted diagnostics while a profile is selected."""
from collections import deque
import logging

from app.state.storage import JsonStore
from app.inference.word_plan_diagnostics import safe_word_event
from app.mcp.office_read_diagnostics import safe_read_event
from app.mcp.office_write_diagnostics import safe_write_event
from app.inference.openai_diagnostics import safe_stream_event
from app.inference.openai_metrics import safe_metrics_event


class ProfileLogHandler(logging.Handler):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self._events = deque(maxlen=200)
        self._store = JsonStore(session.storage_path("diagnostics/events_v1.json"))
        session.register(stop=self.detach, clear=self._events.clear)

    def emit(self, record):
        # Do not format messages, arguments, exception strings or tracebacks.
        if not (record.name == "app" or record.name.startswith("app.")):
            return
        try:
            event = None
            if record.name == "app.inference.word_plan_diagnostics":
                event = safe_word_event(getattr(record, "orsi_word_diagnostic", None))
            elif record.name == "app.mcp.office_read_diagnostics":
                event = safe_read_event(getattr(record, "orsi_read_diagnostic", None))
            elif record.name == "app.mcp.office_write_diagnostics":
                event = safe_write_event(getattr(record, "orsi_write_diagnostic", None))
            elif record.name.startswith("app.inference."):
                event = (safe_stream_event(getattr(record, "orsi_openai_stream_diagnostic", None)) or
                         safe_metrics_event(getattr(record, "orsi_openai_metrics_diagnostic", None)))
            event = event or {"event": "application_diagnostic"}
            self._events.append({**event, "level": "error" if record.levelno >= logging.ERROR else
                "warning" if record.levelno >= logging.WARNING else "info"})
            self._store.save(list(self._events))
        except Exception:
            pass

    def detach(self):
        root = logging.getLogger()
        root.removeHandler(self)
        if not root.handlers:
            root.addHandler(logging.NullHandler())
        self.close()


def configure_profile_logging(session):
    session.require_active()
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if isinstance(handler, ProfileLogHandler) and handler.session is session:
            return
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    root.addHandler(ProfileLogHandler(session))
