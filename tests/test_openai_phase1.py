from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.completion import IncompleteResponseError
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine, normalize_text_response
from app.runtime.skills.selection import SkillCandidate, select_skill
from app.settings.cloud import load_cloud_config
from app.settings.openai_cloud import OpenAICloudConfig, OpenAIModelCatalog, OpenAIModelProfile
from tests.test_cloud_inference import capability_definition


def config(**overrides):
    values = {
        "profiles": (
            OpenAIModelProfile(id="gpt-6-luna", temperature=0.1),
            OpenAIModelProfile(id="gpt-6.1-sol", reasoning_effort="medium"),
        ),
    }
    values.update(overrides)
    return OpenAICloudConfig(**values)


def response(text="hello", **overrides):
    result = {
        "id": "resp_test", "object": "response", "model": "gpt-6-luna",
        "created_at": 1, "status": "completed",
        "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                    "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": 14, "output_tokens": 8, "total_tokens": 22},
    }
    result.update(overrides)
    return result


def engine_with_transport(monkeypatch, payload=None, *, status=200, failure=None, engine_config=None):
    requests = []

    def handle(request):
        requests.append(request)
        if failure:
            raise failure(request)
        value = payload if payload is not None else response()
        return sse_response(value) if status == 200 else httpx.Response(status, json=value)

    transport = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = openai.AsyncOpenAI(api_key="test-key-never-live", base_url="https://api.openai.com/v1",
                          max_retries=0, http_client=transport)
    def http_factory(**kwargs):
        transport.event_hooks = kwargs["event_hooks"]
        return transport
    monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", http_factory)
    factory = Mock(return_value=client)
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    engine = OpenAIResponsesInferenceEngine(engine_config or config(), api_key="test-key-never-live")
    return engine, client, requests, factory


def sse_response(payload):
    created = {**payload, "status": "in_progress", "output": []}
    events = [{"type": "response.created", "sequence_number": 0, "response": created},
              {"type": "response." + payload.get("status", "completed"),
               "sequence_number": 1, "response": payload}]
    return httpx.Response(200, content="".join("data: " + json.dumps(event) + "\n\n" for event in events),
                          headers={"content-type": "text/event-stream", "x-request-id": "request-test"})


def test_checked_in_configuration_uses_luna_and_unqualified_bounded_profiles():
    settings = load_cloud_config()
    assert isinstance(settings, OpenAICloudConfig)
    assert settings.default_model == "gpt-6-luna"
    assert settings.default_mode == "local" and not settings.fallback_to_local
    assert settings.max_retries == 0
    assert all(not item.qualified for item in settings.profiles)
    assert settings.profile(settings.default_model).effective_context_length == 1050000
    assert settings.profile(settings.default_model).max_input_tokens == 922000
    assert settings.profile(settings.default_model).max_output_tokens == 128000
    assert settings.timeout_seconds == 1800
    sol = settings.profile("gpt-6.1-sol")
    assert sol.effective_context_length == 1050000
    assert sol.max_input_tokens == 1045904 and sol.max_output_tokens == 4096


@pytest.mark.parametrize("overrides", [
    {"id": "arbitrary-model"},
    {"context_length": 1_050_001},
    {"max_output_tokens": 128_001},
    {"max_input_tokens": 32768},
    {"id": "gpt-6.1-sol", "reasoning_effort": "none"},
    {"reasoning_effort": "medium", "temperature": 0.1},
    {"context_length": True},
    {"temperature": float("nan")},
])
def test_profiles_reject_unsupported_or_impossible_settings(overrides):
    with pytest.raises(ValueError):
        OpenAIModelProfile(**{"id": "gpt-6-luna", **overrides})


@pytest.mark.parametrize("overrides", [
    {"timeout_seconds": 1801},
    {"api_key": "must-not-be-configured"},
    {"base_url": "https://other.example/v1"},
    {"default_model": "unknown-model"},
    {"profiles": (OpenAIModelProfile(id="gpt-6-luna"),) * 2},
])
def test_cloud_config_rejects_credentials_unknown_profiles_and_endpoints(overrides):
    with pytest.raises(ValueError):
        config(**overrides)


