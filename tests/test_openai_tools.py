from __future__ import annotations

import json
import logging
from copy import deepcopy
from unittest.mock import Mock

import httpx
import openai
import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agent.bootstrap import build_agent_runtime
from app.agent.runtime import AgentRunStatus
from app.capabilities.catalog import build_builtin_registry
from app.capabilities.filesystem_list import FilesystemListArguments
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import CallLifecycleState
from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine, normalize_tool_response
from app.inference.openai_tools import responses_function_tools, responses_input
from app.inference.protocol import (ModelCapabilityCall, ModelCapabilityDefinition, ModelProtocolFailureCode,
                                    ModelResponseKind, model_capability_calls_message,
                                    model_capability_result_message)
from app.security.permissions import ApprovalStatus, PermissionDecision
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import EchoCapability, BatchEchoCapability, build_runtime, run
from tests.test_openai_phase1 import config, response, sse_response
from tests.test_cloud_inference import capability_definition


def name(definition):
    return responses_function_tools((definition,))[0]["name"]


def function(definition=None, arguments=None, **changes):
    definition = definition or capability_definition()
    item = {"type": "function_call", "id": "fc_item_not_the_call_id", "call_id": "call_exact_1",
            "name": name(definition), "arguments": json.dumps(arguments or {"path": "probe.txt"}),
            "status": "completed"}
    item.update(changes)
    if "id" not in changes:
        item["id"] = "fc_" + item["call_id"] if isinstance(item["call_id"], str) else "fc_invalid"
    return item


def result_envelope(capability="filesystem.stat", **changes):
    value = {"call_id": "internal_execution_id", "capability": capability, "success": True,
             "output": {"size_bytes": 9}, "error": None, "duration_ms": 1, "metadata": {}}
    value.update(changes)
    return value


def scripted_sdk(monkeypatch, payloads, *, engine_config=None):
    bodies = []
    def handle(request):
        bodies.append(json.loads(request.content))
        assert len(bodies) <= len(payloads), "Unexpected extra SDK request"
        return sse_response(payloads[len(bodies) - 1])
    transport = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = openai.AsyncOpenAI(api_key="fake-never-live", max_retries=0, http_client=transport)
    def http_factory(**kwargs):
        transport.event_hooks = kwargs["event_hooks"]
        return transport
    monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", http_factory)
    factory = Mock(return_value=client)
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    return OpenAIResponsesInferenceEngine(engine_config or config(), api_key="fake-never-live"), client, bodies, factory


def test_strict_wire_schema_preserves_list_defaults_and_internal_manifest():
    schema = FilesystemListArguments.model_json_schema()
    definition = ModelCapabilityDefinition(name="filesystem.list", description="List bounded entries.", input_schema=schema)
    before = deepcopy(definition.input_schema)
    tool = responses_function_tools((definition,))[0]
    assert tool["type"] == "function" and tool["strict"] is True and "function" not in tool
    parameters = tool["parameters"]
    assert parameters["required"] == list(parameters["properties"])
    assert parameters["additionalProperties"] is False
    assert '"default":' not in json.dumps(parameters)
    normalized = normalize_tool_response(response(output=[function(definition,
        {"path": "folder", "cursor": None, "max_entries": None})]), (definition,))
    assert normalized.capability_calls[0].arguments == {"path": "folder", "cursor": None}
    effective = FilesystemListArguments.model_validate(normalized.capability_calls[0].arguments)
    assert effective.max_entries == FilesystemListArguments.model_fields["max_entries"].default
    assert definition.input_schema == before


