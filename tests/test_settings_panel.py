"""Settings navigation, placeholder boundaries and existing action routing."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_placeholder_controls_do_not_change_preferences_or_draft(app, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    preferences.save({"greeting_message": "Hello", "unrelated": "keep"})
    before = preferences.path.read_bytes()
    window = MainWindow(None, "TEST", preferences_store=preferences)
    try:
        window.show()
        window.input.setPlainText("Keep this draft")
        window.settings_button.click()
        app.processEvents()
        for selector in (window.theme_selector, window.gui_language_selector, window.response_language_selector):
            assert not selector.isEnabled()
            assert selector.currentText() == "Coming soon"
            assert "Placeholder" in selector.accessibleDescription()
        assert not window.tool_approval_toggle.isEnabled()
        assert "Existing tool approval rules" in window.tool_approval_toggle.toolTip()
        assert preferences.path.read_bytes() == before
        assert window.input.toPlainText() == "Keep this draft"
    finally:
        window.close()


def test_navigation_close_and_compact_layout_keep_controls_reachable(app):
    window = MainWindow(None, "TEST")
    try:
        window.resize(760, 600)
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        assert window._root.rect().contains(panel.geometry())
        assert [button.text() for button in panel.navigation] == ["General", "Skills", "Image Generation"]
        for index, button in enumerate(panel.navigation):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            assert panel.pages.currentIndex() == index
            assert sum(item.isChecked() for item in panel.navigation) == 1
        assert not window.image_settings_button.isEnabled()
        panel.navigation[0].click()
        app.processEvents()
        positions = [control.mapTo(panel, QPoint()).x() for control in (
            window.theme_selector, window.model_selector, window.local_model_selector,
            window.gui_language_selector, window.response_language_selector)]
        assert len(set(positions)) == 1
        panel.more_button.click()
        app.processEvents()
        scroll = panel.pages.currentWidget()
        scroll.ensureWidgetVisible(window.greeting_input)
        app.processEvents()
        position = window.greeting_input.mapTo(scroll.viewport(), QPoint())
        assert scroll.viewport().rect().contains(position)
        panel.navigation[0].setFocus()
        QTest.keyClick(panel.navigation[0], Qt.Key.Key_Escape)
        assert panel.isHidden()
        window.settings_button.click()
        QTest.mouseClick(panel.close_button, Qt.MouseButton.LeftButton)
        assert panel.isHidden()
    finally:
        window.close()


def test_mode_row_routes_existing_mode_switch_away_and_back(app):
    class Inference:
        available_modes = ("local", "cloud")
        mode = "local"
        cloud_provider_name = "Test provider"
        cloud_has_api_key = True
        context_length = 8192

        def __init__(self):
            self.switches = []

        def set_mode(self, mode):
            self.mode = mode
            self.switches.append(mode)

    inference = Inference()
    window = MainWindow(None, "TEST", inference=inference)
    try:
        window.show()
        window.settings_button.click()
        window.input.setPlainText("Keep draft")
        for mode in ("cloud", "local"):
            window.model_selector.setCurrentIndex(window.model_selector.findData(mode))
            assert inference.mode == mode
            assert window.model_selector.currentData() == mode
        assert inference.switches == ["cloud", "local"]
        assert window.input.toPlainText() == "Keep draft"
    finally:
        window.close()


def test_image_section_saves_through_existing_settings_handler(app, tmp_path):
    class Inference:
        available_modes = ("cloud",)
        mode = "cloud"
        cloud_provider_name = "Test provider"
        cloud_has_api_key = True
        context_length = 8192
        supports_image_generation = True

    store = ImageSettingsStore(ImageGenerationSettings(), tmp_path / "images.json")
    inference = Inference()
    inference.image_settings = store

    class Service:
        def select_image_settings(self, settings):
            store.select(settings)

    window = MainWindow(Service(), "TEST", inference=inference)
    try:
        window.show()
        window.settings_button.click()
        window.settings_panel.navigation[2].click()
        assert window.image_settings_button.isVisible() and window.image_settings_button.isEnabled()
        window.image_settings_button.click()
        dialog = window._image_settings_dialog
        dialog.choices["size"].setCurrentText("1024x1536")
        dialog._save()
        assert store.current.size == "1024x1536"
        assert ImageSettingsStore(ImageGenerationSettings(), store.store.path).current.size == "1024x1536"
        window._set_busy(True)
        assert not window.image_settings_button.isEnabled()
    finally:
        window.close()
