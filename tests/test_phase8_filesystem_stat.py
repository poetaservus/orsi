from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

import app.agent_config as agent_config_module
from app.agent_bootstrap import build_filesystem_stat_runtime
from app.agent_config import AgentFeatureConfig, load_agent_feature_config
from app.agent_runtime import AgentRuntime
from app.capabilities.crash_journal import CallLifecycleState
from app.conversation.prompt import AGENT_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.conversation.service import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.protocol import ModelCapabilityCall, ModelResponse


class ScriptedStatModel(InferenceEngine):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[dict]] = []
        self.definitions = []

    def respond(self, messages):
        raise AssertionError("Agent mode must use the structured model boundary.")

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append(deepcopy(messages))
        self.definitions.append(tuple(capabilities))
        if not self.responses:
            raise AssertionError("The scripted response list was exhausted.")
        return self.responses.pop(0)


class BlockingStatModel(InferenceEngine):
    def __init__(self):
        self.started = Event()
        self.release = Event()

    def respond(self, messages):
        self.started.set()
        self.release.wait(2.0)
        return "late response"

    def respond_with_capabilities(self, messages, capabilities):
        self.started.set()
        self.release.wait(2.0)
        return ModelResponse.text("late response")


def stat_call(path: str, *, provider_call_id: str = "provider-stat-1") -> ModelResponse:
    return ModelResponse.calls(
        (
            ModelCapabilityCall(
                provider_call_id=provider_call_id,
                capability="filesystem.stat",
                arguments={"path": path},
            ),
        )
    )