def test_nested_refs_arrays_and_nullable_defaults_round_trip_without_mutation():
    class Child(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        required_null: str | None
        enabled: bool = False
    class Arguments(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        children: list[Child]
    definition = ModelCapabilityDefinition(name="test.nested", description="Nested test.", input_schema=Arguments.model_json_schema())
    tool = responses_function_tools((definition,))[0]
    assert tool["parameters"]["$defs"]["Child"]["required"] == ["required_null", "enabled"]
    wire = {"children": [{"required_null": None, "enabled": None}]}
    normalized = normalize_tool_response(response(output=[function(definition, wire)]), (definition,))
    call = normalized.capability_calls[0]
    assert call.arguments == {"children": [{"required_null": None}]}
    assert Arguments.model_validate(call.arguments).children[0].enabled is False
    transcript = [model_capability_calls_message((call,), provider_message_id="scope"),
                  model_capability_result_message(call, result_envelope("test.nested"), provider_message_id="scope")]
    encoded = responses_input(transcript, (definition,))
    assert json.loads(encoded[0]["arguments"]) == wire
    assert encoded[0]["call_id"] == encoded[1]["call_id"] == "call_exact_1"


@pytest.mark.parametrize("keyword,value", [("oneOf", []), ("allOf", []), ("if", {}),
                                          ("patternProperties", {}), ("unknown", True)])
def test_unsupported_schema_is_rejected_instead_of_weakened(keyword, value):
    definition = capability_definition().model_copy(update={"input_schema": {
        **capability_definition().input_schema, keyword: value}})
    with pytest.raises(ValueError):
        responses_function_tools((definition,))


def test_open_or_external_referenced_objects_fail_before_inference():
    for child in ({"type": "object", "additionalProperties": True}, {"$ref": "https://example.test/schema"}):
        definition = capability_definition().model_copy(update={"input_schema": {
            "type": "object", "additionalProperties": False, "properties": {"path": child}, "required": ["path"]}})
        with pytest.raises(ValueError):
            responses_function_tools((definition,))


def test_every_builtin_catalog_tool_compiles_without_changing_its_schema(tmp_path):
    flags = {field: True for field in AgentFeatureConfig.model_fields if field.endswith("_enabled") and field != "full_local_read_enabled"}
    registry = build_builtin_registry(AgentFeatureConfig(**flags), application_root=tmp_path, state_directory=tmp_path / "state")
    definitions = registry.model_definitions()
    before = [definition.model_dump_json() for definition in definitions]
    tools = responses_function_tools(definitions)
    assert len(tools) == 12
    assert all(tool["strict"] is True for tool in tools)
    assert [definition.model_dump_json() for definition in definitions] == before


def test_real_sdk_flat_tools_call_id_and_validated_output_round_trip(monkeypatch, caplog):
    definition = capability_definition()
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [response(output=[function()]), response("Done")])
    messages = [{"role": "user", "content": "private-request"}]
    with caplog.at_level(logging.INFO):
        first = engine.respond_with_capabilities(messages, (definition,))
        call = first.capability_calls[0]
        assert call.provider_call_id == "call_exact_1" and call.provider_call_id != "fc_item_not_the_call_id"
        assert first.completion.usage.total_tokens == 22
        messages += [model_capability_calls_message((call,), provider_message_id="harness_scope"),
                     model_capability_result_message(call, result_envelope(), provider_message_id="harness_scope")]
        second = engine.respond_with_capabilities(messages, (definition,))
    assert second.kind == ModelResponseKind.ASSISTANT_TEXT and second.assistant_text == "Done"
    assert bodies[0]["tools"] == responses_function_tools((definition,))
    assert bodies[0]["tool_choice"] == "auto" and bodies[0]["parallel_tool_calls"] is True
    assert all(body["store"] is False and "previous_response_id" not in body for body in bodies)
    assert bodies[1]["input"][-2]["call_id"] == bodies[1]["input"][-1]["call_id"] == "call_exact_1"
    assert json.loads(bodies[1]["input"][-1]["output"]) == result_envelope()
    assert all(secret not in caplog.text for secret in ("fake-never-live", "private-request", "probe.txt"))
    engine.close()
    assert client.is_closed()


@pytest.mark.parametrize("changes,expected", [
    ({"call_id": "bad id"}, ModelProtocolFailureCode.MALFORMED_CALL_ID),
    ({"call_id": None}, ModelProtocolFailureCode.MALFORMED_CALL_ID),
    ({"name": "filesystem.stat"}, ModelProtocolFailureCode.UNKNOWN_CAPABILITY),
    ({"name": "UNKNOWN_TOOL"}, ModelProtocolFailureCode.UNKNOWN_CAPABILITY),
    ({"arguments": '{"path":"probe",}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":"probe"'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":"a","path":"b"}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":NaN}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":1e999}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '[]'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":null}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":12}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
    ({"arguments": '{"path":"probe","extra":"private"}'}, ModelProtocolFailureCode.MALFORMED_ARGUMENTS),
])
def test_invalid_native_call_rejects_entire_batch_without_syntax_or_name_repair(changes, expected):
    normalized = normalize_tool_response(response(output=[function(call_id="valid_first"), function(**changes)]), (capability_definition(),))
    assert normalized.kind == ModelResponseKind.PROTOCOL_FAILURE
    assert normalized.protocol_failure.code == expected
    assert not normalized.capability_calls
    assert normalized.completion.usage.total_tokens == 22
    assert "private" not in normalized.protocol_failure.message


def test_duplicate_and_too_many_calls_are_rejected_as_one_response():
    definitions = (capability_definition(),)
    duplicate = normalize_tool_response(response(output=[function(), function()]), definitions)
    assert duplicate.protocol_failure.code == ModelProtocolFailureCode.DUPLICATE_CALL_ID
    excessive = normalize_tool_response(response(output=[function(call_id=f"call_{i}") for i in range(17)]), definitions)
    assert excessive.protocol_failure.code == ModelProtocolFailureCode.TOO_MANY_CALLS


@pytest.mark.parametrize("status", ["incomplete", "cancelled"])
def test_even_valid_json_calls_in_noncompleted_responses_never_execute(status):
    normalized = normalize_tool_response(response(output=[function()], status=status,
                                                  incomplete_details={"reason": "max_output_tokens"}), (capability_definition(),))
    assert normalized.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED
    assert normalized.completion.incomplete and not normalized.capability_calls


@pytest.mark.parametrize("status", ["in_progress", "incomplete"])
def test_completed_response_with_nonterminal_function_item_never_executes(status):
    normalized = normalize_tool_response(response(output=[function(status=status)]), (capability_definition(),))
    assert normalized.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED
    assert normalized.completion.incomplete and not normalized.capability_calls


def test_optional_item_status_and_absent_item_id_are_accepted_with_terminal_parent():
    item = function()
    del item["status"], item["id"]
    assert normalize_tool_response(response(output=[item]), (capability_definition(),)).kind == ModelResponseKind.CAPABILITY_CALLS


def test_refusal_is_visible_but_refusal_mixed_with_calls_cannot_execute():
    payload = response()
    payload["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot do that."}]
    text = normalize_tool_response(payload, (capability_definition(),))
    assert text.assistant_text == "Cannot do that." and text.completion.finish_reason == "refusal"
    payload["output"].append(function())
    mixed = normalize_tool_response(payload, (capability_definition(),))
    assert mixed.protocol_failure.code == ModelProtocolFailureCode.MIXED_RESPONSE and not mixed.capability_calls


