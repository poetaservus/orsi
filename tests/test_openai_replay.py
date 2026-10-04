from __future__ import annotations

import json
import logging
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.capabilities.contracts import CapabilityResult
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.conversation.context import calculate_context_budget, select_context_request
from app.conversation.orchestrator import ConversationService
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore, TurnHistoryError
from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.hybrid import HybridInferenceEngine
from app.inference.openai_replay import MAX_REPLAY_BYTES, OpenAIReplay, REPLAY_KEY
from app.inference.openai_tools import responses_input
from app.inference.protocol import ModelCapabilityCall, ModelResponseKind, model_capability_calls_message, model_capability_result_message
from app.runtime.cancellation import CancellationSource
from app.security.permissions import PermissionDecision, ApprovalStatus
from tests.test_agent_runtime import EchoCapability, BatchEchoCapability, CancellingBatchEchoCapability, build_runtime, run
from tests.test_cloud_inference import capability_definition
from tests.test_openai_phase1 import response
from tests.test_openai_tools import function, scripted_sdk, result_envelope


@pytest.fixture(autouse=True)
def synthetic_catalog_in_test_prompt(monkeypatch):
    # ConversationService accepts only built-in names. Extend the fixture catalog
    # for the synthetic echo harness without changing production/acceptance prompts.
    import app.conversation.prompt as prompt
    monkeypatch.setattr(prompt, "_SUPPORTED_CAPABILITIES", (*prompt._SUPPORTED_CAPABILITIES, "test.echo"))


def reasoning(identity="rs_private"):
    return {"type": "reasoning", "id": identity, "summary": [], "encrypted_content": "opaque-private-evidence"}


def message(text, identity="msg_final", phase="final_answer"):
    return {"type": "message", "id": identity, "role": "assistant", "status": "completed", "phase": phase,
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


def definition_for(capability):
    return CapabilityRegistry((CapabilityRegistration(capability, enabled=True, model_visible=True),)).model_definitions()[0]


def evidence(output, identity="resp_private", model="gpt-6-luna"):
    return OpenAIReplay.from_payload(response(id=identity, model=model, output=output), model)


def history_for(replay, calls, *, scope="scope"):
    value = model_capability_calls_message(calls, provider_message_id=scope, assistant_text=replay.text.strip() or None)
    value[REPLAY_KEY] = replay.model_dump()
    return [value, *[model_capability_result_message(call, result_envelope(call.capability), provider_message_id=scope)
                    for call in calls]]


def service_for(engine, tmp_path, **runtime_args):
    runtime, _, implementation, journal, manager = build_runtime(tmp_path, [], model=engine, **runtime_args)
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store, agent_runtime=runtime, portable_root=tmp_path, allowed_read_roots=(tmp_path,))
    return service, runtime, implementation, journal, manager


def test_sdk_and_real_harness_preserve_whole_output_order_arguments_ids_and_phase(monkeypatch, tmp_path):
    capability = BatchEchoCapability()
    definition = definition_for(capability)
    output = [reasoning(), message("Working", "msg_commentary", "commentary"),
              function(definition, {"value": "one"}, call_id="call_one"),
              reasoning("rs_second"), function(definition, {"value": "two"}, call_id="call_two")]
    output[2]["arguments"] = ' { "value" : "one" } '
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [response(output=output),
        response(id="resp_done", output=[reasoning("rs_done"), message("Done")])])
    service, runtime, implementation, journal, _ = service_for(engine, tmp_path, capability=capability)
    runtime.context_recovery_enabled = True
    original = capability.execute
    def execute(arguments, context):
        durable = json.loads(service.store.path.read_text())
        assert json.loads(durable["turns"][0]["provider_responses"][0]["replay"]["items_json"]) == output
        return original(arguments, context)
    monkeypatch.setattr(capability, "execute", execute)
    assert service.run("Echo the test values") == "Done"
    assert implementation.values == ["one", "two"] and len(journal.records) == 2
    replayed = bodies[1]["input"]
    assert replayed[2:2 + len(output)] == output
    results = replayed[2 + len(output):]
    assert [item["call_id"] for item in results] == ["call_one", "call_two"]
    assert [json.loads(item["output"])["output"]["echo"] for item in results] == ["one", "two"]
    assert all(body["store"] is False and "previous_response_id" not in body for body in bodies)
    restored = ConversationStore(service.store.path)
    encoded = responses_input(restored.agent_messages(openai_replay=True), (definition,))
    assert encoded[1:1 + len(output)] == output
    assert encoded[-2:] == [reasoning("rs_done"), message("Done")]
    assert [m["content"] for m in restored.messages()] == ["Echo the test values", "Done"]
    assert "opaque-private" not in repr(restored.turns())
    assert "opaque-private" not in json.dumps(restored.agent_messages())
    disabled = responses_input(restored.agent_messages(openai_replay=True, capability_names=()), (definition,))
    assert [item["id"] for item in disabled if item.get("type") == "reasoning"] == ["rs_done"]
    assert not any(item.get("type") == "function_call" for item in disabled)
    service.shutdown()
    assert client.is_closed()


