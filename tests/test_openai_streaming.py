"""Real async SDK/SSE coverage for stream completion, Stop and retry ownership."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from threading import Event
from time import monotonic

import httpx
import openai
import pytest

from app.agent.contracts import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.completion import IncompleteResponseError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.protocol import ModelResponseKind
from app.runtime.cancellation import CancellationSource
from app.settings.agent import AgentRuntimeLimits
from tests.test_agent_runtime import build_runtime, run
from tests.test_cloud_inference import capability_definition
from tests.test_openai_phase1 import config, response, sse_response
from tests.test_openai_tools import function

MESSAGES = [{"role": "user", "content": "Synthetic streaming probe."}]


def events(payload=None, *, terminal=True):
    payload = payload or response()
    values = [{"type": "response.created", "response": {**payload, "status": "in_progress", "output": []}}]
    for index, item in enumerate(payload["output"]):
        staged = {**item, "status": "in_progress"}
        if item["type"] == "message":
            staged["content"] = []
        elif item["type"] == "function_call":
            staged["arguments"] = ""
        values.append({"type": "response.output_item.added", "output_index": index, "item": staged})
        if item["type"] == "message":
            for part_index, part in enumerate(item["content"]):
                field = "text" if part["type"] == "output_text" else "refusal"
                values.append({"type": "response.content_part.added", "output_index": index,
                    "content_index": part_index, "item_id": item["id"], "part": {**part, field: ""}})
                values.append({"type": "response." + part["type"] + ".delta", "output_index": index,
                    "content_index": part_index, "item_id": item["id"], "delta": part[field], "logprobs": []})
        elif item["type"] == "function_call":
            values.append({"type": "response.function_call_arguments.delta", "output_index": index,
                "item_id": item["id"], "delta": item["arguments"]})
        elif item["type"] == "reasoning":
            values.append({"type": "response.reasoning_summary_text.delta", "output_index": index,
                "item_id": item["id"], "summary_index": 0, "delta": "private-reasoning-summary"})
        values.append({"type": "response.output_item.done", "output_index": index, "item": item})
    if terminal:
        values.append({"type": "response." + payload["status"], "response": payload})
    return [{**value, "sequence_number": sequence} for sequence, value in enumerate(values)]


def encode(values):
    return b"".join(("data: " + json.dumps(value) + "\n\n").encode() for value in values)


class Stream(httpx.AsyncByteStream):
    def __init__(self, values, *, hold=False, failure=None):
        self.values, self.hold, self.failure = values, hold, failure
        self.waiting, self.closed = Event(), Event()

    async def __aiter__(self):
        for value in self.values:
            yield encode([value])
        self.waiting.set()
        if self.failure:
            raise self.failure("private-stream-failure")
        if self.hold:
            await asyncio.Future()

    async def aclose(self):
        self.closed.set()


@pytest.fixture
def make_engine(monkeypatch):
    owned = []
    real_http = openai.DefaultAsyncHttpxClient
    def make(handler, **settings):
        def http_factory(**kwargs):
            return real_http(transport=httpx.MockTransport(handler), **kwargs)
        monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", http_factory)
        engine = OpenAIResponsesInferenceEngine(config(**settings), api_key="fake-never-live")
        owned.append(engine)
        return engine
    yield make
    for engine in owned:
        engine.close()


def streaming_response(stream):
    return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})


def test_text_preview_precedes_terminal_and_final_usage_and_replay_survive(make_engine):
    payload = response("visible answer", output=[{"type": "reasoning", "id": "rs_test",
        "summary": [], "encrypted_content": "private-cipher"}, *response("visible answer")["output"]])
    stream = Stream(events(payload))
    engine = make_engine(lambda request: streaming_response(stream))
    previews = []
    engine.set_text_observer(previews.append)
    answer = engine.respond(MESSAGES)
    assert answer == "visible answer" and previews[0] == "" and previews[-1] == answer
    assert "private" not in "".join(previews)
    assert answer.completion.usage.total_tokens == 22
    assert answer.openai_response.items()[0]["encrypted_content"] == "private-cipher"
    assert stream.closed.is_set()


@pytest.mark.parametrize("failure", [None, httpx.ReadError, httpx.ReadTimeout])
def test_interrupted_stream_keeps_text_with_unknown_usage_and_never_retries(make_engine, failure, caplog):
    stream = Stream(events(response("partial  "), terminal=False), failure=failure)
    requests = []
    def handle(request):
        requests.append(request)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.partial_text == "partial  "
    assert caught.value.completion.interrupted and caught.value.completion.usage.total_tokens is None
    assert len(requests) == 1 and stream.closed.is_set()
    assert "private-stream-failure" not in str(caught.value) + caplog.text


@pytest.mark.parametrize("mutation", ["sequence", "identity", "item", "delta", "unknown", "json"])
def test_invalid_stream_never_accepts_its_terminal(make_engine, mutation):
    values = events()
    if mutation == "sequence":
        values[-1]["sequence_number"] += 1
    elif mutation == "identity":
        values[-1]["response"]["id"] = "wrong"
    elif mutation == "item":
        values[-1]["response"]["output"][0]["id"] = "wrong"
    elif mutation == "delta":
        values[3]["item_id"] = "wrong"
    elif mutation == "unknown":
        values[3]["type"] = "response.hosted_tool.delta"
    body = encode(values) if mutation != "json" else encode(values[:4]) + b"data: {broken-private\n\n"
    engine = make_engine(lambda request: httpx.Response(200, content=body,
        headers={"content-type": "text/event-stream"}))
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.completion.incomplete and "private" not in str(caught.value)


def test_tool_arguments_are_private_and_incomplete_calls_cannot_execute(make_engine):
    definition = capability_definition()
    payload = response(output=[function(definition, {"path": "private-tool-path"})])
    stream = Stream(events(payload, terminal=False))
    engine = make_engine(lambda request: streaming_response(stream), max_retries=3)
    previews = []
    engine.set_text_observer(previews.append)
    result = engine.respond_with_capabilities(MESSAGES, (definition,))
    assert result.kind == ModelResponseKind.PROTOCOL_FAILURE and not result.capability_calls
    assert result.openai_response is None and result.completion.incomplete
    assert "private-tool-path" not in "".join(previews)


def test_tool_call_waits_for_terminal_before_runtime_execution(make_engine, tmp_path):
    # Feed complete arguments and item.done, then hold the socket before the terminal.
    engine = make_engine(lambda request: streaming_response(stream))
    runtime, _, capability, _, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    stream = Stream(events(response(output=[function(definition, {"value": "hello"})]), terminal=False), hold=True)
    source = CancellationSource()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, runtime, tmp_path, cancellation=source.token)
        try:
            assert stream.waiting.wait(3)
            assert capability.values == []
        finally:
            source.cancel("Stop")
            engine.cancel_current_request()
        result = future.result(timeout=3)
    assert result.status == AgentRunStatus.CANCELLED and capability.values == []
    assert stream.closed.is_set()
    runtime.shutdown()


@pytest.mark.parametrize("stage", ["headers", "body", "backoff"])
def test_stop_interrupts_pending_io_or_sdk_delay_and_next_request_works(make_engine, stage):
    waiting = Event()
    stream = Stream(events(response("partial"), terminal=False), hold=True)
    calls = []
    async def handle(request):
        calls.append(request)
        if len(calls) > 1:
            return sse_response(response("next response"))
        if stage == "headers":
            waiting.set()
            await asyncio.Future()
        if stage == "backoff":
            waiting.set()
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}, headers={"retry-after": "30"})
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.respond, MESSAGES)
        try:
            assert (stream.waiting if stage == "body" else waiting).wait(3)
        finally:
            started = monotonic()
            engine.cancel_current_request()
            engine.cancel_current_request()
        with pytest.raises(IncompleteResponseError) as caught:
            future.result(timeout=2)
    assert monotonic() - started < 2
    assert caught.value.completion.finish_reason == "cancelled"
    assert caught.value.partial_text == ("partial" if stage == "body" else None)
    assert len(calls) == 1
    if stage == "body":
        assert stream.closed.is_set()
    assert engine.respond(MESSAGES) == "next response"
    runner, client = engine._runner, engine._client
    engine.close()
    assert client.is_closed() and not runner._thread.is_alive()


@pytest.mark.parametrize("operation", ["close", "key"])
def test_shutdown_and_key_replacement_release_active_request_and_owned_thread(make_engine, operation):
    stream = Stream(events(terminal=False), hold=True)
    engine = make_engine(lambda request: streaming_response(stream))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.respond, MESSAGES)
        assert stream.waiting.wait(3)
        runner, client = engine._runner, engine._client
        if operation == "close":
            engine.close()
        else:
            engine.set_api_key("replacement-fake")
        with pytest.raises(IncompleteResponseError):
            future.result(timeout=2)
    assert stream.closed.is_set() and client.is_closed() and not runner._thread.is_alive()


@pytest.mark.parametrize("status,code,expected_calls", [
    (429, "rate_limit_exceeded", 3), (500, "server_error", 3),
    (429, "insufficient_quota", 1), (401, "invalid_api_key", 1), (400, "invalid_parameter", 1),
])
def test_sdk_is_only_bounded_retry_owner_and_does_not_retry_permanent_errors(make_engine, status, code, expected_calls):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": code, "message": "private-error"}},
                              headers={"retry-after-ms": "1"})
    engine = make_engine(handle, max_retries=2)
    with pytest.raises(CloudInferenceError) as caught:
        engine.respond(MESSAGES)
    assert len(calls) == expected_calls and "private-error" not in str(caught.value)
    assert all(json.loads(request.content)["model"] == "gpt-6-luna" for request in calls)


def test_whole_request_deadline_also_bounds_retry_after_delay(make_engine):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}, headers={"retry-after": "30"})
    engine = make_engine(handle, max_retries=5, timeout_seconds=5)
    started = monotonic()
    with pytest.raises(CloudInferenceError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.code == CloudErrorCode.TIMEOUT and len(calls) == 1
    assert 4.5 < monotonic() - started < 7


def test_chat_stop_preserves_partial_text_and_clears_preview_observer(make_engine, tmp_path):
    stream = Stream(events(response("partial text  "), terminal=False), hold=True)
    engine = make_engine(lambda request: streaming_response(stream))
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store)
    previews = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.run, "Synthetic chat probe", text_observer=previews.append)
        try:
            assert stream.waiting.wait(3)
        finally:
            service.cancel_current_task()
        with pytest.raises(IncompleteResponseError) as caught:
            future.result(timeout=2)
    assert caught.value.partial_text == "partial text  " and previews[-1] == "partial text  "
    assert engine._text_observer is None
    assert store.messages()[-1]["content"] == "partial text  "
    assert store._conversation.turns[-1].outcome.status == AgentRunStatus.CANCELLED
    reopened = ConversationStore(tmp_path / "conversation.json")
    assert reopened._conversation.messages[-1].completion.finish_reason == "cancelled"


def test_overall_agent_deadline_preserves_timeout_status_and_partial_text(make_engine, tmp_path):
    stream = Stream(events(response("partial"), terminal=False), hold=True)
    engine = make_engine(lambda request: streaming_response(stream))
    runtime, _, capability, _, _ = build_runtime(tmp_path, [], model=engine,
        limits=AgentRuntimeLimits(overall_timeout_seconds=0.4))
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.TIMED_OUT and result.partial_text == "partial"
    assert result.completion.interrupted and stream.closed.is_set() and capability.values == []
    runtime.shutdown()


def test_disconnect_before_created_event_is_incomplete_not_safe_to_fallback(make_engine):
    stream = Stream([], failure=httpx.ReadError)
    engine = make_engine(lambda request: streaming_response(stream), max_retries=3)
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.completion.incomplete and stream.closed.is_set()


def test_stop_before_transport_starts_does_not_send_and_does_not_poison_next_turn(make_engine):
    calls = []
    def handle(request):
        calls.append(request)
        return sse_response(response())
    engine = make_engine(handle)
    source = CancellationSource()
    engine.set_request_cancellation(source.token)
    source.cancel("Stop")
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.completion.finish_reason == "cancelled" and calls == []
    engine.set_request_cancellation(None)
    assert engine.respond(MESSAGES) == "hello" and len(calls) == 1


def test_preview_is_plain_text_temporary_and_late_chunks_are_ignored():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt = pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import Qt
    from app.ui.chat import ChatView
    from app.ui.main_window import MainWindow
    app = qt.QApplication.instance() or qt.QApplication([])
    view = ChatView()
    view.set_thinking(True)
    view.set_stream_preview("<b>partial</b> ```python")
    assert view.stream_preview.textFormat() == Qt.TextFormat.PlainText
    assert view.stream_preview.text() == "<b>partial</b> ```python" and len(view._messages) == 0
    view.set_thinking(False)
    view.add_message("Agent", "final response")
    view.set_stream_preview("late")
    assert view.stream_preview.text() == "" and len(view._messages) == 1
    window = MainWindow(None, "TEST")
    window._preview_active = False
    window._stream_preview("late")
    assert window.chat.stream_preview.text() == ""
    window.close()
    view.close()
    app.processEvents()
