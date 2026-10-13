"""Durable, profile-scoped reply-language selection with a non-writing Auto default."""
from contextlib import nullcontext
import logging

from app.conversation.response_language import get_response_language


log = logging.getLogger(__name__)


class ResponseLanguageSettings:
    def __init__(self, store=None, *, session=None):
        self._store = store
        self._session = session or getattr(getattr(store, "path", None), "session", None)
        self._code = "auto"
        self.load_error = False
        self._unregister = None
        with self._operation():
            try:
                missing = object()
                data = store.load(missing) if store is not None else missing
                if data is not missing:
                    if (not isinstance(data, dict) or set(data) != {"schema_version", "language_code"}
                            or type(data["schema_version"]) is not int or data["schema_version"] != 1
                            or not isinstance(data["language_code"], str)):
                        raise ValueError("Invalid response-language preference.")
                    self._code = get_response_language(data["language_code"]).code
            except (OSError, ValueError, TypeError):
                self.load_error = True
                log.warning("Saved response language could not be loaded; Auto is active and the preference is preserved.")
        if self._session is not None:
            self._unregister = self._session.register(clear=self.close)

    def _operation(self):
        return self._session.operation() if self._session is not None else nullcontext()

    @property
    def current_code(self):
        with self._operation():
            if self._code is None:
                raise RuntimeError("The response-language settings are closed.")
            return self._code

    def select(self, code):
        with self._operation():
            if self._code is None:
                raise RuntimeError("The response-language settings are closed.")
            if self.load_error:
                raise ValueError("The unreadable response-language preference has been preserved.")
            selected = get_response_language(code)
            if self._store is not None:
                self._store.save({"schema_version": 1, "language_code": selected.code})
            self._code = selected.code

    def close(self):
        self._code = None
        self._store = None
        if self._unregister is not None:
            self._unregister()
            self._unregister = None
