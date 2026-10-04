"""A large file's content must fit in a complete native write call."""
from types import SimpleNamespace

import pytest

from app.capabilities.filesystem_write_text import FilesystemWriteTextArguments
from app.conversation.context import calculate_context_budget, response_reserve
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.openai_stream import ResponsesStreamState
from app.inference.protocol import ModelCapabilityDefinition, ModelResponseKind, ModelProtocolFailureCode
from app.settings.cloud import load_cloud_config
from tests.test_openai_phase1 import response
from tests.test_openai_tools import function, scripted_sdk


def definition():
    return ModelCapabilityDefinition(name="filesystem.write_text", description="Write text after approval.",
                                    input_schema=FilesystemWriteTextArguments.model_json_schema())


def test_large_complete_write_call_uses_expanded_checked_in_luna_budget(monkeypatch):
    settings = load_cloud_config()
    text = "<article>synthetic fixture</article>\n" * 900
    arguments = {"path": "C:/synthetic-fixture/index.html", "text": text}
    payload = response(output=[function(definition(), arguments)],
                       usage={"input_tokens": 200, "output_tokens": 9000, "total_tokens": 9200})
    engine, client, bodies, factory = scripted_sdk(monkeypatch, [payload], engine_config=settings)
    try:
        result = engine.respond_with_capabilities([{"role": "user", "content": "Write the synthetic fixture."}],
                                                  (definition(),))
        assert result.kind == ModelResponseKind.CAPABILITY_CALLS
        assert result.capability_calls[0].arguments == arguments
        assert result.completion.usage.output_tokens > 4096
        assert bodies[0]["max_output_tokens"] == 128000
        assert bodies[0]["reasoning"] == {"effort": "none"} and bodies[0]["temperature"] == 0.1
        assert engine.context_length == 156672
        assert settings.profile("gpt-6-luna").max_input_tokens == 28672
        assert factory.call_args.kwargs["timeout"] == 1800
    finally:
        engine.close()
    assert client.is_closed()


def test_maximum_output_reserve_preserves_the_existing_input_budget():
    engine = OpenAIResponsesInferenceEngine(load_cloud_config())
    try:
        budget = calculate_context_budget(engine, [{"role": "user", "content": "Synthetic budget probe."}])
        assert budget.requested_output_reserve == 128000
        assert budget.model_context_limit - budget.requested_output_reserve == 28672
        # Admission must reject what the old half-context clamp would admit.
        oversized = calculate_context_budget(engine, [{"role": "user", "content": "x" * 120000}])
        assert not oversized.fits
        local = SimpleNamespace(context_length=8192, max_response_tokens=8000)
        assert response_reserve(local) == 4096
    finally:
        engine.close()


def test_maximum_token_stream_can_finish_after_one_delta_per_token(monkeypatch):
    from typing import Annotated

    from openai.types.responses import ResponseStreamEvent
    from pydantic import Field, TypeAdapter

    from tests.test_openai_streaming import events
    from tests.test_openai_phase1 import response

    payload = response("x" * 128000, parallel_tool_calls=False, tool_choice="auto", tools=[],
                       usage={"input_tokens": 200, "output_tokens": 128000, "total_tokens": 128200,
                              "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                              "output_tokens_details": {"reasoning_tokens": 0}})
    sequence = events(payload)
    adapter = TypeAdapter(Annotated[ResponseStreamEvent, Field(discriminator="type")])
    state = ResponsesStreamState()
    # Every token arrives separately, exceeding the former 65,536-event cap.
    for event in sequence[:3]:
        assert state.accept(adapter.validate_python(event)) is None
    delta = {**sequence[3], "delta": "x"}
    for index in range(128000):
        assert state.accept(adapter.validate_python({**delta, "sequence_number": index + 3})) is None
    assert state.accept(adapter.validate_python({**sequence[4], "sequence_number": 128003})) is None
    terminal = state.accept(adapter.validate_python({**sequence[5], "sequence_number": 128004}))
    assert terminal["status"] == "completed" and state.partial_text == payload["output"][0]["content"][0]["text"]
    # The expanded allowance remains bounded; a pathological continuation fails.
    monkeypatch.setattr("app.inference.openai_stream._MAX_EVENTS", state.events)
    with pytest.raises(ValueError, match="protocol limit"):
        state.accept(adapter.validate_python({"type": "response.in_progress", "sequence_number": 128005,
                                             "response": {**payload, "status": "in_progress"}}))


def test_larger_budget_still_rejects_an_incomplete_tool_call(monkeypatch):
    payload = response(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
                       output=[function(definition(), arguments={"path": "C:/synthetic-fixture/index.html", "text": "partial"},
                                        status="in_progress")],
                       usage={"input_tokens": 200, "output_tokens": 128000, "total_tokens": 128200})
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [payload], engine_config=load_cloud_config())
    try:
        result = engine.respond_with_capabilities([{"role": "user", "content": "Write the synthetic fixture."}],
                                                  (definition(),))
        assert result.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED
        assert not result.capability_calls and result.openai_response is None
        assert result.completion.incomplete
    finally:
        engine.close()
    assert client.is_closed()