def test_plain_text_restart_replays_reasoning_and_phase_without_duplicate_assistant(monkeypatch, tmp_path):
    first = [reasoning(), message("First")]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=first), response(id="resp_second", output=[message("Second", "msg_second")])])
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store)
    assert service.run("hello") == "First"
    # Simulate application restart without closing the mock client yet.
    restored = ConversationService(engine, ConversationStore(store.path))
    assert restored.run("follow up") == "Second"
    assert bodies[1]["input"][2:4] == first
    assert bodies[1]["input"][-1] == {"role": "user", "content": "follow up"}
    assert sum(item.get("id") == "msg_final" for item in bodies[1]["input"]) == 1
    restored.shutdown()


@pytest.mark.parametrize("decision,approved", [(PermissionDecision.ALLOW, False), (PermissionDecision.DENY, False),
                                             (PermissionDecision.ASK, True), (PermissionDecision.ASK, False)])
def test_reasoning_continuations_keep_existing_permission_behavior(monkeypatch, tmp_path, decision, approved):
    capability = EchoCapability()
    definition = definition_for(capability)
    output = [reasoning(), function(definition, {"value": "hello"})]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=output), response(id="resp_done", output=[message("Done")])])
    requester = (lambda manager: lambda record: manager.resolve(record.approval_id, ApprovalStatus.APPROVED)) if approved else None
    service, _, implementation, journal, _ = service_for(engine, tmp_path, capability=capability,
        decision=decision, approval_requester_factory=requester)
    if decision == PermissionDecision.ASK and not approved:
        with pytest.raises(RuntimeError):
            service.run("Echo")
        assert service._turn_result.status == AgentRunStatus.APPROVAL_REQUIRED
        assert len(bodies) == 1 and implementation.values == []
    else:
        assert service.run("Echo") == "Done"
        assert bodies[1]["input"][2:4] == output
        result = json.loads(bodies[1]["input"][-1]["output"])
        assert result["success"] is (decision != PermissionDecision.DENY)
        assert implementation.values == (["hello"] if decision != PermissionDecision.DENY else [])
    assert len(service.store.turns()[0].provider_responses) >= 1
    service.shutdown()


def test_response_persistence_failure_prevents_execution_and_continuation(monkeypatch, tmp_path, caplog):
    capability = EchoCapability()
    output = [reasoning(), function(definition_for(capability), {"value": "private"})]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=output)])
    service, _, implementation, journal, _ = service_for(engine, tmp_path, capability=capability)
    monkeypatch.setattr(service.store, "record_response", Mock(side_effect=OSError("opaque-private-evidence")))
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        service.run("Echo")
    assert service._turn_result.status == AgentRunStatus.INTERNAL_FAILURE
    assert implementation.values == [] and journal.records == () and len(bodies) == 1
    assert "opaque-private" not in caplog.text
    with pytest.raises(TurnHistoryError):
        service.run("try again")
    assert len(bodies) == 1
    service.shutdown()


def test_cancelled_batch_retains_output_but_never_replays_unsettled_call(monkeypatch, tmp_path):
    source = CancellationSource()
    capability = CancellingBatchEchoCapability(source)
    definition = definition_for(capability)
    output = [reasoning(), *[function(definition, {"value": str(i)}, call_id=f"call_{i}") for i in range(2)]]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=output)])
    runtime, _, _, _, _ = build_runtime(tmp_path, [], capability=capability, model=engine)
    store = ConversationStore(tmp_path / "conversation.json")
    turn = store.begin_turn("Echo values")
    result = runtime.run(store.agent_messages(openai_replay=True), session_id=store.session_id, turn_id=turn,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,), cancellation=source.token,
        response_observer=lambda scope, replay: store.record_response(turn, scope, replay),
        settled_observer=lambda settled: store.record_settled(turn, settled))
    assert result.status == AgentRunStatus.CANCELLED and capability.values == ["0"]
    store.finish_turn(turn, result)
    restored = ConversationStore(store.path)
    assert restored.turns()[0].provider_responses[0].replay.items() == output
    inputs = responses_input(restored.agent_messages(openai_replay=True), (definition,))
    assert "opaque-private" not in json.dumps(inputs)
    assert [item["call_id"] for item in inputs if item.get("type") == "function_call"] == ["call_0"]
    assert len(bodies) == 1
    runtime.shutdown()
    engine.close()


