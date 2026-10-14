"""Profile-scoped interface language; reading a default never writes state."""
from contextlib import nullcontext

from app.conversation.response_language import RESPONSE_LANGUAGES
from app.state.storage import JsonStore


CODES = frozenset(language.code for language in RESPONSE_LANGUAGES)


class GuiLanguageSettings:
    def __init__(self, store=None):
        self.store = store
        self.session = getattr(getattr(store, "path", None), "session", None)
        self.code = "en"
        self.load_error = False
        self.closed = False
        self._unregister = None
        with self._operation():
            try:
                missing = object()
                data = store.load(missing) if store is not None else missing
                if data is not missing:
                    if (not isinstance(data, dict) or set(data) != {"schema_version", "language_code"}
                            or type(data.get("schema_version")) is not int or data["schema_version"] != 1
                            or data.get("language_code") not in CODES):
                        raise ValueError("Invalid GUI language preference")
                    self.code = data["language_code"]
            except (OSError, ValueError, TypeError):
                self.load_error = True
        if self.session is not None:
            self._unregister = self.session.register(clear=self.close)

    @classmethod
    def for_preferences(cls, preferences):
        store = JsonStore(preferences.path.parent / "gui_language_v1.json") if preferences is not None else None
        return cls(store)

    def _operation(self):
        return self.session.operation() if self.session is not None else nullcontext()

    def select(self, code):
        with self._operation():
            if self.closed or self.load_error:
                raise ValueError("The GUI language preference is unavailable")
            if code not in CODES:
                raise ValueError("Unsupported GUI language")
            if self.store is not None:
                self.store.save({"schema_version": 1, "language_code": code})
            self.code = code

    def close(self):
        self.closed, self.store, self.code = True, None, None
        if self._unregister is not None:
            self._unregister()
            self._unregister = None


class LoginLanguage:
    """Public language code only, matched to the selected public profile ID."""
    def __init__(self, path):
        self.store = JsonStore(path)

    def _load(self):
        if self.store.path.exists() and self.store.path.stat().st_size > 32768:
            raise ValueError("Invalid login language")
        missing = object()
        data = self.store.load(missing)
        if data is missing:
            return None
        from uuid import UUID
        if (not isinstance(data, dict) or set(data) != {"schema_version", "profiles"}
                or type(data.get("schema_version")) is not int or data["schema_version"] != 1
                or not isinstance(data.get("profiles"), dict) or len(data["profiles"]) > 256):
            raise ValueError("Invalid login language")
        for profile_id, code in data["profiles"].items():
            UUID(profile_id)
            if code not in CODES:
                raise ValueError("Invalid login language")
        return data

    def code_for(self, profile_id):
        try:
            data = self._load()
            return data["profiles"].get(profile_id, "en") if data else "en"
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return "en"

    def remember(self, code, profile_id):
        try:
            from uuid import UUID
            UUID(profile_id)
            data = self._load() or {"schema_version": 1, "profiles": {}}
            if code not in CODES:
                return
            profiles = data["profiles"]
            if len(profiles) == 256 and profile_id not in profiles:
                return
            profiles[profile_id] = code
            self.store.save(data)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass  # Locale persistence must never obstruct lock/unlock.
