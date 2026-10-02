"""Completion-state regressions from the provider boundary to visible UI."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionMetadata, CompletionText, TokenUsage, IncompleteResponseError
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.protocol import ModelResponse, ModelResponseKind, normalize_native_chat_completion
from app.inference.protocol import ModelProtocolFailureCode
from tests.test_inference_protocol import definition, message, native_call
from tests.test_agent_runtime import build_runtime, capability_call, run
from tests.test_cloud_inference import cloud_config
from tests.test_llama_server_inference import scripted_engine


PARTIAL = "```python\nclass Player:\n    def update(self):\n        "


def payload(content=PARTIAL, *, reason="length", calls=None):
    return {"choices": [{"finish_reason": reason, "message": message(content=content, tool_calls=calls)}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 64, "total_tokens": 94}}


def metadata(reason="length"):
    return CompletionMetadata.from_payload(payload(reason=reason))


@pytest.mark.parametrize("arguments", ['{"path":"unfinished"', '{"path":"ok"}', '{"path":"ok",}'])
@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_incomplete_tool_generation_never_reaches_argument_repair(monkeypatch, arguments, reason):
    def forbidden(*args):
        pytest.fail("Incomplete generation must stop before argument decoding/repair")
    monkeypatch.setattr("app.inference.protocol._decode_arguments", forbidden)
    response = normalize_native_chat_completion(payload(None, reason=reason,
        calls=[native_call(arguments=arguments)]), (definition(),))
    assert response.kind == ModelResponseKind.PROTOCOL_FAILURE and not response.capability_calls
    assert response.completion == metadata(reason)


def test_partial_text_and_usage_survive_native_normalization_without_whitespace_loss():
    response = normalize_native_chat_completion(payload(), ())
    assert response.assistant_text == response.partial_text == PARTIAL
    assert response.completion.finish_reason == "length" and response.completion.incomplete
    assert response.completion.usage == TokenUsage(input_tokens=30, output_tokens=64, total_tokens=94)


def test_mixed_truncated_generation_keeps_partial_prose_but_no_executable_calls():
    response = normalize_native_chat_completion(payload(PARTIAL, calls=[native_call()]), (definition(),))
    assert response.kind == ModelResponseKind.PROTOCOL_FAILURE
    assert response.partial_text == PARTIAL and not response.capability_calls


def test_partial_text_cannot_bypass_size_limits_with_padding():
    response = normalize_native_chat_completion(payload(" " * 1_000_001 + "partial"), ())
    assert response.kind == ModelResponseKind.PROTOCOL_FAILURE
    assert response.partial_text is None and response.completion.incomplete


@pytest.mark.parametrize("backend", ["server", "cpp", "cloud"])
def test_chat_adapters_and_lazy_hybrid_keep_completion_metadata(backend, monkeypatch):
    completion = payload()
    if backend == "server":
        engine, _ = scripted_engine([completion])
    elif backend == "cpp":
        from app.inference.llama_backend import LlamaCppInferenceEngine
        from app.settings.model import ModelConfig
        engine = object.__new__(LlamaCppInferenceEngine)
        engine.config = ModelConfig(model_path="unused.gguf")
        engine.model = SimpleNamespace(create_chat_completion=lambda **kwargs: completion)
    else:
        from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
        engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="test-only-placeholder")
        monkeypatch.setattr(engine, "_request_message", lambda *args, **kwargs:
                            (completion["choices"][0]["message"], completion))
    lazy = LazyInferenceEngine(lambda: engine, context_length=8192)
    inference = HybridInferenceEngine(local=lazy, cloud=None)
    result = inference.respond([{"role": "user", "content": "Generate code"}])
    assert result == PARTIAL and result.partial_text == PARTIAL
    assert result.completion == metadata()
    # Mock backends have no owned native process; avoid their real close methods.
    lazy._engine = None
    inference.close()


def test_cloud_does_not_discard_incomplete_tool_output_by_switching_provider(monkeypatch):
    from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
    engine = OpenAICompatibleInferenceEngine(cloud_config(fallback_models=["other/model"]),
                                             api_key="test-only-placeholder")
    requests = []
    def request(body, **kwargs):
        requests.append(body)
        return payload(PARTIAL, calls=[native_call()])
    monkeypatch.setattr(engine, "_request_completion", request)
    result = engine.respond_with_capabilities([{"role": "user", "content": "Inspect a file"}], (definition(),))
    assert result.completion == metadata() and result.partial_text == PARTIAL
    assert len(requests) == 1 and not result.capability_calls


def test_runtime_never_completes_length_ended_text_and_retains_usage(tmp_path):
    response = normalize_native_chat_completion(payload(), ())
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [response])
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE
        assert result.assistant_text is None and result.partial_text == PARTIAL
        assert result.completion == metadata() and result.completion_history == (metadata(),)
        assert not capability.values and not journal.records
    finally:
        runtime.shutdown()


def test_completed_contract_rejects_length_state():
    with pytest.raises(ValidationError):
        AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="partial", steps=1,
                       capability_calls=0, protocol_failures=0, completion=metadata())


def test_defensive_runtime_check_blocks_a_custom_adapter_incomplete_call(tmp_path):
    response = capability_call(1).model_copy(update={"completion": metadata()})
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [response])
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE and result.capability_calls == 0
        assert not capability.values and not journal.records
    finally:
        runtime.shutdown()


def test_incomplete_unsupported_response_cannot_trigger_fallback_retry(tmp_path):
    response = ModelResponse.failure(ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS,
        "Unsupported").model_copy(update={"completion": metadata(), "partial_text": PARTIAL})
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [response])
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE and len(model.requests) == 1
        assert result.partial_text == PARTIAL and not capability.values and not journal.records
    finally:
        runtime.shutdown()


def test_fallback_length_state_is_checked_before_constrained_json_repair(tmp_path, monkeypatch):
    from app.inference.engine import InferenceEngine
    class Model(InferenceEngine):
        def respond(self, messages):
            return CompletionText('{"tool":"test.echo","arguments":{"value":"hello"},"response":null}', metadata())
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=Model())
    monkeypatch.setattr("app.agent.runtime.decode_constrained_decision", lambda *args:
                        pytest.fail("Incomplete fallback must not reach repair"))
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE and result.partial_text.startswith('{"tool"')
        assert result.completion == metadata() and not capability.values and not journal.records
    finally:
        runtime.shutdown()


def test_partial_after_successful_tool_retains_trace_usage_and_persistent_state(tmp_path):
    from tests.test_phase8_filesystem_stat import ScriptedStatModel, stat_call, build_service
    first_metadata = metadata("tool_calls")
    response = normalize_native_chat_completion(payload(), ())
    model = ScriptedStatModel([stat_call("sample.txt").model_copy(update={"completion": first_metadata}), response])
    service, runtime, store, root = build_service(tmp_path, model)
    (root / "sample.txt").write_text("fixture")
    try:
        answer = service.run("Inspect sample.txt")
        assert answer == PARTIAL and answer.completion == metadata()
        assert answer.completion_history == (first_metadata, metadata())
        assert len(model.requests) == 2
        assert any(item.get("role") == "capability" for item in service._agent_history)
        persisted = json.loads(store.path.read_text())["messages"][-1]
        assert persisted["content"] == PARTIAL
        assert persisted["completion"]["finish_reason"] == "length"
        assert len(persisted["completion_history"]) == 2
        assert ConversationStore(store.path).messages()[-1]["content"] == PARTIAL
    finally:
        service.shutdown()


def test_plain_conversation_and_run_conversation_keep_partial_state(tmp_path):
    from app.inference.engine import InferenceEngine
    class Model(InferenceEngine):
        def respond(self, messages):
            return CompletionText(PARTIAL, metadata())
    model = Model()
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"))
    assert service.run("Generate code").completion == metadata()
    runtime, *_ = build_runtime(tmp_path / "runtime", [], model=model)
    try:
        result = runtime.run_conversation([{"role": "user", "content": "Generate code"}])
        assert result.status == AgentRunStatus.INCOMPLETE
        assert result.partial_text == PARTIAL and result.completion == metadata()
    finally:
        runtime.shutdown()
        service.shutdown()


@pytest.fixture
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize("content", [PARTIAL, "```python", "~~~~python\nprint('x')\n~~~\n"])
def test_unfinished_fence_renders_as_readonly_code_with_incomplete_indication(qt_app, content):
    from app.ui.chat import ChatView
    chat = ChatView()
    try:
        chat.add_message("Agent", CompletionText(content, metadata()), duration_seconds=1)
        item = chat._messages[-1]
        assert item.completion == metadata() and item.completion_label is not None
        assert "Incomplete" in item.completion_label.text()
        block = item._code_blocks[0]
        assert block.incomplete and block.editor.isReadOnly()
        expected = content.split("\n", 1)[1] if "\n" in content else ""
        assert block.code == expected
        block.copy_code()
        assert qt_app.clipboard().text() == expected
        assert chat._message_bands[-1].timing_label.text().startswith("Stopped")
    finally:
        chat.close()


def test_short_partial_reply_keeps_incomplete_notice_readable(qt_app):
    from PySide6.QtCore import QRect, Qt
    from app.ui.chat import ChatView
    from app.ui.main_window import _STYLE
    chat = ChatView()
    chat.setStyleSheet(_STYLE)
    try:
        chat.resize(900, 600)
        chat.add_message("Agent", CompletionText("x", metadata()))
        item = chat._messages[-1]
        label = item.completion_label
        assert label.width() > 200
        bounds = label.fontMetrics().boundingRect(
            QRect(0, 0, label.width(), 100_000), int(Qt.TextFlag.TextWordWrap), label.text())
        assert label.height() >= bounds.height()
        assert label.palette().color(label.foregroundRole()).name() == "#e9bd78"
    finally:
        chat.close()


@pytest.mark.parametrize("failure", [False, True])
def test_context_meter_failure_cannot_hide_response_or_lock_ui_controls(qt_app, failure):
    from PySide6.QtTest import QTest
    from app.ui.main_window import MainWindow
    class Service:
        fail_meter = False
        def estimated_context_tokens(self):
            if self.fail_meter:
                raise RuntimeError("tokenizer unavailable")
            return 0
        def run(self, message, activity):
            if failure:
                raise RuntimeError("provider failed")
            return CompletionText(PARTIAL, metadata())
    service = Service()
    from app.settings.model import ModelConfig
    config = ModelConfig(model_path="models/test.gguf", context_length=8192)
    model = SimpleNamespace(id="test.gguf", name="Test", path=Path("test.gguf"),
                            text_only=False, compatibility_note="Text and tools")
    inference = SimpleNamespace(available_modes=("local",), mode="local", context_length=8192,
        consume_notice=lambda: None,
        model_catalog=SimpleNamespace(models=[model], current_id=model.id, current_config=config))
    window = MainWindow(service, "TEST", inference=inference)
    try:
        service.fail_meter = True
        window.input.setPlainText("Generate code")
        window.submit()
        for _ in range(150):
            qt_app.processEvents()
            if window.thread is None:
                break
            QTest.qWait(10)
        qt_app.processEvents()
        assert window.thread is None and window.worker is None
        assert window.send.isEnabled() and window.input.isEnabled() and window.new_session_button.isEnabled()
        assert window.model_selector.isEnabled() and window.local_model_selector.isEnabled()
        assert not window.stop.isEnabled() and not window.chat.thinking_dots.is_running
        assert len(window.chat._messages) == 2
        item = window.chat._messages[-1]
        if failure:
            assert item.label.text() == "provider failed"
        else:
            assert item.completion == metadata() and item._code_blocks[0].incomplete
    finally:
        window.close()


@pytest.mark.parametrize("raises", [False, True])
def test_worker_empty_truncated_generation_carries_metadata_into_error_ui(qt_app, raises):
    from app.ui.worker import ConversationWorker
    class Service:
        def run(self, *args):
            if raises:
                raise IncompleteResponseError("The response was cut off.", metadata())
            return CompletionText("", metadata())
    worker = ConversationWorker(Service(), "Generate code")
    received = []
    worker.failed.connect(received.append)
    worker.run()
    assert len(received) == 1 and received[0].completion == metadata()