def test_crash_before_first_call_retains_evidence_without_replaying_tools(tmp_path):
    store = ConversationStore(tmp_path / "conversation.json")
    turn = store.begin_turn("Inspect")
    replay = evidence([reasoning(), function()])
    store.record_response(turn, "scope", replay)
    restored = ConversationStore(store.path)
    assert restored.turns()[0].outcome.status == AgentRunStatus.INTERNAL_FAILURE
    assert restored.turns()[0].provider_responses[0].replay == replay
    assert all("capability_calls" not in message and REPLAY_KEY not in message for message in restored.agent_messages(openai_replay=True))
    assert restored.begin_turn("new task") == "turn-2"


@pytest.mark.parametrize("change", ["missing_encryption", "duplicate_item", "bad_type", "unfinished_item", "unknown_field", "invalid_json", "duplicate_json_key", "too_big"])
def test_corrupt_or_unreplayable_evidence_is_rejected_without_content(change):
    output = [reasoning(), function()]
    kwargs = {}
    if change == "missing_encryption":
        output[0].pop("encrypted_content")
    elif change == "duplicate_item":
        output[1]["id"] = output[0]["id"]
    elif change == "bad_type":
        output[0]["type"] = "web_search_call"
    elif change == "unfinished_item":
        output[1]["status"] = "in_progress"
    elif change == "unknown_field":
        output[0]["secret_field"] = "private-input"
    elif change == "invalid_json":
        kwargs["items_json"] = "private-input"
    elif change == "duplicate_json_key":
        kwargs["items_json"] = '[{"type":"reasoning","type":"private-input"}]'
    elif change == "too_big":
        kwargs["items_json"] = "private-input" + "x" * MAX_REPLAY_BYTES
    with pytest.raises(ValueError) as failure:
        OpenAIReplay(model="gpt-6-luna", response_id="resp", items_json=kwargs.get("items_json", json.dumps(output)))
    assert "private-input" not in str(failure.value) and "opaque-private" not in str(failure.value)


def test_malformed_sdk_reasoning_fails_before_harness_execution(monkeypatch, tmp_path):
    capability = EchoCapability()
    item = reasoning()
    item.pop("encrypted_content")
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=[item, function(definition_for(capability), {"value": "hello"})])])
    runtime, _, _, journal, _ = build_runtime(tmp_path, [], capability=capability, model=engine)
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.MODEL_UNAVAILABLE
    assert capability.values == [] and journal.records == () and len(bodies) == 1
    engine.close()


@pytest.mark.parametrize("change", ["call_id", "arguments", "text", "order"])
def test_evidence_must_match_neutral_calls_and_text(change):
    definition = capability_definition()
    calls = (ModelCapabilityCall(provider_call_id="call_exact_1", capability=definition.name, arguments={"path": "probe.txt"}),)
    output = [reasoning(), function()]
    if change == "text":
        output.insert(1, message("Working", "msg_work", "commentary"))
    value = history_for(evidence(output), calls)
    if change == "call_id":
        value[0]["capability_calls"][0]["provider_call_id"] = "other"
        value[1]["provider_call_id"] = "other"
    elif change == "arguments":
        value[0]["capability_calls"][0]["arguments"]["path"] = "different.txt"
    elif change == "text":
        value[0]["content"] = "Changed"
    else:
        output.append(function(call_id="call_second"))
        value[0][REPLAY_KEY] = evidence(output).model_dump()
    with pytest.raises(ValueError):
        responses_input(value, (definition,))


def test_context_counts_and_protects_opaque_evidence_and_result_bytes():
    definition = capability_definition()
    calls = (ModelCapabilityCall(provider_call_id="call_exact_1", capability=definition.name, arguments={"path": "probe.txt"}),)
    history = [{"role": "user", "content": "Inspect"}, *history_for(evidence([reasoning(), function()]), calls)]
    history[-1]["result"]["output"] = {"content": "x" * 12000}
    engine = Mock(context_length=32768, max_response_tokens=4096, count_message_tokens=None)
    recovered = recover_context_request(engine, history)
    assert recovered.messages == history and recovered.projected_results == 0
    budget = calculate_context_budget(engine, history)
    assert budget.structured_tool_history_tokens > 3000
    engine.context_length = 512
    assert not recover_context_request(engine, history).budget.fits
    selected = select_context_request(engine, system_prompt="policy", history=history)
    assert selected.messages == [{"role": "system", "content": "policy"}]


