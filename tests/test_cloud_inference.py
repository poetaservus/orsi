from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.inference.cloud_backend import CloudInferenceError, OpenAICompatibleInferenceEngine
from app.inference.cloud_config import CloudConfig
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.llama_backend import LlamaCppInferenceEngine
from app.inference.protocol import (
    ModelCapabilityCall,
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponse,
    ModelResponseKind,
    model_capability_calls_message,
    model_capability_result_message,
    native_function_tools,
)


def cloud_config(**overrides):
    values = {
        "provider_name": "Test Cloud",
        "base_url": "https://cloud.example/v1",
        "model": "free/test-model",
        "api_key_environment": "ORSI_TEST_CLOUD_KEY",
        "timeout_seconds": 20,
    }
    values.update(overrides)
    return CloudConfig(**values)


def capability_definition():
    return ModelCapabilityDefinition(
        name="filesystem.stat",
        description="Return bounded metadata for one allowed path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def provider_capability_name():
    return native_function_tools((capability_definition(),))[0]["function"]["name"]


def test_cloud_config_rejects_insecure_api_urls():
    with pytest.raises(ValueError, match="HTTPS"):
        cloud_config(base_url="http://cloud.example/v1")


def test_cloud_backend_requires_a_session_key(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(cloud_config())
    with pytest.raises(CloudInferenceError, match="API key"):
        engine.respond([{"role": "user", "content": "Hello"}])


def test_cloud_backend_sends_plain_chat_without_action_fields(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="session-secret")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Hello"}}]
    }).encode("utf-8")
    messages = [
        {"role": "system", "content": "Chat only"},
        {"role": "user", "content": "Hello"},
    ]

    with patch("app.inference.cloud_backend.urlopen", return_value=response) as mocked:
        result = engine.respond(messages)

    assert result == "Hello"
    request = mocked.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://cloud.example/v1/chat/completions"
    assert payload["messages"] == messages
    assert set(payload) == {"model", "messages", "temperature", "max_tokens"}
    assert "session-secret" not in request.data.decode("utf-8")
    assert request.get_header("Authorization") == "Bearer session-secret"


def test_local_backend_sends_plain_chat_without_action_fields():
    captured = {}

    class Model:
        @staticmethod
        def create_chat_completion(**kwargs):
            captured.update(kwargs)
            return {"choices": [{"message": {"content": "Local reply"}}]}

    engine = object.__new__(LlamaCppInferenceEngine)
    engine.model = Model()
    engine.config = SimpleNamespace(temperature=0.2, max_tokens=128)
    messages = [{"role": "user", "content": "Hello"}]

    assert engine.respond(messages) == "Local reply"
    assert captured == {"messages": messages, "temperature": 0.2, "max_tokens": 128}


def test_cloud_backend_sends_native_strict_tools_and_preserves_call_identity(
    monkeypatch,
):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(
        cloud_config(), api_key="session-secret"
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "provider_call_1",
                                "type": "function",
                                "function": {
                                    "name": provider_capability_name(),
                                    "arguments": '{"path":"sample.txt"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
    ).encode("utf-8")
    definition = capability_definition()

    with patch("app.inference.cloud_backend.urlopen", return_value=response) as mocked:
        result = engine.respond_with_capabilities(
            [{"role": "user", "content": "Inspect sample.txt"}],
            (definition,),
        )

    request = mocked.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert set(payload) == {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "tools",
        "tool_choice",
    }
    assert payload["tool_choice"] == "auto"
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": provider_capability_name(),
                "description": definition.description,
                "parameters": definition.input_schema,
                "strict": True,
            },
        }
    ]
    assert "session-secret" not in request.data.decode("utf-8")
    assert result.kind == ModelResponseKind.CAPABILITY_CALLS
    assert result.capability_calls[0].provider_call_id == "provider_call_1"
    assert result.capability_calls[0].capability == "filesystem.stat"
    assert result.capability_calls[0].arguments == {"path": "sample.txt"}


def test_cloud_backend_returns_malformed_native_call_as_protocol_result(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(
        cloud_config(), api_key="session-secret"
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "provider_call_1",
                                "type": "function",
                                "function": {
                                    "name": provider_capability_name(),
                                    "arguments": "private malformed arguments",
                                },
                            }
                        ],
                    }
                }
            ]
        }
    ).encode("utf-8")

    with patch("app.inference.cloud_backend.urlopen", return_value=response):
        result = engine.respond_with_capabilities(
            [{"role": "user", "content": "Inspect"}],
            (capability_definition(),),
        )

    assert result.protocol_failure.code == ModelProtocolFailureCode.MALFORMED_ARGUMENTS
    assert "private malformed arguments" not in result.model_dump_json()


