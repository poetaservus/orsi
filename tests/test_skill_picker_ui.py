"""Keyboard/mouse composition and real worker handoff with synthetic inference."""
import os
import json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from tests.test_skill_activation import make_service, skill_payload


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows skill registry")


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, qt_app):
    service, model = make_service(tmp_path)
    service.automatic_skills_enabled = False
    ui = MainWindow(service, "TEST")
    ui.show()
    qt_app.processEvents()
    ui.input.setFocus()
    yield ui, service, model
    # Always let a synthetic worker finish before destroying the window/thread.
    for _ in range(200):
        qt_app.processEvents()
        if ui.thread is None:
            break
        QTest.qWait(10)
    assert ui.thread is None
    ui.close()


def type_command(ui, query=""):
    ui.input.clear()
    QTest.keyClicks(ui.input, "/skill" + query)
    QApplication.processEvents()


def wait_finished(ui):
    for _ in range(200):
        QApplication.processEvents()
        if ui.thread is None:
            return
        QTest.qWait(10)
    pytest.fail("Synthetic conversation worker did not finish")


def test_typing_trigger_opens_cached_catalog_and_enter_attaches_without_sending(window):
    ui, _, model = window
    type_command(ui)
    picker = ui.skill_picker
    assert picker.popup.isVisible() and picker.items.count() == 2
    QTest.keyClick(ui.input, Qt.Key.Key_Down)
    assert picker.items.currentItem().data(Qt.ItemDataRole.UserRole) == "style"
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    assert picker.selected_name == "style" and picker.chip.isVisible()
    assert ui.input.toPlainText() == "" and ui.thread is None and not model.requests
    assert not picker.popup.isVisible()
    assert "Applies to this message" in picker.chip.toolTip()


def test_search_mouse_selection_and_chip_removal_preserve_prompt(window):
    ui, _, _ = window
    ui.input.setPlainText("Explain sorting /skill sty")
    ui.input.moveCursor(QTextCursor.MoveOperation.End)
    picker = ui.skill_picker
    assert picker.items.count() == 1
    QTest.mouseClick(picker.items.viewport(), Qt.MouseButton.LeftButton,
                     pos=picker.items.visualItemRect(picker.items.item(0)).center())
    assert picker.selected_name == "style"
    assert ui.input.toPlainText() == "Explain sorting "
    picker.chip.click()
    assert picker.selected_name is None and ui.input.toPlainText() == "Explain sorting "


