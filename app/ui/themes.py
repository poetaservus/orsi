"""Portable, data-only cosmetic themes. No Qt, executable code or stylesheets."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re

from defusedxml.ElementTree import fromstring

from app.state.storage import JsonStore


ASSETS = Path(__file__).with_name("assets")
BUILTIN_IDS = {"original", "ocean", "conformist"}
PALETTE_DEFAULTS = {
    "text": "#dce2ee", "text_muted": "#b1b8c8", "text_disabled": "#777d8b",
    "surface": "#243247", "surface_hover": "#2d4059", "surface_pressed": "#1c2a3f",
    "border": "#40536d", "focus": "#91bfe0", "accent": "#2475ef",
    "selection": "#3b5675", "selection_text": "#f4f6fb", "icon": "#cbd0da",
    "settings_top": "#1d2637", "settings_bottom": "#090c15",
    "composer_top": "#2c3036", "composer_middle": "#2a2e34", "composer_bottom": "#282c32",
    "composer_border": "#373c43", "composer_highlight": "#ffffff08",
    "composer_text": "#dedee0", "placeholder": "#a2a8ba",
    "user_bubble_top": "#2e3a55d2", "user_bubble_bottom": "#262a3cd4",
    "user_bubble_border": "#aabee837", "user_text": "#dce2ee",
    "inline_reference": "#3b3c40", "scrollbar": "#657385",
    "error": "#f2a5a5", "success": "#8fcaac",
}
ICON_FILES = {
    "new_message": "top_new_session.svg", "settings": "top_settings.svg",
    "send": "send.svg", "stop": "stop.svg", "microphone": "microphone.svg",
    "attach": "plus.svg", "folder": "folder.svg", "copy": "copy.svg", "check": "check.svg",
}
ORIGINAL = {"version": 1, "id": "original", "name": "Original", "palette": {}}
OCEAN = {
    "version": 1, "id": "ocean", "name": "Ocean", "font": {"family": "Segoe UI"},
    "background": {"type": "gradient", "colors": ["#071b26", "#103444"], "direction": "diagonal"},
    "palette": {
        **PALETTE_DEFAULTS, "text": "#e0f5f4", "text_muted": "#a0c9cb", "text_disabled": "#63858b",
        "surface": "#163c4a", "surface_hover": "#225464", "surface_pressed": "#12313d",
        "border": "#3c6a78", "focus": "#8ae0dd", "accent": "#44bbb7", "selection": "#29636b",
        "selection_text": "#f0ffff", "icon": "#b5e9e5", "settings_top": "#17424f",
        "settings_bottom": "#0a202d", "composer_top": "#1c4b57", "composer_middle": "#194550",
        "composer_bottom": "#153e49", "composer_border": "#477980", "composer_text": "#e0f5f4",
        "placeholder": "#a0c9cb", "user_bubble_top": "#286573ee", "user_bubble_bottom": "#205361ee",
        "user_bubble_border": "#6bafb980", "user_text": "#edffff", "inline_reference": "#22505b",
        "scrollbar": "#497e88",
    },
}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
MAX_ASSET = 8 * 1024 * 1024
MAX_PACKAGE = 24 * 1024 * 1024
MAX_CATALOG = 64 * 1024 * 1024


class ThemeError(ValueError):
    pass


def _fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ThemeError(f"Invalid {label} fields.")


def _color(value):
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ThemeError("Colors must use #RRGGBB or #RRGGBBAA.")


def _asset_name(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/"))
            or len(value) > 200 or any(ord(c) < 32 for c in value)):
        raise ThemeError("Assets must use relative paths inside the theme folder.")
    return value


def referenced_assets(manifest):
    assets = set(manifest.get("icons", {}).values())
    assets.update(manifest.get("licenses", []))
    if manifest.get("font", {}).get("file"):
        assets.add(manifest["font"]["file"])
    if manifest.get("background", {}).get("type") == "image":
        assets.add(manifest["background"]["file"])
    return assets


def validate_manifest(manifest, *, builtin=False):
    _fields(manifest, {"version", "id", "name", "palette", "font", "background", "icons", "licenses"}, "theme")
    if type(manifest.get("version")) is not int or manifest["version"] != 1:
        raise ThemeError("This theme format version is not supported.")
    if not isinstance(manifest.get("id"), str) or not _ID.fullmatch(manifest["id"]):
        raise ThemeError("Theme ID must start with a lowercase letter and contain letters, digits, _ or -.")
    if not builtin and manifest["id"] in BUILTIN_IDS:
        raise ThemeError("Choose a new ID; built-in themes cannot be replaced.")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ThemeError("Give the theme a name of 1–80 characters.")
    palette = manifest.get("palette", {})
    _fields(palette, set(PALETTE_DEFAULTS), "palette")
    for value in palette.values():
        _color(value)
    font = manifest.get("font", {})
    _fields(font, {"family", "file"}, "font")
    if "family" in font and (not isinstance(font["family"], str) or not font["family"]
            or len(font["family"]) > 100 or re.search(r"[\x00-\x1f\"'{};\\]", font["family"])):
        raise ThemeError("Invalid font family.")
    if "file" in font and PurePosixPath(_asset_name(font["file"])).suffix.lower() not in {".ttf", ".otf"}:
        raise ThemeError("Bundled fonts must be TTF or OTF files.")
    icons = manifest.get("icons", {})
    _fields(icons, set(ICON_FILES), "icon")
    for value in icons.values():
        if PurePosixPath(_asset_name(value)).suffix.lower() not in {".svg", ".png"}:
            raise ThemeError("Icons must be static SVG or PNG files.")
    licenses = manifest.get("licenses", [])
    if not isinstance(licenses, list) or len(licenses) > 8:
        raise ThemeError("Include at most eight license text files.")
    for value in licenses:
        if PurePosixPath(_asset_name(value)).suffix.lower() != ".txt":
            raise ThemeError("Licenses must be relative text files.")
    background = manifest.get("background", {})
    _fields(background, {"type", "color", "colors", "direction", "file", "fit", "top_crop"}, "background")
    if background:
        kind = background.get("type")
        allowed = {
            "solid": {"type", "color"}, "gradient": {"type", "colors", "direction"},
            "image": {"type", "file", "fit", "top_crop"},
        }
        if kind not in allowed or set(background) - allowed[kind]:
            raise ThemeError("Background must be a solid color, gradient or static image.")
        if kind == "solid":
            _color(background.get("color"))
        elif kind == "gradient":
            colors = background.get("colors")
            if not isinstance(colors, list) or not 2 <= len(colors) <= 8:
                raise ThemeError("Gradients need 2–8 colors.")
            for value in colors:
                _color(value)
            if background.get("direction", "vertical") not in {"vertical", "horizontal", "diagonal"}:
                raise ThemeError("Invalid gradient direction.")
        else:
            if PurePosixPath(_asset_name(background.get("file"))).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                raise ThemeError("Background images must be PNG or JPEG files.")
            if background.get("fit", "cover") not in {"cover", "stretch", "contain"}:
                raise ThemeError("Invalid background fit.")
            crop = background.get("top_crop", 0)
            if type(crop) is not int or not 0 <= crop <= 4096:
                raise ThemeError("Invalid background crop.")
    return deepcopy(manifest)


def _validate_svg(data):
    try:
        root = fromstring(data)
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag.startswith("animate") or tag in {"script", "foreignObject", "image", "set", "discard"}:
                raise ThemeError("SVG icons must contain only static, self-contained artwork.")
            values = list(element.attrib.values())
            if tag == "style":
                stylesheet = element.text or ""
                if re.search(r"@import|animation\s*:", stylesheet, re.IGNORECASE):
                    raise ThemeError("SVG icons must contain only static, self-contained artwork.")
                values.append(stylesheet)
            for key, value in element.attrib.items():
                if key.lower().startswith("on"):
                    raise ThemeError("SVG icons must contain only static artwork.")
                if key.rsplit("}", 1)[-1] == "href" and not value.startswith("#"):
                    raise ThemeError("SVG icons cannot reference outside assets.")
            for value in values:
                urls = re.findall(r"url\((.*?)\)", value, re.IGNORECASE)
                if any(not re.fullmatch(r"#[\w-]+", url.strip().strip("\"'")) for url in urls):
                    raise ThemeError("SVG icons cannot reference outside assets.")
        if root.tag.rsplit("}", 1)[-1] != "svg":
            raise ThemeError("Invalid SVG icon.")
    except ThemeError:
        raise
    except Exception:
        raise ThemeError("Invalid SVG icon.") from None


def validate_package(package, *, builtin=False):
    _fields(package, {"manifest", "assets"}, "theme package")
    manifest = validate_manifest(package.get("manifest"), builtin=builtin)
    assets = package.get("assets", {})
    _fields(assets, referenced_assets(manifest), "asset")
    if set(assets) != referenced_assets(manifest):
        raise ThemeError("A referenced theme asset is missing.")
    total = 0
    for name, encoded in assets.items():
        if not isinstance(encoded, str) or len(encoded) > MAX_ASSET * 4 // 3 + 4:
            raise ThemeError("A theme asset is too large.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ThemeError("Invalid theme asset data.") from None
        if not data or len(data) > MAX_ASSET:
            raise ThemeError("Theme assets must be nonempty and at most 8 MiB each.")
        total += len(data)
        if name.lower().endswith(".svg"):
            _validate_svg(data)
    if total > MAX_PACKAGE:
        raise ThemeError("A theme can contain at most 24 MiB of assets.")
    return {"manifest": manifest, "assets": dict(assets)}


def _read_file(path, limit):
    # Only explicitly selected local, ordinary files beneath the theme folder.
    for part in (path, *path.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ThemeError("Theme files cannot use filesystem links.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ThemeError("A theme file is too large.")
    return data


def import_folder(path, *, builtin=False):
    path = Path(path).absolute()
    if path.is_dir():
        path /= "theme.json"
    try:
        manifest = validate_manifest(json.loads(_read_file(path, 64 * 1024).decode("utf-8-sig")), builtin=builtin)
        assets = {name: base64.b64encode(_read_file(path.parent / name, MAX_ASSET)).decode("ascii")
                  for name in referenced_assets(manifest)}
        return validate_package({"manifest": manifest, "assets": assets}, builtin=builtin)
    except ThemeError:
        raise
    except (OSError, ValueError, TypeError):
        raise ThemeError("Could not read theme.json and its referenced assets.") from None


class ThemeRepository:
    def __init__(self, preferences=None):
        self.preferences = preferences
        self.store = JsonStore(preferences.path.parent / "themes" / "catalog_v1.json") if preferences else None
        self.packages = {m["id"]: {"manifest": deepcopy(m), "assets": {}} for m in (ORIGINAL, OCEAN)}
        self.error = ""
        try:
            self.packages["conformist"] = import_folder(ASSETS / "themes" / "conformist", builtin=True)
        except ThemeError:
            self.error = "Conformist could not be loaded. Original and Ocean remain available."
        self._catalog = None
        try:
            if self.store is not None and self.store.path.exists() and self.store.path.stat().st_size > MAX_CATALOG:
                raise ThemeError("Saved themes are too large.")
            catalog = self.store.load({}) if self.store else {}
            if not isinstance(catalog, dict) or len(catalog) > 100:
                raise ThemeError("Invalid saved theme catalog.")
            valid = {}
            for key, package in catalog.items():
                try:
                    value = validate_package(package)
                    if key != value["manifest"]["id"]:
                        raise ThemeError("Invalid saved theme ID.")
                    valid[key] = value
                except (ThemeError, TypeError):
                    self.error = "Some saved themes could not be loaded; their files are preserved."
            self.packages.update(valid)
            self._catalog = catalog
        except Exception:
            self.error = "Saved themes could not be loaded; their files are preserved."

    def add(self, package):
        package = validate_package(package)
        if self._catalog is None:
            raise ThemeError("Saved themes are unreadable. Their files have been preserved.")
        updated = {**self._catalog, package["manifest"]["id"]: package}
        if len(updated) > 100 or len(json.dumps(updated).encode("utf-8")) > MAX_CATALOG:
            raise ThemeError("The theme library is full.")
        if self.store:
            self.store.save(updated)
        self._catalog = updated
        self.packages[package["manifest"]["id"]] = package

    def selected(self):
        try:
            value = self.preferences.load({}) if self.preferences else {}
            return value.get("theme_id", "original") if isinstance(value, dict) else "original"
        except Exception:
            return "original"

    def save_selection(self, identity):
        if self.preferences:
            value = self.preferences.load({})
            if not isinstance(value, dict):
                raise ThemeError("UI preferences are unreadable; the saved file was preserved.")
            self.preferences.save({**value, "theme_id": identity})

    def clear(self):
        self.packages.clear()
        self._catalog = None
        self.preferences = self.store = None


def export_folder(package, destination):
    """Export to a new folder so an export cannot overwrite existing user files."""
    package = deepcopy(package)
    manifest = package["manifest"]
    manifest["id"] = "my-" + manifest["id"] if manifest["id"] in BUILTIN_IDS else manifest["id"]
    if manifest["name"] in {"Original", "Ocean", "Conformist"}:
        manifest["name"] = "My " + manifest["name"]
    if not manifest.get("background"):
        manifest["background"] = {"type": "image", "file": "background.png", "fit": "stretch", "top_crop": 68}
        package["assets"]["background.png"] = base64.b64encode((ASSETS / "o.r.s.i_gui_bck.png").read_bytes()).decode("ascii")
    validate_package(package)
    destination = Path(destination)
    destination.mkdir(parents=False, exist_ok=False)
    for name, value in package["assets"].items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(value))
    (destination / "theme.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "PALETTE.txt").write_text(
        "Add any of these values to theme.json's palette. Omitted values inherit Original.\n"
        + json.dumps(PALETTE_DEFAULTS, indent=2) + "\n", encoding="utf-8")
    return destination
