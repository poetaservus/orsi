"""Cosmetic themes: real Qt reflow, state preservation and portable assets."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.state.storage import JsonStore
from app.ui.main_window import MainWindow, _STYLE
from app.ui.theme_runtime import color, theme_color
from app.ui.themes import (ASSETS, ThemeError, ThemeRepository, export_folder,
                           import_folder, validate_manifest, validate_package)


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qt, tmp_path):
    preferences = JsonStore(tmp_path / "state" / "ui_preferences_v1.json")
    preferences.save({"greeting_message": "Hello", "unrelated": {"keep": True},
                      "notifications": {"enabled": False, "sound": "silent"}})
    value = MainWindow(None, "TEST", preferences_store=preferences)
    value.resize(1000, 800)
    value.show()
    QTest.qWait(20)
    yield value
    value.close()
    qt.processEvents()


def package(**values):
    return {"manifest": {"version": 1, "id": "custom", "name": "Custom", **values}, "assets": {}}


def save_manifest(root, manifest):
    root.mkdir()
    path = root / "theme.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.mark.parametrize("change", [
    {"version": 2}, {"version": True}, {"id": "../escape"}, {"id": "original"},
    {"name": ""}, {"name": "bad\nname"}, {"animations": {}}, {"notifications": {}},
    {"palette": {"unknown": "#000000"}}, {"palette": {"text": "red; padding: 0"}},
    {"font": {"family": "Bad; font-size: 90px"}}, {"font": {"size": 99}},
    {"icons": {"send": "../send.svg"}}, {"icons": {"send": "https://example.com/icon.svg"}},
    {"background": {"type": "video", "file": "movie.mp4"}},
    {"background": {"type": "gradient", "colors": ["#ffffff"]}},
])
def test_manifest_cannot_change_behavior_layout_or_reference_outside_files(change):
    with pytest.raises(ThemeError):
        validate_manifest(package(**change)["manifest"])


def test_partial_theme_and_rgba_are_unambiguous():
    value = validate_package(package(palette={"text": "#10203080"}))
    assert value["manifest"]["palette"] == {"text": "#10203080"}
    assert color("#10203080").getRgb() == (16, 32, 48, 128)


@pytest.mark.parametrize("svg", [
    '<svg xmlns="http://www.w3.org/2000/svg"><animate attributeName="x"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///secret"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.com/icon.svg"/></svg>',
    '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///secret">]><svg>&x;</svg>',
])
def test_import_rejects_nonstatic_or_external_svg(tmp_path, svg):
    path = save_manifest(tmp_path / "theme", package(icons={"send": "send.svg"})["manifest"])
    (path.parent / "send.svg").write_text(svg, encoding="utf-8")
    with pytest.raises(ThemeError):
        import_folder(path)


def test_original_styles_are_exact_and_partial_palette_inherits(window):
    assert window.styleSheet() == _STYLE
    window.theme_controller.repository.add(package(palette={"composer_top": "#112233"}))
    window.theme_controller.select("custom")
    assert window.styleSheet() == _STYLE
    assert theme_color(window.composer, "#2c3036", "composer_top") == QColor("#112233")
    assert theme_color(window.composer, "#282c32", "composer_bottom") == QColor("#282c32")


def test_selector_remembers_theme_without_touching_draft_or_other_preferences(window, qt):
    before = window._preferences_store.load()
    window.input.setPlainText("Keep this draft\nAnd its second line")
    cursor = window.input.textCursor()
    cursor.setPosition(5)
    cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
    window.input.setTextCursor(cursor)
    window.theme_selector.setCurrentIndex(window.theme_selector.findData("ocean"))
    qt.processEvents()
    assert window.theme_controller.current.identity == "ocean"
    assert window._preferences_store.load() == before | {"theme_id": "ocean"}
    assert window.input.toPlainText() == "Keep this draft\nAnd its second line"
    assert window.input.textCursor().selectedText() == "this"
    assert window.notifications is not None
    assert not window.microphone_placeholder.isEnabled()
    window.theme_selector.setCurrentIndex(window.theme_selector.findData("original"))
    assert window.styleSheet() == _STYLE
    assert window._preferences_store.load() == before | {"theme_id": "original"}


def test_selecting_from_open_dropdown_keeps_settings_usable(window, qt):
    window.settings_panel.show_section("Appearance")
    window.settings_panel.show()
    qt.processEvents()
    selector = window.theme_selector
    selector.showPopup()
    view = selector.view()
    view.setCurrentIndex(selector.model().index(selector.findData("ocean"), 0))
    QTest.keyClick(view, Qt.Key.Key_Return)
    qt.processEvents()
    assert selector.currentData() == "ocean" and window.theme_controller.current.identity == "ocean"
    assert window.settings_panel.isVisible() and window.settings_panel.theme_controls.add.isEnabled()


def test_restart_missing_theme_and_unreadable_preferences_preserve_selection(qt, tmp_path):
    prefs = JsonStore(tmp_path / "ui.json")
    prefs.save({"theme_id": "missing", "unrelated": 1})
    before = prefs.path.read_bytes()
    value = MainWindow(None, "TEST", preferences_store=prefs)
    try:
        assert value.theme_controller.current.identity == "original"
        assert "preserved" in value.theme_controller.notice
        assert prefs.path.read_bytes() == before
    finally:
        value.close()
    prefs.path.write_text("not JSON", encoding="utf-8")
    value = MainWindow(None, "TEST", preferences_store=prefs)
    try:
        with pytest.raises(Exception):
            value.theme_controller.select("ocean")
        assert value.theme_controller.current.identity == "original"
        assert prefs.path.read_text() == "not JSON"
    finally:
        value.close()


def test_import_export_and_update_copy_assets_and_restore(window, tmp_path, qt):
    source = tmp_path / "source"
    path = save_manifest(source, package(icons={"send": "icons/send.svg"},
                         background={"type": "solid", "color": "#142a35"})["manifest"])
    (source / "icons").mkdir()
    (source / "icons/send.svg").write_bytes((ASSETS / "plus.svg").read_bytes())
    controls = window.settings_panel.theme_controls
    controls.import_path(path)
    assert window.theme_controller.current.identity == "custom"
    saved = deepcopy(window.theme_controller.current.package)
    (source / "icons/send.svg").unlink()
    output = export_folder(saved, tmp_path / "export")
    assert import_folder(output) == saved
    with pytest.raises(FileExistsError):
        export_folder(saved, output)
    original_icon = window.send.icon().pixmap(28, 28).toImage()
    window.theme_controller.select("original")
    assert window.send.icon().pixmap(28, 28).toImage() != original_icon
    controls.import_path(output)
    assert window.send.icon().pixmap(28, 28).toImage() == original_icon
    manifest = saved["manifest"] | {"palette": {"composer_top": "#445566"}}
    (output / "theme.json").write_text(json.dumps(manifest), encoding="utf-8")
    controls.import_path(output)
    assert theme_color(window.composer, "#2c3036", "composer_top") == QColor("#445566")
    prefs = window._preferences_store
    restored = MainWindow(None, "TEST", preferences_store=prefs)
    try:
        assert restored.theme_controller.current.identity == "custom"
        assert restored.send.icon().pixmap(28, 28).toImage() == original_icon
    finally:
        restored.close()


def test_failed_import_keeps_current_appearance_and_catalog(window, tmp_path):
    before = window._preferences_store.path.read_bytes()
    path = save_manifest(tmp_path / "bad", package(icons={"send": "bad.png"})["manifest"])
    (path.parent / "bad.png").write_bytes(b"not an image")
    with pytest.raises(ThemeError):
        window.settings_panel.theme_controls.import_path(path)
    assert window.theme_controller.current.identity == "original"
    assert "custom" not in window.theme_controller.repository.packages
    assert window._preferences_store.path.read_bytes() == before


def test_svg_local_gradients_and_static_styles_are_supported(tmp_path):
    path = save_manifest(tmp_path / "theme", package(icons={"send": "send.svg"})["manifest"])
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><style>.a{fill:url(#g)}</style><defs><linearGradient id="g"><stop stop-color="#112233"/><stop offset="1" stop-color="#445566"/></linearGradient></defs><circle class="a" cx="12" cy="12" r="10"/></svg>'
    (path.parent / "send.svg").write_text(svg, encoding="utf-8")
    assert "send.svg" in import_folder(path)["assets"]


def test_all_requested_icons_change_without_changing_actions_or_motion(window, qt):
    buttons = {"new_message": window.new_session_button, "settings": window.settings_button,
               "send": window.send, "microphone": window.microphone_placeholder,
               "attach": window.add_placeholder, "folder": window.folder_placeholder}
    before = {name: (button.size(), button.isEnabled(), button.accessibleName(), button.toolTip(),
                     button.icon().pixmap(28, 28).toImage()) for name, button in buttons.items()}
    duration = window.settings_button.animation.duration()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><circle cx="12" cy="12" r="10" fill="#bb2244"/></svg>'
    value = package(icons={name: "icons/circle.svg" for name in buttons})
    value["assets"]["icons/circle.svg"] = base64.b64encode(svg).decode("ascii")
    window.theme_controller.repository.add(value)
    window.theme_controller.select("custom")
    qt.processEvents()
    assert window.theme_selector.currentData() == "custom"
    for name, button in buttons.items():
        assert (button.size(), button.isEnabled(), button.accessibleName(), button.toolTip()) == before[name][:4]
        assert button.icon().pixmap(28, 28).toImage() != before[name][4]
    assert window.settings_button.animation.duration() == duration
    picture = window.settings_button.grab().toImage()
    assert picture.pixelColor(picture.width() // 2, picture.height() // 2).name() == "#bb2244"


def test_profile_theme_catalogs_and_selection_are_isolated(tmp_path):
    first = ThemeRepository(JsonStore(tmp_path / "one/ui.json"))
    second = ThemeRepository(JsonStore(tmp_path / "two/ui.json"))
    first.add(package())
    first.save_selection("custom")
    assert second.selected() == "original" and "custom" not in second.packages
    assert ThemeRepository(first.preferences).selected() == "custom"


def test_legacy_preference_migration_includes_imported_theme_assets(tmp_path):
    from app.vault.migration import prepare_migration
    legacy = tmp_path / "legacy"
    repository = ThemeRepository(JsonStore(legacy / "state/ui_preferences_v1.json"))
    value = package(icons={"send": "send.svg"})
    value["assets"]["send.svg"] = base64.b64encode((ASSETS / "plus.svg").read_bytes()).decode("ascii")
    repository.add(value)
    repository.save_selection("custom")
    plan = prepare_migration(legacy, ("preferences",))
    migrated = {write.path: write.source for write in plan.writes}
    assert json.loads(migrated["state/ui_preferences_v1.json"])["theme_id"] == "custom"
    assert json.loads(migrated["state/themes/catalog_v1.json"])["custom"] == value


def test_corrupt_catalog_is_preserved_and_not_overwritten(tmp_path):
    prefs = JsonStore(tmp_path / "ui.json")
    path = tmp_path / "themes/catalog_v1.json"
    path.parent.mkdir()
    path.write_text("broken catalog", encoding="utf-8")
    repository = ThemeRepository(prefs)
    with pytest.raises(ThemeError):
        repository.add(package())
    assert path.read_text() == "broken catalog"


def test_font_reflows_existing_markdown_without_changing_structure_or_selection(window, qt):
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
    if not font_path.exists():
        pytest.skip("A second host font is required for real family/reflow verification")
    text = "## Heading\n\n" + "A paragraph with **emphasis** and `inline code` that wraps naturally. " * 5 + "\n\n- First item\n- Second item\n\n```python\nprint('unchanged')\n```"
    band = window.chat.add_message("Agent", text)
    user = window.chat.add_message("User", "Some long user text with spaces to exercise wrapping. " * 8)
    qt.processEvents()
    message = band.message
    label = message._text_labels[0]
    label.setSelection(12, 7)
    selected = label.selectedText()
    source, plain = label.text(), label.plain_text()
    code = message._code_blocks[0]
    code_font, code_source = code.editor.font(), code.code
    original_font, original_height = label.font().family(), label.height()
    before_blocks = []
    block = label.document.begin()
    while block.isValid():
        before_blocks.append((block.text(), block.blockFormat().headingLevel(),
                              block.blockFormat().lineHeight(), block.blockFormat().topMargin(),
                              block.blockFormat().bottomMargin(), bool(block.textList())))
        block = block.next()
    value = package(font={"file": "fonts/ui.ttf"})
    value["assets"]["fonts/ui.ttf"] = base64.b64encode(font_path.read_bytes()).decode("ascii")
    window.theme_controller.repository.add(value)
    window.theme_controller.select("custom")
    qt.processEvents()
    assert label.font().family() != original_font
    assert window.input.font().family() == label.font().family()
    assert label.text() == source and label.plain_text() == plain and label.selectedText() == selected
    after_blocks = []
    block = label.document.begin()
    while block.isValid():
        after_blocks.append((block.text(), block.blockFormat().headingLevel(),
                             block.blockFormat().lineHeight(), block.blockFormat().topMargin(),
                             block.blockFormat().bottomMargin(), bool(block.textList())))
        block = block.next()
    assert after_blocks == before_blocks
    assert code.code == code_source and code.editor.font() == code_font
    for size in ((760, 600), (1280, 900)):
        window.resize(*size)
        qt.processEvents()
        assert label.height() >= label.heightForWidth(label.width())
        assert user.message.width() <= window.chat._message_area_width()
        assert user.message.label.height() >= user.message.label.fontMetrics().lineSpacing()
    active = window.theme_controller.current
    assert active.font_id >= 0
    window.theme_controller.select("original")
    qt.processEvents()
    assert active.font_id == -1
    assert label.font().family() == original_font


def test_switch_while_streaming_preserves_scroll_timer_and_copy_feedback(window, qt):
    for _ in range(14):
        window.chat.add_message("Agent", "A long enough reply for scroll testing. " * 20)
    qt.processEvents()
    bar = window.chat.verticalScrollBar()
    window.chat._follow_tail = False
    bar.setValue(bar.maximum() // 3)
    value = bar.value()
    window.chat.set_thinking(True)
    window.chat.stream_preview.setText("Streaming text")
    window.chat.stream_preview.show()
    copy = window.chat._message_bands[-1].copy_button
    copy.copy_text("original source")
    timer = copy._feedback_timer.remainingTime()
    window.theme_controller.select("ocean")
    qt.processEvents()
    assert bar.value() == value
    assert not window.chat._follow_tail
    assert window.chat._response_timer.isActive() and window.chat.thinking_dots.is_running
    assert window.chat.stream_preview.text() == "Streaming text"
    assert copy.copy_succeeded and 0 < copy._feedback_timer.remainingTime() <= timer
    window.chat.set_thinking(False)


@pytest.mark.parametrize("background", [
    {"type": "solid", "color": "#112233"},
    {"type": "gradient", "colors": ["#112233", "#445566"], "direction": "diagonal"},
    {"type": "image", "file": "background.png", "fit": "cover"},
    {"type": "image", "file": "background.png", "fit": "contain"},
    {"type": "image", "file": "background.png", "fit": "stretch"},
])
def test_background_and_glass_region_share_coordinates(window, qt, background):
    value = package(background=background)
    if background["type"] == "image":
        image = QPixmap(80, 60)
        image.fill(QColor("#112233"))
        painter = QPainter(image)
        painter.fillRect(40, 0, 40, 60, QColor("#445566"))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        value["assets"]["background.png"] = base64.b64encode(bytes(data)).decode("ascii")
    window.theme_controller.repository.add(value)
    window.theme_controller.select("custom")
    surface = window._root.findChild(type(window.composer.parentWidget()), "mainContent")
    full = QPixmap(surface.size())
    painter = QPainter(full)
    surface.paint_background_region(painter, QRectF(full.rect()), QRectF(full.rect()))
    painter.end()
    region = QPixmap(120, 90)
    painter = QPainter(region)
    source = QRectF(100, 130, 120, 90)
    surface.paint_background_region(painter, QRectF(region.rect()), source)
    painter.end()
    assert region.toImage() == full.copy(source.toRect()).toImage()


def test_encrypted_theme_assets_survive_backup_without_plaintext_files(qt, tmp_path):
    pytest.importorskip("nacl")
    from app.vault.engine import Vault
    from app.vault.session import ProfileSession
    password = b"synthetic theme password"
    root = tmp_path / "profile"
    vault = Vault.create(root, password)
    session = ProfileSession(vault)
    prefs = JsonStore(session.storage_path("state/ui_preferences_v1.json"))
    value = package(name="THEME-PRIVATE-MARKER-5967", icons={"send": "send.svg"})
    value["assets"]["send.svg"] = base64.b64encode((ASSETS / "plus.svg").read_bytes()).decode("ascii")
    repo = ThemeRepository(prefs)
    repo.add(value)
    repo.save_selection("custom")
    restored = ThemeRepository(prefs)
    assert restored.packages["custom"] == value and restored.selected() == "custom"
    assert not (root / "state/themes/catalog_v1.json").exists()
    for path in root.rglob("*"):
        if path.is_file() and path.name != ".lease":
            assert b"THEME-PRIVATE-MARKER-5967" not in path.read_bytes()
    backup = vault.backup(tmp_path / "backup")
    copy = Vault.restore(backup, tmp_path / "restored", password=password)
    copy_session = ProfileSession(copy)
    copy_repo = ThemeRepository(JsonStore(copy_session.storage_path("state/ui_preferences_v1.json")))
    assert copy_repo.packages["custom"] == value and copy_repo.selected() == "custom"
    copy_session.lock()
    session.lock()
    repo.clear()
    assert not repo.packages and repo.store is None
