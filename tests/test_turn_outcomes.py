"""Durable settled-call and stopped-turn acceptance with real temporary edits."""
from copy import deepcopy
import hashlib
import json
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore, TurnHistoryError
from app.execution.audit import CallLifecycleState
from app.inference.completion import CompletionMetadata
from app.inference.engine import InferenceUnavailable
from app.inference.protocol import (ModelCapabilityCall, ModelResponse, ModelProtocolFailureCode,
    model_capability_calls_message, model_capability_result_message, native_chat_messages)
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.settings.agent import AgentFeatureConfig, AgentRuntimeLimits
from tests.test_agent_runtime import ScriptedModel, build_runtime, capability_call, run, BatchEchoCapability


def edit_call(target):
    return ModelResponse.calls((ModelCapabilityCall(provider_call_id="call_0",
        capability="filesystem.edit_text", arguments={"path": str(target), "old_text": "old", "new_text": "new"}),))


def edit_service(tmp_path, responses):
    portable = tmp_path / "portable"
    portable.mkdir(exist_ok=True)
    model = ScriptedModel(responses)
    runtime = build_agent_runtime(model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_edit_text_enabled=True),
        portable_root=portable, state_directory=portable / "state")
    store = ConversationStore(portable / "conversation.json")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=portable)
    approvals = []
    def approve(record):
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    return service, approvals


@pytest.mark.skipif(os.name != "nt", reason="Windows approved host edit")
@pytest.mark.parametrize("restart", [False, True])
def test_approved_edit_then_model_failure_is_known_to_next_turn_without_replay(tmp_path, restart):
    target = tmp_path / "note.txt"
    target.write_bytes(b"old\r\nkeep\r\n")
    service, approvals = edit_service(tmp_path, [edit_call(target), InferenceUnavailable("provider disconnected"),
                                               ModelResponse.text("The edit already succeeded.")])
    try:
        with pytest.raises(RuntimeError, match="provider disconnected"):
            service.run("Edit the text file")
        assert target.read_bytes() == b"new\r\nkeep\r\n"
        assert len(approvals) == 1 and service.approval_status(approvals[0].approval_id) == "consumed"
        turn = service.store.turns()[0]
        assert turn.outcome.status == AgentRunStatus.MODEL_UNAVAILABLE
        assert len(turn.settled_calls) == 1 and turn.settled_calls[0].result.success
        assert turn.settled_calls[0].result.output["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert service.agent_runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED
        session_id = service.store.session_id
        if restart:
            service.shutdown()
            assert json.loads(service.store.path.read_text())["session_status"] == "closed"
            service, resumed_approvals = edit_service(tmp_path, [ModelResponse.text("The edit already succeeded.")])
            assert service.store.session_id == session_id
            assert not service.inference.requests  # Restoration never resumes a stopped turn.
        service.run("What happened to the text file?")
        transcript = service.inference.requests[-1]
        results = [item for item in transcript if item["role"] == "capability"]
        assert len(results) == 1 and results[0]["result"]["success"]
        assert results[0]["result"]["output"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert any("model_unavailable" in item.get("content", "") for item in transcript)
        assert len(service.agent_runtime.executor.journal.records) == 1
        assert target.read_bytes() == b"new\r\nkeep\r\n"
        assert len(approvals) == 1
        if restart:
            assert resumed_approvals == []
        assert [turn.turn_id for turn in service.store.turns()] == ["turn-1", "turn-2"]
    finally:
        service.shutdown()


@pytest.mark.parametrize("later, expected", [
    (InferenceUnavailable("offline"), AgentRunStatus.MODEL_UNAVAILABLE),
    (RuntimeError("model failure"), AgentRunStatus.INTERNAL_FAILURE),
    (ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED, "cut off"), AgentRunStatus.INCOMPLETE),
])
def test_runtime_retains_settled_result_on_later_model_stop(tmp_path, later, expected):
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [capability_call(1), later])
    observed = []
    try:
        result = runtime.run([{"role": "user", "content": "Run a call"}], session_id="session", turn_id="turn",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), settled_observer=observed.append)
        assert result.status == expected and len(result.settled_calls) == len(observed) == 1
        assert result.settled_calls[0].result.success and capability.values == ["hello"]
        assert journal.records[0].state == CallLifecycleState.COMPLETED
    finally:
        runtime.shutdown()