def test_cross_model_prior_turn_uses_neutral_history_and_current_turn_cannot_switch():
    definition = capability_definition()
    calls = (ModelCapabilityCall(provider_call_id="call_exact_1", capability=definition.name, arguments={"path": "probe.txt"}),)
    history = [{"role": "user", "content": "Inspect"}, *history_for(evidence([reasoning(), function()]), calls)]
    with pytest.raises(ValueError):
        responses_input(history, (definition,), model_id="gpt-6.1-sol")
    inputs = responses_input([*history, {"role": "user", "content": "new task"}], (definition,), model_id="gpt-6.1-sol")
    assert "opaque-private" not in json.dumps(inputs)
    assert inputs[1]["call_id"] == inputs[2]["call_id"] == "call_exact_1"


def test_cloud_local_cloud_switch_strips_private_items_and_keeps_limits_and_release(monkeypatch):
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [response(output=[reasoning(), message("First")]),
        response(id="resp_last", output=[message("Last", "msg_last")])])
    local = Mock(context_length=8192, max_response_tokens=512, respond=Mock(return_value="Local"))
    hybrid = HybridInferenceEngine(local=local, cloud=engine, default_mode="cloud", fallback_to_local=False)
    value = hybrid.respond([{"role": "user", "content": "hello"}])
    history = [{"role": "assistant", "content": str(value), REPLAY_KEY: value.openai_response.model_dump()},
               {"role": "user", "content": "next"}]
    hybrid.set_mode("local")
    assert hybrid.supports_openai_replay is False and hybrid.context_length == 8192
    assert hybrid.respond(history) == "Local"
    assert "opaque-private" not in json.dumps(local.respond.call_args.args[0])
    hybrid.set_mode("cloud")
    assert hybrid.supports_openai_replay is True and hybrid.context_length == 32768
    assert hybrid.respond(history) == "Last"
    assert bodies[1]["input"][:2] == [reasoning(), message("First")]
    hybrid.close()
    assert client.is_closed()


def test_corrupt_saved_evidence_preserves_file_and_refuses_load(tmp_path):
    store = ConversationStore(tmp_path / "conversation.json")
    turn = store.begin_turn("Inspect")
    store.record_response(turn, "scope", evidence([reasoning(), function()]))
    value = json.loads(store.path.read_text())
    value["turns"][0]["provider_responses"][0]["replay"]["items_json"] = "private-input"
    encoded = json.dumps(value)
    store.path.write_text(encoded)
    with pytest.raises(TurnHistoryError):
        ConversationStore(store.path)
    assert store.path.read_text() == encoded


def test_text_response_persistence_failure_is_redacted_and_blocks_next_turn(monkeypatch, tmp_path):
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(output=[reasoning(), message("First")])])
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(engine, store)
    monkeypatch.setattr(store, "record_response", Mock(side_effect=OSError("opaque-private-evidence")))
    with pytest.raises(TurnHistoryError) as failure:
        service.run("hello")
    assert "opaque-private" not in str(failure.value)
    with pytest.raises(TurnHistoryError):
        service.run("next")
    assert len(bodies) == 1
    service.shutdown()


def test_alias_resolution_keeps_replay_bound_to_requested_profile(monkeypatch):
    definition = capability_definition()
    output = [reasoning(), function()]
    engine, _, bodies, _ = scripted_sdk(monkeypatch, [response(model="gpt-6-luna-snapshot", output=output),
        response(id="resp_final", model="gpt-6-luna-snapshot", output=[message("Done")])])
    result = engine.respond_with_capabilities([{"role": "user", "content": "Inspect"}], (definition,))
    assert result.openai_response.model == "gpt-6-luna"
    inputs = [{"role": "user", "content": "Inspect"}, *history_for(result.openai_response, result.capability_calls)]
    assert engine.respond_with_capabilities(inputs, (definition,)).kind == ModelResponseKind.ASSISTANT_TEXT
    assert bodies[1]["input"][1:3] == output
    engine.close()


def test_generator_catalog_is_snapshotted_once_for_replay_validation():
    definition = capability_definition()
    calls = (ModelCapabilityCall(provider_call_id="call_exact_1", capability=definition.name, arguments={"path": "probe.txt"}),)
    output = [reasoning(), function()]
    value = history_for(evidence(output), calls)
    assert responses_input(value, (item for item in (definition,)))[:2] == output
