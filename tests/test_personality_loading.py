"""File-only additions and every outbound request obey the selected style boundary."""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import app.conversation.personality as personalities
from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.personality import discover_personalities, get_personality, load_personality, with_personality
from app.conversation.prompt import CORE_INSTRUCTIONS
from app.conversation.store import ConversationStore
from app.inference.cloud_errors import CloudInferenceError
from app.inference.engine import InferenceEngine
from app.inference.hybrid import HybridInferenceEngine
from app.settings.agent import AgentFeatureConfig
from app.settings.personality import PersonalitySettings
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from tests.test_personality import RequestRecorder


def assert_selected(messages, selected_id):
    systems = [message["content"] for message in messages if message.get("role") == "system"]
    selected = get_personality(selected_id).guidance
    assert sum(system.startswith(CORE_INSTRUCTIONS) for system in systems) == 1
    assert sum(system.count("SELECTED PERSONALITY (style only)") for system in systems) == 1
    assert sum(system.count(selected) for system in systems) == 1
    for other in personalities.PERSONALITIES:
        if other.id != selected_id:
            assert all(other.guidance not in system for system in systems)


@pytest.mark.parametrize("extension", ["md", "txt"])
def test_new_file_needs_no_registration_and_keeps_unicode_and_body(tmp_path, extension):
    source = tmp_path / ("friendly." + extension)
    source.write_bytes(("\ufeff---\r\nname: Barátságos\r\nversion: 1.0.0\r\n"
                        "description: Warm and thoughtful.\r\n---\r\n\r\n"
                        "Speak warmly.\r\nKeep literal `árvíz` intact.\r\n").encode("utf-8"))
    discovered = discover_personalities(tmp_path)
    assert len(discovered) == 1
    voice = discovered[0]
    assert (voice.id, voice.name, voice.version) == ("friendly", "Barátságos", "1.0.0")
    assert voice.guidance == "Speak warmly.\nKeep literal `árvíz` intact."
    assert "name:" not in voice.guidance


@pytest.mark.parametrize("text", [
    "No metadata", "---\nname: Missing body\n---\n", "---\n- list\n---\nStyle",
    "---\nname: First\nname: Duplicate\n---\nStyle", "---\nname: [nested]\n---\nStyle",
    "---\nid: ../escape\nname: Unsafe\n---\nStyle", "---\nid: empty-name\n---\nStyle",
    "---\nname: Wrong type\ntype: tool\n---\nStyle", "---\nname: [\n---\nStyle",
    "---\nname: 'Too large'\n---\n" + "x" * 32_768,
], ids=["missing-header", "empty-body", "list", "duplicate", "nested", "unsafe-id", "missing-name", "wrong-type", "malformed", "oversized"])
def test_bad_additions_are_skipped_without_blocking_valid_files(tmp_path, text, caplog):
    (tmp_path / "valid.md").write_text("---\nname: Valid\n---\nSpeak clearly.", encoding="utf-8")
    (tmp_path / "invalid.md").write_text(text, encoding="utf-8")
    assert [voice.id for voice in discover_personalities(tmp_path)] == ["valid"]
    assert text not in caplog.text and "skipped" in caplog.text


def test_duplicates_cannot_displace_bundled_identity(tmp_path):
    (tmp_path / "original.md").write_text("---\nname: Original\n---\nOriginal style.")
    (tmp_path / "aaa.md").write_text("---\nid: original\nname: Impostor\n---\nOther style.")
    assert [(voice.id, voice.guidance) for voice in discover_personalities(tmp_path)] == [("original", "Original style.")]


def test_explicit_id_survives_rename_and_loaded_style_is_stable_until_restart(tmp_path):
    source = tmp_path / "first.md"
    source.write_text("---\nid: stable\nname: My Voice\n---\nFirst style.")
    loaded = load_personality(source)
    renamed = source.rename(tmp_path / "renamed.md")
    renamed.write_text("---\nid: stable\nname: My Voice\nversion: 2.0.0\n---\nSecond style.")
    assert loaded.guidance == "First style."
    current = discover_personalities(tmp_path)[0]
    assert current.id == loaded.id == "stable" and current.guidance == "Second style."


def test_legacy_selection_resolves_to_v2_without_rewriting_saved_bytes(tmp_path):
    path = tmp_path / "selection.json"
    saved = b'{"schema_version":1,"personality_id":"choom-v1.0.0"}'
    path.write_bytes(saved)
    settings = PersonalitySettings(JsonStore(path))
    assert not settings.load_error and settings.current_id == "choom"
    assert settings.current.version == "2.0.0"
    assert path.read_bytes() == saved
    assert get_personality("choom-v1.0.0") is get_personality("choom")


