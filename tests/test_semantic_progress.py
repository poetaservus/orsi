"""Essential presentation contracts through real service, worker and Qt delivery."""
import os
from threading import Event
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.questions import QuestionBatch
from app.conversation.questions import Question
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionMetadata, CompletionText
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.agent.bootstrap import build_agent_runtime
from app.settings.agent import AgentFeatureConfig
from app.runtime.cancellation import TaskCancelled
from app.runtime.semantic_progress import ProgressEvent, ProgressPhase as Phase, SemanticProgress, attention_event
from app.ui.main_window import MainWindow
from app.ui.worker import ConversationWorker
from tests.test_agent_runtime import ScriptedModel
from tests.test_attachment_composer import wait_for
from tests.test_conversation import RecordingInference


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_progress_is_sparse_correlated_and_never_reopens_a_finished_run():
    progress = SemanticProgress("task", "run")
    def advance(phase, now, task="task", run="run"):
        return progress.advance(ProgressEvent(task, run, phase), now=now)
    assert advance(Phase.PREPARE, 0) == Phase.PREPARE
    for second in range(1, 100):
        assert advance(Phase.PREPARE, second) is None
    assert advance(Phase.WORK, 101)
    assert advance(Phase.REVIEW, 102) is None
    assert progress.flush(now=112) is None
    assert progress.flush(now=113) == Phase.REVIEW  # Coalesced phase cannot stay stale indefinitely.
    assert advance(Phase.REVIEW, 120, task="other") is None
    assert advance(Phase.REVIEW, 120, run="old") is None
    assert advance(Phase.REVIEW, 120) is None
    progress.waiting = True
    assert advance(Phase.WORK, 140) is None
    progress.waiting = False
    assert advance(Phase.WORK, 160)  # A review can legitimately return to work.
    assert advance(Phase.FINALIZE, 1260)  # Long jobs never gain invented updates.
    assert progress.finish() and not progress.finish()
    assert advance(Phase.WORK, 1300) is None
    assert SemanticProgress("task", "new").advance(ProgressEvent("task", "new", Phase.WORK))


@pytest.mark.parametrize("status,reason,expected", [
    ("completed", None, "response"),
    ("incomplete", None, "error"),
    ("step_limit", None, "error"),
    ("internal_failure", None, "error"),
    ("cancelled", None, None),
    (None, "cancelled", None),
    ("completed", "length", "error"),
])
def test_attention_uses_outcomes_even_when_prose_claims_success(status, reason, expected):
    response = CompletionText("Everything is complete!", CompletionMetadata(finish_reason=reason))
    assert attention_event(response, status=status) == expected


@pytest.mark.parametrize("broken_observer", [False, True])
def test_service_phases_add_no_model_calls_and_observer_failure_cannot_stop_work(tmp_path, broken_observer):
    model = RecordingInference("The answer.")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"))
    phases = []
    def observe(phase):
        phases.append(phase)
        if broken_observer:
            raise RuntimeError("private observer error")
    try:
        assert service.run("Answer this request", progress_observer=observe) == "The answer."
        assert phases == [Phase.PREPARE, Phase.WORK, Phase.FINALIZE]
        assert len(model.calls) == 1 and service.turn_status == "completed"
        assert len(service.store.turns()) == 1
    finally:
        service.shutdown()


def test_worker_recognizes_retained_cancellation_without_cancellation_text_metadata(app, tmp_path):
    model = RecordingInference()
    def cancel(messages):
        raise TaskCancelled("Stopped by the user")
    model.respond = cancel
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"))
    worker = ConversationWorker(service, "Answer this request")
    answers = []
    worker.finished.connect(answers.append)
    try:
        worker.run()
        assert answers and service.turn_status == "cancelled" and worker.attention is None
        # A local control command has no retained task outcome of its own.
        next_worker = ConversationWorker(service, "/skill")
        next_worker.run()
        assert service.turn_status is None and next_worker.attention == "response"
    finally:
        service.shutdown()


def test_real_tool_success_followed_by_failed_completion_review_is_only_a_stop(app, tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("sample", encoding="utf-8")
    call = ModelResponse.calls((ModelCapabilityCall(provider_call_id="stat-1", capability="filesystem.stat",
        arguments={"path": str(target)}),))
    model = ScriptedModel([call, ModelResponse.text("Done."),
        RuntimeError("private provider error")], auto_review=False)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"),
        agent_runtime=runtime, portable_root=tmp_path)
    worker = ConversationWorker(service, "Run the requested task")
    phases, failed = [], []
    worker.progress.connect(phases.append)
    worker.failed.connect(failed.append)
    try:
        worker.run()
        assert service.store.turns()[0].settled_calls[0].result.success
        assert Phase.REVIEW in [event.phase for event in phases]
        assert failed and worker.attention == "error" and service.turn_status != "completed"
        assert len(model.requests) == 3
    finally:
        service.shutdown()