def test_step_limit_preserves_the_settled_call(tmp_path):
    runtime, _, _, _, _ = build_runtime(tmp_path, [capability_call(1)], limits=AgentRuntimeLimits(max_steps=1))
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.STEP_LIMIT and result.settled_calls[0].result.success
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("denied", [False, True])
def test_rejected_calls_remain_settled_when_the_next_model_step_fails(tmp_path, denied):
    from app.security.permissions import PermissionDecision
    call = capability_call(1) if denied else capability_call(1, arguments={"wrong": "value"})
    runtime, _, capability, _, _ = build_runtime(tmp_path, [call, InferenceUnavailable("offline")],
        decision=PermissionDecision.DENY if denied else PermissionDecision.ALLOW)
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.MODEL_UNAVAILABLE and len(result.settled_calls) == 1
        assert not result.settled_calls[0].result.success and not capability.values
        assert result.settled_calls[0].result.error.code.value == ("permission_denied" if denied else "invalid_arguments")
    finally:
        runtime.shutdown()


def test_cancellation_after_a_settled_call_retains_the_success(tmp_path):
    source = CancellationSource()
    runtime, model, capability, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("late")])
    model.before_request[1] = lambda *args: source.cancel("stop later model step")
    try:
        result = run(runtime, tmp_path, cancellation=source.token)
        assert result.status == AgentRunStatus.CANCELLED and len(result.settled_calls) == 1
        assert result.settled_calls[0].result.success and capability.values == ["hello"]
    finally:
        runtime.shutdown()


def test_later_batch_failure_cannot_discard_the_first_settled_call(tmp_path, monkeypatch):
    from app.agent.runtime import _CallOutcome
    calls = tuple(capability_call(index, value=str(index)).capability_calls[0] for index in (1, 2, 3))
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [ModelResponse.calls(calls)],
                                                         capability=BatchEchoCapability())
    original = runtime._process_call
    def process(call, **kwargs):
        if call.arguments["value"] == "2":
            return _CallOutcome(stop_status=AgentRunStatus.INTERNAL_FAILURE, stop_message="second call stopped")
        return original(call, **kwargs)
    monkeypatch.setattr(runtime, "_process_call", process)
    observed = []
    try:
        result = runtime.run([{"role": "user", "content": "Run a batch"}], session_id="session", turn_id="turn",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            result_observer=lambda calls, results: observed.extend(results))
        assert result.status == AgentRunStatus.INTERNAL_FAILURE
        assert capability.values == ["1"] and len(journal.records) == 1
        assert result.settled_calls[0].result.success and len(observed) == 2
        assert not result.settled_calls[1].result.success
        assert len(result.settled_calls) == 2  # Third call was never started or invented.
    finally:
        runtime.shutdown()


def test_observer_failure_stops_continuation_but_result_remains_in_terminal_outcome(tmp_path):
    runtime, model, capability, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("unused")])
    def unavailable(settled):
        raise OSError("history unavailable")
    try:
        result = runtime.run([{"role": "user", "content": "Run a call"}], session_id="session", turn_id="turn",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), settled_observer=unavailable)
        assert result.status == AgentRunStatus.INTERNAL_FAILURE and result.settled_calls[0].result.success
        assert len(model.requests) == 1 and capability.values == ["hello"]
    finally:
        runtime.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows approved host edit")