def test_composer_rejects_appending_a_second_voice():
    composed = with_personality(CORE_INSTRUCTIONS, get_personality("original"))
    with pytest.raises(ValueError, match="already contains"):
        with_personality(composed, get_personality("choom"))


def test_file_only_personality_appears_in_settings_and_actual_request(tmp_path, monkeypatch):
    (tmp_path / "friendly.md").write_text(
        "---\nname: Friendly\nversion: 3.0.0\ndescription: Warm explanations.\n---\nUse warm explanations.")
    catalog = (*personalities.PERSONALITIES, *discover_personalities(tmp_path))
    monkeypatch.setattr(personalities, "PERSONALITIES", catalog)
    monkeypatch.setattr("app.ui.settings_panel.PERSONALITIES", catalog)
    app = QApplication.instance() or QApplication([])
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "SYNTHETIC")
    try:
        window.personality_selector.setCurrentIndex(window.personality_selector.findData("friendly"))
        assert window.personality_hint.text() == "Friendly 3.0.0 · Warm explanations."
        assert window.personality_hint.isHidden()
        assert "Warm explanations." in window.personality_selector.toolTip()
        assert service.run("Explain this clearly.") == "Rendben."
        assert_selected(service.inference.requests[-1][0], "friendly")
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize("backend", ["python", "native", "compatible", "responses"])
def test_round_trip_reaches_real_adapter_bodies_with_history_preserved(tmp_path, monkeypatch, backend):
    bodies = []
    if backend == "python":
        from app.inference.llama_backend import LlamaCppInferenceEngine
        engine = object.__new__(LlamaCppInferenceEngine)
        def create(**body):
            bodies.append(deepcopy(body))
            return {"choices": [{"message": {"content": "Reply"}}]}
        engine.model = SimpleNamespace(create_chat_completion=create, close=lambda: None)
        engine.config = SimpleNamespace(temperature=.1, max_tokens=128)
    elif backend == "native":
        from tests.test_llama_server_inference import completion, scripted_engine
        engine, bodies = scripted_engine([completion({"role": "assistant", "content": "Reply"}) for _ in range(3)])
        monkeypatch.setattr(engine, "close", lambda: None)
    elif backend == "compatible":
        from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
        from tests.test_cloud_inference import cloud_config
        engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="synthetic-never-live")
        def request(body, **kwargs):
            bodies.append(deepcopy(body))
            return {"choices": [{"message": {"content": "Reply"}}]}
        monkeypatch.setattr(engine, "_request_completion", request)
    else:
        from tests.test_openai_tools import scripted_sdk
        from tests.test_openai_phase1 import response
        payloads = [response("Reply", id=f"resp_{i}") for i in range(3)]
        for i, payload in enumerate(payloads):
            payload["output"][0]["id"] = f"msg_{i}"
        engine, client, bodies, _ = scripted_sdk(monkeypatch, payloads)
    if backend in {"python", "native"}:
        engine.context_length, engine.max_response_tokens = 16384, 128
        monkeypatch.setattr(engine, "count_message_tokens", lambda messages: InferenceEngine.count_message_tokens(engine, messages))
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        for selected in ("original", "choom", "original"):
            before = service.store.messages()
            service.select_personality(selected)
            assert service.store.messages() == before
            assert service.run("Explain the current result.")
            assert_selected(bodies[-1]["input" if backend == "responses" else "messages"], selected)
        assert len(service.store.messages()) == 6 and len(bodies) == 3
    finally:
        service.shutdown()
    if backend == "responses":
        assert client.is_closed() and engine._runner is None


