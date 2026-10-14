"""Profile-scoped interface font override, independent of the selected theme."""
from contextlib import nullcontext

from app.state.storage import JsonStore


FONT_CHOICES = (
    ("theme", "Theme default"),
    ("lora", "Lora"),
    ("merriweather", "Merriweather"),
    ("outfit", "Outfit"),
    ("nunito", "Nunito"),
    ("dm-sans", "DM Sans"),
    ("montserrat", "Montserrat"),
)
FONT_IDS = frozenset(identity for identity, _ in FONT_CHOICES)


class FontSettings:
    def __init__(self, store=None):
        self.store = store
        self.session = getattr(getattr(store, "path", None), "session", None)
        self.identity = "theme"
        self.load_error = False
        self.closed = False
        self._unregister = None
        with self._operation():
            try:
                missing = object()
                data = store.load(missing) if store is not None else missing
                if data is not missing:
                    if (not isinstance(data, dict) or set(data) != {"schema_version", "font_id"}
                            or type(data.get("schema_version")) is not int or data["schema_version"] != 1
                            or data.get("font_id") not in FONT_IDS):
                        raise ValueError("Invalid font preference")
                    self.identity = data["font_id"]
            except (OSError, ValueError, TypeError):
                self.load_error = True
        if self.session is not None:
            self._unregister = self.session.register(clear=self.close)

    @classmethod
    def for_preferences(cls, preferences):
        store = JsonStore(preferences.path.parent / "font_v1.json") if preferences is not None else None
        return cls(store)

    def _operation(self):
        return self.session.operation() if self.session is not None else nullcontext()

    def select(self, identity):
        with self._operation():
            if self.closed or self.load_error:
                raise ValueError("The font preference is unavailable")
            if identity not in FONT_IDS:
                raise ValueError("Unsupported interface font")
            if self.store is not None:
                self.store.save({"schema_version": 1, "font_id": identity})
            self.identity = identity

    def close(self):
        self.closed, self.store, self.identity = True, None, "theme"
        if self._unregister is not None:
            self._unregister()
            self._unregister = None
