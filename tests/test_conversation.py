from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

from app.conversation.prompt import SYSTEM_PROMPT
from app.conversation.service import ConversationService
from app.conversation.store import ConversationStore


class RecordingInference:
    def __init__(self, reply="Hello back"):
        self.reply = reply
        self.calls = []

    def respond(self, messages):
        self.calls.append(messages)
        return self.reply


def test_conversation_is_text_only_and_persists(tmp_path: Path):
    path = tmp_path / "conversation.json"
    inference = RecordingInference()
    service = ConversationService(inference, ConversationStore(path))

    assert service.run("Hello") == "Hello back"
    sent = inference.calls[0]
    assert sent[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert sent[1:] == [{"role": "user", "content": "Hello"}]
    assert all(set(message) == {"role", "content"} for message in sent)

    reopened = ConversationStore(path)
    assert reopened.messages() == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hello back"},
    ]


def test_new_session_erases_previous_conversation_without_an_archive(tmp_path: Path):
    path = tmp_path / "conversation.json"
    service = ConversationService(RecordingInference(), ConversationStore(path))
    service.run("This must be erased")
    previous_id = json.loads(path.read_text(encoding="utf-8"))["conversation_id"]

    service.new_session()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["conversation_id"] != previous_id
    assert payload["messages"] == []
    assert ConversationStore(path).messages() == []
    assert [item.name for item in tmp_path.iterdir()] == ["conversation.json"]
    assert service.estimated_context_tokens() == 0


def test_history_uses_token_budget_and_saturates_context_meter(tmp_path: Path):
    class ExactCharacterTokenizer(RecordingInference):
        context_length = 2000
        max_response_tokens = 200

        @staticmethod
        def count_message_tokens(messages):
            return sum(len(message["content"]) for message in messages)

    store = ConversationStore(tmp_path / "conversation.json")
    store.append("user", "A" * 2000)
    service = ConversationService(ExactCharacterTokenizer(), store)

    selected = service._model_messages()

    assert service.inference.count_message_tokens(selected) <= 1800
    assert selected[-1]["content"].startswith("[Earlier content truncated]")
    assert selected[-1]["content"].endswith("A" * 100)
    assert service.estimated_context_tokens() == 2000


def test_system_prompt_explicitly_denies_computer_access():
    prompt = SYSTEM_PROMPT.casefold()
    assert "chat-only" in prompt
    assert "no tools" in prompt
    assert "no access to the computer" in prompt
    assert "never claim" in prompt
    assert "triple-backtick fenced code block" in prompt


def test_bootstrap_uses_fresh_conversation_state(monkeypatch, tmp_path: Path):
    import app.main as main
    from app.inference.engine import InferenceUnavailable

    state_path = tmp_path / "conversation_v1" / "conversation.json"
    previous = ConversationStore(state_path)
    previous.append("user", "This previous-window context must disappear")
    previous_id = json.loads(state_path.read_text(encoding="utf-8"))["conversation_id"]

    monkeypatch.setattr(main, "PATHS", SimpleNamespace(state=tmp_path))
    monkeypatch.setattr(
        main,
        "load_model_config",
        lambda: (_ for _ in ()).throw(InferenceUnavailable("no local model")),
    )
    cloud_config = SimpleNamespace(default_mode="cloud", fallback_to_local=False)
    monkeypatch.setattr(main, "load_cloud_config", lambda: cloud_config)
    monkeypatch.setattr(main, "OpenAICompatibleInferenceEngine", lambda _: object())

    class FakeHybrid:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def respond(self, messages):
            return "reply"

    monkeypatch.setattr(main, "HybridInferenceEngine", FakeHybrid)

    service, host, error, inference = main.build_application()

    assert isinstance(service, ConversationService)
    assert host["hostname"] and error is None and isinstance(inference, FakeHybrid)
    assert state_path.is_file()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["conversation_id"] != previous_id
    assert payload["messages"] == []
    assert service.estimated_context_tokens() == 0
    assert not (tmp_path / "runtime_v4").exists()


def test_removed_action_packages_are_absent():
    root = Path(__file__).resolve().parents[1] / "app"
    for name in ("agent", "tools", "policy", "platform", "fingerprint", "skills"):
        assert not any((root / name).glob("*.py"))