def test_history_write_gap_recovers_journal_success_and_never_replays_edit(tmp_path, monkeypatch):
    target = tmp_path / "note.txt"
    target.write_bytes(b"old")
    service, approvals = edit_service(tmp_path, [edit_call(target), ModelResponse.text("unused")])
    original_save = service.store._store.save
    def fail_save(value):
        raise PermissionError("injected history write failure")
    service.inference.before_request[0] = lambda *args: monkeypatch.setattr(service.store._store, "save", fail_save)
    try:
        with pytest.raises(RuntimeError, match="retained durably"):
            service.run("Edit the text file")
        assert target.read_bytes() == b"new" and len(approvals) == 1
        assert any(item.get("result", {}).get("success") for item in service._agent_history)
        with pytest.raises(TurnHistoryError, match="retained safely"):
            service.run("Try again")
        assert len(service.inference.requests) == 1
        monkeypatch.setattr(service.store._store, "save", original_save)
        service.shutdown()
        service, resumed_approvals = edit_service(tmp_path, [ModelResponse.text("The recovered edit succeeded.")])
        turn = service.store.turns()[0]
        assert turn.outcome.status == AgentRunStatus.INTERNAL_FAILURE
        assert not turn.settled_calls and turn.recovered_calls[0].state == "completed"
        assert turn.recovered_calls[0].result_success is True
        assert not service.inference.requests
        service.run("What happened to the edit?")
        assert any("state completed, success True" in item.get("content", "")
                   for item in service.inference.requests[0])
        assert resumed_approvals == [] and target.read_bytes() == b"new"
        assert len(service.agent_runtime.executor.journal.records) == 1
    finally:
        service.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows approved host edit")
def test_unknown_mutation_is_retained_and_blocks_next_turn_and_restart(tmp_path, monkeypatch):
    import app.capabilities.filesystem_edit_text as editor
    target = tmp_path / "note.txt"
    target.write_bytes(b"old")
    native_write = editor.atomic_write_text_file
    def unknown(*args, **kwargs):
        native_write(*args, **kwargs)
        raise RuntimeError("verification interrupted after replacement")
    monkeypatch.setattr(editor, "atomic_write_text_file", unknown)
    service, approvals = edit_service(tmp_path, [edit_call(target), edit_call(target)])
    try:
        with pytest.raises(RuntimeError, match="(?i)review"):
            service.run("Edit the text file")
        turn = service.store.turns()[0]
        assert turn.settled_calls[0].result.error.code.value == "outcome_unknown"
        assert service.agent_runtime.executor.journal.review_required
        assert target.read_bytes() == b"new"
        with pytest.raises(RuntimeError, match="review"):
            service.run("Try the edit again")
        assert len(service.inference.requests) == len(approvals) == 1
        service.shutdown()
        service, resumed_approvals = edit_service(tmp_path, [edit_call(target)])
        assert not service.inference.requests
        assert service.store.turns()[0].settled_calls[0].result.error.code.value == "outcome_unknown"
        with pytest.raises(RuntimeError, match="review"):
            service.run("Try the edit again")
        assert not service.inference.requests and resumed_approvals == []
        assert target.read_bytes() == b"new" and len(service.agent_runtime.executor.journal.records) == 1
        service.new_session()
        with pytest.raises(RuntimeError, match="review"):
            service.run("Try the edit after resetting the conversation")
        assert not service.inference.requests and resumed_approvals == []
        assert service.agent_runtime.executor.journal.review_required
    finally:
        service.shutdown()


def test_scoped_provider_id_reuse_translates_to_distinct_stable_native_ids():
    from tests.test_inference_protocol import definition, neutral_call
    call = ModelCapabilityCall.model_validate(neutral_call())
    result = {"success": True}
    history = []
    for scope in ("session.turn-1.message-1", "session.turn-1.message-2", "session.turn-2.message-1"):
        history += [model_capability_calls_message((call,), provider_message_id=scope),
                    model_capability_result_message(call, result, provider_message_id=scope)]
    native = native_chat_messages(history, (definition(),))
    ids = [message["tool_call_id"] for message in native if message["role"] == "tool"]
    assert len(ids) == len(set(ids)) == 3
    assert native == native_chat_messages(json.loads(json.dumps(history)), (definition(),))
    with pytest.raises(ValueError, match="duplicate"):
        native_chat_messages(history + history[:2], (definition(),))
    mismatched = deepcopy(history[:2])
    mismatched[1]["provider_message_id"] = "wrong-message"
    with pytest.raises(ValueError, match="match"):
        native_chat_messages(mismatched, (definition(),))


