"""Rate admission, ownership and SDK pacing without paid API requests."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from time import monotonic

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError
from app.inference.completion import IncompleteResponseError, TokenUsage
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.openai_rate_limits import OpenAIRatePacer
from app.settings.cloud import load_cloud_config
from app.settings.openai_cloud import OpenAIRateLimits
from tests.test_openai_phase1 import config, response, sse_response
from tests.test_openai_streaming import MESSAGES, Stream, events, make_engine, streaming_response
from tests.test_agent_runtime import build_runtime, run
from tests.test_openai_tools import function


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def limits(tokens=200_000, requests=500):
    return {"gpt-6-luna": OpenAIRateLimits(requests_per_minute=requests, tokens_per_minute=tokens)}


def headers(resource, limit, remaining, reset):
    return {f"x-ratelimit-limit-{resource}": str(limit), f"x-ratelimit-remaining-{resource}": str(remaining),
        f"x-ratelimit-reset-{resource}": reset, "authorization": "private-secret", "x-request-id": "private-id"}


def test_account_limits_load_from_local_state_without_changing_accepted_profile(tmp_path):
    settings = load_cloud_config()
    assert settings.profile("gpt-6-luna").max_output_tokens == 128_000
    assert not config().rate_limits  # Older configuration still loads.
    path = tmp_path / "limits.json"
    path.write_text(json.dumps({"schema_version": 1, "models": {
        model: value.model_dump() for model, value in limits().items()}}), encoding="utf-8")
    engine = OpenAIResponsesInferenceEngine(settings, api_key="fake-never-live", rate_limits_path=path)
    try:
        assert engine._rate_pacer.budgets["gpt-6-luna"].tokens == 200_000
        assert engine._rate_pacer.budgets["gpt-6-luna"].requests == 500
        assert engine.config == settings and not settings.rate_limits
    finally:
        engine.close()
    with pytest.raises(ValidationError):
        config(rate_limits={"unknown": limits()["gpt-6-luna"]})


def test_reproduced_21_call_pattern_finishes_with_pacing_and_exact_same_wire_settings(make_engine):
    clock, requests, sent = Clock(), [], []
    token_inputs = [5699, 6565, 7484, 8404, 9199, 9985, 10802, 12146, 12910, 13211,
        13844, 15616, 15912, 16178, 16705, 18645, 20605, 22602, 23599, 23773, 24006]
    settings = load_cloud_config().model_copy(update={"rate_limits": limits()})
    def handle(request):
        requests.append(json.loads(request.content))
        # Admission reserves the unchanged maximum output, with room for input.
        assert sum(entry.tokens for entry in pacer.budgets["gpt-6-luna"].ledger) <= 200_000
        sent.append(clock.now)
        count = token_inputs[len(requests) - 1]
        clock.now += 2.0
        return sse_response(response(id=f"resp_{len(requests)}", usage={
            "input_tokens": count, "output_tokens": 100, "total_tokens": count + 100,
            "input_tokens_details": {"cached_tokens": count - 200}}))
    engine = make_engine(handle, **settings.model_dump(exclude={"profiles"}), profiles=settings.profiles)
    pacer = engine._rate_pacer = OpenAIRatePacer(settings.rate_limits, clock=clock, sleep=clock.sleep)
    answers = [engine.respond(MESSAGES) for _ in token_inputs]
    assert len(answers) == len(requests) == 21 and all(answer == "hello" for answer in answers)
    assert clock.waits and sent[-1] - sent[0] > 60
    assert all(body["max_output_tokens"] == 128_000 and body["store"] is False for body in requests)
    assert all(answer.completion.request_metrics.attempts == 1 for answer in answers)
    assert sum(entry.tokens for entry in pacer.budgets["gpt-6-luna"].ledger) < 128_000


@pytest.mark.parametrize("resource", ["requests", "tokens", "project-tokens"])
def test_server_reset_header_delays_the_next_wire_request(make_engine, resource, caplog):
    clock, sent = Clock(), []
    def handle(request):
        sent.append(clock.now)
        value = sse_response(response())
        if len(sent) == 1:
            value.headers.update(headers(resource, 500 if resource == "requests" else 200_000, 0, "1m2.5s"))
        return value
    engine = make_engine(handle)
    engine._rate_pacer = OpenAIRatePacer(clock=clock, sleep=clock.sleep)
    caplog.set_level("INFO", logger="app.inference.openai_rate_limits")
    assert engine.respond(MESSAGES) == engine.respond(MESSAGES) == "hello"
    assert sent == [0, 62.5] and clock.waits == [62.5]
    assert "OpenAI rate wait" in caplog.text
    assert "private-secret" not in caplog.text and "private-id" not in caplog.text


def test_32_step_agent_finishes_after_rate_waits_without_repeating_tools(make_engine, tmp_path):
    clock, requests = Clock(), []
    settings = load_cloud_config().model_copy(update={"rate_limits": limits()})
    def handle(request):
        requests.append(json.loads(request.content))
        index = len(requests)
        clock.now += 2
        output = [function(definition, {"value": str(index)}, call_id=f"call_{index}")] if index < 32 else None
        payload = response("Done", id=f"resp_{index}", usage={"input_tokens": 24_006,
            "output_tokens": 48, "total_tokens": 24_054})
        if output is not None:
            payload["output"] = output
        return sse_response(payload)
    engine = make_engine(handle, **settings.model_dump(exclude={"profiles"}), profiles=settings.profiles)
    engine._rate_pacer = OpenAIRatePacer(settings.rate_limits, clock=clock, sleep=clock.sleep)
    runtime, _, capability, _, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.steps == 32
        assert outcome.capability_calls == 31 and len(requests) == 32
        assert capability.values == [str(index) for index in range(1, 32)]
        assert outcome.assistant_text == "Done" and clock.waits
    finally:
        runtime.shutdown()


def test_request_ledger_and_unknown_interrupted_usage_remain_reserved():
    clock = Clock()
    pacer = OpenAIRatePacer(limits(tokens=100, requests=2), clock=clock, sleep=clock.sleep)
    async def exercise():
        first = await pacer.acquire("gpt-6-luna", 50)
        pacer.settle(first, TokenUsage())
        second = await pacer.acquire("gpt-6-luna", 50)
        pacer.settle(second, TokenUsage(input_tokens=5, output_tokens=5, total_tokens=10))
        await pacer.acquire("gpt-6-luna", 50)
    asyncio.run(exercise())
    assert clock.waits == [60] and clock.now == 60


def test_impossible_request_stops_before_spending_tokens(make_engine):
    requests = []
    engine = make_engine(lambda request: requests.append(request), rate_limits=limits(tokens=100))
    with pytest.raises(CloudInferenceError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.code == CloudErrorCode.RATE_LIMIT and not requests
    assert engine.last_request_metrics.attempts == 0


def test_invalid_header_values_never_enter_diagnostics_or_override_limits(caplog):
    pacer = OpenAIRatePacer(limits())
    caplog.set_level("INFO", logger="app.inference.openai_rate_limits")
    for reset in ("private-text", "nan", "-1s", "999999h", "1s\nprivate", "1e3s"):
        pacer.observe("gpt-6-luna", headers("tokens", "private-number", 0, reset))
    assert not pacer.budgets["gpt-6-luna"].headers
    assert pacer.budgets["gpt-6-luna"].tokens == 200_000 and not caplog.text


def test_model_switch_retains_luna_debt_and_uses_current_model_response_headers(make_engine):
    clock, sent = Clock(), []
    def handle(request):
        model = json.loads(request.content)["model"]
        sent.append((model, clock.now))
        value = sse_response(response(model=model))
        if len(sent) == 1:
            value.headers.update(headers("tokens", 200_000, 0, "60s"))
        elif model == "gpt-6.1-sol":
            value.headers.update(headers("tokens", 300_000, 300_000, "0s"))
        return value
    engine = make_engine(handle)
    engine._rate_pacer = OpenAIRatePacer(clock=clock, sleep=clock.sleep)
    engine.respond(MESSAGES)
    engine.select_model("gpt-6.1-sol")
    engine.respond(MESSAGES)
    engine.select_model("gpt-6-luna")
    engine.respond(MESSAGES)
    assert sent == [("gpt-6-luna", 0), ("gpt-6.1-sol", 0), ("gpt-6-luna", 60)]
    assert engine._rate_pacer.budgets["gpt-6.1-sol"].tokens == 300_000
    assert engine._rate_pacer.budgets["gpt-6-luna"].tokens == 200_000


@pytest.mark.parametrize("operation", ["stop", "close", "key_change"])
def test_pending_rate_wait_is_cancellable_without_a_second_request_or_leaked_runner(make_engine, operation):
    requests, waiting = [], Event()
    def handle(request):
        requests.append(request)
        value = sse_response(response())
        value.headers.update(headers("tokens", 200_000, 0, "60s"))
        return value
    engine = make_engine(handle)
    engine.respond(MESSAGES)
    runner = engine._runner
    async def hold(seconds):
        waiting.set()
        await asyncio.Future()
    engine._rate_pacer.sleep = hold
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.respond, MESSAGES)
        assert waiting.wait(3)
        started = monotonic()
        if operation == "close":
            engine.close()
        elif operation == "key_change":
            engine.set_api_key("fake-replacement-never-live")
        else:
            engine.cancel_current_request()
        with pytest.raises(IncompleteResponseError) as caught:
            future.result(timeout=3)
        assert caught.value.completion.failure_reason == "cancelled"
        assert monotonic() - started < 2 and len(requests) == 1
    engine.close()
    assert not runner._thread.is_alive() and runner.client.is_closed()


def test_partial_rate_limited_stream_does_not_retry_or_refund_reservation(make_engine):
    requests = []
    values = events(response("private partial"), terminal=False)
    values.append({"type": "error", "code": "rate_limit_exceeded", "message": "private-provider-error",
        "param": None, "sequence_number": len(values)})
    def handle(request):
        requests.append(request)
        return streaming_response(Stream(values))
    engine = make_engine(handle, rate_limits=limits(), max_retries=3)
    with pytest.raises(IncompleteResponseError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.partial_text == "private partial"
    assert caught.value.completion.failure_reason == "provider_rate_limit" and len(requests) == 1
    assert engine._rate_pacer.budgets["gpt-6-luna"].ledger[0].tokens > engine.max_response_tokens


@pytest.mark.parametrize("completed", [True, False])
def test_long_stream_retains_output_capacity_for_a_minute_after_it_ends(completed):
    clock = Clock()
    pacer = OpenAIRatePacer(limits(), clock=clock, sleep=clock.sleep)
    async def exercise():
        reservation = await pacer.acquire("gpt-6-luna", 128_000)
        clock.now = 85  # Admission is older than a minute, recent output is not.
        usage = TokenUsage(input_tokens=20_000, output_tokens=80_000, total_tokens=100_000) if completed else None
        pacer.settle(reservation, usage)
        await pacer.acquire("gpt-6-luna", 128_000)
    asyncio.run(exercise())
    assert clock.waits == [60] and clock.now == 145


def test_rate_wait_respects_the_existing_whole_request_deadline(make_engine):
    requests = []
    def handle(request):
        requests.append(request)
        value = sse_response(response())
        value.headers.update(headers("tokens", 200_000, 0, "60s"))
        return value
    engine = make_engine(handle, timeout_seconds=5)
    engine.respond(MESSAGES)
    started = monotonic()
    with pytest.raises(CloudInferenceError) as caught:
        engine.respond(MESSAGES)
    assert caught.value.code == CloudErrorCode.TIMEOUT and len(requests) == 1
    assert engine.last_request_metrics.attempts == 0 and 4.5 < monotonic() - started < 7
