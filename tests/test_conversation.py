from __future__ import annotations

from pathlib import Path
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


def test_system_prompt_explicitly_denies_computer_access():
    prompt = SYSTEM_PROMPT.casefold()
    assert "chat-only" in prompt
    assert "no tools" in prompt
    assert "no access to the computer" in prompt
    assert "never claim" in prompt


def test_bootstrap_uses_fresh_conversation_state(monkeypatch, tmp_path: Path):
    import app.main as main
    from app.inference.engine import InferenceUnavailable

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
    assert (tmp_path / "conversation_v1" / "conversation.json").is_file()
    assert not (tmp_path / "runtime_v4").exists()


def test_removed_action_packages_are_absent():
    root = Path(__file__).resolve().parents[1] / "app"
    for name in ("agent", "tools", "policy", "platform", "fingerprint", "skills"):
        assert not any((root / name).glob("*.py"))
