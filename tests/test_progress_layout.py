"""Visible progress geometry through the actual worker-to-final-answer handoff."""
from threading import Event

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QTextCursor

from app.inference.protocol import ModelResponse
from app.conversation.questions import Question, QuestionBatch
from app.ui.main_window import MainWindow
from app.ui.markdown import MarkdownLabel
from tests.test_attachment_composer import wait_for
from tests.test_progress_narrative import app, task_service


def top(widget, view):
    return widget.mapTo(view.viewport(), QPoint()).y()


def gap(first, second, view):
    return top(second, view) - top(first, view) - first.height()


@pytest.mark.parametrize("stage", ["working", "completed", "failed"])
def test_details_and_counter_stay_compact_and_in_order_through_real_completion(app, tmp_path, monkeypatch, stage):
    monkeypatch.delenv("ORSI_ENABLE_SEMANTIC_PROGRESS", raising=False)
    service, model, _, _ = task_service(tmp_path)
    model.responses[-1] = (RuntimeError("Synthetic task stop") if stage == "failed" else
        ModelResponse.text("The files were inspected.\n\n" + "The detailed result stays below its task header. " * 12))
    held, release = Event(), Event()
    def hold(*_):
        held.set()
        release.wait(15)
    model.before_request[2] = hold
    window = MainWindow(service, "layout")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.resize(960, 760)
    window.show()
    try:
        window.input.setPlainText("Inspect the two supplied files")
        window.submit()
        wait_for(held.is_set)
        wait_for(lambda: window._intro_transition is None)
        view = window.chat
        timeline = view._active_timeline
        assert timeline is not None and view.technical_details.toPlainText()
        if stage != "working":
            release.set()
            wait_for(lambda: window.thread is None)
            counter = view._message_bands[-1].timing_label
        else:
            counter = view.working_label
        app.processEvents()
        for first, second in zip(timeline.entries, timeline.entries[1:]):
            if isinstance(first, MarkdownLabel):
                end = QTextCursor(first.document)
                end.movePosition(QTextCursor.MoveOperation.End)
                line_bottom = first.viewport().mapTo(view.viewport(), first.cursorRect(end).bottomLeft()).y()
                assert 0 <= top(second, view) - line_bottom <= 14
        assert 0 <= gap(timeline.entries[-1], view.technical_toggle, view) <= 12
        assert 0 <= gap(view.technical_toggle, counter, view) <= 12
        view._follow_tail = False
        view.verticalScrollBar().setValue(0)
        window.grab().save(str(tmp_path / f"{stage}-collapsed.png"))
        view.technical_toggle.click()
        app.processEvents()
        assert view.technical_details.isVisible()
        assert 0 <= gap(view.technical_details, counter, view) <= 12
        window.grab().save(str(tmp_path / f"{stage}-expanded.png"))
        window.resize(760, 650)
        app.processEvents()
        assert 0 <= gap(timeline.entries[-1], view.technical_toggle, view) <= 12
        assert 0 <= gap(view.technical_details, counter, view) <= 12
    finally:
        release.set()
        wait_for(lambda: window.thread is None)
        window.close()
        service.shutdown()


@pytest.mark.parametrize("question", [False, True])
def test_completed_details_remain_with_their_own_answer_during_the_next_request(app, tmp_path, monkeypatch, question):
    monkeypatch.delenv("ORSI_ENABLE_SEMANTIC_PROGRESS", raising=False)
    service, model, _, _ = task_service(tmp_path)
    if question:
        batch = QuestionBatch(version=1, questions=(Question(id="q", title="Which comparison?", kind="text"),))
        model.responses[-1] = ModelResponse.text("```orsi_questions\n" + batch.model_dump_json() + "\n```")
    window = MainWindow(service, "layout")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    held, release = Event(), Event()
    try:
        window.input.setPlainText("Inspect the two supplied files")
        window.submit()
        wait_for(lambda: window.thread is None)
        view = window.chat
        old_toggle, old_details = view.technical_toggle, view.technical_details
        old_counter = view._message_bands[-1].timing_label if not question else None
        old_logs = old_details.toPlainText()
        assert old_logs
        if old_counter is not None:
            assert 0 <= gap(old_toggle, old_counter, view) <= 12
        model.responses.append(ModelResponse.text("The follow-up answer."))
        def hold(*_):
            held.set()
            release.wait(15)
        model.before_request[4] = hold
        if question:
            window.submit(question_answer="Compare their sizes")
        else:
            window.input.setPlainText("Answer the follow-up")
            window.submit()
        wait_for(held.is_set)
        assert view.technical_details is not old_details
        assert old_details.toPlainText() == old_logs
        assert top(old_toggle, view) < top(view._message_bands[-1], view)
        assert abs(view.technical_toggle.mapTo(view.viewport(), QPoint()).x()
                   - old_toggle.mapTo(view.viewport(), QPoint()).x()) <= 2
        old_toggle.click()
        app.processEvents()
        assert old_details.isVisible()
        if old_counter is not None:
            assert 0 <= gap(old_details, old_counter, view) <= 12
        release.set()
        wait_for(lambda: window.thread is None)
        assert 0 <= gap(view.technical_toggle, view._message_bands[-1].timing_label, view) <= 12
        assert old_details.toPlainText() == old_logs
        view.clear_messages()
        app.processEvents()
        assert not view._narrative_rows and not view.technical_details.toPlainText()
        assert view._layout.count() == 2  # Only the hidden empty group and bottom stretch remain.
    finally:
        release.set()
        wait_for(lambda: window.thread is None)
        window.close()
        service.shutdown()