def test_rejected_secret_configuration_does_not_echo_values_in_validation_errors():
    with pytest.raises(ValueError) as failure:
        config(api_key="private-rejected-key")
    assert "private-rejected-key" not in str(failure.value)
    with pytest.raises(ValueError) as failure:
        OpenAIModelProfile(id="gpt-6-luna", temperature="private-invalid-value")
    assert "private-invalid-value" not in str(failure.value)


def test_runtime_selection_is_id_only_and_profiles_are_unchanged(tmp_path):
    settings = config()
    before = settings.model_dump_json()
    selection_path = tmp_path / "cloud_model_selection_v1.json"
    catalog = OpenAIModelCatalog(settings, selection_path)
    assert catalog.current_id == "gpt-6-luna" and not selection_path.exists()
    catalog.select("gpt-6.1-sol")
    assert json.loads(selection_path.read_text()) == {"schema_version": 1, "model": "gpt-6.1-sol"}
    assert OpenAIModelCatalog(settings, selection_path).current_id == "gpt-6.1-sol"
    catalog.select("gpt-6-luna")
    assert settings.model_dump_json() == before
    with pytest.raises(ValueError):
        catalog.select("unknown")
    assert catalog.current_id == "gpt-6-luna"


def test_selection_failure_does_not_replace_current_profile(monkeypatch, tmp_path):
    catalog = OpenAIModelCatalog(config(), tmp_path / "selection.json")
    monkeypatch.setattr(catalog._store, "save", Mock(side_effect=OSError("unavailable")))
    with pytest.raises(OSError):
        catalog.select("gpt-6.1-sol")
    assert catalog.current_id == "gpt-6-luna"


def test_unknown_or_corrupt_selection_is_preserved_and_rejected(tmp_path):
    selection = tmp_path / "selection.json"
    for content in ('{"schema_version":1,"model":"unknown"}', "{bad-json"):
        selection.write_text(content)
        with pytest.raises(ValueError):
            OpenAIModelCatalog(config(), selection)
        assert selection.read_text() == content


def test_real_sdk_sends_responses_contract_without_tools_or_secrets_in_body(monkeypatch, caplog):
    engine, client, requests, factory = engine_with_transport(monkeypatch)
    messages = [{"role": "system", "content": "private-policy"}, {"role": "user", "content": "private-input"}]
    with caplog.at_level(logging.INFO):
        result = engine.respond(messages)
    assert result == "hello"
    assert result.completion.usage.input_tokens == 14
    assert result.completion.usage.output_tokens == 8
    assert result.completion.usage.total_tokens == 22
    assert requests[0].url == "https://api.openai.com/v1/responses"
    body = json.loads(requests[0].content)
    assert body == {"model": "gpt-6-luna", "input": messages, "store": False,
                    "stream": True, "truncation": "disabled", "max_output_tokens": 4096,
                    "reasoning": {"effort": "none"}, "temperature": 0.1,
                    "include": ["reasoning.encrypted_content"]}
    assert requests[0].headers["authorization"] == "Bearer test-key-never-live"
    factory.assert_called_once_with(api_key="test-key-never-live", base_url="https://api.openai.com/v1",
                                    timeout=90, max_retries=0, http_client=client._client)
    assert all(value not in caplog.text for value in ("private-input", "private-policy", "test-key-never-live"))
    engine.close()
    assert client.is_closed()


def test_model_switch_away_and_back_uses_each_profiles_effective_settings(monkeypatch):
    small = OpenAIModelProfile(id="gpt-6.1-sol", context_length=8192,
                              max_input_tokens=7168, max_output_tokens=1024, reasoning_effort="medium")
    settings = config(profiles=(OpenAIModelProfile(id="gpt-6-luna", temperature=0.1), small))
    engine, client, requests, _ = engine_with_transport(monkeypatch, engine_config=settings)
    engine.respond([{"role": "user", "content": "hello"}])
    engine.select_model("gpt-6.1-sol")
    assert (engine.context_length, engine.max_response_tokens) == (8192, 1024)
    engine.respond([{"role": "user", "content": "hello"}])
    engine.select_model("gpt-6-luna")
    assert (engine.context_length, engine.max_response_tokens) == (32768, 4096)
    engine.respond([{"role": "user", "content": "hello"}])
    bodies = [json.loads(request.content) for request in requests]
    assert [body["model"] for body in bodies] == ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-luna"]
    assert "temperature" not in bodies[1]
    assert bodies[1]["reasoning"] == {"effort": "medium"}
    assert bodies[1]["max_output_tokens"] == 1024
    engine.close()
    assert client.is_closed()


