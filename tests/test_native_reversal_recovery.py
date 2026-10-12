"""Cloud wire-to-Windows rollback recovery without assistant narration."""
import json
import os

import pytest
from pydantic import ValidationError

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.capabilities.filesystem_edit_text import FilesystemEditTextArguments
from app.capabilities.filesystem_read_text import FilesystemReadTextArguments
from app.capabilities.filesystem_write_text import FilesystemWriteTextArguments
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.openai_backend import normalize_tool_response
from app.inference.openai_tools import responses_input
from app.inference.protocol import ModelCapabilityCall, ModelCapabilityDefinition, ModelResponseKind
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig
from tests.test_openai_phase1 import response
from tests.test_openai_tools import function, name, scripted_sdk
from tests.test_openai_replay import evidence, history_for


def definition(name, arguments):
    return ModelCapabilityDefinition(name=name, description="Native file operation.", input_schema=arguments.model_json_schema())


@pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter")
def test_actual_sdk_tool_only_reversal_reaches_normal_approval(monkeypatch, tmp_path):
    path = tmp_path / "App.tsx"
    path.write_text("disabled", encoding="utf-8")
    read = definition("filesystem.read_text", FilesystemReadTextArguments)
    edit = definition("filesystem.edit_text", FilesystemEditTextArguments)

    def tool(index, capability, **arguments):
        wire = {key: None for key in capability.input_schema["properties"]}
        wire.update(path=str(path), **arguments)
        return response(output=[function(capability, wire, call_id=f"call_{index}")], id=f"resp_{index}")

    reason = "The current source does not meet the animation request; restore the baseline before correcting it."
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [tool(1, read),
        tool(2, edit, old_text="disabled", new_text="broken"),
        tool(3, edit, old_text="broken", new_text="disabled"), tool(4, read),
        tool(5, edit, old_text="broken", new_text="disabled", reversal_reason=reason),
        tool(6, edit, old_text="disabled", new_text="enabled"), tool(7, read),
        response("Re-enabled the animation; source checked, runtime checks unrun.", id="resp_answer"),
        response(json.dumps({"goal_id": "turn-1", "status": "ready", "remaining": []}), id="resp_review")])
    portable = tmp_path / "portable"
    portable.mkdir()
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True, full_local_read_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(engine, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
        portable_root=portable, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    approvals = []

    def approve(record):
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)

    service.set_approval_requester(approve)
    try:
        service.run("great. currently the first section animation is disabled, can you re-enable it?\\")
        result = service._turn_result
        assert result.status == AgentRunStatus.COMPLETED
        assert path.read_text(encoding="utf-8") == "enabled" and len(approvals) == 3
        assert result.semantic_corrections == 1 and result.protocol_failures == 0
        assert result.settled_calls[2].result.metadata["edit_recovery"] == "revision_reversal"
        assert result.settled_calls[4].call.arguments["reversal_reason"] == reason
        assert result.settled_calls[4].result.success
        replayed = next(item for item in bodies[5]["input"] if item.get("type") == "function_call" and item.get("call_id") == "call_5")
        assert json.loads(replayed["arguments"])["reversal_reason"] == reason
        assert "reversal_reason" in next(tool for tool in bodies[0]["tools"] if tool["name"] == name(edit))["parameters"]["properties"]
    finally:
        service.shutdown()
        engine.close()
    assert client.is_closed()


@pytest.mark.parametrize("name,model,arguments", [
    ("filesystem.edit_text", FilesystemEditTextArguments, {"old_text": "old", "new_text": "new"}),
    ("filesystem.write_text", FilesystemWriteTextArguments, {"text": "new"}),
])
@pytest.mark.parametrize("reason", ["", 1, "x" * 1001])
def test_cloud_rejects_invalid_reversal_reason_before_execution(name, model, arguments, reason):
    capability = definition(name, model)
    wire = {key: None for key in capability.input_schema["properties"]}
    wire.update(path="C:\\fixture\\App.tsx", **arguments, reversal_reason=reason)
    normalized = normalize_tool_response(response(output=[function(capability,
        wire)]), (capability,))
    # The wire layer owns JSON types; the executor's Pydantic boundary owns value
    # constraints. Either rejection occurs before approval or filesystem access.
    if normalized.kind != ModelResponseKind.PROTOCOL_FAILURE:
        with pytest.raises(ValidationError):
            model.model_validate(normalized.capability_calls[0].arguments)


@pytest.mark.parametrize("capability,model,arguments", [
    ("filesystem.edit_text", FilesystemEditTextArguments,
        {"path": "C:\\fixture\\App.tsx", "old_text": "old", "new_text": "new", "replace_all": False, "expected_sha256": None}),
    ("filesystem.write_text", FilesystemWriteTextArguments, {"path": "C:\\fixture\\App.tsx", "text": "new"}),
])
def test_existing_cloud_edit_history_survives_optional_reason_argument(capability, model, arguments):
    current = definition(capability, model)
    output = [function(current, arguments)]  # Recorded before reversal_reason existed.
    calls = (ModelCapabilityCall(provider_call_id="call_exact_1", capability=capability, arguments=arguments),)
    history = history_for(evidence(output), calls)
    assert responses_input(history, (current,))[0] == output[0]
    # Existing evidence still must agree with the settled argument transcript.
    changed = {**output[0], "arguments": json.dumps({**arguments, "reversal_reason": "fabricated"})}
    with pytest.raises(ValueError, match="does not match"):
        responses_input(history_for(evidence([changed]), calls), (current,))
