"""Original settings must not inherit native cyan focus/selection outlines."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QCheckBox, QFrame, QLineEdit, QListWidget, QPushButton,
                              QRadioButton, QStyle, QStyleOptionButton, QTextEdit, QVBoxLayout, QWidget)

from app.ui.inputs import CompactNumberInput, ScrollSafeComboBox
from app.ui.notification_settings import NotificationSwitch
from app.ui.personal_profile import _STYLE as PROFILE_STYLE
from app.ui.settings_panel import _STYLE as SETTINGS_STYLE
from tests.test_ui_themes import qt


def assert_no_cyan_border(widget, rect=None):
    image = widget.grab().toImage()
    rect = (rect or widget.rect()).intersected(widget.rect())
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(rect.left(), rect.right() + 1):
            if min(x - rect.left(), rect.right() - x, y - rect.top(), rect.bottom() - y) >= 2:
                continue
            color = image.pixelColor(x, y)
            assert not (color.blue() > 140 and color.green() - color.red() > 25
                        and color.blue() - color.red() > 25), (type(widget).__name__, x, y, color.name())


def assert_neutral_border(widget):
    image = widget.grab().toImage()
    color = image.pixelColor(image.width() // 2, 0)
    assert color.red() == color.green() == color.blue(), (type(widget).__name__, color.name())


@pytest.mark.parametrize("root_type,name,style", [
    (QFrame, "settingsPanel", SETTINGS_STYLE),
    (QWidget, "personalProfilePage", PROFILE_STYLE),
], ids=["settings", "profile"])
def test_original_shared_controls_keep_neutral_borders_in_native_states(qt, root_type, name, style):
    root = root_type()
    root.setObjectName(name)
    root.setStyleSheet(style)
    layout = QVBoxLayout(root)
    line, number, text = QLineEdit("Example"), CompactNumberInput(), QTextEdit("Example")
    selector = ScrollSafeComboBox()
    selector.addItems(["First", "Second"])
    items = QListWidget()
    items.addItems(["First", "Second"])
    button = QPushButton("Apply")
    checkbox, radio, switch = QCheckBox("Consent"), QRadioButton("Policy"), NotificationSwitch()
    for widget in (line, number, text, selector, items, button, checkbox, radio, switch):
        layout.addWidget(widget)
    root.resize(380, 600)
    root.show()
    root.activateWindow()
    QTest.qWait(20)
    try:
        for widget in (line, number, text, selector, items, button):
            root.setFocus()
            QTest.mouseMove(root, QPoint(1, 1))
            qt.processEvents()
            assert_neutral_border(widget)
            widget.setFocus()
            QTest.mouseMove(widget, widget.rect().center())
            qt.processEvents()
            assert widget.hasFocus()
            assert_neutral_border(widget)
        QTest.mousePress(button, Qt.MouseButton.LeftButton)
        qt.processEvents()
        assert_neutral_border(button)
        QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
        items.setCurrentRow(0)
        items.setFocus()
        qt.processEvents()
        assert_no_cyan_border(items)
        row = items.visualItemRect(items.item(0)).translated(items.viewport().pos())
        assert_no_cyan_border(items, row)
        selector.showPopup()
        qt.processEvents()
        assert_no_cyan_border(selector.view())
        selector.hidePopup()
        for widget in (checkbox, radio, switch):
            option = QStyleOptionButton()
            widget.initStyleOption(option)
            element = QStyle.SubElement.SE_RadioButtonIndicator if widget is radio else QStyle.SubElement.SE_CheckBoxIndicator
            indicator = widget.rect() if widget is switch else widget.style().subElementRect(element, option, widget)
            widget.setFocus()
            QTest.mouseMove(widget, QPoint(8, widget.height() // 2))
            qt.processEvents()
            assert_no_cyan_border(widget, indicator)
            QTest.keyClick(widget, Qt.Key.Key_Space)
            assert widget.isChecked()
            QTest.qWait(150)
            if widget is switch:
                # The enabled track is intentionally blue; focus must not add
                # a separate native selection outline to that custom painting.
                widget._slide.setCurrentTime(widget._slide.duration())
                qt.processEvents()
                focused = widget.grab().toImage()
                widget.clearFocus()
                qt.processEvents()
                assert widget.grab().toImage() == focused
            else:
                assert_no_cyan_border(widget, indicator)
            widget.setEnabled(False)
            qt.processEvents()
            if widget is not switch:
                assert_no_cyan_border(widget, indicator)
    finally:
        root.close()
        qt.processEvents()