def test_hybrid_local_cloud_local_switch_preserves_limits_and_releases_owned_client(monkeypatch):
    cloud, client, _, _ = engine_with_transport(monkeypatch)
    owned_local = SimpleNamespace(context_length=8192, max_response_tokens=512,
                                  respond=Mock(return_value="local"), close=Mock())
    local = LazyInferenceEngine(lambda: owned_local, context_length=8192)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, fallback_to_local=False)
    assert hybrid.respond([{"role": "user", "content": "hi"}]) == "local"
    hybrid.set_mode("cloud")
    owned_local.close.assert_called_once()
    assert not local.is_loaded
    assert (hybrid.context_length, hybrid.max_response_tokens) == (32768, 4096)
    assert hybrid.respond([{"role": "user", "content": "hi"}]) == "hello"
    hybrid.set_mode("local")
    assert (hybrid.context_length, hybrid.max_response_tokens) == (8192, 512)
    hybrid.close()
    assert client.is_closed()


def test_session_key_required_and_explicit_empty_key_does_not_reuse_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    engine = OpenAIResponsesInferenceEngine(config(), api_key="")
    assert not engine.has_api_key
    with pytest.raises(CloudInferenceError) as failure:
        engine.respond([{"role": "user", "content": "hello"}])
    assert failure.value.code == CloudErrorCode.AUTHENTICATION
    assert not failure.value.allow_local_fallback


def test_session_key_change_releases_old_client_and_close_is_terminal(monkeypatch):
    engine, client, _, factory = engine_with_transport(monkeypatch)
    engine.respond([{"role": "user", "content": "hello"}])
    engine.set_api_key("replacement-test-key")
    assert client.is_closed()
    engine.close()
    engine.close()
    assert not engine.has_api_key
    with pytest.raises(CloudInferenceError) as failure:
        engine.respond([{"role": "user", "content": "hello"}])
    assert failure.value.code == CloudErrorCode.CLOSED
    assert factory.call_count == 1


@pytest.mark.parametrize("status, provider_code, expected, retryable", [
    (401, "invalid_api_key", CloudErrorCode.AUTHENTICATION, False),
    (403, None, CloudErrorCode.PERMISSION, False),
    (429, "insufficient_quota", CloudErrorCode.QUOTA, False),
    (429, "rate_limit_exceeded", CloudErrorCode.RATE_LIMIT, True),
    (400, "context_length_exceeded", CloudErrorCode.CONTEXT_OVERFLOW, False),
    (400, "invalid_parameter", CloudErrorCode.BAD_REQUEST, False),
    (404, "model_not_found", CloudErrorCode.BAD_REQUEST, False),
    (500, "server_error", CloudErrorCode.PROVIDER_UNAVAILABLE, True),
])
def test_sdk_errors_are_classified_without_exposing_bodies_or_silently_switching_models(
        monkeypatch, caplog, status, provider_code, expected, retryable):
    payload = {"error": {"code": provider_code, "message": "private-input test-key-never-live"}}
    engine, client, requests, _ = engine_with_transport(monkeypatch, payload, status=status)
    with caplog.at_level(logging.INFO), pytest.raises(CloudInferenceError) as failure:
        engine.respond([{"role": "user", "content": "private-input"}])
    assert failure.value.code == expected and failure.value.retryable is retryable
    assert len(requests) == 1 and engine.active_model == "gpt-6-luna"
    assert "private-input" not in str(failure.value) + caplog.text
    assert "test-key-never-live" not in str(failure.value) + caplog.text
    assert failure.value.__suppress_context__
    engine.close()
    assert client.is_closed()


@pytest.mark.parametrize("exception, expected", [
    (httpx.ConnectError, CloudErrorCode.CONNECTION),
    (httpx.ReadTimeout, CloudErrorCode.TIMEOUT),
])
def test_connection_and_timeout_are_separate_errors(monkeypatch, exception, expected):
    engine, _, requests, _ = engine_with_transport(
        monkeypatch, failure=lambda request: exception("private-connection-error", request=request))
    with pytest.raises(CloudInferenceError) as failure:
        engine.respond([{"role": "user", "content": "hello"}])
    assert failure.value.code == expected and len(requests) == 1
    assert "private-connection-error" not in str(failure.value)
    engine.close()


