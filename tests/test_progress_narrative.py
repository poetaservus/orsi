"""Chronological user-facing commentary uses real tool and completion boundaries."""
import os
from dataclasses import asdict
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.semantic_progress import NarrativeEvent, NarrativeItem, OperationKind
from app.security.host_access import HostReadScope
from app.settings.agent import AgentFeatureConfig
from app.ui.main_window import MainWindow
from app.ui.progress_timeline import ProgressTimeline, operation_label
from tests.test_agent_runtime import ScriptedModel
from tests.test_attachment_composer import wait_for


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def task_service(tmp_path):
    targets = [tmp_path / "first.txt", tmp_path / "second.txt"]
    for target in targets:
        target.write_text("private fixture content", encoding="utf-8")
    notes = ["I'll inspect the two supplied files, then compare their metadata.",
        "The first file is available. I'll check the second before reporting the comparison."]
    responses = [ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"stat-{index}",
        capability="filesystem.stat", arguments={"path": str(target)}),), assistant_text=note)
        for index, (target, note) in enumerate(zip(targets, notes), 1)]
    model = ScriptedModel([*responses, ModelResponse.text("Both files were inspected.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"),
        agent_runtime=runtime, portable_root=tmp_path)
    return service, model, runtime, notes


@pytest.mark.parametrize("broken_display", [False, True])
def test_real_service_reports_public_notes_before_tools_and_summaries_after_settlement(tmp_path, broken_display):
    service, model, runtime, notes = task_service(tmp_path)
    items, executions = [], []
    original = runtime.executor.execute
    def execute(*args, **kwargs):
        assert items[-1].text == notes[len(executions)]  # Before the actual operation.
        executions.append(True)
        return original(*args, **kwargs)
    runtime.executor.execute = execute
    def observe(item):
        items.append(item)
        if item.operation is not None:
            assert len(service.store.turns()[0].settled_calls) == len(executions)
            assert str(tmp_path) not in str(asdict(item)) and "private fixture" not in str(asdict(item))
        if broken_display:
            raise RuntimeError("display unavailable")
    try:
        assert service.run("Inspect the two supplied files", narrative_observer=observe) == "Both files were inspected."
        assert [item.text for item in items if item.text] == notes
        assert [item.operation for item in items if item.operation] == [OperationKind.INSPECT] * 2
        assert len(model.requests) == 4  # Two tool requests, final answer and existing completion review.
        assert service.turn_status == "completed"
        assert len(service.store.visible_messages()) == 2
        prompt = model.requests[0][0]["content"]
        assert "short public progress paragraph" in prompt and "never mix calls with assistant prose" not in prompt.lower()
        assert not any("goal_id" in item.text for item in items)  # Internal assessment is never progress.
    finally:
        service.shutdown()


@pytest.mark.parametrize("read_batches", [False, True])
def test_opt_in_prompt_keeps_existing_execution_guidance_and_fallback_schema(read_batches):
    plain = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, ("filesystem.stat",), allow_read_batches=read_batches)
    enabled = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, ("filesystem.stat",),
        progress_narrative=True, allow_read_batches=read_batches)
    assert "never mix calls with assistant prose" in plain.lower()
    assert "short public progress paragraph" not in plain
    assert "never mix calls with assistant prose" not in enabled.lower()
    assert "JSON fallback must still follow its exact schema" in enabled
    for policy in ("Never guess destructive arguments", "Preserve exact paths", "portable root"):
        assert policy in plain and policy in enabled


def test_timeline_groups_only_settled_operations_and_keeps_notes_readable_and_bounded(app):
    timeline = ProgressTimeline()
    try:
        timeline.append(NarrativeItem("start", "I'll inspect `sample.txt`, then check its formatting."))
        timeline.append(NarrativeItem("read", operation=OperationKind.READ))
        timeline.append(NarrativeItem("edit", operation=OperationKind.EDIT))
        timeline.append(NarrativeItem("command", operation=OperationKind.COMMAND))
        assert len(timeline.entries) == 2
        assert timeline.entries[0].plain_text() == "I'll inspect sample.txt, then check its formatting."
        assert timeline.entries[1].caption.text() == "Read files · Updated files · Ran commands"
        timeline.append(NarrativeItem("failed", operation=OperationKind.EDIT, success=False))
        assert "Tool attempt stopped" in timeline.entries[1].caption.text()
        assert operation_label(OperationKind.EDIT, False) != "Updated files"
        assert not timeline.append(NarrativeItem("command", operation=OperationKind.COMMAND))
        assert not timeline.append(NarrativeItem("empty", "  "))
        for index in range(70):
            timeline.append(NarrativeItem(f"note-{index}", f"Observed milestone {index}."))
        assert len(timeline.entries) == 40 and "69" in timeline.entries[-1].text()
        timeline.set_available_width(360)
        assert all(entry.width() <= 360 for entry in timeline.entries)
    finally:
        timeline.close()


def test_real_worker_timeline_survives_final_and_excludes_late_events_and_model_history(app, tmp_path, monkeypatch):
    monkeypatch.delenv("ORSI_ENABLE_SEMANTIC_PROGRESS", raising=False)
    service, model, runtime, notes = task_service(tmp_path)
    entered, release = Event(), Event()
    def hold(messages, capabilities):
        entered.set()
        release.wait(10)
    model.before_request[2] = hold
    window = MainWindow(service, "fixture")
    append = window.chat.append_narrative
    threads = []
    def append_on_gui(item):
        threads.append(QThread.currentThread())
        assert QThread.currentThread() == app.thread()
        append(item)
    monkeypatch.setattr(window.chat, "append_narrative", append_on_gui)
    notifications = []
    monkeypatch.setattr(window.notifications, "notify", notifications.append)
    window.show()
    try:
        window.input.setPlainText("Inspect the two supplied files")
        window.submit()
        wait_for(entered.is_set)
        timeline = window.chat._active_timeline
        assert timeline is not None and len(timeline.entries) == 4
        assert len(threads) == 4 and all(thread == app.thread() for thread in threads)
        assert timeline.entries[0].text() == notes[0] and timeline.entries[2].text() == notes[1]
        assert timeline.entries[1].caption.text() == "Inspected files"
        assert not notifications and len(service.store.visible_messages()) == 1
        window._receive_narrative(NarrativeEvent("foreign", "old", NarrativeItem("late", "Must stay hidden")))
        assert len(timeline.entries) == 4
        event = NarrativeEvent(window.worker.task_id, window.worker.run_id, NarrativeItem("late", "Must stay hidden"))
        release.set()
        wait_for(lambda: window.thread is None)
        window._receive_narrative(event)
        assert len(timeline.entries) == 4 and timeline.isVisible()
        assert notifications == ["response"]
        assert len(service.store.visible_messages()) == 2 and len(window.chat._messages) == 2
        assert len(model.requests) == 4
        window.chat.clear_messages()
        assert not window.chat._narrative_rows and window.chat._active_timeline is None
    finally:
        release.set()
        wait_for(lambda: window.thread is None)
        window.close()
        service.shutdown()