def build_service(tmp_path: Path, model: InferenceEngine):
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    state = tmp_path / "state"
    runtime = build_filesystem_stat_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    assert isinstance(runtime, AgentRuntime)
    store = ConversationStore(state / "conversation.json")
    service = ConversationService(
        model,
        store,
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    return service, runtime, store, portable_root


def test_checked_in_config_enables_requested_read_capabilities(monkeypatch):
    for name in (
        "ORSI_ENABLE_FILESYSTEM_STAT",
        "ORSI_ENABLE_FILESYSTEM_LIST",
        "ORSI_ENABLE_FILESYSTEM_READ_TEXT",
        "ORSI_ENABLE_FULL_LOCAL_READ",
    ):
        monkeypatch.delenv(name, raising=False)

    assert load_agent_feature_config() == AgentFeatureConfig(
        filesystem_stat_enabled=True,
        filesystem_list_enabled=True,
        filesystem_read_text_enabled=True,
        full_local_read_enabled=True,
    )


def test_feature_gate_supports_explicit_file_and_environment_values(
    monkeypatch, tmp_path: Path
):
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    monkeypatch.setattr(
        agent_config_module,
        "PATHS",
        SimpleNamespace(config=config_directory),
    )
    monkeypatch.delenv("ORSI_ENABLE_FILESYSTEM_STAT", raising=False)

    assert not load_agent_feature_config().filesystem_stat_enabled
    (config_directory / "agent.json").write_text(
        '{"filesystem_stat_enabled": true}', encoding="utf-8"
    )
    assert load_agent_feature_config().filesystem_stat_enabled

    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_STAT", "off")
    assert not load_agent_feature_config().filesystem_stat_enabled
    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_STAT", "sometimes")
    with pytest.raises(ValueError, match="explicit true or false"):
        load_agent_feature_config()


def test_disabled_gate_builds_nothing(tmp_path: Path):
    runtime = build_filesystem_stat_runtime(
        object(),
        config=AgentFeatureConfig(filesystem_stat_enabled=False),
        portable_root=tmp_path,
        state_directory=tmp_path / "state",
    )

    assert runtime is None
    assert not (tmp_path / "state").exists()


def test_enabled_bootstrap_exposes_exactly_filesystem_stat(tmp_path: Path):
    model = ScriptedStatModel([ModelResponse.text("done")])
    service, runtime, _store, portable_root = build_service(tmp_path, model)
    try:
        assert service.agent_enabled
        assert runtime.registry.names == ("filesystem.stat",)
        assert runtime.registry.enabled_names == ("filesystem.stat",)
        assert runtime.registry.model_visible_names == ("filesystem.stat",)
        definition = runtime.registry.model_definitions()[0]
        assert definition.name == "filesystem.stat"
        assert definition.input_schema["required"] == ["path"]
        assert runtime.permission_gate.evaluate(
            _prepared_call(runtime, portable_root)
        ).decision.value == "allow"
    finally:
        service.shutdown()


def _prepared_call(runtime: AgentRuntime, portable_root: Path):
    from app.capabilities.contracts import CapabilityContext
    from app.capabilities.permissions import prepare_capability_call
    from app.runtime.cancellation import CancellationToken

    capability = runtime.registry.resolve("filesystem.stat")
    prepared = prepare_capability_call(
        capability,
        {"path": "README.md"},
        CapabilityContext(
            call_id="bootstrap-policy-test",
            session_id="session",
            turn_id="turn",
            portable_root=portable_root,
            allowed_read_roots=(portable_root,),
            cancellation=CancellationToken(),
        ),
    )
    return prepared


def test_conversation_runs_real_stat_and_persists_only_user_and_final_text(
    tmp_path: Path,
):
    private_body = "TOP-SECRET-FILE-CONTENT"
    model = ScriptedStatModel(
        [stat_call("sample.txt"), ModelResponse.text("The file metadata is available.")]
    )
    service, runtime, store, portable_root = build_service(tmp_path, model)
    sample = portable_root / "sample.txt"
    sample.write_text(private_body, encoding="utf-8")
    try:
        answer = service.run("What is the size of sample.txt?")

        assert answer == "The file metadata is available."
        assert len(model.requests) == 2
        assert all(
            [definition.name for definition in definitions] == ["filesystem.stat"]
            for definitions in model.definitions
        )
        result = model.requests[1][-1]["result"]
        assert result["success"] is True
        assert Path(result["output"]["path"]) == sample.resolve()
        assert result["output"]["type"] == "file"
        assert result["output"]["size_bytes"] == len(private_body.encode("utf-8"))
        assert private_body not in json.dumps(model.requests)
        assert store.messages() == [
            {"role": "user", "content": "What is the size of sample.txt?"},
            {"role": "assistant", "content": answer},
        ]
        assert runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED
        service.new_session()
        assert runtime.executor.journal.records == ()
        assert store.messages() == []
    finally:
        service.shutdown()


@pytest.mark.parametrize(
    ("requested_path", "expected_code", "expected_state"),
    [
        ("missing.txt", "not_found", CallLifecycleState.FAILED),
        ("{outside}", "permission_denied", CallLifecycleState.DENIED),
    ],
)
def test_missing_and_outside_paths_return_structured_failures_without_content(
    tmp_path: Path,
    requested_path: str,
    expected_code: str,
    expected_state: CallLifecycleState,
):
    outside = tmp_path / "outside.txt"
    private_body = "OUTSIDE-PRIVATE-CONTENT"
    outside.write_text(private_body, encoding="utf-8")
    path = str(outside.resolve()) if requested_path == "{outside}" else requested_path
    model = ScriptedStatModel(
        [stat_call(path), ModelResponse.text("I could not inspect that path.")]
    )
    service, runtime, _store, _portable_root = build_service(tmp_path, model)
    try:
        assert service.run("Inspect the requested path") == "I could not inspect that path."
        result = model.requests[1][-1]["result"]
        assert result["success"] is False
        assert result["error"]["code"] == expected_code
        assert private_body not in json.dumps(model.requests)
        assert runtime.executor.journal.records[0].state == expected_state
    finally:
        service.shutdown()


def test_agent_cancellation_stores_no_assistant_message(tmp_path: Path):
    model = BlockingStatModel()
    service, _runtime, store, _portable_root = build_service(tmp_path, model)
    result: list[str] = []
    worker = Thread(target=lambda: result.append(service.run("Wait for the model")))
    worker.start()
    try:
        assert model.started.wait(1.0)
        assert service.cancel_current_task()
        worker.join(1.0)
        assert not worker.is_alive()
        assert result == ["The response was stopped."]
        assert store.messages() == [{"role": "user", "content": "Wait for the model"}]
    finally:
        model.release.set()
        worker.join(1.0)
        service.shutdown()


def test_chat_only_fallback_keeps_plain_prompt_and_boundary(tmp_path: Path):
    class PlainModel:
        def __init__(self):
            self.messages = None

        def respond(self, messages):
            self.messages = messages
            return "plain reply"

    model = PlainModel()
    service = ConversationService(
        model,
        ConversationStore(tmp_path / "conversation.json"),
    )

    assert not service.agent_enabled
    assert service.run("hello") == "plain reply"
    assert model.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert all(set(message) == {"role", "content"} for message in model.messages)


def test_agent_prompt_describes_the_exact_metadata_boundary():
    prompt = " ".join(AGENT_SYSTEM_PROMPT.casefold().split())

    assert "capable general conversational assistant" in prompt
    assert "including recipes" in prompt
    assert "without using filesystem.stat" in prompt
    assert "does not restrict or replace" in prompt
    assert "filesystem.stat only from the latest user request" in prompt
    assert "return assistant text without a capability call" in prompt
    assert "never repeat, verify, or continue an earlier metadata call" in prompt
    assert "exactly one read-only capability: filesystem.stat" in prompt
    assert "cannot read file content" in prompt
    assert "preserve a user-provided absolute path exactly" in prompt
    assert "never prefix the portable root's directory name" in prompt
    assert "let the capability decide" in prompt
    assert "sole evidence" in prompt
    assert "never claim success" in prompt


def test_application_bootstrap_wires_agent_only_when_enabled(monkeypatch, tmp_path: Path):
    import app.main as main

    model = ScriptedStatModel([ModelResponse.text("ready")])
    server = tmp_path / "runtime" / "llama-server" / "llama-server.exe"
    server.parent.mkdir(parents=True)
    server.touch()
    paths = SimpleNamespace(
        root=tmp_path,
        config=tmp_path / "config",
        models=tmp_path / "models",
        state=tmp_path / "state",
    )
    monkeypatch.setattr(main, "PATHS", paths)
    monkeypatch.setattr(
        main,
        "load_model_config",
        lambda: (_ for _ in ()).throw(InferenceUnavailable("no local model")),
    )
    cloud_config = SimpleNamespace(default_mode="cloud", fallback_to_local=False)
    monkeypatch.setattr(main, "load_cloud_config", lambda: cloud_config)
    monkeypatch.setattr(main, "OpenAICompatibleInferenceEngine", lambda _: object())
    monkeypatch.setattr(main, "HybridInferenceEngine", lambda **_: model)
    monkeypatch.setattr(
        main,
        "load_agent_feature_config",
        lambda: AgentFeatureConfig(filesystem_stat_enabled=True),
    )

    service, _host, error, inference = main.build_application()
    try:
        assert error is None
        assert inference is model
        assert service.agent_enabled
        assert service.agent_runtime.registry.model_visible_names == ("filesystem.stat",)
    finally:
        service.shutdown()


def test_application_bootstrap_fails_closed_to_chat_when_agent_start_fails(
    monkeypatch, tmp_path: Path
):
    import app.main as main

    model = ScriptedStatModel([ModelResponse.text("ready")])
    server = tmp_path / "runtime" / "llama-server" / "llama-server.exe"
    server.parent.mkdir(parents=True)
    server.touch()
    paths = SimpleNamespace(
        root=tmp_path,
        config=tmp_path / "config",
        models=tmp_path / "models",
        state=tmp_path / "state",
    )
    monkeypatch.setattr(main, "PATHS", paths)
    monkeypatch.setattr(
        main,
        "load_model_config",
        lambda: (_ for _ in ()).throw(InferenceUnavailable("no local model")),
    )
    cloud_config = SimpleNamespace(default_mode="cloud", fallback_to_local=False)
    monkeypatch.setattr(main, "load_cloud_config", lambda: cloud_config)
    monkeypatch.setattr(main, "OpenAICompatibleInferenceEngine", lambda _: object())
    monkeypatch.setattr(main, "HybridInferenceEngine", lambda **_: model)
    monkeypatch.setattr(
        main,
        "load_agent_feature_config",
        lambda: AgentFeatureConfig(filesystem_stat_enabled=True),
    )
    monkeypatch.setattr(
        main,
        "build_filesystem_stat_runtime",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unsafe state")),
    )

    service, _host, error, _inference = main.build_application()

    assert error is None
    assert not service.agent_enabled
    assert service.agent_error == (
        "Agent mode could not start safely. Chat-only mode remains available."
    )


def test_application_uses_native_server_factory_for_enabled_local_agent(
    monkeypatch,
    tmp_path: Path,
):
    import app.main as main
    from app.inference.model_config import ModelConfig

    model_path = tmp_path / "model.gguf"
    model_path.touch()
    server = tmp_path / "runtime" / "llama-server" / "llama-server.exe"
    server.parent.mkdir(parents=True)
    server.touch()
    paths = SimpleNamespace(
        root=tmp_path,
        config=tmp_path / "config",
        models=tmp_path / "models",
        state=tmp_path / "state",
    )
    created = []
    native_model = ScriptedStatModel([ModelResponse.text("ready")])

    monkeypatch.setattr(main, "PATHS", paths)
    monkeypatch.setattr(
        main,
        "load_model_config",
        lambda: ModelConfig(model_path=str(model_path), context_length=4096),
    )
    monkeypatch.setattr(main, "detect_nvidia_memory_mib", lambda: None)
    monkeypatch.setattr(
        main,
        "load_agent_feature_config",
        lambda: AgentFeatureConfig(filesystem_stat_enabled=True),
    )
    monkeypatch.setattr(
        main,
        "LlamaServerInferenceEngine",
        lambda config: created.append(config) or native_model,
    )
    monkeypatch.setattr(
        main,
        "LlamaCppInferenceEngine",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("Enabled agent mode must not use the generic GGUF handler.")
        ),
    )
    monkeypatch.setattr(
        main,
        "load_cloud_config",
        lambda: (_ for _ in ()).throw(ValueError("cloud disabled for test")),
    )

    service, _host, error, inference = main.build_application()
    try:
        assert error is None
        assert service.agent_enabled
        assert inference.local._get_engine() is native_model
        assert len(created) == 1
    finally:
        service.shutdown()