def test_refusal_is_visible_and_not_treated_as_provider_failure():
    payload = response()
    payload["output"][0]["content"] = [{"type": "refusal", "refusal": "I cannot help with that."}]
    result = normalize_text_response(payload)
    assert result == "I cannot help with that."
    assert result.completion.finish_reason == "refusal" and not result.completion.incomplete


@pytest.mark.parametrize("reason, expected", [("max_output_tokens", "length"), ("content_filter", "content_filter"), ("unknown", "error")])
def test_incomplete_text_retains_partial_output_and_completion_state(reason, expected):
    result = normalize_text_response(response("partial", status="incomplete", incomplete_details={"reason": reason}))
    assert result.partial_text == "partial" and result.completion.incomplete
    assert result.completion.finish_reason == expected


def test_reasoning_only_budget_exhaustion_is_incomplete_not_success():
    with pytest.raises(IncompleteResponseError) as failure:
        normalize_text_response(response(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
                                          output=[{"type": "reasoning", "encrypted_content": "opaque"}]))
    assert failure.value.completion.finish_reason == "length"


@pytest.mark.parametrize("overrides", [
    {"status": "in_progress"}, {"output": None}, {"output": []},
    {"output": ["invalid"]},
    {"output": [{"type": "function_call", "call_id": "call_unrequested", "name": "do_work", "arguments": "{}"}]},
])
def test_nonterminal_malformed_empty_or_unrequested_call_responses_fail_closed(overrides):
    with pytest.raises(CloudInferenceError) as failure:
        normalize_text_response(response(**overrides))
    assert failure.value.code == CloudErrorCode.MALFORMED_RESPONSE


def test_missing_usage_is_not_reported_as_zero_and_invalid_counts_are_ignored():
    result = normalize_text_response(response(usage={"input_tokens": True, "output_tokens": -1, "total_tokens": "22"}))
    assert all(value is None for value in result.completion.usage.model_dump().values())


def test_text_only_structured_history_stops_before_any_request(monkeypatch):
    engine, _, requests, factory = engine_with_transport(monkeypatch)
    with pytest.raises(ValueError):
        engine.respond([{"role": "capability", "provider_call_id": "call_1", "result": {}}])
    assert not requests
    factory.assert_not_called()
    engine.close()


def test_plain_conversation_uses_responses_and_restorable_usage(monkeypatch, tmp_path):
    engine, _, requests, _ = engine_with_transport(monkeypatch)
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store)
    assert service.run("hello") == "hello"
    assert len(requests) == 1
    assert service._turn_result.completion.usage.total_tokens == 22
    assert ConversationStore(store.path).messages()[-1]["content"] == "hello"
    service.shutdown()


def test_automatic_skill_selection_uses_the_same_text_adapter(monkeypatch):
    engine, _, requests, _ = engine_with_transport(monkeypatch, response('{"skill":"writing"}'))
    selection = select_skill(engine, candidates=(SkillCandidate("writing", "Draft and revise prose"),),
                             request="Draft an email")
    assert selection.name == "writing" and selection.model_requests == 1
    assert selection.input_tokens == 14 and selection.output_tokens == 8
    assert "tools" not in json.loads(requests[0].content)
    engine.close()


def test_bootstrap_selects_responses_without_constructing_a_network_client(monkeypatch, tmp_path):
    import app.startup as startup
    from app.settings.agent import AgentFeatureConfig
    from app.settings.paths import RuntimePaths
    from app.inference.engine import InferenceUnavailable

    monkeypatch.setattr(startup, "PATHS", RuntimePaths(tmp_path, tmp_path / "config", tmp_path / "models", tmp_path / "state"))
    monkeypatch.setattr(startup, "load_model_config", Mock(side_effect=InferenceUnavailable("no local test model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config(default_mode="cloud"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = Mock(side_effect=AssertionError("SDK must be lazy"))
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    service, _, error, hybrid = startup.build_application(agent_config_override=AgentFeatureConfig())
    assert error is None and isinstance(hybrid.cloud, OpenAIResponsesInferenceEngine)
    assert hybrid.mode == "cloud" and not hybrid.cloud_has_api_key
    assert not (tmp_path / "state" / "cloud_model_selection_v1.json").exists()
    factory.assert_not_called()
    service.shutdown()