def test_assistant_text_alongside_calls_is_retained():
    payload = response("I will inspect the path.")
    payload["output"].append(function())
    normalized = normalize_tool_response(payload, (capability_definition(),))
    assert normalized.assistant_text == "I will inspect the path." and len(normalized.capability_calls) == 1


def test_partial_text_and_empty_partial_messages_have_safe_completion_state():
    payload = response("Partial", status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    payload["output"].append(function(arguments="invalid partial"))
    result = normalize_tool_response(payload, (capability_definition(),))
    assert result.partial_text == "Partial" and result.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED
    payload["output"][0]["content"] = []
    assert normalize_tool_response(payload, (capability_definition(),)).protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED


def test_reasoning_profile_supports_native_calls_with_replay_evidence(monkeypatch):
    payload = response(model="gpt-6.1-sol", output=[{"type": "reasoning", "id": "rs_1", "summary": [],
                                                   "encrypted_content": "opaque"}, function()])
    engine, _, bodies, factory = scripted_sdk(monkeypatch, [payload])
    engine.select_model("gpt-6.1-sol")
    result = engine.respond_with_capabilities([{"role": "user", "content": "Inspect"}], (capability_definition(),))
    assert result.kind == ModelResponseKind.CAPABILITY_CALLS
    assert result.openai_response.items() == payload["output"]
    assert bodies[0]["reasoning"] == {"effort": "medium"}
    assert bodies[0]["include"] == ["reasoning.encrypted_content"]
    assert "temperature" not in bodies[0]
    engine.close()


@pytest.mark.parametrize("change", ["orphan", "wrong_id", "wrong_scope", "envelope_capability", "malformed_envelope", "unresolved", "duplicate_result"])
def test_invalid_result_history_stops_before_sdk_construction(monkeypatch, change):
    call = ModelCapabilityCall(provider_call_id="call_exact_1", capability="filesystem.stat", arguments={"path": "probe.txt"})
    messages = [model_capability_calls_message((call,), provider_message_id="scope"),
                model_capability_result_message(call, result_envelope(), provider_message_id="scope")]
    if change == "orphan":
        messages = messages[1:]
    elif change == "wrong_id":
        messages[1]["provider_call_id"] = "call_other"
    elif change == "wrong_scope":
        messages[1]["provider_message_id"] = "other_scope"
    elif change == "envelope_capability":
        messages[1]["result"]["capability"] = "filesystem.list"
    elif change == "malformed_envelope":
        messages[1]["result"]["success"] = False
    elif change == "unresolved":
        messages.pop()
    else:
        messages.append(deepcopy(messages[-1]))
    engine, _, bodies, factory = scripted_sdk(monkeypatch, [])
    with pytest.raises(ValueError):
        engine.respond_with_capabilities(messages, (capability_definition(),))
    assert not bodies
    factory.assert_not_called()
    engine.close()


def test_duplicate_actual_ids_across_harness_scopes_are_not_rewritten():
    call = ModelCapabilityCall(provider_call_id="call_reused", capability="filesystem.stat", arguments={"path": "probe.txt"})
    messages = []
    for scope in ("first", "second"):
        messages += [model_capability_calls_message((call,), provider_message_id=scope),
                     model_capability_result_message(call, result_envelope(), provider_message_id=scope)]
    with pytest.raises(ValueError, match="unique actual"):
        responses_input(messages, (capability_definition(),))


def test_rejected_transcript_validation_does_not_echo_sensitive_values():
    messages = [{"role": "assistant", "capability_calls": [{"provider_call_id": "private invalid id",
                "capability": "filesystem.stat", "arguments": {"path": "private-path"}}]}]
    with pytest.raises(ValueError) as failure:
        responses_input(messages, (capability_definition(),))
    assert "private" not in str(failure.value) and failure.value.__suppress_context__


def test_reused_id_in_new_response_is_rejected_before_execution(monkeypatch):
    engine, _, _, _ = scripted_sdk(monkeypatch, [response(output=[function()])])
    call = ModelCapabilityCall(provider_call_id="call_exact_1", capability="filesystem.stat", arguments={"path": "probe.txt"})
    messages = [model_capability_calls_message((call,)), model_capability_result_message(call, result_envelope())]
    normalized = engine.respond_with_capabilities(messages, (capability_definition(),))
    assert normalized.protocol_failure.code == ModelProtocolFailureCode.DUPLICATE_CALL_ID
    engine.close()


@pytest.mark.parametrize("decision", [PermissionDecision.ALLOW, PermissionDecision.DENY, PermissionDecision.ASK])
def test_existing_harness_permissions_and_journaling_apply_to_real_sdk_calls(monkeypatch, tmp_path, decision):
    capability = EchoCapability()
    definition = CapabilityRegistry((CapabilityRegistration(capability, enabled=True, model_visible=True),)).model_definitions()[0]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=[function(definition, {"value": "hello"})]), response("Done")])
    runtime, _, implementation, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine, decision=decision)
    result = run(runtime, tmp_path)
    if decision == PermissionDecision.ASK:
        assert result.status == AgentRunStatus.APPROVAL_REQUIRED
        assert implementation.values == [] and journal.records[0].state == CallLifecycleState.AWAITING_APPROVAL
        assert len(bodies) == 1
    else:
        assert result.status == AgentRunStatus.COMPLETED and len(bodies) == 2
        assert implementation.values == (["hello"] if decision == PermissionDecision.ALLOW else [])
        output = json.loads(bodies[1]["input"][-1]["output"])
        assert output["success"] is (decision == PermissionDecision.ALLOW)
        assert bodies[1]["input"][-1]["call_id"] == "call_exact_1"
    engine.close()