def test_cloud_backend_translates_structured_continuation_history(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(
        cloud_config(), api_key="session-secret"
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The file is available.",
                    }
                }
            ]
        }
    ).encode("utf-8")
    call = ModelCapabilityCall(
        provider_call_id="provider_call_1",
        capability="filesystem.stat",
        arguments={"path": "sample.txt"},
    )
    normalized_result = {
        "call_id": "internal-call-1",
        "capability": "filesystem.stat",
        "success": True,
        "output": {"type": "file"},
        "error": None,
        "duration_ms": 1,
        "metadata": {},
    }
    transcript = [
        {"role": "user", "content": "Inspect sample.txt"},
        model_capability_calls_message((call,)),
        model_capability_result_message(call, normalized_result),
    ]

    with patch("app.inference.cloud_backend.urlopen", return_value=response) as mocked:
        result = engine.respond_with_capabilities(
            transcript,
            (capability_definition(),),
        )

    payload = json.loads(mocked.call_args.args[0].data.decode("utf-8"))
    assert payload["messages"][1]["tool_calls"][0]["id"] == "provider_call_1"
    assert payload["messages"][1]["tool_calls"][0]["function"]["name"] == (
        provider_capability_name()
    )
    assert payload["messages"][2]["role"] == "tool"
    assert payload["messages"][2]["tool_call_id"] == "provider_call_1"
    assert json.loads(payload["messages"][2]["content"]) == normalized_result
    assert result.assistant_text == "The file is available."


