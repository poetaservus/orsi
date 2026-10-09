"""Bounded, content-free encrypted diagnostics while a profile is selected."""
from collections import deque
import logging

from app.state.storage import JsonStore


class ProfileLogHandler(logging.Handler):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self._events = deque(maxlen=200)
        self._store = JsonStore(session.path("diagnostics/events_v1.json"))
        session.register(stop=self.detach, clear=self._events.clear)

    def emit(self, record):
        # Do not format messages, arguments, exception strings or tracebacks.
        if not (record.name == "app" or record.name.startswith("app.")):
            return
        try:
            self._events.append({"event": "application_diagnostic", "level":
                "error" if record.levelno >= logging.ERROR else "warning" if record.levelno >= logging.WARNING else "info"})
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
