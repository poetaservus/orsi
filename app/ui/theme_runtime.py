"""Resolve cosmetic theme values for existing Qt widgets without rebuilding UI."""
from __future__ import annotations

import base64
import re

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QImageReader, QLinearGradient, QPainter, QPixmap, QPalette
from PySide6.QtWidgets import QWidget

from app.ui.themes import ASSETS, ICON_FILES, ORIGINAL, ThemeError, ThemeRepository


# Legacy style literals remain the exact Original theme. Their semantic aliases
# let a partial custom palette replace only the requested colors.
_GROUPS = {
    "text": "#dce2ee #e4e5eb #d9dde5 #eeeeef #ededee #ededed #d9dce3 #d6d9e0 #e4e6eb #d5d6dc #ccd3de #cbd0da #e2e5eb #e7ebf1 #dddddf",
    "text_muted": "#b1b8c8 #939cac #b5bccb #a6aebe #bec4d0 #b9bfcc #c6c9d2 #929292 #c7cad2 #b9c2d0 #bcc7d5 #aeb8c8 #a7adb7 #acb2c0 #b8becc #b6b9c0 #9baec6",
    "text_disabled": "#777d8b #777777 #a2afc1 #545964 #777c83 #777c8b",
    "surface": "#243247 #292d36 #303640 #262626 #202328 #343f50 #202224 #151719 #252627 #20242d #292d3c #323747 #262a33",
    "surface_hover": "#2d4059 #3e4551 #454852 #414753 #42484d #41485b #292a30",
    "surface_pressed": "#1c2a3f #2c2e35 #1e1f24",
    "border": "#40536d #35465e #4b505d #3c3c3c #424242 #48525f #526171 #35393f #3b4046 #666666 #373c43 #505050 #686868 #3d3d3d",
    "focus": "#91bfe0 #6983a2 #91baff #65bdea #80adf8 #c4e3f6 #888888",
    "selection": "#3b5675 #355e7e #3b3b3b #2475ef",
    "selection_text": "#f4f6fb #ffffff",
    "scrollbar": "#657385 #3f4149",
    "error": "#f2a5a5 #e6b1b1 #f4b8b8 #efb4b4",
    "success": "#8fcaac",
}
STYLE_ROLES = {value: role for role, values in _GROUPS.items() for value in values.split()}
_COLORS = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)")


def color(value):
    """Manifest colors use conventional RGBA, while QColor hex uses ARGB."""
    if isinstance(value, QColor):
        return QColor(value)
    if isinstance(value, str) and value.startswith("#") and len(value) == 9:
        return QColor(int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), int(value[7:9], 16))
    return QColor(value)


def _key(value):
    value = color(value)
    rgb = value.name().lower()
    return rgb if value.alpha() == 255 else rgb + f"{value.alpha():02x}"


def _css(value):
    value = color(value)
    if value.alpha() == 255:
        return value.name()
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {value.alpha()})"


def controller_for(widget):
    while widget is not None:
        controller = getattr(widget, "theme_controller", None)
        if controller is not None:
            return controller
        widget = widget.parentWidget()
    return None


def theme_color(widget, original, role=None):
    controller = controller_for(widget)
    original = color(original)
    role = role or STYLE_ROLES.get(_key(original))
    return color(controller.current.palette.get(role, original)) if controller else original


def themed_stylesheet(widget, source):
    controller = controller_for(widget)
    if controller is None:
        return source
    theme = controller.current
    source = source.replace("font-family: Saira", f'font-family: "{theme.family}"') if theme.family != "Saira" else source
    if not theme.palette:
        return source

    def block(match):
        selectors, rules = match.group(1), match.group(2)
        # Code keeps its established syntax palette and monospace typography.
        if any(name in selectors for name in ("#codeBlock", "#codeEditor", "#codeHeader", "#codeLanguage")):
            return match.group(0)

        def declaration(item):
            prop, value = item.group(1), item.group(2)

            def replace(token):
                raw = token.group()
                if raw.startswith("rgba"):
                    rgba = [int(v) for v in re.findall(r"\d+", raw)]
                    original = QColor(*rgba)
                else:
                    original = color(raw)
                role = STYLE_ROLES.get(_key(original))
                if prop.startswith("background"):
                    role = ("selection" if "selected" in selectors or "selection" in prop else
                            "surface_pressed" if ":pressed" in selectors else
                            "surface_hover" if ":hover" in selectors else role or "surface")
                elif "border" in prop:
                    role = getattr(widget, "_theme_focus_border_role", "focus") if ":focus" in selectors else "border"
                elif prop == "color":
                    role = ("user_text" if "#userMessage" in selectors else
                            "composer_text" if "#messageInput" in selectors else
                            "text_disabled" if ":disabled" in selectors else role or "text")
                elif prop == "selection-background-color":
                    role = "selection"
                elif prop == "selection-color":
                    role = "selection_text"
                return _css(theme.palette[role]) if role in theme.palette else raw

            return prop + ":" + _COLORS.sub(replace, value) + ";"

        rules = re.sub(r"([\w-]+)\s*:([^;{}]+);", declaration, rules)
        return selectors + "{" + rules + "}"

    if "{" not in source:
        return re.sub(r"([^{}]+)\{([^{}]*)\}", block, "QWidget{" + source + "}")[8:-1]
    return re.sub(r"([^{}]+)\{([^{}]*)\}", block, source)