def test_question_alert_is_distinct_from_completion_and_resume_rearms_the_next_run(app, tmp_path, monkeypatch):
    batch = QuestionBatch(version=1, questions=(Question(id="q", title="Which private workbook?", kind="text"),))
    model = RecordingInference("Which private workbook?\n\n```orsi_questions\n" + batch.model_dump_json() + "\n```")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "test", semantic_progress_enabled=True)
    notifications = []
    monkeypatch.setattr(window.notifications, "notify", notifications.append)
    try:
        window.input.setPlainText("Prepare the dashboard")
        window.submit()
        wait_for(lambda: window.thread is None)
        assert notifications == ["question"] and window._question_panel is not None
        assert not window._progress_timer.isActive()
        window._sync_question_form()
        assert notifications == ["question"]
        model.reply = "The result is ready."
        window.submit(question_answer="Use the supplied workbook")
        wait_for(lambda: window.thread is None)
        assert notifications == ["question", "response"] and window._question_panel is None
        assert len(model.calls) == 2 and len(service.store.visible_messages()) == 4
        assert len(window.chat._messages) == 3  # The question itself lives in the composer.
    finally:
        window.close()
        service.shutdown()


def test_two_workers_keep_raw_details_separate_and_deliver_phases_on_gui_thread(app, monkeypatch):
    class Service:
        supports_progress_reporting = True
        def __init__(self):
            self.entered, self.release = Event(), Event()
        def run(self, message, activity, *, progress_observer):
            progress_observer(Phase.PREPARE)
            progress_observer(Phase.WORK)
            for index in range(105):
                activity(f"Reading <private-{message}-{index}>…")
            self.entered.set()
            self.release.wait(10)
            return "The result."
    class Window(MainWindow):
        def _display_progress(self, sentence):
            assert QThread.currentThread() == app.thread()
            super()._display_progress(sentence)
    services = [Service(), Service()]
    windows = [Window(service, "test", semantic_progress_enabled=True) for service in services]
    notifications = [[], []]
    try:
        for index, window in enumerate(windows):
            monkeypatch.setattr(window.notifications, "notify", notifications[index].append)
            window.input.setPlainText(str(index))
            window.submit()
            window._progress.min_interval = .03  # Exercise the actual coalescing timer without a long sleep.
        wait_for(lambda: all(service.entered.is_set() for service in services))
        wait_for(lambda: all(window.chat.activity_label.text() == "I'm working through the requested task." for window in windows))
        for index, window in enumerate(windows):
            assert not window._progress_timer.isActive()
            assert window.chat.activity_label.text() == "I'm working through the requested task."
            assert f"private-{index}-104" in window.chat.technical_details.toPlainText()
            assert f"private-{1-index}-104" not in window.chat.technical_details.toPlainText()
            assert window.chat.technical_details.document().blockCount() == 100
            assert window.chat.technical_details.isHidden()
            window._stream_preview("A proposed answer")
            assert window.chat.activity_label.text() == "I'm working through the requested task."
            window._receive_progress(ProgressEvent("other", "old", Phase.REVIEW))
            foreign = ConversationWorker(Service(), "late callback")
            foreign.activity.connect(window._set_working_activity, Qt.ConnectionType.QueuedConnection)
            foreign.finished.connect(window._worker_succeeded, Qt.ConnectionType.QueuedConnection)
            foreign.activity.emit("Foreign private activity")
            foreign.finished.emit("Foreign final response")
            app.processEvents()
            assert window.chat.activity_label.text() == "I'm working through the requested task."
            assert not window._progress.closed
            assert not notifications[index] and len(window.chat._messages) == 1
    finally:
        for service in services:
            service.release.set()
        wait_for(lambda: all(window.thread is None for window in windows))
        for index, window in enumerate(windows):
            assert notifications[index] == ["response"]
            window._worker_succeeded("Duplicate or late final")
            assert notifications[index] == ["response"] and len(window.chat._messages) == 2
            window.chat.technical_toggle.click()
            assert not window.chat.technical_details.isHidden()
            window.close()


def test_notifier_rejects_nonattention_events_before_audio_or_banner(app, monkeypatch):
    window = MainWindow(None, "test")
    manager = window.notifications
    manager.backend = Mock()
    monkeypatch.setattr(manager, "_needs_attention", lambda: True)
    monkeypatch.setattr(manager, "play_sound", Mock())
    try:
        for event in ("task_started", "phase_started", "retry_scheduled", "raw_tool_status", "task_cancelled"):
            manager.notify(event)
        manager.play_sound.assert_not_called()
        manager.backend.show_message.assert_not_called()
        manager.notify("question")
        manager.backend.show_message.assert_called_once_with(
            "O.R.S.I needs your input", "A task is waiting for your answer.")
    finally:
        window.close()
