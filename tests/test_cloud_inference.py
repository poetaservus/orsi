from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.inference.cloud_backend import CloudInferenceError, OpenAICompatibleInferenceEngine
from app.inference.cloud_config import CloudConfig
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.llama_backend import LlamaCppInferenceEngine


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
