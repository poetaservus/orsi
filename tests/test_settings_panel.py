"""Settings navigation, placeholder boundaries and existing action routing."""
import os
from types import SimpleNamespace
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QFont, QHoverEvent, QImage, QPainter, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QLabel, QStyle, QStyleOptionButton, QStyleOptionComboBox, QWidget

from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.ui.settings_layout import SettingsButton
from app.ui.theme_runtime import theme_color
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
def test_clean_settings_keep_labels_and_accessible_help_without_subtexts(app, theme):
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
            "General", "Greeting", "Personality",
            "Response Language", "Tool execution approval", "Notifications", "Notification sound",
        }
        notification_labels = [label for label in general.findChildren(QLabel)
                               if label.isVisible() and label.text() == "Notifications"]
        assert len(notification_labels) == 1
        assert notification_labels[0].font().weight() >= QFont.Weight.DemiBold
        approval_row = window.tool_approval_toggle.parentWidget()
        notification_row = window.notification_toggle.parentWidget()
        assert notification_row.parentWidget() is approval_row.parentWidget()
        assert notification_row.y() - (approval_row.y() + approval_row.height()) <= 1
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
            assert not any(label.text() == introduction and label.isVisible() for label in page.findChildren(QLabel))
            for row in page.findChildren(QFrame, "settingRow"):
                assert len(row.findChildren(QLabel)) == 1
                assert all(label.wordWrap() for label in row.findChildren(QLabel))
        assert not panel.theme_controls.status.isVisible()
        assert "drop a folder/file" in window.skill_settings_page.source.toolTip()
        window.skill_settings_page.set_vault_guidance(True)
        assert "encrypted while locked" in window.skill_settings_page.install_button.toolTip()
    finally:
        window.close()


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_action_buttons_stay_compact_at_native_caption_width(app, theme):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.show()
        window.theme_controller.select(theme)
        window.skill_settings_page.set_vault_guidance(True)
        for font in ("theme", "merriweather", "outfit"):
            window.theme_controller.select_font(font)
            for size in ((1280, 900), (760, 600)):
                window.resize(*size)
                for section in ("Skills", "Image Generation", "Appearance"):
                    panel = window.settings_panel
                    panel.show_section(section)
                    panel.show()
                    panel.page_transition.cancel()
                    app.processEvents()
                    if section == "Skills" and size[0] >= 900:
                        page = window.skill_settings_page
                        buttons = (page.browse, page.browse_folder, page.preview_button, page.install_button)
                        centers = [button.mapTo(page, button.rect().center()).y() for button in buttons]
                        assert max(centers) - min(centers) <= 1
                    elif section == "Image Generation":
                        page = window.image_settings_page
                        row = page.choices["output_format"].parentWidget()
                        bottom = row.mapTo(page, QPoint(0, row.height())).y()
                        assert page.actions.mapTo(page, QPoint()).y() - bottom >= 12
                    elif section == "Appearance":
                        controls = panel.theme_controls
                        row = controls.selector.parentWidget()
                        parent = row.parentWidget()
                        bottom = row.mapTo(parent, QPoint(0, row.height())).y()
                        assert controls.actions.mapTo(parent, QPoint()).y() - bottom >= 12
                    for button in panel.findChildren(SettingsButton):
                        if not button.isVisible():
                            continue
                        option = QStyleOptionButton()
                        button.initStyleOption(option)
                        content = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
                        metrics = button.fontMetrics()
                        assert metrics.horizontalAdvance(button.text()) <= content.width(), (theme, font, button.text())
                        assert button.height() <= max(36, metrics.height() + 16), (theme, font, button.text(), button.height())
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


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_settings_dropdowns_have_borderless_choices_and_subtle_hover(app, theme):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(1280, 900)
        window.theme_controller.select(theme)
        window.show()
        panel = window.settings_panel
        panel.show()
        checked = 0
        for section in ("General", "Models", "Image Generation", "Appearance"):
            panel.show_section(section)
            panel.page_transition.cancel()
            app.processEvents()
            scroll = panel.pages.currentWidget()
            for selector in scroll.widget().findChildren(QComboBox):
                if selector.count() < 2:
                    continue
                selector.setEnabled(True)  # Inspect unavailable synthetic-service controls, too.
                scroll.ensureWidgetVisible(selector)
                app.processEvents()
                before = selector.currentIndex()
                selector.showPopup()
                app.processEvents()
                view = selector.view()
                QTest.qWaitForWindowExposed(view.window())
                QTest.qWait(50)
                app.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
                image = view.viewport().grab().toImage()
                visible = [view.model().index(row, 0) for row in range(selector.count())
                           if view.viewport().rect().contains(view.visualRect(view.model().index(row, 0)))]
                assert len(visible) >= 2
                for index in visible[:2]:
                    bounds = view.visualRect(index)
                    x = bounds.right() - 10
                    assert image.pixelColor(x, bounds.top()) == image.pixelColor(x, bounds.center().y())
                    assert image.pixelColor(x, bounds.bottom()) == image.pixelColor(x, bounds.center().y())
                target = visible[1]
                bounds = view.visualRect(target)
                local, global_pos = QPointF(bounds.center()), QPointF(view.viewport().mapToGlobal(bounds.center()))
                app.sendEvent(view.viewport(), QEnterEvent(local, local, global_pos))
                app.sendEvent(view.viewport(), QHoverEvent(QEvent.Type.HoverMove, local, global_pos, QPointF(-1, -1)))
                bounds = view.visualRect(target)
                assert view.viewport().rect().contains(bounds)
                hover = view.viewport().grab().toImage()
                assert hover.pixelColor(bounds.right() - 10, bounds.center().y()) == theme_color(selector, "#2d4059", "surface_hover"), selector.accessibleName()
                assert selector.currentIndex() == before
                QTest.keyClick(view, Qt.Key.Key_Escape)
                assert not view.isVisible() and selector.currentIndex() == before
                checked += 1
        assert checked >= 9
    finally:
        window.close()


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_module_highlight_slides_retargets_and_fits_after_reopen_resize(app, theme):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.theme_controller.select(theme)
        window.show()
        panel = window.settings_panel
        panel.show()
        app.processEvents()
        motion = panel.navigation_highlight
        start = panel.navigation[0].geometry()
        assert motion.highlight.geometry() == start
        QTest.mouseClick(panel.navigation[2], Qt.MouseButton.LeftButton)
        assert panel.pages.currentIndex() == 2
        assert motion.animation.state() == motion.animation.State.Running
        motion.animation.setCurrentTime(80)
        midway = motion.highlight.geometry()
        assert start.y() < midway.y() < panel.navigation[2].y()
        QTest.mouseClick(panel.navigation[4], Qt.MouseButton.LeftButton)
        assert panel.pages.currentIndex() == 4 and motion.highlight.geometry() == midway
        motion.animation.setCurrentTime(motion.animation.duration())
        assert motion.highlight.geometry() == panel.navigation[4].geometry()
        for size in ((760, 600), (1280, 900)):
            panel.show_section("General")
            motion.animation.setCurrentTime(70)
            panel.hide()
            assert motion.animation.state() == motion.animation.State.Stopped
            window.resize(*size)
            panel.show()
            app.processEvents()
            assert motion.highlight.geometry() == panel.navigation[0].geometry()
            button = panel.navigation[0]
            assert panel.childAt(button.mapTo(panel, button.rect().center())) is button
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("hu"))
        app.processEvents()
        assert motion.highlight.geometry() == panel.navigation[0].geometry()
        personal_page = QWidget()
        personal_page.tabbed = False
        panel.add_personal_page(personal_page)
        app.processEvents()
        QTest.mouseClick(panel.navigation[-1], Qt.MouseButton.LeftButton)
        assert panel.pages.currentIndex() == len(panel.navigation) - 1
        motion.animation.setCurrentTime(motion.animation.duration())
        assert motion.highlight.geometry() == panel.navigation[-1].geometry()
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


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_switch_tracks_distinguish_states_without_a_focus_outline(app, theme):
    def rendered(switch):
        image = QImage(switch.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        switch.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return image

    window = MainWindow(None, "SYNTHETIC")
    try:
        window.theme_controller.select(theme)
        window.show()
        window.settings_panel.show()
        app.processEvents()
        app.setActiveWindow(window)
        for switch in (window.tool_approval_toggle, window.notification_toggle):
            for checked in (False, True):
                switch.setChecked(checked)
                wait_for(lambda: switch._slide.state() == switch._slide.State.Stopped)
                switch.clearFocus()
                unfocused = rendered(switch)
                track = unfocused.pixelColor(22, 12)
                if checked:
                    assert track.blue() > track.red() + 40
                else:
                    assert max(track.red(), track.green(), track.blue()) - min(track.red(), track.green(), track.blue()) < 15
                switch.setFocus()
                app.processEvents()
                assert switch.hasFocus()
                assert rendered(switch) == unfocused
                QTest.keyClick(switch, Qt.Key.Key_Space)
                assert switch.isChecked() != checked
    finally:
        window.close()


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_settings_blur_draws_new_chat_greeting_in_its_original_position(app, theme):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(1280, 900)
        window.theme_controller.select(theme)
        window.show()
        app.processEvents()
        greeting = window.startup_greeting
        bounds = greeting.rect().translated(greeting.mapTo(window, QPoint()))
        geometry = greeting.geometry()
        composer = window.composer.geometry()
        for _ in range(2):
            window.settings_panel.show()
            app.processEvents()
            greeting.hide()
            hidden = window.grab().toImage()
            greeting.show()
            shown = window.grab().toImage()
            changed = []
            for y in range(100, shown.height(), 4):
                for x in range(10, shown.width(), 4):
                    a, b = hidden.pixelColor(x, y), shown.pixelColor(x, y)
                    if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) > 3:
                        changed.append(QPoint(x, y))
            assert len(changed) > 10
            assert all(bounds.adjusted(-30, -30, 30, 30).contains(point) for point in changed)
            assert greeting.geometry() == geometry and window.composer.geometry() == composer
            window.settings_panel.hide()
            app.processEvents()
            assert window.startup_greeting_opacity.isEnabled()
            assert greeting.geometry() == geometry and window.composer.geometry() == composer
    finally:
        window.close()


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
            assert field.width() >= field.parentWidget().width() - 2
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