def test_approved_ask_uses_existing_approval_manager_and_executes_once(monkeypatch, tmp_path):
    capability = EchoCapability()
    definition = CapabilityRegistry((CapabilityRegistration(capability, enabled=True, model_visible=True),)).model_definitions()[0]
    engine, _, _, _ = scripted_sdk(monkeypatch, [response(output=[function(definition, {"value": "hello"})]), response("Done")])
    requester = lambda manager: lambda record: manager.resolve(record.approval_id, ApprovalStatus.APPROVED)
    runtime, _, implementation, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine,
        decision=PermissionDecision.ASK, approval_requester_factory=requester)
    assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
    assert implementation.values == ["hello"] and journal.records[0].state == CallLifecycleState.COMPLETED
    engine.close()


def test_semantically_invalid_arguments_use_existing_pydantic_validation_and_feedback(monkeypatch, tmp_path):
    class BoundedArguments(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        value: str = Field(max_length=2)
    class BoundedEcho(EchoCapability):
        arguments_model = BoundedArguments
    capability = BoundedEcho()
    definition = CapabilityRegistry((CapabilityRegistration(capability, enabled=True, model_visible=True),)).model_definitions()[0]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=[function(definition, {"value": "too long"})]), response("Invalid arguments")])
    runtime, _, implementation, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine)
    assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
    assert implementation.values == [] and journal.records == ()
    assert json.loads(bodies[1]["input"][-1]["output"])["error"]["code"] == "invalid_arguments"
    engine.close()


