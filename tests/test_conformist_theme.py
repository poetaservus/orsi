"""The bundled Conformist theme remains flat, offline and redistributable."""
import base64
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.themes import (ICON_FILES, ThemeError, ThemeRepository, export_folder,
                           import_folder, validate_manifest)


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def test_conformist_is_bundled_with_flat_surfaces_and_one_accent():
    value = ThemeRepository().packages["conformist"]
    manifest = value["manifest"]
    assert manifest["name"] == "Conformist"
    assert manifest["background"] == {"type": "solid", "color": "#171717"}
    palette = manifest["palette"]
    assert palette["composer_top"] == palette["composer_middle"] == palette["composer_bottom"]
    assert palette["user_bubble_top"] == palette["user_bubble_bottom"]
    assert palette["settings_top"] == palette["settings_bottom"]
    assert palette["composer_highlight"] == "#00000000"
    chromatic = {value for value in palette.values()
                 if not value[1:3] == value[3:5] == value[5:7]}
    assert chromatic == {"#3b82f6"}
    assert set(manifest["icons"]) == set(ICON_FILES)
    assert manifest["font"]["family"] == "DM Sans"
    with pytest.raises(ThemeError):
        validate_manifest(manifest)


def test_conformist_exports_font_icons_and_full_licenses(tmp_path):
    value = ThemeRepository().packages["conformist"]
    output = export_folder(value, tmp_path / "my-conformist")
    imported = import_folder(output)
    assert imported["manifest"]["id"] == "my-conformist"
    assert imported["manifest"]["name"] == "My Conformist"
    assert imported["assets"] == value["assets"]
    for name in value["manifest"]["licenses"]:
        assert (output / name).read_bytes() == base64.b64decode(value["assets"][name])
    assert "SIL OPEN FONT LICENSE" in (output / "fonts/OFL-DM-Sans.txt").read_text()
    assert "ISC License" in (output / "icons/LICENSE-Lucide.txt").read_text()


def test_missing_conformist_assets_leave_the_original_themes_available(tmp_path, monkeypatch):
    import app.ui.themes as themes
    monkeypatch.setattr(themes, "ASSETS", tmp_path)
    repository = ThemeRepository()
    assert set(repository.packages) == {"original", "ocean"}
    assert "Conformist could not be loaded" in repository.error


@pytest.mark.parametrize("licenses", [["../outside.txt"], ["code.py"], "LICENSE.txt"])
def test_license_references_stay_within_the_theme(licenses):
    with pytest.raises(ThemeError):
        validate_manifest({"version": 1, "id": "custom", "name": "Custom", "licenses": licenses})


def test_dm_sans_reflows_and_switches_back_without_changing_code_or_draft(qt):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(1000, 800)
        window.show()
        window._intro_active = False
        window._position_overlays()
        band = window.chat.add_message("Agent", "## A familiar place to think\n\n"
            + "A paragraph with **emphasis** and `inline code` that wraps naturally. " * 8
            + "\n\n```python\nprint('unchanged')\n```")
        window.input.setPlainText("Keep this draft")
        qt.processEvents()
        label = band.message.label
        original_family = label.font().family()
        code = band.message._code_blocks[0]
        original_code_font = code.editor.font()
        window.theme_controller.select("conformist")
        qt.processEvents()
        active = window.theme_controller.current
        assert active.family.startswith("DM Sans") and not active.warning
        assert window.input.font().family() == active.family
        assert label.font().family() == active.family
        assert code.editor.font() == original_code_font
        for size in ((760, 600), (1280, 900)):
            window.resize(*size)
            qt.processEvents()
            assert label.height() >= label.heightForWidth(label.width())
            assert window.input.toPlainText() == "Keep this draft"
        window.theme_controller.select("original")
        qt.processEvents()
        assert active.font_id == -1 and label.font().family() == original_family
    finally:
        window.close()


def test_flat_background_stays_neutral_around_compact_composer(qt):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(1280, 900)
        window.show()
        window._intro_active = False
        window._position_overlays()
        window.chat.add_message("User", "Please keep the surfaces flat and the typography clear.")
        window.chat.add_message("Agent", "## A familiar place to think\n\n"
            + "A neutral paragraph that wraps across several lines. " * 5
            + "\n\n- First item\n- Second item\n- Third item")
        qt.processEvents()
        window.theme_controller.select("conformist")
        window.resize(760, 600)
        qt.processEvents()
        QTest.qWait(30)
        window.chat.verticalScrollBar().setValue(0)
        image = window.grab().toImage()
        # Neutral prose and flat surfaces stay neutral around the composer.
        for x in range(20, window.width() - 20, 20):
            pixel = image.pixelColor(x, window.height() - 10)
            assert max(pixel.red(), pixel.green(), pixel.blue()) - min(pixel.red(), pixel.green(), pixel.blue()) <= 2
    finally:
        window.close()


def test_selected_background_keeps_live_transcript_blur(qt):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(760, 600)
        window.show()
        window._intro_active = False
        window._position_overlays()
        band = window.chat.add_message("Agent", "A line of live transcript text.\n\n" * 40)
        window.theme_controller.select("conformist")
        QTest.qWait(30)
        bar = window.chat.verticalScrollBar()
        window.chat._follow_tail = False
        bar.setValue(bar.maximum() // 2)
        QTest.qWait(20)
        before = window.bottom_glass._blurred_backdrop().toImage()
        band.message.label.document.setPlainText("")
        QTest.qWait(10)
        after = window.bottom_glass._blurred_backdrop().toImage()
        assert before != after
    finally:
        window.close()
