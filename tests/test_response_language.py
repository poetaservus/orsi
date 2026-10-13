"""Reply preferences preserve literal input, native protocols and profile authority."""
import json
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.agent.bootstrap import build_agent_runtime
from app.conversation.language_detection import detect_language, reply_locale
from app.conversation.language_messages import _MESSAGES, image_notice, notice
from app.conversation.orchestrator import ConversationService
from app.conversation.response_language import RESPONSE_LANGUAGES, with_response_language
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse, ModelProtocolFailureCode
from app.runtime.skills import SkillRegistry
from app.settings.agent import AgentFeatureConfig
from app.settings.response_language import ResponseLanguageSettings
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.vault.profiles import ProfileManager
from tests.test_personality import RequestRecorder
from tests.test_skill_activation import write_skill, skill_payload
from tests.test_vault_controls import PASSWORD


@pytest.mark.parametrize("language", RESPONSE_LANGUAGES)
def test_catalog_options_render_explicit_policy_and_complete_runtime_notices(language):
    assert len({item.code for item in RESPONSE_LANGUAGES}) == len(RESPONSE_LANGUAGES)
    prompt = with_response_language("core", language.code)
    assert prompt.startswith("core\n\nREPLY LANGUAGE POLICY")
    assert "original JSON protocols" in prompt and "skill language defaults" in prompt
    if language.code != "auto":
        assert f"{language.name} ({language.code})" in prompt
        assert len(_MESSAGES[language.code]) == 7
        assert "literal.json" in notice(language.code, "contents", name="literal.json")
        assert image_notice(language.code, 2) not in {"✓", ""}


@pytest.mark.parametrize("voice", ["original", "choom"])
@pytest.mark.parametrize("code", ["auto", "hu", "nl", "uk", "el"])
@pytest.mark.parametrize("agent", [False, True])
def test_real_requests_preserve_skill_guidance_catalog_and_unicode_user_text(tmp_path, voice, code, agent):
    model = RequestRecorder(16384)
    registry = SkillRegistry(global_root=tmp_path / "skills")
    write_skill(registry.global_root, "test-style", "Explain accurately in clear prose. Default to English.")
    registry.discover()
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=agent),
        portable_root=tmp_path, state_directory=tmp_path / "runtime") if agent else None
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"),
        agent_runtime=runtime, portable_root=tmp_path if agent else None, skill_registry=registry)
    text = 'Magyarázd el a működését. A név: "árvíz.json". Ne módosítsd.'
    try:
        service.select_personality(voice)
        service.select_response_language(code)
        service.run(text, skill_name="test-style")
        messages, catalog = model.requests[0]
        assert messages[-1] == {"role": "user", "content": text}
        assert with_response_language("", code).strip() in messages[0]["content"]
        assert skill_payload(messages)["instructions"] == "Explain accurately in clear prose. Default to English."
        assert catalog == (("filesystem.stat",) if agent else ())
        assert service.store.messages()[0]["content"] == text
        assert not list(tmp_path.glob("*.json.tmp"))
    finally:
        service.shutdown()


def test_default_persistence_busy_failure_and_new_chat(tmp_path, monkeypatch):
    path = tmp_path / "state/response_language_v1.json"
    settings = ResponseLanguageSettings(JsonStore(path))
    assert settings.current_code == "auto" and not path.exists()
    ui = JsonStore(tmp_path / "ui.json")
    ui.save({"greeting_message": "Keep greeting", "unrelated": True})
    before = ui.path.read_bytes()
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "chat.json"),
                                  response_language_settings=settings)
    try:
        service.run("A clear English request for the baseline")
        history = service.store.messages()
        service.select_response_language("hu")
        assert service.store.messages() == history and ui.path.read_bytes() == before
        saved = path.read_bytes()
        with monkeypatch.context() as patch:
            patch.setattr(settings._store, "save", Mock(side_effect=OSError("private synthetic path")))
            with pytest.raises(OSError):
                service.select_response_language("nl")
        assert settings.current_code == "hu" and path.read_bytes() == saved
        service.new_session()
        assert settings.current_code == "hu"
        service._run_lock.acquire()
        try:
            with pytest.raises(RuntimeError, match="current response"):
                service.select_response_language("nl")
        finally:
            service._run_lock.release()
    finally:
        service.shutdown()
    with pytest.raises(RuntimeError, match="closed"):
        service.select_response_language("nl")
    restored = ResponseLanguageSettings(JsonStore(path))
    assert restored.current_code == "hu"
    restored.select("auto")
    assert ResponseLanguageSettings(JsonStore(path)).current_code == "auto"