def test_settings_fill_window_through_resize_and_preserve_chat_draft(app):
    window = MainWindow(None, "TEST")
    try:
        window.resize(1600, 1000)
        window.show()
        window.input.setPlainText("Keep this draft while changing settings")
        cursor = window.input.textCursor()
        cursor.setPosition(7)
        window.input.setTextCursor(cursor)
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        assert panel.parentWidget() is window and panel.geometry() == window.rect()
        window_position = window.pos()
        panel.show_section("Appearance")
        window._position_overlays()
        assert window.pos() == window_position and not window.input.isEnabled()
        for size in ((760, 600), (1280, 800), (1600, 1000)):
            window.resize(*size)
            app.processEvents()
            assert panel.geometry() == window.rect()
            assert panel.pages.currentIndex() == 4
            assert window.greeting_input.font().pixelSize() == 18
        panel.hide()
        window.settings_button.click()
        app.processEvents()
        assert panel.geometry() == window.rect() and panel.pages.currentIndex() == 4
        panel.hide()
        assert window.input.isEnabled()
        assert window.input.toPlainText() == "Keep this draft while changing settings"
        assert window.input.textCursor().position() == 7
    finally:
        window.close()


def test_full_window_settings_retain_native_caption_controls_and_close_action(app):
    window = MainWindow(None, "TEST")
    try:
        window.show()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        for size in ((1280, 800), (760, 600)):
            window.resize(*size)
            app.processEvents()
            assert window.drag_strip.parentWidget() is panel
            assert window.window_controls.parentWidget() is panel
            assert window.window_controls.isEnabled()
            close = panel.close_button
            top_left = close.mapTo(panel, QPoint())
            close_rect = close.rect().translated(top_left)
            assert not window.drag_strip.geometry().intersects(close_rect)
            assert panel.childAt(close_rect.center()) is close
            assert close.cursor().shape() == Qt.CursorShape.ArrowCursor
            assert panel.header.cursor().shape() == Qt.CursorShape.ArrowCursor
        position = panel.pos()
        window.showMaximized()
        app.processEvents()
        assert panel.geometry() == window.rect()
        window.showNormal()
        app.processEvents()
        assert panel.geometry() == window.rect()
        QTest.mouseClick(panel.close_button, Qt.MouseButton.LeftButton)
        assert panel.pos() == position
        wait_for(panel.isHidden)
        assert window.window_controls.parentWidget() is window._root
        assert window.drag_strip.parentWidget() is window._root
        assert window._root.isEnabled() and window._root.graphicsEffect() is None
    finally:
        window.close()


