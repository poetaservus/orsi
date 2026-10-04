"""Cloud admission at vendor context ceilings keeps local budgets unchanged."""
import json
from types import SimpleNamespace

import pytest

from app.conversation.context import calculate_context_budget
from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.openai_replay import REPLAY_KEY
from app.settings.cloud import load_cloud_config
from tests.test_openai_efficiency import replay_history
from tests.test_openai_phase1 import engine_with_transport, response


@pytest.mark.parametrize("model_id", ["gpt-6-luna", "gpt-6.1-sol"])
def test_previously_oversized_tool_history_is_admitted_without_projection(monkeypatch, model_id):
    settings = load_cloud_config()
    engine, client, requests, _ = engine_with_transport(monkeypatch, response(model=model_id), engine_config=settings)
    history, definition = replay_history(110000)
    for message in history:
        if REPLAY_KEY in message:
            message[REPLAY_KEY]["model"] = model_id
    try:
        engine.select_model(model_id)
        schema = engine.count_capability_schema_tokens((definition,))
        budget = calculate_context_budget(engine, history, reserved_tokens=schema)
        assert budget.request_input_tokens > 28672 and budget.fits
        result = engine.respond_with_capabilities(history, (definition,))
        assert result.assistant_text == "hello"
        body = json.loads(requests[0].content)
        assert body["model"] == model_id and body["max_output_tokens"] == settings.profile(model_id).max_output_tokens
        # Actual request retains the original tool evidence rather than an excerpt.
        output = json.loads(body["input"][-1]["output"])
        assert output["output"]["content"] == history[-1]["result"]["output"]["content"]
    finally:
        engine.close()
    assert client.is_closed()


@pytest.mark.parametrize("model_id", ["gpt-6-luna", "gpt-6.1-sol"])
def test_exact_cloud_input_boundary_and_safety_margin(monkeypatch, model_id):
    settings = load_cloud_config()
    engine, client, requests, _ = engine_with_transport(monkeypatch, engine_config=settings)
    try:
        engine.select_model(model_id)
        profile = settings.profile(model_id)
        boundary = profile.max_input_tokens - 256
        # Exercise the real wire-admission branch without sending a huge fixture.
        monkeypatch.setattr("app.inference.openai_backend.estimate_input_tokens", lambda items: boundary)
        assert engine.respond([{"role": "user", "content": "Synthetic boundary probe."}]) == "hello"
        monkeypatch.setattr("app.inference.openai_backend.estimate_input_tokens", lambda items: boundary + 1)
        with pytest.raises(CloudInferenceError) as failure:
            engine.respond([{"role": "user", "content": "Synthetic boundary probe."}])
        assert failure.value.code == CloudErrorCode.CONTEXT_OVERFLOW and len(requests) == 1
        assert profile.max_input_tokens + profile.max_output_tokens == profile.effective_context_length == 1050000
    finally:
        engine.close()
    assert client.is_closed()


def test_real_local_cloud_mode_switch_restores_local_limits():
    settings = load_cloud_config()
    cloud = OpenAIResponsesInferenceEngine(settings)
    released = []
    local = LazyInferenceEngine(lambda: SimpleNamespace(context_length=16384, max_response_tokens=4096,
                                close=lambda: released.append(True)), context_length=16384, max_response_tokens=4096)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="local", fallback_to_local=False)
    try:
        messages = [{"role": "user", "content": "Synthetic mode probe."}]
        before = calculate_context_budget(hybrid, messages)
        assert (hybrid.context_length, hybrid.max_response_tokens) == (16384, 4096)
        hybrid.set_mode("cloud")
        assert not local.is_loaded and len(released) == 1
        assert (hybrid.context_length, hybrid.max_response_tokens) == (1050000, 128000)
        hybrid.select_cloud_model("gpt-6.1-sol")
        assert (hybrid.context_length, hybrid.max_response_tokens) == (1050000, 4096)
        hybrid.select_cloud_model("gpt-6-luna")
        hybrid.set_mode("local")
        assert calculate_context_budget(hybrid, messages) == before
        assert cloud._client is None
    finally:
        hybrid.close()
    assert len(released) == 2 and not local.is_loaded