@pytest.mark.parametrize("payload", [b"null", b"not JSON", b'{"schema_version":true,"language_code":"hu"}',
    b'{"schema_version":2,"language_code":"hu"}', b'{"schema_version":1,"language_code":"missing"}'])
def test_invalid_saved_preference_is_preserved(tmp_path, payload):
    path = tmp_path / "language.json"
    path.write_bytes(payload)
    settings = ResponseLanguageSettings(JsonStore(path))
    assert settings.load_error and settings.current_code == "auto"
    with pytest.raises(ValueError, match="preserved"):
        settings.select("hu")
    assert path.read_bytes() == payload


@pytest.mark.parametrize("encrypted", [False, True])
def test_profile_isolation_lock_and_restart(tmp_path, encrypted):
    owner = ProfileManager(tmp_path)
    first, second = tmp_path / "profiles/one", tmp_path / "profiles/two"
    owner.create(first, encrypted=encrypted, password=PASSWORD if encrypted else b"")
    old = ResponseLanguageSettings(JsonStore(owner.session.storage_path("state/response_language_v1.json")), session=owner.session)
    old.select("hu")
    owner.lock()
    assert old._code is None and old._store is None
    owner.create(second, encrypted=encrypted, password=PASSWORD if encrypted else b"")
    try:
        new = ResponseLanguageSettings(JsonStore(owner.session.storage_path("state/response_language_v1.json")), session=owner.session)
        assert new.current_code == "auto"
        new.select("nl")
        owner.lock()
        owner.select(first, encrypted=encrypted, password=PASSWORD if encrypted else None)
        restored = ResponseLanguageSettings(JsonStore(owner.session.storage_path("state/response_language_v1.json")), session=owner.session)
        assert restored.current_code == "hu"
        assert not (tmp_path / "state/response_language_v1.json").exists()
        if encrypted:
            owner.lock()
            for path in first.rglob("*"):
                if path.is_file():
                    assert b'"language_code"' not in path.read_bytes()
    finally:
        owner.lock()


@pytest.mark.parametrize("size", [(760, 600), (1280, 800)])
def test_native_dropdown_keyboard_busy_and_failed_save(tmp_path, monkeypatch, size):
    app = QApplication.instance() or QApplication([])
    settings = ResponseLanguageSettings(JsonStore(tmp_path / "language.json"))
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "chat.json"), response_language_settings=settings)
    window = MainWindow(service, "SYNTHETIC")
    try:
        window.resize(*size)
        window.show()
        window.settings_button.click()
        scroll = window.settings_panel.pages.currentWidget()
        selector = window.response_language_selector
        scroll.ensureWidgetVisible(selector)
        app.processEvents()
        assert selector.currentText() == "Auto" and selector.isEnabled()
        assert selector.count() == len(RESPONSE_LANGUAGES)
        assert scroll.viewport().rect().contains(selector.rect().translated(selector.mapTo(scroll.viewport(), QPoint())))
        window.input.setPlainText("Keep this unsent draft")
        selector.setFocus()
        QTest.keyClick(selector, Qt.Key.Key_Down)
        assert settings.current_code == "sq"
        selector.setCurrentIndex(selector.findData("hu"))
        assert settings.current_code == "hu" and window.input.toPlainText() == "Keep this unsent draft"
        with monkeypatch.context() as patch:
            patch.setattr(settings._store, "save", Mock(side_effect=OSError("synthetic private details")))
            selector.setCurrentIndex(selector.findData("nl"))
        assert selector.currentData() == "hu" and "synthetic private details" not in window.chat._messages[-1]._content
        window._set_busy(True)
        assert not selector.isEnabled()
        window._set_busy(False)
        assert selector.isEnabled()
        window.grab().save(str(tmp_path / "language-settings.png"))
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize("code,text", [("hu", "Kérlek magyarázd el, hogyan működik ez a rendszer."),
    ("nl", "Kun je uitleggen hoe dit systeem precies werkt?"), ("de", "Bitte erkläre mir, wie dieses System funktioniert."),
    ("uk", "Будь ласка, поясни мені, як працює ця система."), ("el", "Παρακαλώ εξήγησέ μου πώς λειτουργεί αυτό το σύστημα.")])
