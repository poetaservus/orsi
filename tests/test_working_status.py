"""Working status reflects real stages and remains contained in the UI."""
import os
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.chat import ChatView, _elapsed_label
from app.ui.main_window import MainWindow
from app.agent.contracts import AgentRunStatus
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.protocol import ModelResponse
from app.security.permissions import PermissionDecision
from tests.test_agent_runtime import build_runtime, capability_call
from tests.test_skill_reference_conversations_v1 import conversation, request_reference
from tests.test_openai_streaming import make_engine, MESSAGES
from tests.test_openai_phase1 import response, sse_response


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("seconds,text", [(59, "59s"), (60, "1 m 0s"), (130, "2 m 10s"),
    (3730, "1 h 2 m 10s")])
def test_timer_formats_active_and_finished_durations(seconds, text):
    for prefix in ("Working", "Worked", "Stopped"):
        assert _elapsed_label(prefix, seconds) == f"{prefix} for {text}"


def test_status_order_alignment_updates_and_cleanup(app):
    view = ChatView()
    view.resize(720, 280)
    view.show()
    try:
        view.set_thinking(True)
        view.set_activity("Reading skill references…")
        QTest.qWait(80)
        timer, activity, animation = view.working_label, view.activity_label, view.thinking_dots
        positions = [widget.mapTo(view._thinking_row, QPoint()) for widget in (timer, activity, animation)]
        assert len({point.x() for point in positions}) == 1
        assert positions[0].y() + timer.height() < positions[1].y()
        assert positions[1].y() + activity.height() < positions[2].y()
        assert activity.text() == "Reading skill references…"
        assert activity.width() >= activity.fontMetrics().horizontalAdvance(activity.text())
        view.set_activity("Waiting for API capacity…")
        assert activity.text() == "Waiting for API capacity…"
        view.set_thinking(False)
        view.set_activity("late callback")
        assert not activity.text() and not animation.is_running
        view.set_thinking(True)
        assert activity.text() == "Preparing your request…"
        view.close()
        assert not animation.is_running and not view._response_timer.isActive()
    finally:
        view.close()


def test_worker_activity_reaches_the_label_above_animation(app):
    entered, release = Event(), Event()
    class Service:
        def run(self, message, activity):
            activity("Reading files…")
            entered.set()
            release.wait(3)
            return "Finished"
        def reported_context_tokens(self):
            return None
    window = MainWindow(Service(), "fixture")
    window.show()
    try:
        window.input.setPlainText("Synthetic UI status probe")
        window.submit()
        assert entered.wait(2)
        QTest.qWait(60)
        assert window.chat.activity_label.text() == "Reading files…"
        assert window.activity.text() == "Reading files…"
    finally:
        release.set()
        for _ in range(100):
            QTest.qWait(10)
            if window.thread is None:
                break
        assert window.thread is None and not window.chat.thinking_dots.is_running
        assert not window.chat.activity_label.text()
        window.close()


def test_tool_progress_occurs_before_execution_and_returns_to_model_stage(tmp_path):
    runtime, model, tool, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("Done")])
    stages = []
    original = tool.execute
    def observe_execution(*args, **kwargs):
        assert stages[-1] == "Running a tool…"
        return original(*args, **kwargs)
    tool.execute = observe_execution
    try:
        outcome = runtime.run([{"role": "user", "content": "Synthetic activity probe"}],
            session_id="fixture", turn_id="turn", portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            activity_observer=stages.append)
        assert outcome.status == AgentRunStatus.COMPLETED and tool.values == ["hello"]
        assert stages.index("Checking permissions…") < stages.index("Running a tool…")
        assert stages[-1] == "Thinking…"
    finally:
        runtime.shutdown()


def test_skill_reference_read_reports_the_real_stage_and_detaches_observer(tmp_path):
    stages = []
    with conversation(tmp_path, actions=[request_reference(), ModelResponse.text("Done")]) as (service, model, root):
        service.activate_skill("python-clamp")
        assert service.run("Synthetic skill activity probe", stages.append) == "Done"
        assert "Reading skill guidance…" in stages and "Reading skill references…" in stages
        assert stages[-1] == "Saving the conversation…"
        assert getattr(model, "_activity_observer", None) is None
        assert not any(str(root) in stage or "behavior.md" in stage for stage in stages)


@pytest.mark.parametrize("decision", [PermissionDecision.ASK, PermissionDecision.DENY])
def test_permission_status_does_not_claim_a_tool_is_executing(tmp_path, decision):
    runtime, _, tool, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("Done")],
        decision=decision)
    stages = []
    try:
        runtime.run([{"role": "user", "content": "Synthetic permission activity probe"}],
            session_id="fixture", turn_id="turn", portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            activity_observer=stages.append)
        assert not tool.values and "Running a tool…" not in stages
        if decision == PermissionDecision.ASK:
            assert stages[-1] == "Waiting for your approval…"
    finally:
        runtime.shutdown()


def test_failed_activity_observer_cannot_interrupt_execution(tmp_path, caplog):
    runtime, _, tool, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("Done")])
    def failed_observer(text):
        raise RuntimeError("Synthetic private observer error")
    try:
        outcome = runtime.run([{"role": "user", "content": "Synthetic observer failure probe"}],
            session_id="fixture", turn_id="turn", portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            activity_observer=failed_observer)
        assert outcome.status == AgentRunStatus.COMPLETED and tool.values == ["hello"]
        assert "An activity display update failed." in caplog.text
        assert "Synthetic private observer error" not in caplog.text
    finally:
        runtime.shutdown()


def test_pacing_status_changes_back_when_capacity_returns(make_engine):
    from tests.test_openai_rate_limits import Clock, headers
    from app.inference.openai_rate_limits import OpenAIRatePacer
    clock, stages, requests = Clock(), [], []
    def handle(request):
        requests.append(request)
        value = sse_response(response())
        if len(requests) == 1:
            value.headers.update(headers("tokens", 200_000, 0, "60s"))
        return value
    engine = make_engine(handle)
    engine._rate_pacer = OpenAIRatePacer(clock=clock, sleep=clock.sleep)
    engine.set_activity_observer(stages.append)
    engine.respond(MESSAGES)
    engine.respond(MESSAGES)
    wait = stages.index("Waiting for API capacity…")
    assert stages[wait + 1:wait + 3] == ["Thinking…", "Generating response…"]
    assert len(requests) == 2


def test_local_load_activity_does_not_load_a_model_in_cloud_mode():
    from tests.test_agent_runtime import ScriptedModel
    stages, loaded = [], []
    def create():
        loaded.append(True)
        return ScriptedModel([ModelResponse.text("Ready")])
    local = LazyInferenceEngine(create, context_length=8192)
    cloud = ScriptedModel([])
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    hybrid.set_activity_observer(stages.append)
    assert not loaded
    local._get_engine()
    assert stages == ["Loading local model…", "Thinking…"] and len(loaded) == 1
    hybrid.set_activity_observer(None)
    hybrid.close()