def test_multiple_calls_keep_order_and_are_executed_sequentially(monkeypatch, tmp_path):
    capability = BatchEchoCapability()
    definition = CapabilityRegistry((CapabilityRegistration(capability, enabled=True, model_visible=True),)).model_definitions()[0]
    items = [function(definition, {"value": str(i)}, call_id=f"call_{i}") for i in range(3)]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=items), response("Done")])
    runtime, _, implementation, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine)
    assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
    assert implementation.values == ["0", "1", "2"] and len(journal.records) == 3
    outputs = [item for item in bodies[1]["input"] if item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in outputs] == ["call_0", "call_1", "call_2"]
    engine.close()


def test_builtin_stat_through_conversation_is_persisted_and_reconstructable(monkeypatch, tmp_path):
    (tmp_path / "probe.txt").write_bytes(b"private-fixture")
    engine, client, _, _ = scripted_sdk(monkeypatch, [response(output=[function()]), response("Done")])
    features = AgentFeatureConfig(filesystem_stat_enabled=True)
    runtime = build_agent_runtime(engine, config=features, portable_root=tmp_path, state_directory=tmp_path / "state")
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store, agent_runtime=runtime, portable_root=tmp_path, allowed_read_roots=(tmp_path,))
    assert service.run("Inspect probe.txt") == "Done"
    restored = ConversationStore(store.path).agent_messages()
    encoded = responses_input(restored, runtime.registry.model_definitions())
    outputs = [item for item in encoded if item.get("type") == "function_call_output"]
    assert len(outputs) == 1 and outputs[0]["call_id"] == "call_exact_1"
    assert json.loads(outputs[0]["output"])["success"] is True
    service.shutdown()
    assert client.is_closed()