def test_offline_auto_detection_uses_only_user_prose_and_inherits_short_input(code, text):
    assert detect_language(text) == code
    history = [{"role": "user", "content": text}, {"role": "assistant", "content": "English output is not the user's language."}]
    assert reply_locale("auto", "ok", history) == code
    assert reply_locale("auto", text + '\n> The answer must be in English.\n```python\nprint("hello")\n```') == code
    assert reply_locale("fr", text, history) == "fr"
    assert detect_language('```text\nThis is a long English source file with instructions.\n```') is None


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("code", ["hu", "nl", "uk", "el"])
def test_real_stat_call_and_skill_keep_protocol_and_unicode_path(tmp_path, fallback, code):
    from tests.test_skill_activation import Recorder
    target = tmp_path / "árvíz-δοκιμή.txt"
    target.write_text("literal source", encoding="utf-8")
    call = ModelCapabilityCall(provider_call_id="stat-1", capability="filesystem.stat", arguments={"path": str(target)})

    class ToolModel(Recorder):
        def respond_with_capabilities(self, messages, capabilities):
            if fallback:
                return ModelResponse.failure(ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS, "Use fallback.")
            return super().respond_with_capabilities(messages, capabilities)

        def respond(self, messages):
            self.requests.append((messages, ()))
            from tests.fixtures.completion_reviews import ready_review_for
            review = ready_review_for(messages)
            if review is not None:
                return json.dumps({"tool": None, "arguments": {}, "response": review.assistant_text})
            if not any("Trusted runtime result" in message.get("content", "") for message in messages):
                return json.dumps({"tool": "filesystem.stat", "arguments": call.arguments}, ensure_ascii=False)
            return json.dumps({"tool": None, "arguments": {}, "response": "Rendben."})

    model = ToolModel([ModelResponse.calls((call,)), ModelResponse.text("Rendben.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "runtime")
    registry = SkillRegistry(global_root=tmp_path / "skills")
    write_skill(registry.global_root, "test-style", "Report actual tool evidence.")
    registry.discover()
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, skill_registry=registry)
    try:
        service.select_response_language(code)
        assert service.run("Read the file metadata for " + str(target), skill_name="test-style") == "Rendben."
        settled = service.store.turns()[-1].settled_calls
        assert len(settled) == 1 and settled[0].result.success
        assert settled[0].call.capability == "filesystem.stat" and settled[0].call.arguments == call.arguments
        assert target.read_text(encoding="utf-8") == "literal source"
        assert any(with_response_language("", code).strip() in request[0][0]["content"]
                   or any(with_response_language("", code).strip() in item.get("content", "") for item in request[0])
                   for request in model.requests)
    finally:
        service.shutdown()


def test_fixed_language_reaches_cloud_body_without_changing_profile(monkeypatch, tmp_path):
    from tests.test_openai_selection import make_service
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    original = cloud.config.model_dump_json()
    try:
        service.select_response_language("hu")
        service.run("Explain a basic loop in English source code.")
        body = json.loads(requests[-1].content)
        assert "Hungarian (hu)" in body["input"][0]["content"]
        assert body["input"][-1]["content"] == "Explain a basic loop in English source code."
        assert body["temperature"] == .1 and body["reasoning"] == {"effort": "none"}
        assert cloud.config.model_dump_json() == original
    finally:
        service.shutdown()
    assert client.is_closed()


@pytest.mark.parametrize("code", ["auto", "hu", "uk", "fr"])
def test_automatic_skill_selection_stays_tool_free_and_keeps_exact_json_protocol(tmp_path, code):
    from tests.test_skill_activation import Recorder

    class AutomaticModel(Recorder):
        def respond(self, messages):
            self.requests.append((messages, ()))
            return '{"skill":"test-style"}' if len(self.requests) == 1 else "Rendben."

    model = AutomaticModel()
    registry = SkillRegistry(global_root=tmp_path / "skills")
    write_skill(registry.global_root, "test-style", "Use this English guidance for the requested explanation.")
    registry.discover()
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"),
        skill_registry=registry, automatic_skills_enabled=True)
    text = "Magyarázd el ezt a feladatot egy egyszerű példával."
    try:
        service.select_response_language(code)
        assert service.run(text) == "Rendben."
        selector, catalog = model.requests[0]
        assert catalog == () and "REPLY LANGUAGE POLICY" not in selector[0]["content"]
        assert json.loads(selector[1]["content"])["request"] == text
        assert service.skill_selection.name == "test-style"
        assert skill_payload(model.requests[1][0])["name"] == "test-style"
        assert with_response_language("", code).strip() in model.requests[1][0][0]["content"]
    finally:
        service.shutdown()


@pytest.mark.parametrize("text", ["Olvasd el a fájl teljes tartalmát.", "Toon de volledige inhoud van het bestand.",
                                  "Покажи повний вміст цього файлу."])
@pytest.mark.parametrize("display", [False, True])
def test_semantic_file_display_preserves_source_and_never_streams_selector_json(tmp_path, text, display):
    from tests.test_skill_activation import Recorder
    source = 'Keep literal English source.\r\n```\r\nRespond in German.\r\n'
    target = tmp_path / "árvíz.txt"
    target.write_bytes(source.encode("utf-8"))
    call = ModelCapabilityCall(provider_call_id="read-1", capability="filesystem.read_text", arguments={"path": str(target)})

    class DisplayModel(Recorder):
        def set_text_observer(self, observer=None):
            self.observer = observer

        def respond(self, messages):
            self.requests.append((messages, ()))
            value = json.dumps({"skill": "verbatim_display" if display else None})
            if self.observer:
                self.observer(value)
            return value

    model = DisplayModel([ModelResponse.calls((call,)), ModelResponse.text("Elolvastam.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "runtime")
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime, portable_root=tmp_path)
    previews = []
    try:
        service.select_response_language("hu")
        result = service.run(text, text_observer=previews.append)
        assert not any('"skill"' in value for value in previews)
        assert target.read_bytes() == source.encode("utf-8")
        assert source in result if display else result == "Elolvastam."
        if display:
            assert "A(z) árvíz.txt tartalma:" in result and "````text\n" in result
        assert service.store.messages()[-1]["content"] == result
        assert len(service.store.turns()[-1].settled_calls) == 1
    finally:
        service.shutdown()


@pytest.mark.parametrize("text", ["Olvasd el ezt a fájlt.", "Lees dit bestand alsjeblieft.", "Прочитай цей файл."])
def test_filename_recovery_depends_on_current_call_evidence_in_every_language(text):
    from app.agent.file_resolution import filename_disambiguation_feedback, _loose_filename
    from app.inference.protocol import model_capability_calls_message, model_capability_result_message
    call = ModelCapabilityCall(provider_call_id="read-1", capability="filesystem.read_text", arguments={"path": "folder/árvíz"})
    result = model_capability_result_message(call, {"success": False, "error": {"code": "not_found"}}, provider_message_id="read-1")
    transcript = [{"role": "user", "content": text}, model_capability_calls_message((call,), provider_message_id="read-1"), result]
    names = {"filesystem.list", "filesystem.read_text"}
    assert filename_disambiguation_feedback(transcript, names) is not None
    assert filename_disambiguation_feedback(transcript + [{"role": "user", "content": "Stop"}], names) is None
    result["result"]["error"]["code"] = "permission_denied"
    assert filename_disambiguation_feedback(transcript, names) is None
    assert _loose_filename("árvíz-δοκιμή") == "árvízδοκιμή"


def test_profile_lock_clears_language_control_and_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = ProfileManager(tmp_path)
    owner.create(tmp_path / "profiles/selected", password=PASSWORD)
    session = owner.session
    settings = ResponseLanguageSettings(JsonStore(session.storage_path("state/response_language_v1.json")), session=session)
    service = ConversationService(RequestRecorder(16384), ConversationStore(session.storage_path("state/conversation.json")),
        response_language_settings=settings)
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    window = MainWindow(service, "SYNTHETIC", preferences_store=JsonStore(session.storage_path("state/ui_preferences_v1.json")))
    window.bind_profile(session)
    try:
        window.response_language_selector.setCurrentIndex(window.response_language_selector.findData("hu"))
        owner.lock()
        assert settings._code is None and settings._store is None
        assert window.response_language_selector.currentIndex() == -1
        assert not window.response_language_selector.isEnabled() and not window.response_language_hint.text()
    finally:
        owner.lock()
        window.close()
        app.processEvents()


@pytest.mark.parametrize("text,choice", [
    ("Készíts egy képet egy macskáról.", "visual_creation"),
    ("Maak een afbeelding van een kat.", "visual_creation"),
    ("Erstelle ein Bild von einer Katze.", "visual_creation"),
    ("Создай изображение кошки.", "visual_creation"),
])
def test_multilingual_image_route_and_caption_reach_actual_sdk(native_sdk, tmp_path, text, choice):
    from tests.test_image_generation import image_payload
    from tests.test_openai_phase1 import response
    engine, counts, bodies, _ = native_sdk(payloads=[response(json.dumps({"skill": choice})), image_payload()])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        service.select_response_language("hu")
        result = service.run(text)
        assert str(result) == "A kép elkészült." and len(result.generated_images) == 1
        assert len(bodies) == 2
        assert bodies[0].get("tools", []) == []
        assert bodies[1]["tool_choice"] == {"type": "image_generation"}
        assert "Hungarian (hu)" in bodies[1]["input"][0]["content"]
        assert bodies[1]["input"][-1]["content"] == text
        assert service.store.messages()[0]["content"] == text
    finally:
        service.shutdown()


def test_rejected_multilingual_attachment_makes_no_selector_or_provider_request(native_sdk, tmp_path):
    from app.inference.attachments import AttachmentError
    from tests.test_attachment_processing import image_data
    engine, counts, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    reference = service.store.attachment_store.import_bytes(image_data(), name="source.png")
    (service.store.attachment_store.root / reference.id / "content").write_bytes(b"tampered synthetic source")
    try:
        with pytest.raises(AttachmentError):
            service.run("Készíts egy képet egy macskáról.", attachments=(reference,))
        assert not counts and not bodies and not service.store.messages()
    finally:
        service.shutdown()


def test_multilingual_visual_followup_reuses_only_current_source(native_sdk, tmp_path):
    from tests.test_image_generation import image_payload
    from tests.test_openai_phase1 import response
    from tests.test_cloud_attachment_input import inputs
    engine, counts, bodies, _ = native_sdk(payloads=[image_payload(),
        response('{"skill":"visual_edit"}'), image_payload(), response("Done"),
        response('{"skill":"visual_edit"}'), response("No current visual source")])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        original = service.run("Draw a blue circle").generated_images
        edited = service.run("Sötétítsd a hátteret ezen a képen.")
        assert edited.generated_images and len(inputs(bodies[-1], "input_image")) == 1
        assert service.store.visible_messages()[-2].attachments == original
        service.store.attachment_store.verify(original[0])
        service.run("Explain a basic loop")
        later = service.run("Sötétítsd a hátteret ezen a képen.")
        assert not later.generated_images and not service.store.visible_messages()[-2].attachments
        assert bodies[-1].get("tool_choice") != {"type": "image_generation"}
    finally:
        service.shutdown()


@pytest.mark.parametrize("selector", ['{"skill":null}', '{"skill":"shell.run"}', 'not JSON'])
def test_multilingual_routing_failure_cannot_force_image_or_execute_a_tool(native_sdk, tmp_path, selector):
    from tests.test_openai_phase1 import response
    engine, counts, bodies, _ = native_sdk(payloads=[response(selector), response("Rendben.")])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        result = service.run("Ne készíts képet, csak magyarázd el a feladatot.")
        assert result == "Rendben." and not result.generated_images
        assert bodies[-1].get("tool_choice") != {"type": "image_generation"}
        assert not service.store.turns()[-1].settled_calls
    finally:
        service.shutdown()


# Import the existing synthetic SDK fixture, never a live provider.
from tests.test_cloud_attachment_input import native_sdk
