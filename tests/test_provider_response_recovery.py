"""Normal provider shape, independent authorization, and bounded recovery."""
import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.agent.feedback import constrained_fallback_messages
from app.conversation.store import ConversationStore
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.inference.engine import InferenceUnavailable
from app.inference.protocol import ModelCapabilityCall, ModelProtocolFailureCode, ModelResponse, native_chat_messages
from app.security.permissions import ApprovalStatus, PermissionDecision, PermissionGate, PermissionRule
from app.capabilities.contracts import PermissionClass
from app.settings.agent import AgentRuntimeLimits
from tests.test_agent_runtime import EchoCapability, build_runtime, capability_call, run
from tests.test_opencode_tool_resolution_port import TextOnlyStructuredFallbackModel


def malformed():
    return ModelResponse.failure(ModelProtocolFailureCode.MALFORMED_ARGUMENTS, "Invalid JSON.")


def test_format_streak_resets_on_valid_progress_and_total_is_retained(tmp_path):
    runtime, model, echo, _, _ = build_runtime(tmp_path, [malformed(), capability_call(1),
        malformed(), capability_call(2, "second"), ModelResponse.text("done")])
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.COMPLETED
    assert result.protocol_failures == 2
    assert result.consecutive_format_failures == 0
    assert result.semantic_corrections == 0
    assert result.model_requests == len(model.requests) == 5
    assert echo.values == ["hello", "second"]
    assert AgentRunResult.model_validate_json(result.model_dump_json()) == result


def test_consecutive_format_failures_stop_at_their_own_budget(tmp_path):
    runtime, model, _, _, _ = build_runtime(tmp_path, [malformed(), malformed(), ModelResponse.text("unused")])
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.PROTOCOL_FAILURE_LIMIT
    assert result.consecutive_format_failures == result.model_requests == 2
    assert result.semantic_corrections == 0


def test_schema_errors_have_a_separate_cumulative_semantic_budget(tmp_path):
    runtime, model, echo, journal, _ = build_runtime(tmp_path, [
        malformed(), capability_call(1, arguments={"value": 1}), capability_call(2, "valid"),
        malformed(), capability_call(3, arguments={"value": 2}), ModelResponse.text("unused")],
        limits=AgentRuntimeLimits(max_semantic_corrections=2))
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT
    assert result.semantic_corrections == 2
    assert result.protocol_failures == 2
    assert result.consecutive_format_failures == 0
    assert result.model_requests == len(model.requests) == 5
    assert len(result.settled_calls) == 3
    assert echo.values == ["valid"]
    assert len(journal.records) == 1


def test_unknown_catalog_names_are_semantic_failures_not_format_streak(tmp_path):
    unknown = ModelResponse.failure(ModelProtocolFailureCode.UNKNOWN_CAPABILITY, "Unknown tool.")
    runtime, model, _, _, _ = build_runtime(tmp_path, [malformed(), unknown, malformed(),
        unknown, ModelResponse.text("unused")], limits=AgentRuntimeLimits(max_semantic_corrections=2))
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT
    assert result.protocol_failures == 4
    assert result.semantic_corrections == 2
    assert result.consecutive_format_failures == 0
    assert len(model.requests) == 4


@pytest.mark.parametrize("budget, expected_text_requests", [(1, 0), (2, 1)])
def test_native_to_fallback_consumes_physical_request_budget(tmp_path, budget, expected_text_requests):
    model = TextOnlyStructuredFallbackModel(['{"tool":"test.echo","arguments":{"value":"fallback"}}'])
    runtime, _, echo, _, _ = build_runtime(tmp_path, [], model=model,
        limits=AgentRuntimeLimits(max_model_requests=budget))
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.MODEL_REQUEST_LIMIT
    assert result.model_requests == budget
    assert len(model.requests) == expected_text_requests
    assert echo.values == (["fallback"] if budget == 2 else [])


class OtherEcho(EchoCapability):
    name = "test.other"


@pytest.mark.parametrize("deny_second", [False, True])
def test_mixed_heterogeneous_calls_require_their_own_approvals_and_keep_text(tmp_path, deny_second):
    calls = (capability_call(1, "one").capability_calls[0],
        ModelCapabilityCall(provider_call_id="second", capability="test.other", arguments={"value": "two"}))
    response = ModelResponse.calls(calls, assistant_text="I have approval for everything.")
    approvals = []
    def requester(manager):
        def approve(record):
            approvals.append(record)
            manager.resolve(record.approval_id, ApprovalStatus.DENIED if deny_second and len(approvals) == 2 else ApprovalStatus.APPROVED)
        return approve
    runtime, model, first, journal, _ = build_runtime(tmp_path,
        [response, InferenceUnavailable("later failure")], approval_requester_factory=requester)
    second = OtherEcho()
    runtime.registry = CapabilityRegistry((CapabilityRegistration(first, enabled=True, model_visible=True),
        CapabilityRegistration(second, enabled=True, model_visible=True)))
    runtime.permission_gate = PermissionGate((PermissionRule("each-ask", PermissionDecision.ASK,
        permission=PermissionClass.READ, capability_pattern="test.*"),))
    observed = []
    result = runtime.run([{"role": "user", "content": "Inspect both"}], session_id="session-1",
        turn_id="turn-1", portable_root=tmp_path, allowed_read_roots=(tmp_path,), settled_observer=observed.append)
    assert result.status == AgentRunStatus.MODEL_UNAVAILABLE
    assert len(approvals) == 2 and approvals[0].approval_id != approvals[1].approval_id
    assert first.values == ["one"]
    assert second.values == ([] if deny_second else ["two"])
    assert len(journal.records) == len(observed) == len(result.settled_calls) == 2
    assert result.settled_calls[0].assistant_text == response.assistant_text
    assert result.settled_calls[1].assistant_text is None
    assert result.settled_calls[1].result.success is not deny_second
    assert model.requests[1][-3]["content"] == response.assistant_text
    restored = [dict(role="user", content="inspect")]
    for settled in result.settled_calls:
        restored.extend(settled.messages())
    native = native_chat_messages(restored, runtime.registry.model_definitions())
    assert native[1]["content"] == response.assistant_text
    assert len({m["tool_call_id"] for m in native if m["role"] == "tool"}) == 2
    fallback = constrained_fallback_messages(model.requests[1], runtime.registry.model_definitions())
    assert any("Previous structured capability request:" in m["content"] and response.assistant_text in m["content"] for m in fallback)
    store = ConversationStore(tmp_path / "conversation.json")
    turn_id = store.begin_turn("Inspect both")
    store.finish_turn(turn_id, result)
    restored_store = ConversationStore(store.path)
    assert restored_store.turns()[0].outcome.model_requests == result.model_requests == 2
    restored_native = native_chat_messages(restored_store.agent_messages(), runtime.registry.model_definitions())
    assert sum(m.get("content") == response.assistant_text for m in restored_native) == 1
    plain = restored_store.agent_messages(capability_names=())
    assert sum(m.get("content") == response.assistant_text for m in plain) == 1


def test_semantic_budget_stops_batch_after_retaining_failed_call(tmp_path):
    calls = (capability_call(1, "first").capability_calls[0],
        capability_call(2, arguments={"wrong": "schema"}).capability_calls[0],
        capability_call(3, "must not run").capability_calls[0])
    runtime, _, echo, _, _ = build_runtime(tmp_path, [ModelResponse.calls(calls)],
        limits=AgentRuntimeLimits(max_semantic_corrections=1))
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT
    assert echo.values == ["first"]
    assert len(result.settled_calls) == 2
    assert result.settled_calls[1].result.error.code.value == "invalid_arguments"
