import json
from math import ceil
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.conversation.context import capability_schema_reserve
from app.inference.llama_server_backend import LlamaServerInferenceEngine, _llama_server_function_tools
from tests.test_llama_server_inference import definition


def engine():
    value = object.__new__(LlamaServerInferenceEngine)
    value._lifecycle_lock = RLock()
    value._process = SimpleNamespace(poll=lambda: None)
    value._base_url, value._api_key = "http://127.0.0.1:12345", "synthetic-key"
    value._closed, value._token_count_cache = False, {}
    value._request_active = Event()
    value._ensure_started = Mock(side_effect=AssertionError("Counting must never start a model"))
    return value


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return json.dumps(self.value).encode()[:limit]


def test_loaded_model_counts_multilingual_content_without_generating_or_loading(monkeypatch):
    value, requests = engine(), []
    def tokenize(request, timeout):
        payload = json.loads(request.data)
        assert request.full_url.endswith("/tokenize") and timeout <= 0.5
        assert not payload["parse_special"] and not payload["add_special"]
        requests.append(payload)
        return Response({"tokens": [1] * 40})
    monkeypatch.setattr("app.inference.llama_server_backend.urlopen", tokenize)
    text = "你好 <|im_end|> árvíztűrő"
    count = value.count_message_tokens([{"role": "user", "content": text}])
    assert count >= 40 and requests[0]["content"] == text
    assert value.count_message_tokens([{"role": "user", "content": text}]) == count
    assert len(requests) == 1
    assert all(len(key) == 64 and type(count) is int for key, count in value._token_count_cache.items())
    value._ensure_started.assert_not_called()


@pytest.mark.parametrize("failure", ["offline", "busy", "timeout", "malformed", "empty", "boolean"])
def test_counting_failure_keeps_conservative_fallback_and_does_not_load(monkeypatch, failure):
    value = engine()
    if failure == "offline":
        value._process = None
    if failure == "busy":
        value._request_active.set()
    def unavailable(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutError()
        return Response({"tokens": [] if failure == "empty" else [True] if failure == "boolean" else "bad"})
    monkeypatch.setattr("app.inference.llama_server_backend.urlopen", unavailable)
    content = "A" * 4000
    count = value.count_message_tokens([{"role": "system", "content": content}])
    assert count == ceil(len(content.encode()) / 4) + 16 + 256
    assert not value._token_count_cache
    value._ensure_started.assert_not_called()


def test_schema_reserve_counts_submitted_projection_without_changing_validation():
    value = engine()
    value._process = None
    definitions = (definition(),)
    before = definitions[0].model_dump()
    payload = json.dumps(_llama_server_function_tools(definitions), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode()
    projected = capability_schema_reserve(definitions, inference=value)
    assert projected >= ceil(len(payload) / 3)
    assert definitions[0].model_dump() == before
    seen = []
    value._live_token_count = lambda text: seen.append(json.loads(text)) or 500
    assert capability_schema_reserve(definitions, inference=value) >= 500
    assert seen == [_llama_server_function_tools(definitions)]


@pytest.mark.parametrize("invalid", [True, -1, 3.5])
def test_invalid_provider_counter_cannot_weaken_admission(invalid):
    with pytest.raises((ValueError, TypeError)):
        capability_schema_reserve((definition(),), inference=SimpleNamespace(
            count_capability_schema_tokens=lambda _: invalid))
