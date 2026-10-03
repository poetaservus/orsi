from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace
import pytest

from app.conversation.prompt import SYSTEM_PROMPT
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.conversation.store import TurnHistoryError
from app.state.storage import JsonStore


class RecordingInference:
    def __init__(self, reply="Hello back"):
        self.reply = reply
        self.calls = []

    def respond(self, messages):
        self.calls.append(messages)
        return self.reply


def test_context_measurement_is_latest_request_scoped_to_session_and_model(tmp_path):
    from app.inference.completion import CompletionMetadata, CompletionText, TokenUsage
    first = CompletionMetadata(usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120))
    last = CompletionMetadata(finish_reason="length", usage=TokenUsage(input_tokens=300, output_tokens=40))
    inference = RecordingInference(CompletionText("partial code", last, (first, last)))
    inference.context_revision = 0
    service = ConversationService(inference, ConversationStore(tmp_path / "conversation.json"))
    assert service.reported_context_tokens() is None
    service.run("Generate code")
    assert service.reported_context_tokens() == 340  # Not cumulative across physical requests.
    assert service.store.turns()[-1].outcome.status.value == "incomplete"
    inference.context_revision += 1
    assert service.reported_context_tokens() is None
    inference.context_revision += 1  # Away and back does not resurrect stale usage.
    assert service.reported_context_tokens() is None
    inference.reply = CompletionText("done", first)
    service.run("Next task")
    assert service.reported_context_tokens() == 120
    service.new_session()
    assert service.reported_context_tokens() is None
    service.run("Fresh task")
    assert service.reported_context_tokens() == 120
    reopened = ConversationService(inference, ConversationStore(service.store.path))
    assert reopened.reported_context_tokens() is None  # Legacy usage lacks model provenance.


def test_unreported_or_failed_request_does_not_reuse_previous_usage(tmp_path):
    from app.inference.completion import CompletionMetadata, CompletionText, TokenUsage
    inference = RecordingInference(CompletionText("done", CompletionMetadata(
        usage=TokenUsage(total_tokens=500))))
    service = ConversationService(inference, ConversationStore(tmp_path / "conversation.json"))
    service.run("First")
    assert service.reported_context_tokens() == 500
    inference.reply = "No usage supplied"
    service.run("Second")
    assert service.reported_context_tokens() is None
    inference.reply = CompletionText("done", CompletionMetadata(usage=TokenUsage(total_tokens=200)))
    service.run("Third")
    def fail(messages):
        raise RuntimeError("provider failed")
    inference.respond = fail
    with pytest.raises(RuntimeError, match="provider failed"):
        service.run("Fourth")
    assert service.reported_context_tokens() is None


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


@pytest.mark.parametrize("failure_stage", ["archive", "active"])
def test_preserved_session_rotation_failure_retains_active_history(tmp_path, monkeypatch, failure_stage):
    path = tmp_path / "conversation.json"
    service = ConversationService(RecordingInference(), ConversationStore(path))
    service.run("Keep the previous task")
    before = path.read_bytes()
    previous_id = service.store.session_id
    native_save = JsonStore.save

    def failing_save(store, value):
        is_archive = store.path.parent.name == "archives"
        if is_archive == (failure_stage == "archive"):
            raise PermissionError("replacement denied")
        return native_save(store, value)

    monkeypatch.setattr(JsonStore, "save", failing_save)
    with pytest.raises(TurnHistoryError, match="preserved|persisted safely"):
        service.new_session(preserve_history=True)
    assert path.read_bytes() == before
    assert service.store.session_id == previous_id
    assert service.store.messages()[0]["content"] == "Keep the previous task"
    assert service._agent_history[0]["content"] == "Keep the previous task"
    archives = list((tmp_path / "archives").glob("*.json"))
    assert len(archives) == int(failure_stage == "active")
    if archives:
        assert json.loads(archives[0].read_text())["conversation_id"] == previous_id


def test_empty_startup_sessions_do_not_accumulate_archives(tmp_path):
    path = tmp_path / "conversation.json"
    for _ in range(3):
        service = ConversationService(RecordingInference(), ConversationStore(path))
        service.new_session(preserve_history=True)
        service.shutdown()
    assert not (tmp_path / "archives").exists()


def test_history_uses_token_budget_and_saturates_context_meter(tmp_path: Path):
    class ExactCharacterTokenizer(RecordingInference):
        # Leave a fixed history allowance regardless of the production prompt length.
        context_length = len(SYSTEM_PROMPT) + 1000
        max_response_tokens = 200

        @staticmethod
        def count_message_tokens(messages):
            return sum(len(message["content"]) for message in messages)

    store = ConversationStore(tmp_path / "conversation.json")
    store.append("user", "A" * 2000)
    service = ConversationService(ExactCharacterTokenizer(), store)

    selected = service._model_messages()

    assert service.inference.count_message_tokens(selected) <= ExactCharacterTokenizer.context_length - 200
    assert selected[-1]["content"].startswith("[Earlier content truncated]")
    assert selected[-1]["content"].endswith("A" * 100)
    assert service.estimated_context_tokens() == ExactCharacterTokenizer.context_length


def test_system_prompt_explicitly_denies_computer_access():
    prompt = SYSTEM_PROMPT.casefold()
    assert "chat-only" in prompt
    assert "no tools" in prompt
    assert "no access to the computer" in prompt
    assert "never claim" in prompt
    assert "triple-backtick fenced code block" in prompt


@pytest.mark.parametrize("corrupted", [False, True])
def test_bootstrap_archives_previous_conversation_and_starts_empty(monkeypatch, tmp_path: Path, corrupted):
    import app.startup as main
    from app.inference.engine import InferenceUnavailable

    state_path = tmp_path / "conversation_v1" / "conversation.json"
    previous = ConversationStore(state_path)
    previous.append("user", "This previous-window context remains known")
    previous_id = json.loads(state_path.read_text(encoding="utf-8"))["conversation_id"]
    if corrupted:
        state_path.write_text("{corrupted history")

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

    service, host, error, inference = main.build_application(
        agent_config_override=main.AgentFeatureConfig()
    )

    if corrupted:
        assert service is None and "preserved" in error and "restored safely" in error
        assert state_path.read_text() == "{corrupted history"
        return
    assert isinstance(service, ConversationService)
    assert host["hostname"] and error is None and isinstance(inference, FakeHybrid)
    assert state_path.is_file()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["conversation_id"] != previous_id
    assert payload["messages"] == service.store.messages() == []
    assert service.estimated_context_tokens() == 0
    archives = list((state_path.parent / "archives").glob("*.json"))
    assert len(archives) == 1
    archived = json.loads(archives[0].read_text(encoding="utf-8"))
    assert archived["conversation_id"] == previous_id
    assert archived["session_status"] == "closed"
    assert archived["messages"][0]["content"] == "This previous-window context remains known"
    service.run("A new task")
    assert service._agent_history[0] == {"role": "user", "content": "A new task"}
    assert all("previous-window" not in message["content"] for message in service._agent_history)
    assert not (tmp_path / "runtime_v4").exists()


def test_abandoned_action_packages_are_absent():
    root = Path(__file__).resolve().parents[1] / "app"
    for name in ("tools", "policy", "platform", "fingerprint", "skills"):
        assert not any((root / name).glob("*.py"))
