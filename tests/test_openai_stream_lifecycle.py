"""Queued lifecycle events through the real SDK with an isolated HTTP transport."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.agent.contracts import AgentRunStatus
from app.inference.completion import IncompleteResponseError
from app.inference.protocol import ModelResponseKind
from tests.test_agent_runtime import build_runtime, run
from tests.test_cloud_inference import capability_definition
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import response
from tests.test_openai_streaming import MESSAGES, Stream, events, make_engine, streaming_response
from tests.test_openai_tools import function


def queued_events(payload=None, *, terminal=True, progress=True):
    values = deepcopy(events(payload, terminal=terminal))
    created = values[0]
    queued = {"type": "response.queued", "response": {**created["response"], "status": "queued"}}
    lifecycle = [queued]
    if progress:
        lifecycle.append({"type": "response.in_progress", "response": created["response"]})
    values[1:1] = lifecycle
    return numbered(values)


def numbered(values):
    return [{**value, "sequence_number": sequence} for sequence, value in enumerate(values)]


def install_stream(make_engine, values, **settings):
    stream, requests = Stream(values), []
    def handle(request):
        requests.append(request)
        return streaming_response(stream)
    return make_engine(handle, **settings), stream, requests


@pytest.mark.parametrize("progress", [False, True])
def test_queued_text_accepts_matching_completion_without_replay(make_engine, progress):
    engine, stream, requests = install_stream(make_engine, queued_events(response("Done"), progress=progress))
    previews = []
    engine.set_text_observer(previews.append)
    answer = engine.respond(MESSAGES)
    assert answer == "Done" and previews[-1] == "Done"
    assert answer.completion.usage.total_tokens == 22
    assert len(requests) == 1 and stream.closed.is_set()


def test_queued_function_call_executes_exactly_once_after_terminal(make_engine, tmp_path):
    streams, requests, payloads = [], [], []
    def handle(request):
        requests.append(request)
        stream = Stream(payloads.pop(0))
        streams.append(stream)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    payloads.extend([
        queued_events(response(output=[function(definition, {"value": "once"})])),
        queued_events(response("Done")),
    ])
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.COMPLETED
        assert capability.values == ["once"] and len(journal.records) == 1
        assert len(requests) == 2 and not payloads
        assert all(stream.closed.is_set() for stream in streams)
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("mutation,expected", [
    ("identity", "invalid_identity"),
    ("missing_response", "invalid_identity"),
    ("status", "invalid_lifecycle"),
    ("sequence", "invalid_sequence"),
    ("missing_creation", "missing_creation"),
    ("duplicate", "invalid_lifecycle"),
    ("late", "invalid_lifecycle"),
    ("after_output", "invalid_lifecycle"),
    ("embedded_output", "invalid_lifecycle"),
    ("progress_identity", "invalid_identity"),
    ("progress_status", "invalid_lifecycle"),
    ("terminal_identity", "invalid_terminal"),
    ("terminal_status", "invalid_terminal"),
])
def test_invalid_queued_lifecycle_never_accepts_or_replays(make_engine, mutation, expected):
    values = queued_events()
    if mutation == "identity":
        values[1]["response"]["id"] = "different"
    elif mutation == "missing_response":
        values[1].pop("response")
    elif mutation == "status":
        values[1]["response"]["status"] = "completed"
    elif mutation == "sequence":
        values[1]["sequence_number"] += 1
    elif mutation == "missing_creation":
        values = numbered(values[1:])
    elif mutation == "duplicate":
        values = numbered(values[:2] + [deepcopy(values[1])] + values[2:])
    elif mutation == "late":
        values = numbered([values[0], values[2], values[1], *values[3:]])
    elif mutation == "after_output":
        values = numbered([values[0], values[3], values[1], *values[4:]])
    elif mutation == "embedded_output":
        values[1]["response"]["output"] = response()["output"]
    elif mutation == "progress_identity":
        values[2]["response"]["id"] = "different"
    elif mutation == "progress_status":
        values[2]["response"]["status"] = "queued"
    elif mutation == "terminal_identity":
        values[-1]["response"]["id"] = "different"
    elif mutation == "terminal_status":
        values[-1]["response"]["status"] = "incomplete"
    engine, stream, requests = install_stream(make_engine, values, max_retries=3)
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.completion.failure_reason == expected
    assert caught.value.completion.observed_function_call is False
    assert len(requests) == 1 and stream.closed.is_set()


@pytest.mark.parametrize("with_output", [False, True])
def test_queued_stream_still_requires_terminal_and_knows_if_a_function_was_seen(make_engine, with_output):
    payload = response(output=[function()]) if with_output else response()
    values = queued_events(payload, terminal=False)
    if not with_output:
        values = values[:2]  # A queued response itself provides no answer or call.
    engine, stream, requests = install_stream(make_engine, values, max_retries=3)
    result = engine.respond_with_capabilities(MESSAGES, (capability_definition(),))
    assert result.kind == ModelResponseKind.PROTOCOL_FAILURE and not result.capability_calls
    assert result.openai_response is None
    assert result.completion.failure_reason == "stream_ended"
    assert result.completion.observed_function_call is with_output
    assert result.completion.request_phase == "reply"
    assert len(requests) == 1 and stream.closed.is_set()


def test_queued_unknown_executable_event_still_cannot_dispatch(make_engine, tmp_path):
    engine, stream, requests = install_stream(make_engine, [], max_retries=3)
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    values = queued_events(response(output=[function(definition, {"value": "never"})]))
    values.insert(-1, {"type": "response.code_interpreter_call.in_progress", "item_id": "private-item",
                       "output_index": 1})
    stream.values = numbered(values)
    try:
        result = run(runtime, tmp_path)
        assert result.status != AgentRunStatus.COMPLETED
        assert result.completion.failure_reason == "unsupported_event"
        assert result.completion.observed_function_call is True
        assert capability.values == [] and journal.records == ()
        assert len(requests) == 1 and stream.closed.is_set()
    finally:
        runtime.shutdown()


def test_queued_preserves_image_endpoint_capability_boundary(make_engine, tmp_path):
    from app.conversation.attachments import AttachmentStore
    payload = image_payload()
    engine, stream, requests = install_stream(make_engine, queued_events(payload))
    engine.set_attachment_store(AttachmentStore(tmp_path / "attachments"))
    result = engine.generate_images(MESSAGES)
    assert len(result.generated_images) == 1
    assert len(requests) == 1 and stream.closed.is_set()


@pytest.mark.parametrize("limit", ["events", "bytes"])
def test_queued_does_not_bypass_existing_protocol_bounds(make_engine, monkeypatch, limit):
    from app.inference import openai_stream
    values = queued_events()
    # Creation fits; the next queue notification crosses the selected bound.
    if limit == "events":
        monkeypatch.setattr(openai_stream, "_MAX_EVENTS", 1)
    else:
        import json
        first_bytes = len(json.dumps(values[0], ensure_ascii=False, allow_nan=False).encode())
        monkeypatch.setattr(openai_stream, "_MAX_EVENT_BYTES", first_bytes + 1)
    engine, stream, requests = install_stream(make_engine, values)
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.completion.failure_reason == "protocol_limit"
    assert len(requests) == 1 and stream.closed.is_set()
