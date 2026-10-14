"""Settings navigation, placeholder boundaries and existing action routing."""
import os
from types import SimpleNamespace
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.settings.personality import PersonalitySettings
from app.settings.response_language import ResponseLanguageSettings


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate() and monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_clean_settings_keep_module_introductions_and_accessible_help(app, theme):
    service = SimpleNamespace(personality_settings=PersonalitySettings(),
                              response_language_settings=ResponseLanguageSettings())
    window = MainWindow(service, "TEST")
    try:
        window.theme_controller.select(theme)
        window.resize(760, 600)
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        general = panel.pages.currentWidget().widget()
        assert {label.text() for label in general.findChildren(QLabel) if label.isVisible()} == {
            "General", "Everyday preferences for O.R.S.I.", "Greeting", "Personality",
            "Response Language", "Tool execution approval", "Notifications", "Notification sound",
        }
        assert not window.activity.isVisible()
        assert not window.personality_hint.isVisible()
        assert not window.response_language_hint.isVisible()
        assert window.personality_selector.toolTip()
        assert "next response" in window.response_language_selector.accessibleDescription()
        assert "pending review" in window.tool_approval_toggle.accessibleDescription()
        for index, introduction in enumerate((
            "Everyday preferences for O.R.S.I.",
            "Choose where O.R.S.I runs and which model it uses.",
            "Preview, install and manage skills here.",
            "Preferences for your next generated image.",
            "Display and accessibility preferences.",
        )):
            panel.pages.setCurrentIndex(index)
            app.processEvents()
            page = panel.pages.currentWidget().widget()
            assert any(label.text() == introduction and label.isVisible() for label in page.findChildren(QLabel))
            for row in page.findChildren(QFrame, "settingRow"):
                assert len(row.findChildren(QLabel)) == 1
        assert not panel.theme_controls.status.isVisible()
        assert "drop a folder/file" in window.skill_settings_page.source.toolTip()
        window.skill_settings_page.set_vault_guidance(True)
        assert "encrypted while locked" in window.skill_settings_page.install_button.toolTip()
    finally:
        window.close()


def test_clean_settings_still_display_unreadable_preference_errors(app, tmp_path):
    store = JsonStore(tmp_path / "invalid.json")
    store.path.write_text("{unreadable", encoding="utf-8")
    original = store.path.read_bytes()
    service = SimpleNamespace(personality_settings=PersonalitySettings(store),
                              response_language_settings=ResponseLanguageSettings(store))
    window = MainWindow(service, "TEST")
    try:
        window.show()
        window.settings_button.click()
        app.processEvents()
        for hint, selector in ((window.personality_hint, window.personality_selector),
                               (window.response_language_hint, window.response_language_selector)):
            assert hint.isVisible() and "could not be loaded" in hint.text()
            assert not selector.isEnabled()
        assert store.path.read_bytes() == original
        service.personality_settings = PersonalitySettings()
        service.response_language_settings = ResponseLanguageSettings()
        window._sync_personality_selector()
        window._sync_response_language_selector()
        assert not window.personality_hint.isVisible() and not window.response_language_hint.isVisible()
    finally:
        window.close()


