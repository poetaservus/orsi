from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent_config as agent_config_module
from app.agent_bootstrap import AgentBootstrapError, build_filesystem_stat_runtime
from app.agent_config import AgentFeatureConfig, load_agent_feature_config
from app.agent_runtime import AgentRuntime
from app.capabilities.crash_journal import CallLifecycleState
from app.capabilities.host_access import (
    HostAccessPolicy,
    HostReadScope,
    WindowsDriveType,
    _windows_drive_type,
)
from app.conversation.service import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="Full local reads are implemented by the Windows host adapter.",
)


class ScriptedModel(InferenceEngine):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[dict]] = []

    def respond(self, messages):
        raise AssertionError("Agent mode must use the native capability boundary.")

    def respond_with_capabilities(self, messages, capabilities):
        assert [item.name for item in capabilities] == ["filesystem.stat"]
        self.requests.append(deepcopy(messages))
        return self.responses.pop(0)


def _stat_call(path: str) -> ModelResponse:
    return ModelResponse.calls(
        (
            ModelCapabilityCall(
                provider_call_id="phase9-stat",
                capability="filesystem.stat",
                arguments={"path": path},
            ),
        )
    )


def _full_local_service(tmp_path: Path, model: InferenceEngine):
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "user-home"
    portable_root.mkdir()
    user_home.mkdir()
    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    config = AgentFeatureConfig(
        filesystem_stat_enabled=True,
        full_local_read_enabled=True,
    )
    runtime = build_filesystem_stat_runtime(
        model,
        config=config,
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    assert isinstance(runtime, AgentRuntime)
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    return service, runtime, policy, portable_root, user_home


def test_full_local_feature_gate_requires_metadata_agent_and_explicit_values(
    monkeypatch,
    tmp_path: Path,
):
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    monkeypatch.setattr(
        agent_config_module,
        "PATHS",
        SimpleNamespace(config=config_directory),
    )
    monkeypatch.delenv("ORSI_ENABLE_FILESYSTEM_STAT", raising=False)
    monkeypatch.delenv("ORSI_ENABLE_FILESYSTEM_LIST", raising=False)
    monkeypatch.delenv("ORSI_ENABLE_FULL_LOCAL_READ", raising=False)

    assert load_agent_feature_config() == AgentFeatureConfig()
    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_STAT", "1")
    monkeypatch.setenv("ORSI_ENABLE_FULL_LOCAL_READ", "yes")
    enabled = load_agent_feature_config()
    assert enabled.filesystem_stat_enabled
    assert not enabled.filesystem_list_enabled
    assert enabled.full_local_read_enabled

    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_LIST", "on")
    enabled = load_agent_feature_config()
    assert enabled.filesystem_list_enabled

    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_STAT", "0")
    with pytest.raises(ValueError, match="Directory listing requires"):
        load_agent_feature_config()

    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_STAT", "1")
    monkeypatch.setenv("ORSI_ENABLE_FULL_LOCAL_READ", "occasionally")
    with pytest.raises(ValueError, match="explicit true or false"):
        load_agent_feature_config()


def test_full_local_policy_snapshots_only_enabled_local_drive_roots(tmp_path: Path):
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    portable_root.mkdir()
    user_home.mkdir()
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )

    roots = policy.permission_roots()
    assert roots
    assert roots == policy.permission_roots()
    assert all(root.parent == root for root in roots)
    assert all(
        _windows_drive_type(root)
        in {
            WindowsDriveType.REMOVABLE,
            WindowsDriveType.FIXED,
            WindowsDriveType.RAMDISK,
        }
        for root in roots
    )


def test_full_local_config_without_acknowledged_policy_fails_closed(tmp_path: Path):
    model = ScriptedModel([ModelResponse.text("unused")])
    portable_root = tmp_path / "portable"
    portable_root.mkdir()

    with pytest.raises(AgentBootstrapError, match="do not match"):
        build_filesystem_stat_runtime(
            model,
            config=AgentFeatureConfig(
                filesystem_stat_enabled=True,
                full_local_read_enabled=True,
            ),
            portable_root=portable_root,
            state_directory=tmp_path / "state",
        )


def test_full_local_stat_reads_host_metadata_outside_portable_root(tmp_path: Path):
    private_content = "PHASE9-CONTENT-MUST-NOT-REACH-THE-MODEL"
    outside = tmp_path / "host-project" / "probe.txt"
    outside.parent.mkdir()
    outside.write_text(private_content, encoding="utf-8")
    model = ScriptedModel(
        [_stat_call(str(outside.resolve())), ModelResponse.text("Host metadata received.")]
    )
    service, runtime, policy, portable_root, _user_home = _full_local_service(
        tmp_path, model
    )
    try:
        assert service.host_read_scope == HostReadScope.FULL_LOCAL
        assert service.run("Inspect the exact host path") == "Host metadata received."
        result = model.requests[1][-1]["result"]
        assert result["success"] is True
        assert Path(result["output"]["path"]) == outside.resolve()
        assert result["output"]["size_bytes"] == len(
            private_content.encode("utf-8")
        )
        assert not str(outside.resolve()).startswith(str(portable_root.resolve()))
        assert private_content not in json.dumps(model.requests)
        assert runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED
        prompt = model.requests[0][0]["content"].casefold()
        assert "enabled local filesystem drive" in prompt
        assert "current windows user's home directory" in prompt
        assert policy.permission_roots()
    finally:
        service.shutdown()


def test_full_local_relative_paths_resolve_from_current_user_home(tmp_path: Path):
    model = ScriptedModel(
        [_stat_call(r"Documents\notes.txt"), ModelResponse.text("Relative metadata received.")]
    )
    service, runtime, _policy, _portable_root, user_home = _full_local_service(
        tmp_path, model
    )
    target = user_home / "Documents" / "notes.txt"
    target.parent.mkdir()
    target.write_text("notes", encoding="utf-8")
    try:
        assert service.run("Inspect my notes metadata") == "Relative metadata received."
        result = model.requests[1][-1]["result"]
        assert result["success"] is True
        assert Path(result["output"]["path"]) == target.resolve()
        assert runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED
    finally:
        service.shutdown()


@pytest.mark.parametrize(
    "path",
    [r"\\server\share\secret.txt", r"\\.\PhysicalDrive0"],
)
def test_full_local_special_paths_are_denied_before_execution(
    tmp_path: Path,
    path: str,
):
    model = ScriptedModel(
        [_stat_call(path), ModelResponse.text("The request was denied.")]
    )
    service, runtime, _policy, _portable_root, _user_home = _full_local_service(
        tmp_path, model
    )
    try:
        assert service.run("Inspect the requested path") == "The request was denied."
        result = model.requests[1][-1]["result"]
        assert result["success"] is False
        assert result["error"]["code"] == "permission_denied"
        assert runtime.executor.journal.records == ()
    finally:
        service.shutdown()


def test_full_local_mode_preserves_ordinary_conversation_without_calls(tmp_path: Path):
    model = ScriptedModel([ModelResponse.text("Pancakes use flour, eggs, milk, and butter.")])
    service, runtime, _policy, _portable_root, _user_home = _full_local_service(
        tmp_path, model
    )
    try:
        answer = service.run("Give me a pancake recipe")
        assert answer.startswith("Pancakes")
        assert len(model.requests) == 1
        assert runtime.executor.journal.records == ()
    finally:
        service.shutdown()
