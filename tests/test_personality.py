"""The actual request retains voice, user text and authority across prompt fallbacks."""
from math import ceil

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.personality import PERSONALITY_GUIDANCE
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelResponse
from app.settings.agent import AgentFeatureConfig


class RequestRecorder(InferenceEngine):
    max_response_tokens = 128

    def __init__(self, context_length):
        self.context_length = context_length
        self.requests = []

    def count_message_tokens(self, messages):
        return ceil(sum(len(m['content']) for m in messages) / 4)

    def respond(self, messages):
        self.requests.append((messages, ()))
        return "Rendben."

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append((messages, tuple(c.name for c in capabilities)))
        return ModelResponse.text("Rendben.")


@pytest.mark.parametrize("mode", ["chat", "conversation", "agent", "compact"])
def test_personality_survives_request_selection_without_changing_catalog_or_user_text(tmp_path, mode):
    model = RequestRecorder(2000 if mode == "compact" else 16384)
    runtime = None
    if mode != "chat":
        runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True),
            portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"),
        agent_runtime=runtime, portable_root=tmp_path)
    user_text = "Szia. A fájl neve report.json; ne módosítsd."
    try:
        if mode == "conversation":
            service.store.append("user", user_text)
            request = service._model_request(capability_turn=False)
            model.respond(request.messages)
        else:
            assert service.run(user_text) == "Rendben."
        messages, catalog = model.requests[-1]
        system = messages[0]["content"]
        assert system.startswith(PERSONALITY_GUIDANCE)
        assert messages[-1] == {"role": "user", "content": user_text}
        assert service._model_request(capability_turn=mode != "conversation").budget.fits
        assert catalog == (() if mode in {"chat", "conversation"} else ("filesystem.stat",))
        if mode in {"chat", "conversation"}:
            assert "no tools" in system or "No computer capability" in system
        else:
            assert "filesystem.write_text" not in system
        if mode == "compact":
            assert "Available names: filesystem.stat." in system
        assert list(tmp_path.glob("report.json")) == []
    finally:
        service.shutdown()