def test_escape_no_matches_and_shift_enter_do_not_send(window):
    ui, _, model = window
    type_command(ui, " no-such-skill")
    assert ui.skill_picker.empty.text() == "No matching skills"
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    assert ui.thread is None and not model.requests and ui.skill_picker.selected_name is None
    QTest.keyClick(ui.input, Qt.Key.Key_Escape)
    assert not ui.skill_picker.popup.isVisible()
    type_command(ui)
    QTest.keyClick(ui.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert ui.input.toPlainText() == "/skill\n" and not model.requests


def test_send_button_chooses_skill_then_only_submits_a_real_prompt(window):
    ui, service, model = window
    type_command(ui, " sty")
    # Real mouse focus moves before clicked; calling .click() misses that order.
    QTest.mouseClick(ui.send, Qt.MouseButton.LeftButton)
    assert ui.skill_picker.selected_name == "style" and not model.requests
    ui.send.click()
    assert not model.requests and ui.skill_picker.selected_name == "style"
    QTest.keyClicks(ui.input, "First prompt")
    ui.send.click()
    assert ui.skill_picker.selected_name is None and ui.skill_picker.chip.isHidden()
    wait_finished(ui)
    assert skill_payload(model.requests[0][0])["name"] == "style"
    assert model.requests[0][0][-1]["content"] == "First prompt"
    assert service.active_skill is None
    ui.input.setPlainText("Next prompt")
    ui.send.click()
    wait_finished(ui)
    assert "\nACTIVE SKILL\n" not in model.requests[-1][0][0]["content"]


def test_backspace_new_session_and_busy_state_clear_or_hide_pending_selection(window):
    ui, _, _ = window
    type_command(ui, " sty")
    QTest.keyClick(ui.input, Qt.Key.Key_Tab)
    QTest.keyClick(ui.input, Qt.Key.Key_Backspace)
    assert ui.skill_picker.selected_name is None
    type_command(ui, " sty")
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    ui.input.setPlainText("Keep text")
    ui.create_new_session()
    assert ui.skill_picker.selected_name is None and ui.input.toPlainText() == ""
    type_command(ui)
    ui._set_busy(True)
    assert not ui.skill_picker.popup.isVisible() and not ui.skill_picker.chip.isEnabled()
    ui._set_busy(False)


def test_unicode_prefix_and_text_after_cursor_are_preserved(window):
    ui, _, _ = window
    ui.input.setPlainText("🎨 Please /skill sty\nremaining text")
    cursor = ui.input.textCursor()
    cursor.setPosition(len("🎨 Please /skill sty".encode("utf-16-le")) // 2)
    ui.input.setTextCursor(cursor)
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    assert ui.skill_picker.selected_name == "style"
    assert ui.input.toPlainText() == "🎨 Please \nremaining text"


def test_empty_catalog_and_literal_slash_words_do_not_start_inference(qt_app):
    ui = MainWindow(None, "TEST")
    ui.show()
    qt_app.processEvents()
    try:
        type_command(ui)
        assert ui.skill_picker.popup.isVisible() and ui.skill_picker.empty.text() == "No skills installed"
        QTest.keyClick(ui.input, Qt.Key.Key_Return)
        assert ui.thread is None
        QTest.mouseClick(ui.send, Qt.MouseButton.LeftButton)
        assert ui.thread is None and ui.input.hasFocus()
        ui.input.setPlainText("/skills")
        assert not ui.skill_picker.popup.isVisible()
        ui.input.setPlainText("https://example.com/skill")
        assert not ui.skill_picker.popup.isVisible()
    finally:
        ui.close()


def test_model_failure_clears_chip_and_skill_without_sticking_busy_controls(window):
    ui, service, model = window
    original = model.respond
    def fail(messages):
        raise RuntimeError("Synthetic failure")
    model.respond = fail
    type_command(ui, " sty")
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    ui.input.setPlainText("Prompt")
    ui.send.click()
    wait_finished(ui)
    assert service.active_skill is None and ui.skill_picker.selected_name is None
    assert ui.input.isEnabled() and ui.send.isEnabled() and ui.new_session_button.isEnabled()
    model.respond = original
    ui.input.setPlainText("Follow-up")
    ui.send.click()
    wait_finished(ui)
    assert "\nACTIVE SKILL\n" not in model.requests[-1][0][0]["content"]


def test_plain_send_remains_compatible_with_legacy_service_signature(qt_app):
    calls = []
    class Service:
        def run(self, message, activity):
            calls.append(message)
            return "Reply"
    ui = MainWindow(Service(), "TEST")
    ui.show()
    qt_app.processEvents()
    try:
        ui.input.setPlainText("Ordinary prompt")
        QTest.keyClick(ui.input, Qt.Key.Key_Return)
        wait_finished(ui)
        assert calls == ["Ordinary prompt"] and ui.skill_picker.chip.isHidden()
    finally:
        ui.close()


def test_metadata_is_plain_bounded_display_but_keeps_exact_identifier(window, tmp_path):
    ui, service, model = window
    name = "odd & <img src='x'> " + "x" * 300
    folder = tmp_path / "skills/odd-folder"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nname: " + json.dumps(name) +
        "\ndescription: " + json.dumps("</qt><img src='private'> " + "y" * 600) +
        "\n---\nSECRET-BODY", encoding="utf-8")
    service.skill_registry.reload()
    type_command(ui, " odd")
    item = ui.skill_picker.items.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == name and "SECRET-BODY" not in item.text()
    assert "<img" not in item.toolTip() and "&lt;img" in item.toolTip()
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    assert ui.skill_picker.selected_name == name and "<img" not in ui.skill_picker.chip.toolTip()
    assert "&&" in ui.skill_picker.chip.text()
    assert len(ui.skill_picker.chip.accessibleName()) < 150 and not model.requests


def test_removed_selected_skill_fails_without_silent_routing_or_stuck_input(window, tmp_path):
    ui, service, model = window
    type_command(ui, " sty")
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    (tmp_path / "skills/style/SKILL.md").unlink()
    service.skill_registry.reload()
    ui.input.setPlainText("Prompt")
    ui.send.click()
    wait_finished(ui)
    assert not model.requests and service.active_skill is None
    assert ui.skill_picker.selected_name is None and ui.input.isEnabled()


def test_replacing_chip_and_large_multiline_paste_keeps_one_exact_attachment(window):
    ui, _, model = window
    type_command(ui, " sty")
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    type_command(ui, " oth")
    QTest.keyClick(ui.input, Qt.Key.Key_Return)
    assert ui.skill_picker.selected_name == "other"
    assert len(ui.composer.findChildren(type(ui.skill_picker.chip), "skillChip")) == 1
    prompt = ("Keep every pasted line.\n" * 3000).rstrip()
    ui.input.setPlainText(prompt)
    assert ui.input.toPlainText() == prompt and ui.skill_picker.selected_name == "other"
    ui.skill_picker.chip.click()
    assert ui.input.toPlainText() == prompt and not model.requests
