from __future__ import annotations

from copy import deepcopy
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agent.runtime import AgentRunStatus, AgentRuntime, AgentRuntimeLimits
from app.capabilities.application_launch import (
    ApplicationLaunchArguments,
    ApplicationLaunchCapability,
)
from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    ExecutionIsolation,
    PermissionClass,
)
from app.execution.audit import (
    CapabilityCrashJournal,
    JournaledCapabilityExecutor,
)
from app.execution.executor import CapabilityExecutor
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.security.host_access import HostAccessPolicy
from app.security.permissions import (
    ApprovalManager,
    ApprovalStatus,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
    prepare_capability_call,
)
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.protocol import (
    ModelCapabilityCall,
    ModelProtocolFailureCode,
    ModelResponse,
    ModelResponseKind,
    native_function_tools,
    normalize_native_chat_message,
)
from app.inference.tool_repair import (
    StructuredCallDecodeError,
    decode_constrained_decision,
    decode_json_object,
)
from app.inference.contracts import ModelCapabilityDefinition
from app.runtime.cancellation import CancellationToken


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


class EchoCapability(Capability[EchoArguments]):
    name = "test.echo"
    description = "Echo one test value."
    arguments_model = EchoArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def __init__(self):
        self.values: list[str] = []

    def execute(self, arguments, context):
        self.values.append(arguments.value)
        return {"value": arguments.value}


class TextOnlyStructuredFallbackModel(InferenceEngine):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[dict]] = []

    def respond(self, messages):
        self.requests.append(deepcopy(messages))
        return self.responses.pop(0)


class NativeScriptedModel(InferenceEngine):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[dict]] = []
        self.definitions: list[tuple[ModelCapabilityDefinition, ...]] = []

    def respond(self, messages):
        raise AssertionError("Native-capable tests must not use the text fallback.")

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append(deepcopy(messages))
        self.definitions.append(tuple(capabilities))
        return self.responses.pop(0)


def _definition(name: str = "filesystem.stat") -> ModelCapabilityDefinition:
    return ModelCapabilityDefinition(
        name=name,
        description="Inspect one path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def _native_call(name: str, arguments: str):
    return {
        "id": "provider-call-1",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _echo_runtime(tmp_path: Path, model: InferenceEngine):
    capability = EchoCapability()
    registry = CapabilityRegistry(
        (CapabilityRegistration(capability, enabled=True, model_visible=True),)
    )
    gate = PermissionGate(
        (
            PermissionRule(
                "echo-read",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="test.echo",
            ),
        )
    )
    ids = count(1)
    runtime = AgentRuntime(
        model=model,
        registry=registry,
        permission_gate=gate,
        approval_manager=ApprovalManager(),
        executor=JournaledCapabilityExecutor(
            CapabilityExecutor(),
            CapabilityCrashJournal(tmp_path / "fallback-journal.json"),
        ),
        call_id_factory=lambda: f"internal-{next(ids)}",
        fallback_call_id_factory=lambda: "fallback-provider-1",
    )
    return runtime, capability


def test_native_name_capitalization_and_safe_json_syntax_are_repaired():
    definition = _definition()
    provider_name = native_function_tools((definition,))[0]["function"]["name"]

    response = normalize_native_chat_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                _native_call(provider_name.upper(), '{"path":"My File.txt",}')
            ],
        },
        (definition,),
    )

    assert response.kind == ModelResponseKind.CAPABILITY_CALLS
    assert response.capability_calls[0].capability == "filesystem.stat"
    assert response.capability_calls[0].arguments == {"path": "My File.txt"}


def test_safe_repair_closes_unambiguous_objects_but_never_scrapes_prose():
    assert decode_json_object('{"path":"C:\\\\Users\\\\Me\\\\A B.txt"')[0] == {
        "path": r"C:\Users\Me\A B.txt"
    }
    with pytest.raises(StructuredCallDecodeError):
        decode_json_object('I would call {"tool":"filesystem.stat","arguments":{}}')
    with pytest.raises(StructuredCallDecodeError):
        decode_json_object('{"path":"one","path":"two"}')


def test_constrained_decision_rejects_mixed_text_and_hallucinated_fields():
    with pytest.raises(StructuredCallDecodeError):
        decode_constrained_decision(
            '{"tool":"test.echo","arguments":{"value":"x"},"response":"done"}'
        )
    with pytest.raises(StructuredCallDecodeError):
        decode_constrained_decision(
            '{"tool":"test.echo","arguments":{},"self_authorized":true}'
        )


def test_text_only_backend_uses_constrained_fallback_and_continues(tmp_path: Path):
    model = TextOnlyStructuredFallbackModel(
        [
            '{"tool":"TEST.ECHO","arguments":{"value":"héllo world"}}',
            '{"tool":null,"arguments":{},"response":"Completed safely."}',
        ]
    )
    runtime, capability = _echo_runtime(tmp_path, model)

    result = runtime.run(
        [{"role": "user", "content": "Echo héllo world"}],
        session_id="session-1",
        turn_id="turn-1",
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.assistant_text == "Completed safely."
    assert capability.values == ["héllo world"]
    assert len(model.requests) == 2
    assert '"name":"test.echo"' in model.requests[0][0]["content"]
    assert model.requests[1][-1]["content"].startswith("Trusted runtime result")


def test_text_fallback_fails_closed_for_prose_and_unknown_tools(tmp_path: Path):
    model = TextOnlyStructuredFallbackModel(
        [
            'I would call {"tool":"test.echo","arguments":{"value":"unsafe"}}',
            '{"tool":"shell.run","arguments":{"command":"cmd.exe"}}',
        ]
    )
    runtime, capability = _echo_runtime(tmp_path, model)

    result = runtime.run(
        [{"role": "user", "content": "Do something"}],
        session_id="session-1",
        turn_id="turn-1",
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
    )

    assert result.status == AgentRunStatus.PROTOCOL_FAILURE_LIMIT
    assert capability.values == []


@pytest.mark.parametrize(
    "value",
    [
        {"application": "blender"},
        {"application": "Blender", "file": r"C:\Scenes\My Scene.blend"},
        {"application": "blender", "file": "projects/My Scene.blend"},
        {"application": "blender", "file": "projektek/árvíztűrő.blend"},
    ],
)
def test_application_arguments_cover_optional_paths_spaces_windows_and_unicode(value):
    parsed = ApplicationLaunchArguments.model_validate(value)
    assert parsed.application == "blender"


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"application": "cmd"},
        {"application": 7},
        {"application": "blender", "approved": True},
        {"application": "blender", "file": 7},
    ],
)
def test_application_arguments_reject_missing_wrong_extra_and_self_authorizing_fields(value):
    with pytest.raises(ValidationError):
        ApplicationLaunchArguments.model_validate(value)