def test_cloud_backend_normalizes_malformed_completion_envelope(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    engine = OpenAICompatibleInferenceEngine(
        cloud_config(), api_key="session-secret"
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"choices":[]}'

    with patch("app.inference.cloud_backend.urlopen", return_value=response):
        result = engine.respond_with_capabilities(
            [{"role": "user", "content": "Inspect"}],
            (capability_definition(),),
        )

    assert result.protocol_failure.code == ModelProtocolFailureCode.MALFORMED_RESPONSE


def test_structured_adapters_reject_empty_catalog_before_provider_request(monkeypatch):
    monkeypatch.delenv("ORSI_TEST_CLOUD_KEY", raising=False)
    cloud = OpenAICompatibleInferenceEngine(
        cloud_config(), api_key="session-secret"
    )
    with patch("app.inference.cloud_backend.urlopen") as request:
        with pytest.raises(ValueError, match="at least one"):
            cloud.respond_with_capabilities(
                [{"role": "user", "content": "Inspect"}],
                (),
            )
    assert not request.called

    class Model:
        calls = 0

        def create_chat_completion(self, **kwargs):
            self.calls += 1
            raise AssertionError("The model must not be called.")

    local = object.__new__(LlamaCppInferenceEngine)
    local.model = Model()
    local.config = SimpleNamespace(temperature=0.2, max_tokens=128)
    with pytest.raises(ValueError, match="at least one"):
        local.respond_with_capabilities(
            [{"role": "user", "content": "Inspect"}],
            (),
        )
    assert local.model.calls == 0


def test_local_backend_sends_native_tools_and_normalizes_structured_response():
    captured = {}

    class Model:
        @staticmethod
        def create_chat_completion(**kwargs):
            captured.update(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "local_call_1",
                                    "type": "function",
                                    "function": {
                                        "name": provider_capability_name(),
                                        "arguments": '{"path":"sample.txt"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

    engine = object.__new__(LlamaCppInferenceEngine)
    engine.model = Model()
    engine.config = SimpleNamespace(temperature=0.2, max_tokens=128)
    messages = [{"role": "user", "content": "Inspect sample.txt"}]

    result = engine.respond_with_capabilities(
        messages,
        (capability_definition(),),
    )

    assert set(captured) == {
        "messages",
        "temperature",
        "max_tokens",
        "tools",
        "tool_choice",
    }
    assert captured["messages"] == messages
    assert captured["tool_choice"] == "auto"
    assert captured["tools"][0]["function"]["strict"] is True
    assert result.capability_calls[0].provider_call_id == "local_call_1"


class StubEngine:
    context_length = 8192

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def respond(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class StubCloud(StubEngine):
    context_length = 32768

    def __init__(self, result=None, error=None):
        super().__init__(result, error)
        self.config = cloud_config()
        self.has_api_key = True

    def set_api_key(self, key):
        self.has_api_key = bool(key)


class StructuredStub(StubEngine):
    def __init__(self, result=None, error=None):
        super().__init__(result, error)
        self.capability_calls = []

    def respond_with_capabilities(self, messages, capabilities):
        self.calls += 1
        self.capability_calls.append((messages, capabilities))
        if self.error:
            raise self.error
        return self.result


class StructuredCloud(StructuredStub):
    context_length = 32768

    def __init__(self, result=None, error=None):
        super().__init__(result, error)
        self.config = cloud_config()
        self.has_api_key = True

    def set_api_key(self, key):
        self.has_api_key = bool(key)


def test_hybrid_switches_between_conversational_models():
    local = StubEngine("local")
    cloud = StubCloud("cloud")
    engine = HybridInferenceEngine(local=local, cloud=cloud)

    engine.set_mode("cloud")
    assert engine.respond([{"role": "user", "content": "hello"}]) == "cloud"
    assert cloud.calls == 1 and local.calls == 0


def test_hybrid_falls_back_to_local_for_cloud_outage():
    local = StubEngine("local fallback")
    cloud = StubCloud(error=CloudInferenceError("offline", allow_local_fallback=True))
    engine = HybridInferenceEngine(
        local=local, cloud=cloud, default_mode="cloud", fallback_to_local=True
    )

    assert engine.respond([{"role": "user", "content": "hello"}]) == "local fallback"
    assert engine.mode == "local"
    assert engine.consume_notice() == "Cloud was unavailable, so O.R.S.I safely switched to the local model."


def test_local_backend_is_lazy_and_released_for_cloud():
    created = []

    class ClosableEngine(StubEngine):
        def close(self):
            self.closed = True

    def create_local():
        instance = ClosableEngine("local")
        instance.closed = False
        created.append(instance)
        return instance

    local = LazyInferenceEngine(create_local, context_length=8192)
    cloud = StubCloud("cloud")
    engine = HybridInferenceEngine(local=local, cloud=cloud)

    assert not local.is_loaded
    engine.respond([{"role": "user", "content": "hello"}])
    engine.set_mode("cloud")
    assert not local.is_loaded and created[0].closed


def test_token_count_refreshes_a_lazy_local_context_hint():
    class CountingEngine(StubEngine):
        context_length = 4096
        max_response_tokens = 128

        @staticmethod
        def count_message_tokens(messages):
            return len(messages) * 10

    local = LazyInferenceEngine(
        lambda: CountingEngine("local"),
        context_length=32768,
        max_response_tokens=1536,
    )
    engine = HybridInferenceEngine(local=local, cloud=None)

    assert engine.context_length == 32768
    assert engine.count_message_tokens([{"role": "user", "content": "hello"}]) == 10
    assert engine.context_length == 4096
    assert engine.max_response_tokens == 128


def test_lazy_engine_delegates_structured_requests_without_consuming_definitions():
    response = ModelResponse.text("No capability needed.")
    created = []

    def factory():
        engine = StructuredStub(response)
        created.append(engine)
        return engine

    lazy = LazyInferenceEngine(factory, context_length=8192)
    definitions = (item for item in (capability_definition(),))

    result = lazy.respond_with_capabilities(
        [{"role": "user", "content": "Hello"}],
        definitions,
    )

    assert result == response
    assert len(created) == 1
    assert created[0].capability_calls[0][1] == (capability_definition(),)


def test_hybrid_structured_request_uses_selected_provider():
    local = StructuredStub(ModelResponse.text("local"))
    cloud = StructuredCloud(ModelResponse.text("cloud"))
    engine = HybridInferenceEngine(local=local, cloud=cloud)
    engine.set_mode("cloud")

    result = engine.respond_with_capabilities(
        [{"role": "user", "content": "Hello"}],
        (capability_definition(),),
    )

    assert result.assistant_text == "cloud"
    assert cloud.calls == 1 and local.calls == 0


def test_hybrid_structured_request_falls_back_to_native_local_adapter():
    local = StructuredStub(ModelResponse.text("local structured fallback"))
    cloud = StructuredCloud(
        error=CloudInferenceError("offline", allow_local_fallback=True)
    )
    engine = HybridInferenceEngine(
        local=local,
        cloud=cloud,
        default_mode="cloud",
        fallback_to_local=True,
    )

    result = engine.respond_with_capabilities(
        [{"role": "user", "content": "Hello"}],
        (capability_definition(),),
    )

    assert result.assistant_text == "local structured fallback"
    assert engine.mode == "local"
    assert engine.consume_notice() == (
        "Cloud was unavailable, so O.R.S.I safely switched to the local model."
    )