def test_application_falls_back_to_chat_when_native_server_is_missing(
    monkeypatch,
    tmp_path: Path,
):
    import app.main as main
    from app.inference.model_config import ModelConfig

    model_path = tmp_path / "model.gguf"
    model_path.touch()
    paths = SimpleNamespace(
        root=tmp_path,
        config=tmp_path / "config",
        models=tmp_path / "models",
        state=tmp_path / "state",
    )
    chat_model = ScriptedStatModel([ModelResponse.text("ready")])

    monkeypatch.setattr(main, "PATHS", paths)
    monkeypatch.setattr(
        main,
        "load_model_config",
        lambda: ModelConfig(model_path=str(model_path), context_length=4096),
    )
    monkeypatch.setattr(main, "detect_nvidia_memory_mib", lambda: None)
    monkeypatch.setattr(
        main,
        "load_agent_feature_config",
        lambda: AgentFeatureConfig(filesystem_stat_enabled=True),
    )
    monkeypatch.setattr(main, "LlamaCppInferenceEngine", lambda _config: chat_model)
    monkeypatch.setattr(
        main,
        "LlamaServerInferenceEngine",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("A missing server must not be selected.")
        ),
    )
    monkeypatch.setattr(
        main,
        "load_cloud_config",
        lambda: (_ for _ in ()).throw(ValueError("cloud disabled for test")),
    )

    service, _host, error, inference = main.build_application()
    try:
        assert error is None
        assert not service.agent_enabled
        assert service.agent_error == (
            "Agent mode could not start safely. Chat-only mode remains available."
        )
        assert inference.local._get_engine() is chat_model
    finally:
        service.shutdown()