def test_application_launch_requires_bound_execute_approval_and_uses_no_shell(tmp_path: Path):
    executable = tmp_path / "blender.exe"
    executable.write_bytes(b"test executable")
    scene = tmp_path / "My ünicode Scene.blend"
    scene.write_text("scene", encoding="utf-8")
    launches: list[tuple[list[str], Path]] = []
    capability = ApplicationLaunchCapability(
        locator=lambda _name: executable,
        launcher=lambda command, cwd: (
            launches.append((list(command), cwd)) or SimpleNamespace(pid=42)
        ),
    )
    context = CapabilityContext(
        call_id="launch-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
        cancellation=CancellationToken(),
        host_access_policy=HostAccessPolicy.portable_root(tmp_path),
    )
    prepared = prepare_capability_call(
        capability,
        {"application": "blender", "file": scene.name},
        context,
    )
    gate = PermissionGate(
        (
            PermissionRule(
                "launch-ask",
                PermissionDecision.ASK,
                permission=PermissionClass.EXECUTE,
                capability_pattern="application.launch",
            ),
        )
    )
    evaluation = gate.evaluate(prepared)
    manager = ApprovalManager(id_factory=lambda: "approval-1")

    assert manager.authorize(evaluation).allowed is False
    assert launches == []
    record = manager.request(evaluation)
    assert "Launch Blender" in record.approval_preview
    manager.resolve(record.approval_id, ApprovalStatus.APPROVED)
    authorization = manager.authorize(evaluation, approval_id=record.approval_id)
    result = CapabilityExecutor().execute(prepared, authorization)

    assert result.success is True
    assert launches == [([str(executable.resolve()), str(scene.resolve())], tmp_path.resolve())]
    assert result.output["pid"] == 42


@pytest.mark.parametrize(
    "utterance",
    [
        "open blender",
        "launch Blender",
        "start blender please",
        "could you fire up Blender?",
        "open my 3d program Blender",
    ],
)
def test_natural_language_variants_reach_model_with_launch_tool(
    tmp_path: Path,
    utterance: str,
):
    executable = tmp_path / "blender.exe"
    executable.write_bytes(b"test executable")
    launches = []
    launch = ApplicationLaunchCapability(
        locator=lambda _name: executable,
        launcher=lambda command, cwd: (
            launches.append((command, cwd)) or SimpleNamespace(pid=84)
        ),
    )
    model = NativeScriptedModel(
        [
            ModelResponse.calls(
                (
                    ModelCapabilityCall(
                        provider_call_id="launch-provider-1",
                        capability="application.launch",
                        arguments={"application": "blender"},
                    ),
                )
            ),
            ModelResponse.text("Blender was launched after approval."),
        ]
    )
    registry = CapabilityRegistry(
        (
            CapabilityRegistration(
                FilesystemStatCapability(), enabled=True, model_visible=True
            ),
            CapabilityRegistration(launch, enabled=True, model_visible=True),
        )
    )
    policy = HostAccessPolicy.portable_root(tmp_path)
    gate = PermissionGate(
        (
            PermissionRule(
                "read-root",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=tmp_path,
            ),
            PermissionRule(
                "launch-ask",
                PermissionDecision.ASK,
                permission=PermissionClass.EXECUTE,
                capability_pattern="application.launch",
            ),
        )
    )
    manager = ApprovalManager(id_factory=lambda: "approval-1")
    runtime = AgentRuntime(
        model=model,
        registry=registry,
        permission_gate=gate,
        approval_manager=manager,
        approval_requester=lambda record: manager.resolve(
            record.approval_id, ApprovalStatus.APPROVED
        ),
        executor=JournaledCapabilityExecutor(
            CapabilityExecutor(),
            CapabilityCrashJournal(tmp_path / "launch-journal.json"),
        ),
        call_id_factory=lambda: "internal-launch-1",
    )
    service = ConversationService(
        model,
        ConversationStore(tmp_path / "conversation.json"),
        agent_runtime=runtime,
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
        host_access_policy=policy,
    )

    answer = service.run(utterance)

    assert answer == "Blender was launched after approval."
    assert len(launches) == 1
    assert {item.name for item in model.definitions[0]} == {
        "filesystem.stat",
        "application.launch",
    }
    assert model.requests[0][-1] == {"role": "user", "content": utterance}


def test_unknown_native_tool_still_returns_invalid_tool_feedback():
    response = normalize_native_chat_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_native_call("orsi_hallucinated", "{}")],
        },
        (_definition(),),
    )
    assert response.protocol_failure.code == ModelProtocolFailureCode.UNKNOWN_CAPABILITY
