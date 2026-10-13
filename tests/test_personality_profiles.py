"""Selections affect real requests and remain isolated, durable profile state."""
import json
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.personality import PERSONALITY_GUIDANCE, get_personality, with_personality
from app.conversation.prompt import SYSTEM_PROMPT, AGENT_CONVERSATION_SYSTEM_PROMPT, compact_agent_system_prompt, agent_system_prompt
from app.conversation.store import ConversationStore
from app.security.host_access import HostReadScope
from app.settings.personality import PersonalitySettings
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.vault.profiles import ProfileManager
from app.vault.types import VaultLocked
from tests.test_personality import RequestRecorder
from tests.test_vault_controls import PASSWORD


@pytest.mark.parametrize("prompt", [SYSTEM_PROMPT, AGENT_CONVERSATION_SYSTEM_PROMPT,
    agent_system_prompt(HostReadScope.PORTABLE_ROOT, ("filesystem.stat",)),
    compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, ("filesystem.stat",))])
def test_personality_changes_only_voice_and_preserves_operational_policy(prompt):
    assert with_personality(prompt, get_personality("original")) == prompt
    changed = with_personality(prompt, get_personality("choom-v1.0.0"))
    assert changed.removeprefix(get_personality("choom-v1.0.0").guidance) == prompt.removeprefix(PERSONALITY_GUIDANCE)


def test_new_chat_restart_and_failed_save_preserve_choice_history_and_preferences(tmp_path, monkeypatch):
    path = tmp_path / "state/personality_selection_v1.json"
    ui = JsonStore(tmp_path / "state/ui_preferences_v1.json")
    ui.save({"greeting_message": "Keep greeting", "unrelated": True})
    previous_ui = ui.path.read_bytes()
    settings = PersonalitySettings(JsonStore(path))
    assert settings.current_id == "original" and not path.exists()
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "conversation.json"),
                                  personality_settings=settings)
    try:
        service.run("Synthetic baseline")
        history = service.store.messages()
        service.select_personality("choom-v1.0.0")
        assert service.store.messages() == history
        assert ui.path.read_bytes() == previous_ui
        saved = path.read_bytes()
        with monkeypatch.context() as patch:
            patch.setattr(settings._store, "save", Mock(side_effect=OSError("synthetic private error")))
            with pytest.raises(OSError):
                service.select_personality("original")
        assert settings.current_id == "choom-v1.0.0" and path.read_bytes() == saved
        service.new_session()
        assert settings.current_id == "choom-v1.0.0"
        service.run("Synthetic next chat")
        assert service.inference.requests[-1][0][0]["content"].startswith(get_personality("choom-v1.0.0").guidance)
        service._run_lock.acquire()
        try:
            with pytest.raises(RuntimeError, match="current response"):
                service.select_personality("original")
        finally:
            service._run_lock.release()
        with pytest.raises(ValueError):
            service.select_personality("unknown-personality")
    finally:
        service.shutdown()
    with pytest.raises(RuntimeError, match="closed"):
        service.select_personality("original")
    restored = PersonalitySettings(JsonStore(path))
    assert restored.current_id == "choom-v1.0.0"
    restored.select("original")
    assert PersonalitySettings(JsonStore(path)).current.guidance == PERSONALITY_GUIDANCE


@pytest.mark.parametrize("encrypted", [False, True])
def test_two_profiles_remember_independent_choices_and_revoke_old_settings(tmp_path, encrypted):
    owner = ProfileManager(tmp_path)
    first, second = tmp_path / "profiles/one", tmp_path / "profiles/two"
    owner.create(first, encrypted=encrypted, password=PASSWORD if encrypted else b"")
    old = PersonalitySettings(JsonStore(owner.session.storage_path("state/personality_selection_v1.json")), session=owner.session)
    old.select("choom-v1.0.0")
    owner.create(second, encrypted=encrypted, password=PASSWORD if encrypted else b"")
    try:
        assert old._id is None
        with pytest.raises(VaultLocked):
            old.current_id
        other = PersonalitySettings(JsonStore(owner.session.storage_path("state/personality_selection_v1.json")), session=owner.session)
        assert other.current_id == "original"
        owner.select(first, encrypted=encrypted, password=PASSWORD if encrypted else None)
        restored = PersonalitySettings(JsonStore(owner.session.storage_path("state/personality_selection_v1.json")), session=owner.session)
        assert restored.current_id == "choom-v1.0.0"
        assert not (tmp_path / "state/personality_selection_v1.json").exists()
        if encrypted:
            owner.lock()  # Release the real exclusive Windows lease before inspecting ciphertext.
            for path in first.rglob("*"):
                if path.is_file():
                    assert b"choom-v1.0.0" not in path.read_bytes()
    finally:
        owner.lock()


