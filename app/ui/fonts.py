"""Application-local Google Fonts; no installation or network access required."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


FONT_DIRECTORY = Path(__file__).with_name("assets") / "fonts"
FONT_FILES = {
    "lora": ("Lora.ttf", "Lora-Italic.ttf"),
    "merriweather": ("Merriweather.ttf", "Merriweather-Italic.ttf"),
    "outfit": ("Outfit.ttf",),
    "nunito": ("Nunito.ttf", "Nunito-Italic.ttf"),
    "dm-sans": ("DMSans.ttf", "DMSans-Italic.ttf"),
    "montserrat": ("Montserrat.ttf", "Montserrat-Italic.ttf"),
}


def load_font(identity):
    if identity == "theme":
        return ""
    if identity not in FONT_FILES:
        raise ValueError("Unsupported interface font")
    app = QApplication.instance()
    # Public, immutable bundled fonts live for the application lifetime, even
    # when a theme unloads its own independent copy of DM Sans.
    if not hasattr(app, "_orsi_bundled_fonts"):
        app._orsi_bundled_fonts = {}
    if identity not in app._orsi_bundled_fonts:
        font_ids = []
        family = ""
        try:
            for filename in FONT_FILES[identity]:
                font_id = QFontDatabase.addApplicationFont(str(FONT_DIRECTORY / filename))
                font_ids.append(font_id)
                families = QFontDatabase.applicationFontFamilies(font_id)
                if not families:
                    raise ValueError("The bundled font is unavailable. The current font is unchanged.")
                family = family or families[0]
        except Exception:
            for font_id in font_ids:
                if font_id >= 0:
                    QFontDatabase.removeApplicationFont(font_id)
            raise
        app._orsi_bundled_fonts[identity] = family
    return app._orsi_bundled_fonts[identity]