@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_settings_blur_actual_backdrop_and_restore_chat_busy_state(app, theme):
    class Stripes(QWidget):
        def paintEvent(self, event):
            painter = QPainter(self)
            for x in range(0, self.width(), 4):
                painter.fillRect(x, 0, 4, self.height(), QColor("white" if x % 8 else "black"))

    def contrast(image):
        values = [image.pixelColor(x, image.height() // 2).red() for x in range(image.width())]
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / len(values)

    window = MainWindow(None, "TEST")
    try:
        window.resize(1280, 800)
        window.theme_controller.select(theme, persist=False)
        window.show()
        marker = Stripes(window._root)
        marker.setGeometry(28, 650, 160, 70)
        marker.show()
        marker.raise_()
        app.processEvents()
        before = window.grab(marker.geometry()).toImage()
        window.settings_button.click()
        app.processEvents()
        panel = window.settings_panel
        blurred = window.grab(marker.geometry()).toImage()
        assert contrast(blurred) < contrast(before) * .2
        assert panel.graphicsEffect() is None and window._root.graphicsEffect() is not None
        assert window.greeting_input.font().pixelSize() == 18
        assert panel.navigation[0].font().pixelSize() == 22
        assert window.input.font().pixelSize() != 16
        sound = window.notification_sound.selector
        option = QStyleOptionComboBox()
        sound.initStyleOption(option)
        bounds = sound.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                             QStyle.SubControl.SC_ComboBoxEditField, sound)
        assert sound.fontMetrics().horizontalAdvance(sound.currentText()) <= bounds.width()
        window._set_busy(True)
        panel.hide()
        app.processEvents()
        assert not window.input.isEnabled()  # Closing Settings must not end active work.
        window._set_busy(False)
        assert window.input.isEnabled() and window._root.graphicsEffect() is None
        restored = window.grab(marker.geometry()).toImage()
        assert contrast(restored) == pytest.approx(contrast(before), rel=.01)
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