def test_opening_settings_does_not_change_preferences_or_draft(app, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    preferences.save({"greeting_message": "Hello", "unrelated": "keep"})
    before = preferences.path.read_bytes()
    window = MainWindow(None, "TEST", preferences_store=preferences)
    try:
        window.show()
        window.input.setPlainText("Keep this draft")
        window.settings_button.click()
        app.processEvents()
        assert window.theme_selector.isEnabled()
        assert window.theme_selector.currentData() == "original"
        assert window.gui_language_selector.isEnabled()
        assert window.gui_language_selector.currentData() == "en"
        assert window.gui_language_selector.count() == 46
        assert window.response_language_selector.currentData() == "auto"
        assert not window.response_language_selector.isEnabled()  # No conversation service.
        assert window.tool_approval_toggle.isEnabled()
        assert window.tool_approval_toggle.isChecked()
        assert preferences.path.read_bytes() == before
        assert window.input.toPlainText() == "Keep this draft"
    finally:
        window.close()


def test_tool_approval_switch_persists_and_preserves_other_preferences_and_draft(app, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    original = {"greeting_message": "Hello", "unrelated": "keep", "notifications": {"enabled": False}}
    preferences.save(original)
    selections = []
    service = SimpleNamespace(set_tool_approval_required=selections.append)
    window = MainWindow(service, "TEST", preferences_store=preferences)
    try:
        window.show()
        window.settings_button.click()
        window.input.setPlainText("Keep this draft")
        app.processEvents()
        toggle = window.tool_approval_toggle
        assert toggle.isChecked() and selections == [True]
        QTest.mouseClick(toggle, Qt.MouseButton.LeftButton)
        assert not toggle.isChecked() and selections == [True, False]
        assert preferences.load() == original | {"tool_approval_required": False}
        assert window.input.toPlainText() == "Keep this draft"
    finally:
        window.close()
    restored = MainWindow(service, "TEST", preferences_store=preferences)
    try:
        assert not restored.tool_approval_toggle.isChecked() and selections[-1] is False
        restored.show()
        restored.settings_button.click()
        app.processEvents()
        restored.tool_approval_toggle.setFocus()
        QTest.keyClick(restored.tool_approval_toggle, Qt.Key.Key_Space)
        assert restored.tool_approval_toggle.isChecked() and selections[-1] is True
        assert preferences.load() == original | {"tool_approval_required": True}
    finally:
        restored.close()


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], {}])
def test_invalid_tool_approval_preference_defaults_to_review(app, tmp_path, value):
    preferences = JsonStore(tmp_path / "ui.json")
    preferences.save({"tool_approval_required": value})
    original = preferences.path.read_bytes()
    selections = []
    window = MainWindow(SimpleNamespace(set_tool_approval_required=selections.append), "TEST",
                        preferences_store=preferences)
    try:
        assert window.tool_approval_toggle.isChecked() and selections == [True]
        assert preferences.path.read_bytes() == original
    finally:
        window.close()


