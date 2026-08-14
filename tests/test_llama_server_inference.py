from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from threading import Lock, RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.llama_server_backend import _llama_server_function_tools
from app.inference.model_config import ModelConfig
from app.inference.protocol import (
    ModelCapabilityCall,
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponseKind,
    model_capability_calls_message,
    model_capability_result_message,
    native_function_tools,
)


FINGERPRINT = "b9976-e3546c794"


def definition() -> ModelCapabilityDefinition:
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


def provider_name() -> str:
    return native_function_tools((definition(),))[0]["function"]["name"]


def completion(message: dict, *, fingerprint: str = FINGERPRINT) -> dict:
    return {
        "choices": [{"index": 0, "message": message}],
        "system_fingerprint": fingerprint,
    }


def call(
    *,
    name: str | None = None,
    call_id: str = "native-stat-1",
    arguments: str = '{"path":"README.md"}',
) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name or provider_name(),
            "arguments": arguments,
        },
    }


def scripted_engine(responses: list[dict]):
    engine = object.__new__(LlamaServerInferenceEngine)
    engine.config = SimpleNamespace(temperature=0.1, max_tokens=256)
    captured: list[dict] = []

    def request(body):
        captured.append(deepcopy(body))
        return responses.pop(0)

    engine._request_completion = request
    return engine, captured


def test_explicit_stat_request_uses_native_server_tools_and_strict_normalizer():
    engine, requests = scripted_engine(
        [
            completion(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [call()],
                }
            )
        ]
    )

    result = engine.respond_with_capabilities(
        [{"role": "user", "content": "Inspect README.md"}],
        (definition(),),
    )

    assert result.kind == ModelResponseKind.CAPABILITY_CALLS
    assert result.capability_calls == (
        ModelCapabilityCall(
            provider_call_id="native-stat-1",
            capability="filesystem.stat",
            arguments={"path": "README.md"},
        ),
    )
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["tools"][0]["function"]["name"] == provider_name()
    assert requests[0]["tools"][0]["function"]["strict"] is True


def test_server_schema_projection_drops_only_unsupported_length_hints():
    constrained = ModelCapabilityDefinition(
        name="filesystem.stat",
        description="Return metadata.",
        input_schema={
            "title": "FilesystemStatArguments",
            "type": "object",
            "properties": {
                "path": {
                    "title": "Path",
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 32767,
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )

    tool = _llama_server_function_tools((constrained,))[0]["function"]

    assert tool["strict"] is True
    assert tool["parameters"] == {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }
    assert constrained.input_schema["properties"]["path"]["minLength"] == 1


def test_ordinary_conversation_with_advertised_tool_returns_zero_calls():
    engine, _requests = scripted_engine(
        [completion({"role": "assistant", "content": "Hello there."})]
    )

    result = engine.respond_with_capabilities(
        [{"role": "user", "content": "Say hello"}],
        (definition(),),
    )

    assert result.kind == ModelResponseKind.ASSISTANT_TEXT
    assert result.assistant_text == "Hello there."
    assert result.capability_calls == ()


def test_structured_result_continuation_preserves_exact_native_call_identity():
    engine, requests = scripted_engine(
        [completion({"role": "assistant", "content": "README.md is 42 bytes."})]
    )
    native_call = ModelCapabilityCall(
        provider_call_id="native-stat-1",
        capability="filesystem.stat",
        arguments={"path": "README.md"},
    )
    normalized_result = {
        "call_id": "internal-stat-1",
        "capability": "filesystem.stat",
        "success": True,
        "output": {"path": "README.md", "type": "file", "size_bytes": 42},
        "error": None,
        "duration_ms": 1,
        "metadata": {},
    }

    result = engine.respond_with_capabilities(
        [
            {"role": "user", "content": "Inspect README.md"},
            model_capability_calls_message((native_call,)),
            model_capability_result_message(native_call, normalized_result),
        ],
        (definition(),),
    )

    sent = requests[0]["messages"]
    assert sent[1]["tool_calls"][0]["id"] == "native-stat-1"
    assert sent[2]["role"] == "tool"
    assert sent[2]["tool_call_id"] == "native-stat-1"
    assert json.loads(sent[2]["content"]) == normalized_result
    assert result.assistant_text == "README.md is 42 bytes."


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [call(arguments="bad-json")],
            },
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            {"role": "assistant", "content": "mixed", "tool_calls": [call()]},
            ModelProtocolFailureCode.MIXED_RESPONSE,
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [call(name="unadvertised")],
            },
            ModelProtocolFailureCode.UNKNOWN_CAPABILITY,
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [call(call_id=f"call-{index}") for index in range(17)],
            },
            ModelProtocolFailureCode.TOO_MANY_CALLS,
        ),
    ],
)
def test_malformed_mixed_unknown_and_oversized_calls_remain_protocol_failures(
    message,
    expected,
):
    engine, _requests = scripted_engine([completion(message)])

    result = engine.respond_with_capabilities(
        [{"role": "user", "content": "Inspect"}],
        (definition(),),
    )

    assert result.kind == ModelResponseKind.PROTOCOL_FAILURE
    assert result.protocol_failure.code == expected


