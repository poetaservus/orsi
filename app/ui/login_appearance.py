"""Public login colors and bundled-theme identity; never cache profile assets."""
from copy import deepcopy
from uuid import UUID

from app.state.storage import JsonStore
from app.ui.themes import BUILTIN_IDS, validate_manifest, validate_package


class LoginAppearance:
    def __init__(self, path):
        self.store = JsonStore(path)

    def _load(self):
        if self.store.path.exists() and self.store.path.stat().st_size > 64 * 1024:
            raise ValueError("Invalid login appearance.")
        value = self.store.load()
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) - {"version", "profile_id", "theme_id", "overrides"}
                or type(value.get("version")) is not int or value["version"] != 1
                or value.get("theme_id") not in BUILTIN_IDS):
            raise ValueError("Invalid login appearance.")
        if not isinstance(value.get("profile_id"), str):
            raise ValueError("Invalid login appearance.")
        UUID(value["profile_id"])
        overrides = value.get("overrides", {})
        if not isinstance(overrides, dict) or set(overrides) - {"palette", "font", "background"}:
            raise ValueError("Invalid login appearance.")
        validate_manifest({"version": 1, "id": "login-appearance", "name": "Login appearance", **overrides})
        if set(overrides.get("font", {})) - {"family"} or overrides.get("background", {}).get("type") == "image":
            raise ValueError("Invalid login appearance.")
        return value

    def remember(self, theme, profile_id):
        try:
            self._load()  # Preserve an unreadable cache just like other preferences.
            value = {"version": 1, "profile_id": profile_id, "theme_id": theme.identity}
            if theme.identity not in BUILTIN_IDS:
                value["theme_id"] = "conformist" if theme.family == "DM Sans" else "original"
                overrides = {"palette": deepcopy(theme.palette), "font": {"family": theme.family}}
                background = theme.package["manifest"].get("background", {})
                if background.get("type") in {"solid", "gradient"}:
                    overrides["background"] = deepcopy(background)
                value["overrides"] = overrides
            self.store.save(value)
        except (OSError, ValueError, TypeError, KeyError):
            pass  # Appearance persistence must never prevent locking or unlocking.

    def apply(self, controller, profile_id):
        try:
            value = self._load()
            if value is None or value["profile_id"] != profile_id:
                return
            identity = value["theme_id"]
            if value.get("overrides"):
                package = deepcopy(controller.repository.packages[identity])
                overrides = deepcopy(value["overrides"])
                family = overrides.get("font", {}).get("family")
                if family == package["manifest"].get("font", {}).get("family"):
                    overrides.pop("font", None)  # Keep a bundled font loaded from public assets.
                package["manifest"].update(overrides, id="login-appearance", name="Login appearance")
                controller.repository.packages["login-appearance"] = validate_package(package)
                identity = "login-appearance"
            controller.select(identity, persist=False)
        except (OSError, ValueError, TypeError, KeyError):
            pass