def test_larger_personality_is_counted_and_never_expands_actual_context_limit(tmp_path):
    model = RequestRecorder(1024)
    service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"))
    try:
        service.select_personality("choom-v1.0.0")
        with pytest.raises(RuntimeError, match="context window"):
            service.run("Synthetic tiny-context request")
        assert model.context_length == 1024 and model.requests == []
    finally:
        service.shutdown()


@pytest.mark.parametrize("payload", [b"null", b"not JSON", b'{"schema_version":true,"personality_id":"original"}',
    b'{"schema_version":2,"personality_id":"original"}', b'{"schema_version":1,"personality_id":"missing"}'])
def test_invalid_saved_preferences_keep_original_chat_and_preserve_bytes(tmp_path, payload):
    path = tmp_path / "personality.json"
    path.write_bytes(payload)
    settings = PersonalitySettings(JsonStore(path))
    assert settings.current_id == "original" and settings.load_error
    with pytest.raises(ValueError, match="preserved"):
        settings.select("choom-v1.0.0")
    assert path.read_bytes() == payload


@pytest.mark.parametrize("size", [(760, 600), (1280, 800)])
def test_general_control_changes_real_request_and_restores_failed_selection(tmp_path, monkeypatch, size):
    app = QApplication.instance() or QApplication([])
    settings = PersonalitySettings(JsonStore(tmp_path / "state/personality_selection_v1.json"))
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "conversation.json"),
                                  personality_settings=settings)
    ui = JsonStore(tmp_path / "ui.json")
    ui.save({"greeting_message": "Keep greeting", "unrelated": True})
    before = ui.path.read_bytes()
    window = MainWindow(service, "SYNTHETIC", preferences_store=ui)
    try:
        window.resize(*size)
        window.show()
        window.settings_button.click()
        app.processEvents()
        selector = window.personality_selector
        scroll = window.settings_panel.pages.currentWidget()
        scroll.ensureWidgetVisible(selector)
        app.processEvents()
        assert selector.isVisible() and selector.isEnabled()
        assert scroll.viewport().rect().contains(selector.rect().translated(selector.mapTo(scroll.viewport(), QPoint())))
        assert [selector.itemText(i) for i in range(selector.count())] == ["Original", "Choom"]
        window.input.setPlainText("Keep unsent draft")
        selector.setFocus()
        QTest.keyClick(selector, Qt.Key.Key_Down)
        assert settings.current_id == "choom-v1.0.0"
        assert window.input.toPlainText() == "Keep unsent draft" and ui.path.read_bytes() == before
        service.run("Synthetic style request")
        assert service.inference.requests[-1][0][0]["content"].startswith(get_personality("choom-v1.0.0").guidance)
        with monkeypatch.context() as patch:
            patch.setattr(settings._store, "save", Mock(side_effect=OSError("synthetic private error")))
            selector.setCurrentIndex(selector.findData("original"))
        assert selector.currentData() == settings.current_id == "choom-v1.0.0"
        assert "synthetic private error" not in window.chat._messages[-1]._content
        window._set_busy(True)
        assert not selector.isEnabled()
        window._set_busy(False)
        assert selector.isEnabled()
        selector.setCurrentIndex(selector.findData("original"))
        service.run("Synthetic original request")
        assert service.inference.requests[-1][0][0]["content"].startswith(PERSONALITY_GUIDANCE)
    finally:
        window.close()
        app.processEvents()


def test_selected_personality_reaches_openai_request_without_changing_model_profile(monkeypatch, tmp_path):
    from tests.test_openai_selection import make_service
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    configuration = cloud.config.model_dump_json()
    try:
        service.select_personality("choom-v1.0.0")
        service.run("Synthetic cloud personality request")
        body = json.loads(requests[-1].content)
        assert body["input"][0]["content"].startswith(get_personality("choom-v1.0.0").guidance)
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == 4096 and body["temperature"] == .1
        assert cloud.config.model_dump_json() == configuration
    finally:
        service.shutdown()
    assert client.is_closed() and cloud._runner is None


def test_profile_lock_clears_the_selected_personality_from_the_view(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = ProfileManager(tmp_path)
    owner.create(tmp_path / "profiles/selected", password=PASSWORD)
    session = owner.session
    settings = PersonalitySettings(JsonStore(session.storage_path("state/personality_selection_v1.json")), session=session)
    service = ConversationService(RequestRecorder(16384), ConversationStore(session.storage_path("state/conversation.json")),
                                  personality_settings=settings)
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    window = MainWindow(service, "SYNTHETIC", preferences_store=JsonStore(session.storage_path("state/ui_preferences_v1.json")))
    window.bind_profile(session)
    try:
        window.personality_selector.setCurrentIndex(window.personality_selector.findData("choom-v1.0.0"))
        assert window.personality_selector.currentText() == "Choom"
        owner.lock()
        assert window.personality_selector.currentIndex() == -1
        assert not window.personality_selector.isEnabled() and not window.personality_hint.text()
        assert window._preferences_store is None and settings._id is None
    finally:
        owner.lock()
        window.close()
        app.processEvents()