def test_plain_respond_rejects_unexpected_tool_calls():
    engine, _requests = scripted_engine(
        [completion({"role": "assistant", "content": None, "tool_calls": [call()]})]
    )

    with pytest.raises(Exception, match="invalid conversational response"):
        engine.respond([{"role": "user", "content": "Hello"}])


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.waits = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        self.waits += 1
        if self.waits == 1:
            raise subprocess.TimeoutExpired("llama-server", timeout)
        return 0


def test_cancellation_terminates_then_kills_within_bounded_shutdown():
    engine = object.__new__(LlamaServerInferenceEngine)
    process = FakeProcess()
    engine._process = process
    engine._base_url = "http://127.0.0.1:12345"
    engine._api_key = "secret"
    engine._lifecycle_lock = RLock()
    engine.shutdown_timeout_seconds = 0.2

    engine.cancel_current_request()

    assert process.terminated
    assert process.killed
    assert engine._process is None
    assert engine._base_url is None
    assert engine._api_key is None


def test_http_boundary_rejects_wrong_build_and_oversized_response():
    engine = object.__new__(LlamaServerInferenceEngine)
    engine._request_lock = Lock()
    engine._request_active = __import__("threading").Event()
    engine.request_timeout_seconds = 1.0
    process = SimpleNamespace(poll=lambda: None)
    engine._ensure_started = lambda: (
        "http://127.0.0.1:12345",
        "secret",
        process,
    )

    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        completion(
            {"role": "assistant", "content": "hello"},
            fingerprint="wrong",
        )
    ).encode("utf-8")
    with patch("app.inference.llama_server_backend.urlopen", return_value=response):
        with pytest.raises(Exception, match="pinned runtime"):
            engine._request_completion({"messages": []})

    response.__enter__.return_value.read.return_value = b"x" * (4 * 1024 * 1024 + 1)
    with patch("app.inference.llama_server_backend.urlopen", return_value=response):
        with pytest.raises(Exception, match="size limit"):
            engine._request_completion({"messages": []})


def test_server_launch_is_hidden_loopback_only_and_uses_qwen_jinja(
    monkeypatch,
    tmp_path: Path,
):
    model = tmp_path / "model.gguf"
    model.touch()
    server = tmp_path / "llama-server.exe"
    server.touch()
    process = SimpleNamespace(poll=lambda: None)
    captured = {}

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        "app.inference.llama_server_backend.detect_nvidia_memory_mib",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.inference.llama_server_backend._free_loopback_port",
        lambda: 54321,
    )
    monkeypatch.setattr(
        "app.inference.llama_server_backend.secrets.token_urlsafe",
        lambda _: "test-key",
    )
    monkeypatch.setattr(
        "app.inference.llama_server_backend.subprocess.Popen",
        popen,
    )
    engine = LlamaServerInferenceEngine(
        ModelConfig(model_path=str(model), context_length=4096),
        server_executable=server,
    )
    monkeypatch.setattr(engine, "_wait_until_healthy", lambda *args: None)

    base_url, api_key, returned = engine._ensure_started()

    command = captured["command"]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "54321"
    assert "--jinja" in command
    assert "--no-webui" in command
    assert command[command.index("--parallel") + 1] == "1"
    assert command[command.index("--api-key") + 1] == "test-key"
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["stdout"] is subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] is subprocess.DEVNULL
    assert base_url == "http://127.0.0.1:54321"
    assert api_key == "test-key"
    assert returned is process


def test_portable_runtime_pins_matching_python_and_server_revisions():
    root = Path(__file__).resolve().parents[1]
    for name in (
        "requirements-inference-cpu.txt",
        "requirements-inference-cuda.txt",
    ):
        requirements = (root / name).read_text(encoding="utf-8")
        assert "llama-cpp-python==0.3.34" in requirements

    builder = (root / "packaging" / "build-llama-server.ps1").read_text(
        encoding="utf-8"
    )
    assert 'build = "b9976"' in builder
    assert 'commit = "e3546c794"' in builder
    assert "6dbe0c9854632af2e7b4bf7f3a39a8f1a7f13a8cadbce917cfba99e34347b1ee" in builder
    assert "8eee04969ae12a5f2e949b2bce571b83b5e81268fdec78657f9aa617acd9d7b6" in builder