def test_reused_provider_id_across_service_turns_has_durable_message_scopes(tmp_path):
    from tests.test_phase8_filesystem_stat import ScriptedStatModel, stat_call, build_service
    model = ScriptedStatModel([stat_call("one.txt"), ModelResponse.text("first"),
                               stat_call("two.txt"), ModelResponse.text("second")])
    service, runtime, store, root = build_service(tmp_path, model)
    (root / "one.txt").write_text("one")
    (root / "two.txt").write_text("two")
    try:
        service.run("Inspect one.txt")
        service.run("Inspect two.txt")
        assert len(runtime.executor.journal.records) == 2
        calls = [turn.settled_calls[0] for turn in store.turns()]
        assert calls[0].call.provider_call_id == calls[1].call.provider_call_id
        assert calls[0].provider_message_id != calls[1].provider_message_id
        native = native_chat_messages(model.requests[-1], model.definitions[-1])
        ids = [item["tool_call_id"] for item in native if item["role"] == "tool"]
        assert len(ids) == len(set(ids)) == 2
        reopened = ConversationStore(store.path)
        assert reopened.turns()[1].settled_calls[0].provider_message_id == calls[1].provider_message_id
    finally:
        service.shutdown()


@pytest.mark.parametrize("failure, expected", [(RuntimeError("chat failed"), AgentRunStatus.INTERNAL_FAILURE),
                                             (TaskCancelled("stopped"), AgentRunStatus.CANCELLED)])
def test_chat_stopped_turn_is_durable_and_visible_to_next_turn(tmp_path, failure, expected):
    from tests.test_conversation import RecordingInference
    class Model(RecordingInference):
        def respond(self, messages):
            self.calls.append(messages)
            if len(self.calls) == 1:
                raise failure
            return "Next reply"
    service = ConversationService(Model(), ConversationStore(tmp_path / "conversation.json"))
    try:
        if isinstance(failure, TaskCancelled):
            assert service.run("Hello") == "The response was stopped."
        else:
            with pytest.raises(RuntimeError, match="chat failed"):
                service.run("Hello")
        assert ConversationStore(service.store.path).turns()[0].outcome.status == expected
        service.run("Continue")
        assert any(expected.value in item["content"] for item in service.inference.calls[1])
    finally:
        service.shutdown()


@pytest.mark.parametrize("content", ['{"turns": ["corrupted"]}', 'null', '0', '[]', '{}'])
def test_corrupted_durable_history_is_not_silently_replaced(tmp_path, content):
    path = tmp_path / "conversation.json"
    path.write_text(content)
    with pytest.raises(TurnHistoryError, match="preserved"):
        ConversationStore(path)
    assert path.read_text() == content


@pytest.mark.skipif(os.name != "nt", reason="Windows approved host edit")
def test_restore_with_tools_disabled_keeps_edit_outcome_as_plain_context(tmp_path):
    from tests.test_conversation import RecordingInference
    target = tmp_path / "note.txt"
    target.write_bytes(b"old")
    service, _ = edit_service(tmp_path, [edit_call(target), InferenceUnavailable("offline")])
    try:
        with pytest.raises(RuntimeError, match="offline"):
            service.run("Edit the text file")
        service.shutdown()
        model = RecordingInference()
        resumed = ConversationService(model, ConversationStore(service.store.path))
        try:
            resumed.run("What happened to the file?")
            assert all(set(message) == {"role", "content"} for message in model.calls[0])
            assert any("Retained settled call: filesystem.edit_text" in message["content"]
                       and "success True" in message["content"] for message in model.calls[0])
            assert target.read_bytes() == b"new"
        finally:
            resumed.shutdown()
    finally:
        service.shutdown()


def test_ui_restores_partial_and_stopped_history_without_starting_work(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    from app.inference.completion import CompletionText
    from tests.test_conversation import RecordingInference
    app = QApplication.instance() or QApplication([])
    model = RecordingInference(CompletionText("```python\nprint(", CompletionMetadata(finish_reason="length")))
    service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"))
    service.run("Generate code")
    service.shutdown()
    resumed_model = RecordingInference()
    resumed = ConversationService(resumed_model, ConversationStore(service.store.path))
    window = MainWindow(resumed, "test")
    try:
        assert len(window.chat._messages) == 2 and not resumed_model.calls
        assert not window._intro_active
        message = window.chat._messages[-1]
        assert message.completion.incomplete and message._code_blocks[0].incomplete
        assert "Incomplete" in message.completion_label.text()
    finally:
        window.close()
        resumed.shutdown()
