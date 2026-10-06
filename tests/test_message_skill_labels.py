"""Skill captions follow admitted requests, survive reopen, and stay out of prompts/copy."""
import os
from threading import Event
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.conversation.store import ConversationStore
from app.runtime.skills import SkillActivationError
from app.ui.main_window import MainWindow
from tests.test_skill_activation import make_service
from tests.test_skill_picker_ui import wait_finished
from tests.test_skill_selection import Recorder as RoutingRecorder, make_service as routing_service


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("agent", [False, True])
def test_usage_is_saved_per_user_message_and_reopens_without_changing_model_history(tmp_path, app, agent):
    service, model = make_service(tmp_path, agent=agent)
    service.automatic_skills_enabled = False
    names = []
    try:
        service.run("First prompt", skill_name="style", skill_observer=names.append)
        service.run("Next prompt", skill_observer=names.append)
        assert names == ["style"] and service._skill_observer is None
        reopened = ConversationStore(service.store.path)
        assert [m.skill_name for m in reopened.visible_messages()] == ["style", None, None, None]
        assert reopened.messages() == service.store.messages()
        assert all(set(m) == {"role", "content"} for m in reopened.messages())
        assert model.requests[0][0][-1] == {"role": "user", "content": "First prompt"}
        window = MainWindow(SimpleNamespace(store=reopened), "fixture")
        window.show()
        QTest.qWait(40)
        try:
            first, _, second, _ = window.chat._message_bands
            assert first.message.from_user and second.message.from_user
            assert first.skill_label.text() == "/style" and first.skill_label.isVisible()
            assert not second.skill_label.isVisible()
            first.copy_message()
            assert QApplication.clipboard().text() == "First prompt"
        finally:
            window.close()
    finally:
        service.shutdown()


def test_caption_updates_while_worker_is_generating_and_does_not_leak_to_next_message(tmp_path, app):
    service, model = make_service(tmp_path)
    service.automatic_skills_enabled = False
    entered, release = Event(), Event()
    original = model.respond
    def blocking(messages):
        entered.set()
        release.wait(3)
        return original(messages)
    model.respond = blocking
    window = MainWindow(service, "fixture")
    window.show()
    try:
        window.input.setPlainText("/skill sty")
        window.input.moveCursor(window.input.textCursor().MoveOperation.End)
        QApplication.processEvents()
        QTest.keyClick(window.input, Qt.Key.Key_Return)
        assert window.skill_picker.selected_name == "style"
        window.input.setPlainText("Hi")
        window.submit()
        assert entered.wait(2)
        QTest.qWait(60)
        band = window.chat._message_bands[0]
        assert band.skill_label.text() == "/style" and band.skill_label.isVisible()
        caption = band.skill_label.mapTo(band, QPoint())
        bubble = band.message.mapTo(band, QPoint())
        assert abs(caption.x() - bubble.x()) <= 2 and caption.y() < bubble.y()
        release.set()
        wait_finished(window)
        assert window._active_user_message_band is None
        model.respond = original
        window.input.setPlainText("Next prompt")
        window.submit()
        wait_finished(window)
        assert not window.chat._message_bands[2].skill_label.isVisible()
        assert band.skill_label.isVisible()
    finally:
        release.set()
        wait_finished(window)
        window.close()


def test_rejected_skill_has_no_usage_caption_or_callback(tmp_path):
    service, model = make_service(tmp_path, body="oversized body " * 10000)
    service.automatic_skills_enabled = False
    names = []
    try:
        with pytest.raises(SkillActivationError):
            service.run("Prompt", skill_name="style", skill_observer=names.append)
        assert not names and not model.requests
        assert service.store.visible_messages()[0].skill_name is None
    finally:
        service.shutdown()


def test_automatic_choice_is_recorded_but_no_match_is_not(tmp_path):
    model = RoutingRecorder(['{"skill": "design-taste-frontend"}', '{"skill": null}'])
    service = routing_service(tmp_path, model)
    names = []
    try:
        service.run("Redesign the page", skill_observer=names.append)
        service.run("Ordinary question", skill_observer=names.append)
        users = [m for m in service.store.visible_messages() if m.role == "user"]
        assert names == ["design-taste-frontend"]
        assert [m.skill_name for m in users] == ["design-taste-frontend", None]
        assert len(model.router_requests) == 2 and len(model.answer_requests) == 2
    finally:
        service.shutdown()


def test_old_messages_load_without_labels_and_long_names_stay_plain_text(tmp_path, app):
    store = ConversationStore(tmp_path / "legacy.json")
    store.append("user", "An earlier message")
    store.append("assistant", "An earlier reply")
    reopened = ConversationStore(store.path)
    assert all(m.skill_name is None for m in reopened.visible_messages())
    window = MainWindow(SimpleNamespace(store=reopened), "fixture")
    window.resize(760, 600)
    window.show()
    try:
        assert not window.chat._message_bands[0].skill_label.isVisible()
        name = "<img src='private'>&" + "long-skill-name-" * 25
        band = window.chat.add_message("User", "Short", skill_name=name)
        QTest.qWait(40)
        assert band.skill_label.textFormat() == Qt.TextFormat.PlainText
        assert "<img" not in band.skill_label.toolTip() and "&lt;img" in band.skill_label.toolTip()
        assert band.skill_label.width() <= band.message.width()
        band.copy_message()
        assert QApplication.clipboard().text() == "Short"
    finally:
        window.close()


def test_observer_failure_does_not_interrupt_inference_or_persistence(tmp_path):
    service, _ = make_service(tmp_path)
    service.automatic_skills_enabled = False
    def fail(name):
        raise RuntimeError("Synthetic display failure")
    try:
        assert service.run("Prompt", skill_name="style", skill_observer=fail) == "reply"
        assert service.store.visible_messages()[0].skill_name == "style"
        assert service._skill_observer is None
    finally:
        service.shutdown()