def test_cloud_tool_continuations_and_reviews_switch_without_leakage(tmp_path, monkeypatch):
    from tests.test_openai_tools import function, scripted_sdk
    from tests.test_openai_phase1 import response
    target = tmp_path / "probe.txt"
    target.write_bytes(b"literal fixture")
    payloads = []
    for i in range(1, 4):
        call = function(arguments={"path": str(target)}, call_id=f"call_{i}")
        answer = response("Done", id=f"resp_answer_{i}")
        answer["output"][0]["id"] = f"msg_answer_{i}"
        review = response(json.dumps({"goal_id": f"turn-{i}", "status": "ready", "remaining": []}), id=f"resp_review_{i}")
        review["output"][0]["id"] = f"msg_review_{i}"
        payloads.extend((response(output=[call], id=f"resp_call_{i}"), answer, review))
    engine, client, bodies, _ = scripted_sdk(monkeypatch, payloads)
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "runtime")
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,))
    definitions, permissions = runtime.registry.model_definitions(), runtime.permission_gate
    try:
        for selected in ("original", "choom", "original"):
            start = len(bodies)
            service.select_personality(selected)
            assert service.run("Inspect probe.txt") == "Done"
            assert len(bodies) - start == 3
            for body in bodies[start:]:
                assert_selected(body["input"], selected)
                assert body["tools"] == bodies[0]["tools"]
            assert bodies[-1]["tool_choice"] == "none"
            assert service.store.turns()[-1].settled_calls[0].result.success
            assert runtime.registry.model_definitions() == definitions and runtime.permission_gate is permissions
        assert target.read_bytes() == b"literal fixture"
    finally:
        service.shutdown()
    assert client.is_closed() and engine._runner is None


def test_cloud_to_local_fallback_preserves_selected_style(tmp_path):
    class Offline(RequestRecorder):
        def respond(self, messages):
            self.requests.append((deepcopy(messages), ()))
            raise CloudInferenceError("Synthetic offline", allow_local_fallback=True)
    cloud, local = Offline(16384), RequestRecorder(16384)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=True)
    service = ConversationService(hybrid, ConversationStore(tmp_path / "chat.json"))
    try:
        for selected in ("original", "choom", "original"):
            hybrid.set_mode("cloud")
            service.select_personality(selected)
            assert service.run("Explain the current result.") == "Rendben."
            assert_selected(cloud.requests[-1][0], selected)
            assert_selected(local.requests[-1][0], selected)
    finally:
        service.shutdown()


@pytest.mark.parametrize("fallback", [False, True])
def test_local_tool_and_protocol_fallback_round_trip_keep_one_voice(tmp_path, fallback):
    from app.inference.protocol import ModelCapabilityCall, ModelProtocolFailureCode, ModelResponse
    from tests.fixtures.completion_reviews import ready_review_for

    target = tmp_path / "probe.txt"
    target.write_bytes(b"unchanged")

    class ToolModel(RequestRecorder):
        def respond_with_capabilities(self, messages, capabilities):
            self.requests.append((deepcopy(messages), tuple(capabilities)))
            if fallback:
                return ModelResponse.failure(ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS, "Use fallback.")
            return ready_review_for(messages) or next(self.responses)

        def respond(self, messages):
            self.requests.append((deepcopy(messages), ()))
            review = ready_review_for(messages)
            if review is not None:
                return json.dumps({"tool": None, "arguments": {}, "response": review.assistant_text})
            if not self.sent_tool:
                self.sent_tool = True
                return json.dumps({"tool": "filesystem.stat", "arguments": {"path": str(target)}})
            return json.dumps({"tool": None, "arguments": {}, "response": "Done"})

    model = ToolModel(16384)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "runtime")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,))
    try:
        for i, selected in enumerate(("original", "choom", "original")):
            start = len(model.requests)
            model.sent_tool = False
            call = ModelCapabilityCall(provider_call_id=f"local-{i}", capability="filesystem.stat", arguments={"path": str(target)})
            model.responses = iter((ModelResponse.calls((call,)), ModelResponse.text("Done")))
            service.select_personality(selected)
            assert service.run("Inspect probe.txt") == "Done"
            assert len(model.requests) - start >= 3
            for messages, catalog in model.requests[start:]:
                assert_selected(messages, selected)
            assert service.store.turns()[-1].settled_calls[0].result.success
        assert target.read_bytes() == b"unchanged"
    finally:
        service.shutdown()


def test_image_requests_share_core_and_selected_voice(tmp_path, monkeypatch):
    from tests.test_image_generation import image_payload
    from tests.test_openai_phase1 import engine_with_transport
    engine, client, requests, _ = engine_with_transport(monkeypatch, image_payload())
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        for selected in ("original", "choom", "original"):
            service.select_personality(selected)
            assert service.run("Generate an image of a blue circle").generated_images
            body = json.loads(requests[-1].content)
            assert_selected(body["input"], selected)
            assert body["tool_choice"] == {"type": "image_generation"}
    finally:
        service.shutdown()
    assert client.is_closed()
