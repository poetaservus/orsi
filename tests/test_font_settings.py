"""Essential portable-font, theme-override and profile-lifecycle checks."""
from copy import deepcopy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontInfo, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app.settings.font import FONT_CHOICES, FontSettings
from app.state.storage import JsonStore
from app.ui.fonts import FONT_DIRECTORY, FONT_FILES
from app.ui.localization import language_runtime
from app.ui.main_window import MainWindow
from app.ui.themes import export_folder, import_folder


@pytest.fixture
def qt():
    app = QApplication.instance() or QApplication([])
    runtime = language_runtime()
    runtime.apply(runtime.prepare("en"))
    yield app
    runtime.apply(runtime.prepare("en"))
    app.processEvents()


@pytest.fixture
def window(qt, tmp_path):
    preferences = JsonStore(tmp_path / "state/ui_preferences_v1.json")
    preferences.save({"greeting_message": "Hello", "unrelated": {"keep": True}})
    value = MainWindow(None, "SYNTHETIC", preferences_store=preferences)
    value.resize(1000, 800)
    value.show()
    qt.processEvents()
    yield value
    value.close()
    qt.processEvents()


def test_default_is_read_only_and_override_is_separate_and_profile_scoped(tmp_path):
    first = JsonStore(tmp_path / "first/ui.json")
    first.save({"theme_id": "conformist", "unrelated": 1})
    original = first.path.read_bytes()
    settings = FontSettings.for_preferences(first)
    assert settings.identity == "theme" and not settings.store.path.exists()
    settings.select("lora")
    assert first.path.read_bytes() == original
    assert FontSettings.for_preferences(first).identity == "lora"
    assert FontSettings.for_preferences(JsonStore(tmp_path / "second/ui.json")).identity == "theme"


@pytest.mark.parametrize("identity,name", FONT_CHOICES[1:])
def test_each_bundled_family_overrides_themes_and_preserves_text(window, qt, tmp_path, identity, name):
    controller = window.theme_controller
    original = window._preferences_store.path.read_bytes()
    package = deepcopy(controller.repository.packages["conformist"])
    window.input.setPlainText("Keep this draft")
    cursor = window.input.textCursor()
    cursor.setPosition(5)
    cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
    window.input.setTextCursor(cursor)
    band = window.chat.add_message("Agent", "## A familiar heading\n\n"
        + "A paragraph with **emphasis**, *italics* and `inline code`. " * 8
        + "\n\n```python\nprint('unchanged')\n```")
    label = band.message.label
    code = band.message._code_blocks[0]
    code_font = code.editor.font()
    label.setSelection(12, 7)
    selection, source = label.selectedText(), label.text()
    window.font_selector.setCurrentIndex(window.font_selector.findData(identity))
    qt.processEvents()
    family = controller.family
    # Windows exposes optical-size aliases for some variable font families.
    assert controller.font_identity == identity and family.startswith(name)
    assert window.input.font().family() == label.font().family() == family
    assert QFontInfo(window.input.font()).family().startswith(name)
    assert window.startup_greeting.font().family() == family
    for filename in FONT_FILES[identity]:
        assert (FONT_DIRECTORY / filename).is_file()
    stem = FONT_FILES[identity][0].removesuffix(".ttf")
    assert "SIL OPEN FONT LICENSE" in (FONT_DIRECTORY / f"OFL-{stem}.txt").read_text(encoding="utf-8")
    assert window._preferences_store.path.read_bytes() == original
    for theme in ("conformist", "ocean", "original", "conformist"):
        controller.select(theme)
        qt.processEvents()
        assert controller.family == label.font().family() == family
        assert QFontInfo(QFont(family)).family().startswith(name)
        assert controller.font_settings.identity == identity
    assert controller.current.family.startswith("DM Sans")
    assert controller.current.package == package
    exported = export_folder(controller.current.package, tmp_path / "exported")
    assert import_folder(exported)["manifest"]["font"] == package["manifest"]["font"]
    for width, height in ((760, 600), (1280, 900)):
        window.resize(width, height)
        qt.processEvents()
        assert label.height() >= label.heightForWidth(label.width())
    assert window.input.toPlainText() == "Keep this draft"
    assert window.input.textCursor().selectedText() == "this"
    assert label.text() == source and label.selectedText() == selection
    assert code.editor.font() == code_font
    window.font_selector.setCurrentIndex(window.font_selector.findData("theme"))
    qt.processEvents()
    assert controller.family == label.font().family() == controller.current.family
    controller.select("original")
    assert controller.family == "Saira"


