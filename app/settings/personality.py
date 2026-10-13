"""Profile-scoped personality choice; bundled definitions travel with the app."""
from contextlib import nullcontext
import logging

from app.conversation.personality import get_personality


log = logging.getLogger(__name__)


class PersonalitySettings:
    def __init__(self, store=None, *, session=None):
        self._store = store
        self._session = session or getattr(getattr(store, "path", None), "session", None)
        self._id = "original"
        self.load_error = False
        self._unregister = None
        with self._operation():
            try:
                missing = object()
                data = store.load(missing) if store is not None else missing
                if data is not missing:
                    if (not isinstance(data, dict) or set(data) != {"schema_version", "personality_id"}
                            or type(data["schema_version"]) is not int or data["schema_version"] != 1
                            or not isinstance(data["personality_id"], str)):
                        raise ValueError("Invalid personality preference.")
                    selected = get_personality(data["personality_id"])
                    selected.guidance  # Check the installed definition before activating it.
                    self._id = selected.id
            except (OSError, ValueError, TypeError):
                self.load_error = True
                log.warning("Saved personality could not be loaded; Original is active and the preference is preserved.")
        if self._session is not None:
            self._unregister = self._session.register(clear=self.close)

    def _operation(self):
        return self._session.operation() if self._session is not None else nullcontext()

    @property
    def current_id(self):
        with self._operation():
            if self._id is None:
                raise RuntimeError("The personality settings are closed.")
            return self._id

    @property
    def current(self):
        return get_personality(self.current_id)

    def select(self, personality_id):
        with self._operation():
            if self._id is None:
                raise RuntimeError("The personality settings are closed.")
            if self.load_error:
                raise ValueError("The unreadable personality preference has been preserved.")
            selected = get_personality(personality_id)
            selected.guidance
            if self._store is not None:
                self._store.save({"schema_version": 1, "personality_id": selected.id})
            self._id = selected.id

    def close(self):
        self._id = None
        self._store = None
        if self._unregister is not None:
            self._unregister()
            self._unregister = None