def apply_theme_style(widget, source):
    widget._theme_style_source = source
    widget.setStyleSheet(themed_stylesheet(widget, source))


def theme_icon(widget, action):
    controller = controller_for(widget)
    return controller.current.icon(action) if controller else QIcon(str(ASSETS / ICON_FILES[action]))


def set_theme_icon(widget, action):
    widget._theme_icon_action = action
    widget.setIcon(theme_icon(widget, action))


def apply_theme_tree(root):
    controller = controller_for(root)
    if controller:
        controller.apply_tree(root)


def _pixmap(data):
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    size = reader.size()
    if not size.isValid() or size.width() > 8192 or size.height() > 8192 or size.width() * size.height() > 24_000_000:
        raise ThemeError("Theme images must be valid and at most 24 megapixels / 8192 pixels per side.")
    if reader.supportsAnimation():
        raise ThemeError("Theme images must be static.")
    result = QPixmap.fromImage(reader.read())
    if result.isNull():
        raise ThemeError("Could not decode a theme image.")
    return result


class PreparedTheme:
    def __init__(self, package):
        self.package = package
        manifest = package["manifest"]
        self.identity, self.name = manifest["id"], manifest["name"]
        self.palette = manifest.get("palette", {})
        self.family = "Saira"
        self.warning = ""
        self.font_id = -1
        self.background = manifest.get("background", {})
        self.background_image = None
        self.background_cache = None
        self._icons = {}
        self.assets = {key: base64.b64decode(value) for key, value in package["assets"].items()}
        try:
            font = manifest.get("font", {})
            if "file" in font:
                self.font_id = QFontDatabase.addApplicationFontFromData(QByteArray(self.assets[font["file"]]))
                families = QFontDatabase.applicationFontFamilies(self.font_id)
                if not families:
                    raise ThemeError("Could not load the bundled font.")
                self.family = families[0]
                if re.search(r"[\x00-\x1f\"'{};\\]", self.family):
                    raise ThemeError("Invalid bundled font family.")
            elif "family" in font:
                requested = font["family"]
                installed = {name.casefold(): name for name in QFontDatabase.families()}
                if requested.casefold() in installed:
                    self.family = installed[requested.casefold()]
                else:
                    self.warning = "The requested font is unavailable. Saira is being used."
            if self.background.get("type") == "image":
                self.background_image = _pixmap(self.assets[self.background["file"]])
                crop = self.background.get("top_crop", 0)
                if crop:
                    if crop >= self.background_image.height():
                        raise ThemeError("Background crop exceeds the image height.")
                    self.background_image = self.background_image.copy(0, crop, self.background_image.width(), self.background_image.height() - crop)
            for action in ICON_FILES:
                self.icon(action)
        except Exception:
            self.close()
            raise

    def icon(self, action):
        if action in self._icons:
            return self._icons[action]
        name = self.package["manifest"].get("icons", {}).get(action)
        if name:
            data = self.assets[name]
            if name.lower().endswith(".svg"):
                from PySide6.QtSvg import QSvgRenderer
                renderer = QSvgRenderer(QByteArray(data))
                if not renderer.isValid():
                    raise ThemeError("Could not load a theme icon.")
                result = QIcon()
                for side in (16, 22, 24, 28, 32, 48, 64, 96, 128):
                    pixmap = QPixmap(side, side)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    result.addPixmap(pixmap)
            else:
                result = QIcon(_pixmap(data))
        else:
            result = QIcon(str(ASSETS / ICON_FILES[action]))
            if "icon" in self.palette:
                tinted = QIcon()
                for side in (16, 22, 24, 28, 32, 48, 64, 96, 128):
                    pixmap = result.pixmap(QSize(side, side))
                    painter = QPainter(pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                    painter.fillRect(pixmap.rect(), color(self.palette["icon"]))
                    painter.end()
                    tinted.addPixmap(pixmap)
                result = tinted
        self._icons[action] = result
        return result

    def close(self):
        if self.font_id >= 0:
            QFontDatabase.removeApplicationFont(self.font_id)
            self.font_id = -1
        self._icons.clear()
        self.assets.clear()
        self.background_image = None
        self.background_cache = None
        self.package = {}
        self.palette = {}
        self.background = {}


def paint_theme_background(widget, painter, target, source):
    controller = controller_for(widget)
    if controller is None or not controller.current.background:
        return False
    theme = controller.current
    background = theme.background
    bounds = QRectF(widget.rect())
    if theme.background_cache is not None and theme.background_cache.size() == widget.size():
        painter.drawPixmap(target, theme.background_cache, source)
        return True
    # Render once, then sample the same pixels for the surface and bottom glass.
    # This also avoids gradient raster rounding seams between separate regions.
    theme.background_cache = QPixmap(widget.size())
    theme.background_cache.fill(Qt.GlobalColor.transparent)
    canvas = QPainter(theme.background_cache)
    kind = background["type"]
    if kind == "solid":
        canvas.fillRect(bounds, color(background["color"]))
    elif kind == "gradient":
        direction = background.get("direction", "vertical")
        end = bounds.bottomLeft() if direction == "vertical" else bounds.topRight() if direction == "horizontal" else bounds.bottomRight()
        gradient = QLinearGradient(bounds.topLeft(), end)
        colors = background["colors"]
        for index, value in enumerate(colors):
            gradient.setColorAt(index / (len(colors) - 1), color(value))
        canvas.fillRect(bounds, gradient)
    else:
        image = theme.background_image
        canvas.fillRect(bounds, theme_color(widget, "#101214", "surface"))
        fit = background.get("fit", "cover")
        destination = QRectF(bounds)
        if fit != "stretch":
            ratios = (bounds.width() / image.width(), bounds.height() / image.height())
            ratio = max(ratios) if fit == "cover" else min(ratios)
            destination.setSize(QSizeF(image.size()) * ratio)
            destination.moveCenter(bounds.center())
        canvas.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        canvas.drawPixmap(destination, image, QRectF(image.rect()))
    canvas.end()
    painter.drawPixmap(target, theme.background_cache, source)
    return True


class ThemeController(QObject):
    changed = Signal()

    def __init__(self, window, preferences):
        super().__init__(window)
        self.window = window
        self.repository = ThemeRepository(preferences)
        self.current = PreparedTheme({"manifest": dict(ORIGINAL), "assets": {}})
        self.notice = self.repository.error
        self._applying = False
        selected = self.repository.selected()
        if isinstance(selected, str) and selected != "original":
            try:
                self.current = PreparedTheme(self.repository.packages[selected])
                self.notice = self.current.warning or self.notice
            except Exception:
                self.notice = "The saved theme is unavailable. Original is active; your selection is preserved."

    def apply_tree(self, root):
        if self._applying:
            return
        self._applying = True
        try:
            root_font = self.window.font()
            root_font.setFamily(self.current.family)
            self.window.setFont(root_font)
            for widget in (root, *root.findChildren(QWidget)):
                source = getattr(widget, "_theme_style_source", None)
                if source is not None:
                    rendered = themed_stylesheet(widget, source)
                    if widget.styleSheet() != rendered:
                        widget.setStyleSheet(rendered)
                action = getattr(widget, "_theme_icon_action", None)
                if action:
                    widget.setIcon(self.current.icon(action))
                if hasattr(widget, "refresh_theme_icons"):
                    widget.refresh_theme_icons()
                # Explicit composer/greeting fonts must follow the stylesheet family.
                if widget.objectName() in {"messageInput", "startupGreeting"}:
                    font = widget.font()
                    font.setFamily(self.current.family)
                    widget.setFont(font)
                if widget.objectName() == "messageInput":
                    palette = widget.palette()
                    palette.setColor(QPalette.ColorRole.PlaceholderText, theme_color(widget, "#a2a8ba", "placeholder"))
                    widget.setPalette(palette)
                widget.update()
        finally:
            self._applying = False

    def select(self, identity, *, persist=True):
        if identity not in self.repository.packages:
            raise ThemeError("This theme is unavailable.")
        prepared = PreparedTheme(self.repository.packages[identity])
        try:
            if persist:
                self.repository.save_selection(identity)
        except Exception:
            prepared.close()
            raise
        previous, self.current = self.current, prepared
        self.apply_tree(self.window)
        self.window.chat.refresh_theme()
        self.window.bottom_glass._transition_blur = None
        self.window.bottom_glass.update()
        previous.close()
        self.notice = prepared.warning
        controls = self.window.settings_panel.theme_controls
        controls.refresh()
        controls.status.setText(self.notice)
        self.changed.emit()

    def clear(self):
        previous = self.current
        self.current = PreparedTheme({"manifest": dict(ORIGINAL), "assets": {}})
        self.apply_tree(self.window)
        previous.close()
        self.repository.clear()

    def release(self):
        self.current.close()
        self.repository.clear()
