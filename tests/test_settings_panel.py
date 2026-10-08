"""Settings navigation, placeholder boundaries and existing action routing."""
import os
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate() and monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


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
            assert field.parentWidget().width() >= scroll.viewport().width() - 16
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
        assert store.current.size == "1024x1536"
        assert ImageSettingsStore(ImageGenerationSettings(), store.store.path).current.size == "1024x1536"
        window.service.fail = True
        page.choices["size"].setCurrentText("1536x1024")
        page.save_button.click()
        assert store.current.size == "1024x1536" and "Could not save" in page.notice.text()
        assert page.choices["size"].currentText() == "1536x1024"
        page.reset_button.click()
        assert page.choices["size"].currentText() == "1024x1536"
        window._set_busy(True)
        assert not window.image_settings_page.save_button.isEnabled()
    finally:
        window.close()