def test_unreadable_tool_approval_preferences_are_preserved(app, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    preferences.path.write_text("{unreadable", encoding="utf-8")
    original = preferences.path.read_bytes()
    window = MainWindow(None, "TEST", preferences_store=preferences)
    try:
        assert window.tool_approval_toggle.isChecked()
        window.tool_approval_toggle.setChecked(False)
        assert preferences.path.read_bytes() == original
    finally:
        window.close()


def test_greeting_field_is_visible_clickable_and_persists_at_all_window_sizes(app, tmp_path):
    preferences = JsonStore(tmp_path / "ui.json")
    preferences.save({"greeting_message": "Hello", "unrelated": "keep"})
    window = MainWindow(None, "TEST", preferences_store=preferences)
    try:
        window.show()
        window.settings_button.click()
        window.settings_panel.show_section("General")
        for size in ((1280, 800), (760, 600)):
            window.resize(*size)
            app.processEvents()
            scroll = window.settings_panel.pages.currentWidget()
            field = window.greeting_input
            visible_rect = field.rect().translated(field.mapTo(scroll.viewport(), QPoint()))
            assert field.isVisible() and field.isEnabled()
            assert scroll.viewport().rect().contains(visible_rect)
            assert field.width() >= scroll.viewport().width() - 16
            center = field.mapTo(window.settings_panel, field.rect().center())
            assert window.settings_panel.childAt(center) is field
            QTest.mouseClick(field, Qt.MouseButton.LeftButton)
            assert field.hasFocus()
            QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(field, "Welcome back")
            QTest.keyClick(field, Qt.Key.Key_Tab)
            app.processEvents()
            assert window.startup_greeting.text() == "Welcome back"
            assert preferences.load() == {"greeting_message": "Welcome back", "unrelated": "keep"}
        window.settings_panel.show_section("Appearance")
        window.settings_panel.hide()
        window.settings_button.click()
        window.settings_panel.show_section("General")
        app.processEvents()
        assert window.greeting_input.isVisible() and window.greeting_input.text() == "Welcome back"
    finally:
        window.close()
    restored = MainWindow(None, "TEST", preferences_store=preferences)
    try:
        assert restored.greeting_input.text() == "Welcome back"
    finally:
        restored.close()


def test_navigation_close_and_compact_layout_keep_controls_reachable(app):
    window = MainWindow(None, "TEST")
    try:
        window.resize(760, 600)
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        assert window._root.rect().contains(panel.geometry())
        assert [button.text() for button in panel.navigation] == ["General", "Models", "Skills", "Image Generation", "Appearance"]
        for index, button in enumerate(panel.navigation):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            assert panel.pages.currentIndex() == index
            assert sum(item.isChecked() for item in panel.navigation) == 1
        assert not window.image_settings_page.save_button.isEnabled()
        panel.navigation[0].click()
        app.processEvents()
        positions = []
        for section, control in (("Appearance", window.theme_selector), ("Models", window.model_selector),
                                 ("Models", window.local_model_selector), ("Appearance", window.gui_language_selector),
                                 ("General", window.response_language_selector)):
            panel.show_section(section)
            app.processEvents()
            positions.append(control.mapTo(panel, QPoint()).x())
        assert len(set(positions)) == 1
        assert all(not control.isEnabled() for control in panel.future_settings.values())
        panel.show_section("General")
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
        wait_for(panel.isHidden)
    finally:
        window.close()


@pytest.mark.parametrize("size", [(1280, 800), (760, 600)])
def test_full_agent_status_keeps_general_controls_inside_viewport(app, size):
    status = (
        "Ready · Local · Agent · Full local read · Metadata + find + listing + text + search"
        " · Folder approval · Text-write approval · Text-edit approval"
        " · Copy approval · Move approval · Trash approval"
    )
    window = MainWindow(None, "TEST")
    try:
        window.activity.set_activity(status)
        window.resize(*size)
        window.show()
        window.settings_button.click()
        app.processEvents()
        scroll = window.settings_panel.pages.currentWidget()
        for activity in (status, "Working…", status):
            window.activity.set_activity(activity)
            app.processEvents()
            assert scroll.widget().width() <= scroll.viewport().width()
            for control in (window.response_language_selector, window.tool_approval_toggle,
                            window.notification_toggle, window.notification_sound):
                scroll.ensureWidgetVisible(control)
                app.processEvents()
                bounds = control.rect().translated(control.mapTo(scroll.viewport(), QPoint()))
                assert scroll.viewport().rect().contains(bounds)
    finally:
        window.close()


def test_larger_panel_drags_independently_and_keeps_position_during_chat_layout(app):
    window = MainWindow(None, "TEST")
    try:
        window.resize(1600, 1000)
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        assert panel.size().width() == 1120 and panel.size().height() == 740
        original = panel.pos()
        window_position = window.pos()
        header = panel.drag_strip
        local = QPoint(90, 8)
        global_start = header.mapToGlobal(local)
        QTest.mousePress(header, Qt.MouseButton.LeftButton, pos=local)
        target = global_start + QPoint(70, 40)
        move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(header.mapFromGlobal(target)),
                           QPointF(target), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
        app.sendEvent(header, move)
        QTest.mouseRelease(header, Qt.MouseButton.LeftButton, pos=local)
        assert panel.pos() == original + QPoint(70, 40)
        assert panel.user_positioned
        assert window.pos() == window_position
        dragged = panel.pos()
        window._position_overlays()
        window.input.setPlainText("Keep draft while dragging")
        app.processEvents()
        assert panel.pos() == dragged
        window.settings_button.click()
        window.settings_button.click()
        assert panel.pos() == dragged
        window.resize(760, 600)
        app.processEvents()
        assert window._root.rect().contains(panel.geometry())
        local = QPoint(90, 8)
        target = header.mapToGlobal(local) + QPoint(5000, 5000)
        QTest.mousePress(header, Qt.MouseButton.LeftButton, pos=local)
        move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(header.mapFromGlobal(target)),
                           QPointF(target), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
        app.sendEvent(header, move)
        QTest.mouseRelease(header, Qt.MouseButton.LeftButton, pos=local)
        assert window._root.rect().contains(panel.geometry())
        assert window.input.toPlainText() == "Keep draft while dragging"
    finally:
        window.close()


def test_dragging_is_at_top_edge_and_does_not_overlap_close_button(app):
    window = MainWindow(None, "TEST")
    try:
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        for size in ((1280, 800), (760, 600)):
            window.resize(*size)
            app.processEvents()
            assert panel.childAt(QPoint(100, 4)) is panel.drag_strip
            close = panel.close_button
            top_left = close.mapTo(panel, QPoint())
            close_rect = close.rect().translated(top_left)
            assert not panel.drag_strip.geometry().intersects(close_rect)
            assert panel.childAt(close_rect.center()) is close
            assert close.cursor().shape() == Qt.CursorShape.ArrowCursor
            assert panel.header.cursor().shape() == Qt.CursorShape.ArrowCursor
        position = panel.pos()
        # Clicking the close area must activate its button rather than starting a drag.
        QTest.mouseClick(panel.close_button, Qt.MouseButton.LeftButton)
        assert panel.drag_strip._drag_offset is None and panel.pos() == position
        wait_for(panel.isHidden)
    finally:
        window.close()


def test_vector_button_feedback_keeps_hit_targets_and_finishes_or_cancels(app):
    window = MainWindow(None, "TEST")
    try:
        window.show()
        app.processEvents()
        cog = window.settings_button
        geometry = cog.geometry()
        window.settings_button.click()
        assert cog.animation.state() == cog.animation.State.Running
        cog.animation.setCurrentTime(160)
        assert cog.scale == pytest.approx(0.82)
        assert cog.angle == pytest.approx(90.0)
        assert cog.geometry() == geometry
        wait_for(lambda: cog.animation.state() == cog.animation.State.Stopped)
        assert cog.scale == pytest.approx(1.0) and cog.angle == pytest.approx(180.0)
        panel = window.settings_panel
        close = panel.close_button
        # Deliver widget enter/leave events directly: moving the OS pointer in a
        # background test window does not reliably deliver these on Windows.
        app.sendEvent(close, QEvent(QEvent.Type.Leave))
        app.processEvents()
        rest = close.grab().toImage()
        center = QPointF(close.rect().center())
        app.sendEvent(close, QEnterEvent(center, center, QPointF(close.mapToGlobal(center.toPoint()))))
        app.processEvents()
        assert close.underMouse()
        before = close.grab().toImage()
        assert before != rest
        QTest.mouseClick(close, Qt.MouseButton.LeftButton)
        assert panel.isVisible()
        close.animation.setCurrentTime(100)
        assert close.scale == pytest.approx(0.82)
        assert close.grab().toImage() != before
        wait_for(panel.isHidden)
        window.settings_button.click()
        assert cog.animation.state() == cog.animation.State.Running
        close.click()
        panel.navigation[0].setFocus()
        QTest.keyClick(panel.navigation[0], Qt.Key.Key_Escape)
        assert panel.isHidden() and close.animation.state() == close.animation.State.Stopped
        window.close()
        assert cog.animation.state() == cog.animation.State.Stopped
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
        fail = False

        def select_image_settings(self, settings):
            if self.fail:
                raise RuntimeError("Synthetic save failure")
            store.select(settings)

    window = MainWindow(Service(), "TEST", inference=inference)
    try:
        window.show()
        window.settings_button.click()
        window._open_image_settings()
        page = window.image_settings_page
        assert page.save_button.isVisible() and page.save_button.isEnabled()
        assert not page.notice.isVisible() and not window.settings_panel.image_hint.isVisible()
        assert not page.isWindow() and QApplication.activeModalWidget() is None
        page.choices["size"].setCurrentText("1024x1536")
        window.settings_panel.show_section("General")
        window.settings_panel.hide()
        window._open_image_settings()
        window._set_busy(True)
        assert not page.save_button.isEnabled()
        window._set_busy(False)
        assert page.choices["size"].currentText() == "1024x1536"
        page.save_button.click()
        assert page.isVisible() and window.settings_panel.isVisible()
        assert page.notice.isVisible() and "saved" in page.notice.text()
        assert store.current.size == "1024x1536"
        assert ImageSettingsStore(ImageGenerationSettings(), store.store.path).current.size == "1024x1536"
        window.service.fail = True
        page.choices["size"].setCurrentText("1536x1024")
        page.save_button.click()
        assert store.current.size == "1024x1536" and "Could not save" in page.notice.text()
        assert page.notice.isVisible()
        assert page.choices["size"].currentText() == "1536x1024"
        page.reset_button.click()
        assert page.choices["size"].currentText() == "1024x1536"
        window._set_busy(True)
        assert not window.image_settings_page.save_button.isEnabled()
    finally:
        window.close()
