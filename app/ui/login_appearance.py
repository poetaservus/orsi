"""Public login colors and bundled-theme identity; never cache profile assets."""
from copy import deepcopy
from uuid import UUID

from app.state.storage import JsonStore
from app.settings.font import FONT_IDS
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
        if (not isinstance(value, dict) or set(value) - {"version", "profile_id", "theme_id", "overrides", "font_id"}
                or type(value.get("version")) is not int or value["version"] != 1
                or value.get("theme_id") not in BUILTIN_IDS or value.get("font_id", "theme") not in FONT_IDS):
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

    def remember(self, theme, profile_id, *, font_id="theme"):
        try:
            self._load()  # Preserve an unreadable cache just like other preferences.
            value = {"version": 1, "profile_id": profile_id, "theme_id": theme.identity}
            if font_id not in FONT_IDS:
                return
            if font_id != "theme":
                value["font_id"] = font_id
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
            controller.select_font(value.get("font_id", "theme"), persist=False)
        except (OSError, ValueError, TypeError, KeyError):
            pass