def test_font_restores_after_restart_and_dm_sans_survives_theme_unload(qt, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    window = MainWindow(None, "SYNTHETIC", preferences_store=preferences)
    try:
        window.theme_controller.select("conformist")
        window.theme_controller.select_font("dm-sans")
        former = window.theme_controller.current
        window.theme_controller.select("original")
        assert former.font_id == -1
        assert QFontInfo(window.input.font()).family().startswith("DM Sans")
    finally:
        window.close()
    restored = MainWindow(None, "SYNTHETIC", preferences_store=preferences)
    try:
        assert restored.theme_controller.current.identity == "original"
        assert restored.font_selector.currentData() == "dm-sans"
        assert QFontInfo(restored.input.font()).family().startswith("DM Sans")
    finally:
        restored.close()


@pytest.mark.parametrize("data", [b"not JSON", b"[]", b'{"schema_version":1,"font_id":"unknown"}',
                                  b'{"schema_version":true,"font_id":"lora"}'])
def test_invalid_saved_font_is_preserved(qt, tmp_path, data):
    preferences = JsonStore(tmp_path / "ui.json")
    saved = tmp_path / "font_v1.json"
    saved.write_bytes(data)
    window = MainWindow(None, "SYNTHETIC", preferences_store=preferences)
    try:
        assert window.theme_controller.family == "Saira"
        assert not window.font_selector.isEnabled()
        assert "preserved" in window.settings_panel.font_controls.status.text()
        with pytest.raises(ValueError):
            window.theme_controller.select_font("lora")
        assert saved.read_bytes() == data
        assert window.theme_controller.font_identity == "theme"
    finally:
        window.close()


def test_failed_save_or_missing_asset_keeps_current_font(window, qt, monkeypatch, tmp_path):
    controller = window.theme_controller
    controller.select_font("lora")
    previous = controller.font_settings.store.path.read_bytes()
    with monkeypatch.context() as patch:
        def fail_save(_):
            raise OSError("Synthetic unavailable preference")
        patch.setattr(controller.font_settings.store, "save", fail_save)
        window.font_selector.setCurrentIndex(window.font_selector.findData("nunito"))
        assert controller.family == "Lora" and window.font_selector.currentData() == "lora"
        assert "preserved" in window.settings_panel.font_controls.status.text()
    with monkeypatch.context() as patch:
        import app.ui.fonts as fonts
        patch.setattr(qt, "_orsi_bundled_fonts", {})
        patch.setattr(fonts, "FONT_DIRECTORY", tmp_path / "missing-assets")
        window.font_selector.setCurrentIndex(window.font_selector.findData("outfit"))
        assert controller.family == "Lora" and window.font_selector.currentData() == "lora"
        assert "unavailable" in window.settings_panel.font_controls.status.text()
    assert controller.font_settings.store.path.read_bytes() == previous


def test_font_dropdown_works_and_remains_english_on_language_switch(window, qt):
    panel = window.settings_panel
    panel.show_section("Appearance")
    panel.show()
    qt.processEvents()
    selector = window.font_selector
    selector.showPopup()
    view = selector.view()
    view.setCurrentIndex(selector.model().index(selector.findData("outfit"), 0))
    QTest.keyClick(view, Qt.Key.Key_Return)
    qt.processEvents()
    language_runtime().apply(language_runtime().prepare("hu"))
    qt.processEvents()
    assert panel.isVisible() and selector.currentData() == "outfit"
    assert window.theme_controller.family == "Outfit"
    assert selector.accessibleName() == "Font" and selector.itemText(0) == "Theme default"
    assert any(label.text() == "Font" for label in panel.findChildren(QLabel, "settingName"))
    assert "Text size" not in panel.future_settings


def test_encrypted_profile_font_survives_lock_restart_unlock_and_profile_switch(qt, tmp_path):
    from app.ui.profile_application import ProfileApplication
    from app.vault.profiles import ProfileManager
    from tests.test_profile_onboarding import close_controller
    from tests.test_vault_controls import PASSWORD, build_synthetic
    application_root = tmp_path / "application"
    application_root.mkdir()
    manager = ProfileManager(application_root)
    first_root = tmp_path / "first-profile"
    manager.create(first_root, password=PASSWORD)
    owner = ProfileApplication(qt, application_root, build_synthetic, manager=manager)
    try:
        owner.start()
        owner.window.theme_controller.select("conformist")
        owner.window.theme_controller.select_font("merriweather")
        previous = owner.window.theme_controller.font_settings
        owner.transition(manager.lock)
        qt.processEvents()
        assert previous.closed and previous.store is None
        assert owner.window.service is None
        assert QFontInfo(owner.window.personal_profile_page.password.font()).family().startswith("Merriweather")
        assert set(owner.login_appearance.store.load()) == {"version", "profile_id", "theme_id", "font_id"}
        owner.window.personal_profile_page.password.setText(PASSWORD.decode())
        owner.window.personal_profile_page._unlock()
        assert owner.window.font_selector.currentData() == "merriweather"
        owner.transition(lambda: manager.create(tmp_path / "second-profile", password=PASSWORD))
        assert owner.window.font_selector.currentData() == "theme"
        owner.transition(lambda: manager.select(first_root, password=PASSWORD))
        assert owner.window.theme_controller.family.startswith("Merriweather")
        owner.transition(manager.lock)
    finally:
        close_controller(qt, owner)
    restarted = ProfileApplication(qt, application_root, build_synthetic)
    try:
        restarted.start()
        assert restarted.window.service is None
        assert QFontInfo(restarted.window.personal_profile_page.password.font()).family().startswith("Merriweather")
        restarted.window.personal_profile_page.password.setText(PASSWORD.decode())
        restarted.window.personal_profile_page._unlock()
        assert restarted.window.theme_controller.font_settings.identity == "merriweather"
        assert restarted.window.theme_controller.family.startswith("Merriweather")
    finally:
        close_controller(qt, restarted)
