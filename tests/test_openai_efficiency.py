"""Context pressure, stable cache prefixes and numeric-only Responses accounting."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import logging
from types import SimpleNamespace

import httpx
import pytest

from app.agent.contracts import AgentRunStatus
from app.conversation.context import calculate_context_budget, count_message_tokens, select_context_request
from app.conversation.orchestrator import ConversationService
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore
from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.completion import CompletionMetadata, IncompleteResponseError, TokenUsage
from app.inference.hybrid import HybridInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine, normalize_text_response
from app.inference.openai_context import context_input_items, estimate_input_tokens
from app.inference.openai_metrics import OpenAIRequestMetrics, RequestMeasurement
from app.inference.openai_replay import REPLAY_KEY
from app.inference.openai_tools import responses_input
from app.inference.protocol import ModelCapabilityCall
from app.settings.openai_cloud import OpenAIModelProfile
from tests.test_agent_runtime import EchoCapability, build_runtime, run
from tests.test_cloud_inference import capability_definition
from tests.test_openai_phase1 import config, response, sse_response
from tests.test_openai_replay import definition_for, evidence, history_for, message, reasoning
from tests.test_openai_streaming import Stream, events, make_engine, streaming_response, MESSAGES
from tests.test_openai_tools import function, scripted_sdk


def replay_history(text_size=400):
    definition = capability_definition()
    call = ModelCapabilityCall(provider_call_id="call_exact_1", capability=definition.name, arguments={"path": "probe.txt"})
    raw = evidence([reasoning(), message("Working", "msg_work", "commentary"), function()])
    history = [{"role": "system", "content": "Exact policy"}, {"role": "user", "content": "Keep all requirements: SESSION_MARKER"},
               *history_for(raw, (call,))]
    history[-1]["result"]["output"] = {"content": "start " + "x" * text_size + " SESSION_MARKER=expected end",
                                        "path": "C:/exact/file.txt", "content_is_untrusted": True}
    return history, definition


def test_fitting_openai_history_is_preserved_even_with_large_tool_result():
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    history, definition = replay_history(12_000)
    before = deepcopy(history)
    recovered = recover_context_request(engine, history, reserved_tokens=engine.count_capability_schema_tokens((definition,)))
    assert recovered.budget.fits and recovered.messages == before
    assert recovered.projected_results == 0 and not recovered.compacted and history == before
    engine.close()


def test_pressure_projects_results_preserving_raw_items_calls_requirements_and_durable_evidence():
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    history, definition = replay_history(130_000)
    original = deepcopy(history)
    assert not calculate_context_budget(engine, history).fits
    recovered = recover_context_request(engine, history, reserved_tokens=engine.count_capability_schema_tokens((definition,)))
    assert recovered.budget.fits and recovered.projected_results == 1
    assert history == original and recovered.messages[:-1] == original[:-1]
    result = recovered.messages[-1]["result"]
    assert result["success"] is True and result["output"]["path"] == "C:/exact/file.txt"
    assert "SESSION_MARKER=expected" in result["output"]["content"]
    assert result["metadata"]["context_projection"]["complete"] is False
    wire = responses_input(recovered.messages, (definition,), model_id=engine.active_model)
    assert wire[2:5] == evidence([reasoning(), message("Working", "msg_work", "commentary"), function()]).items()
    assert wire[-1]["call_id"] == "call_exact_1"
    assert "context_projection" in json.loads(wire[-1]["output"])["metadata"]
    engine.close()


def test_protected_raw_assistant_and_opaque_evidence_are_never_compacted():
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    raw = evidence([reasoning(), message("x" * 100_000)])
    history = [{"role": "system", "content": "exact policy"}, {"role": "user", "content": "earlier requirement"},
        {"role": "assistant", "content": raw.text, REPLAY_KEY: raw.model_dump()},
        {"role": "user", "content": "current exact requirement"}]
    recovered = recover_context_request(engine, history)
    assert not recovered.budget.fits and recovered.messages == history and not recovered.compacted
    engine.close()


@pytest.mark.parametrize("recovery_enabled", [False, True])
def test_oversized_user_requirements_stop_instead_of_silent_truncation(recovery_enabled):
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    history = [{"role": "user", "content": "Exact requirement " * 10_000}]
    selected = select_context_request(engine, system_prompt="Exact policy", history=history, recovery_enabled=recovery_enabled)
    assert selected.messages == [{"role": "system", "content": "Exact policy"}, *history]
    assert not selected.budget.fits
    engine.close()


def test_disabled_recovery_admits_no_projection_under_pressure():
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    history, _ = replay_history(130_000)
    selected = select_context_request(engine, system_prompt="policy", history=history[1:], recovery_enabled=False)
    assert selected.messages[1:] == history[1:] and not selected.budget.fits
    engine.close()


def test_raw_items_are_counted_once_unicode_as_utf8_and_cipher_as_opaque_reserve():
    engine = OpenAIResponsesInferenceEngine(config(), api_key="fake")
    raw = evidence([reasoning(), message("visible" * 200)])
    source = {"role": "assistant", "content": raw.text, REPLAY_KEY: raw.model_dump()}
    assert count_message_tokens(engine, [source]) == estimate_input_tokens(raw.items())
    assert count_message_tokens(engine, [{"role": "user", "content": "界" * 100}]) > count_message_tokens(engine,
        [{"role": "user", "content": "x" * 100}])
    big_cipher = {**reasoning(), "encrypted_content": "a" * 10_000}
    assert estimate_input_tokens([big_cipher]) > 10_000
    engine.select_model("gpt-6.1-sol")
    assert context_input_items([source], engine.active_model) == [{"role": "assistant", "content": raw.text}]
    engine.close()


def test_final_wire_admission_rejects_direct_oversized_requests_without_network(make_engine):
    requests = []
    def forbidden(request):
        requests.append(request)
        pytest.fail("An oversized request cannot reach the network")
    engine = make_engine(forbidden)
    with pytest.raises(CloudInferenceError) as caught:
        engine.respond([{"role": "user", "content": "x" * 100_000}])
    assert caught.value.code == CloudErrorCode.CONTEXT_OVERFLOW
    assert not caught.value.allow_local_fallback and requests == [] and engine._client is None


def detailed_payload():
    return response(usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
        "input_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 20},
        "output_tokens_details": {"reasoning_tokens": 12}})


def test_cached_and_reasoning_subsets_do_not_reduce_input_occupancy_or_inflate_output():
    result = normalize_text_response(detailed_payload())
    assert result.completion.usage == TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120,
        cached_input_tokens=60, cache_write_tokens=20, reasoning_tokens=12)
    assert result.completion.usage.total_tokens == 120


@pytest.mark.parametrize("field,value", [("cached_tokens", True), ("cached_tokens", "private-secret"),
    ("cached_tokens", -1), ("cached_tokens", 101), ("cache_write_tokens", 60), ("reasoning_tokens", 21)])
def test_bad_or_inconsistent_detail_counts_are_unknown_not_coerced(field, value):
    payload = detailed_payload()
    section = "output_tokens_details" if field == "reasoning_tokens" else "input_tokens_details"
    payload["usage"][section][field] = value
    result = normalize_text_response(payload)
    attribute = {"cached_tokens": "cached_input_tokens", "cache_write_tokens": "cache_write_tokens",
                 "reasoning_tokens": "reasoning_tokens"}[field]
    assert getattr(result.completion.usage, attribute) is None
    assert result.completion.usage.total_tokens == 120
    assert "private-secret" not in str(result.completion.model_dump())


def test_missing_usage_details_remain_unknown_and_explicit_zero_stays_zero():
    assert normalize_text_response(response()).completion.usage.cached_input_tokens is None
    payload = detailed_payload()
    payload["usage"]["input_tokens_details"] = {"cached_tokens": 0, "cache_write_tokens": 0}
    payload["usage"]["output_tokens_details"] = {"reasoning_tokens": 0}
    usage = normalize_text_response(payload).completion.usage
    assert usage.cached_input_tokens == usage.cache_write_tokens == usage.reasoning_tokens == 0
    assert CompletionMetadata.model_validate({"usage": {"input_tokens": 2}}).usage.cached_input_tokens is None


def test_measurement_has_numeric_only_separate_queue_and_stream_times():
    clock = iter([1.0, 1.05, 1.2, 1.3, 2.0])
    measurement = RequestMeasurement(clock=lambda: next(clock))
    measurement.start()
    state = SimpleNamespace(partial_text=None)
    measurement.observe(state)
    state.partial_text = "private-text"
    measurement.observe(state)
    metrics = measurement.finish("completed")
    assert metrics.queue_ms == 50 and metrics.duration_ms == 950
    assert metrics.first_event_ms == 150 and metrics.first_text_ms == 250
    assert "private" not in metrics.model_dump_json()
    with pytest.raises(ValueError):
        OpenAIRequestMetrics(outcome="private-text", attempts=1, queue_ms=0.0, duration_ms=1.0)
    with pytest.raises(ValueError):
        OpenAIRequestMetrics(outcome="completed", attempts=1, queue_ms=0.0, duration_ms=float("nan"))


def test_metrics_usage_and_cache_details_persist_and_same_limit_switch_invalidates_meter(monkeypatch, tmp_path):
    engine, client, _, _ = scripted_sdk(monkeypatch, [detailed_payload()])
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store)
    answer = service.run("Synthetic probe")
    metrics = answer.completion.request_metrics
    assert metrics == engine.last_request_metrics and metrics.attempts == 1 and metrics.outcome == "completed"
    assert metrics.duration_ms >= metrics.first_event_ms >= 0 and metrics.first_text_ms is None  # terminal-only fixture
    assert service.reported_context_tokens() == 120
    restored = ConversationStore(store.path)._conversation.messages[-1].completion
    assert restored == answer.completion and restored.usage.cached_input_tokens == 60
    engine.select_model("gpt-6.1-sol")
    assert engine.context_length == 32768 and service.reported_context_tokens() is None
    engine.select_model("gpt-6-luna")
    assert service.reported_context_tokens() is None
    engine.close()
    assert client.is_closed()


def test_pool_reuse_updates_each_request_hook_and_prefix_is_exactly_append_only(make_engine):
    bodies = []
    def handle(request):
        bodies.append(json.loads(request.content))
        return sse_response(response(id=f"resp_{len(bodies)}", output=[message(f"Answer {len(bodies)}", f"msg_{len(bodies)}")]))
    engine = make_engine(handle)
    first = engine.respond(MESSAGES)
    transcript = [*MESSAGES, {"role": "assistant", "content": str(first), REPLAY_KEY: first.openai_response.model_dump()},
                  {"role": "user", "content": "next"}]
    second = engine.respond(transcript)
    assert first.completion.request_metrics.attempts == second.completion.request_metrics.attempts == 1
    assert bodies[1]["input"][:len(bodies[0]["input"])] == bodies[0]["input"]
    assert bodies[1]["input"][1] == first.openai_response.items()[0]
    for body in bodies:
        assert not {"prompt_cache_key", "prompt_cache_retention", "prompt_cache_options", "context_management", "previous_response_id"} & body.keys()
        assert body["store"] is False and body["truncation"] == "disabled"


def test_metrics_include_sdk_attempts_and_do_not_log_private_data(make_engine, caplog):
    requests = []
    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(500, json={"error": {"message": "private-provider-body"}}, headers={"retry-after-ms": "1"})
        return streaming_response(Stream(events(detailed_payload())))
    engine = make_engine(handle, max_retries=1)
    with caplog.at_level(logging.INFO):
        result = engine.respond([{ "role": "user", "content": "private-user-text"}])
    metrics = result.completion.request_metrics
    assert metrics.attempts == 2 and metrics.first_text_ms >= metrics.first_event_ms
    assert "cached_input_tokens=60" in caplog.text and "reasoning_tokens=12" in caplog.text
    assert all(value not in caplog.text for value in ["private-provider-body", "private-user-text", "fake-never-live", "resp_test", "msg_test"])


def test_cancelled_metrics_have_partial_timing_but_unknown_token_usage(make_engine):
    stream = Stream(events(response("partial"), terminal=False), hold=True)
    engine = make_engine(lambda request: streaming_response(stream))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.respond, MESSAGES)
        try:
            assert stream.waiting.wait(3)
        finally:
            engine.cancel_current_request()
        with pytest.raises(IncompleteResponseError) as caught:
            future.result(timeout=2)
    completion = caught.value.completion
    assert completion.request_metrics.outcome == "cancelled" and completion.request_metrics.attempts == 1
    assert completion.request_metrics.first_text_ms is not None and completion.usage.cached_input_tokens is None
    assert caught.value.completion_history[-1] == completion


def test_hybrid_identity_changes_on_cloud_profile_switch_without_changing_mode(make_engine, tmp_path):
    engine = make_engine(lambda request: sse_response(detailed_payload()))
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode="cloud")
    service = ConversationService(hybrid, ConversationStore(tmp_path / "conversation.json"))
    service.run("Synthetic probe")
    assert service.reported_context_tokens() == 120
    engine.select_model("gpt-6.1-sol")
    assert hybrid.mode == "cloud" and service.reported_context_tokens() is None
    assert count_message_tokens(hybrid, MESSAGES) == count_message_tokens(engine, MESSAGES)
    hybrid.close()


def test_real_runtime_projects_large_settled_output_without_reexecuting_or_mutating_journal(monkeypatch, tmp_path):
    class WideEcho(EchoCapability):
        def execute(self, arguments, context):
            super().execute(arguments, context)
            return {"content": "x" * 60_000, "content_is_untrusted": True}
    capability = WideEcho()
    definition = definition_for(capability)
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [
        response(output=[reasoning(), function(definition, {"value": "once"})]),
        response(id="resp_final", output=[message("Done", "msg_done")])], engine_config=config(profiles=(
            OpenAIModelProfile(id="gpt-6-luna", context_length=8192, max_input_tokens=7168, max_output_tokens=1024),)))
    runtime, _, _, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine)
    runtime.context_recovery_enabled = True  # Explicit fixture setting, no production config change.
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.COMPLETED and capability.values == ["once"]
    assert result.context_projections == 1 and len(journal.records) == 1 and len(bodies) == 2
    assert bodies[1]["input"][1:3] == [reasoning(), function(definition, {"value": "once"})]
    projected = json.loads(bodies[1]["input"][-1]["output"])
    assert projected["metadata"]["context_projection"]["complete"] is False
    assert len(result.settled_calls[0].result.output["content"]) == 60_000
    runtime.shutdown()
    engine.close()
    assert client.is_closed()
