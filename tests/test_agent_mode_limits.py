"""Cloud/local step budgets follow the active backend without a live request."""
import logging

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.inference.hybrid import HybridInferenceEngine
from app.inference.protocol import ModelResponse
from app.settings.agent import AgentRuntimeLimits, MAX_AGENT_STEPS, load_agent_feature_config
from tests.test_phase8_filesystem_stat import ScriptedStatModel, build_service, stat_call


def test_cloud_completes_beyond_old_32_request_limit(tmp_path):
    cloud = scripted_model(40)
    cloud.mode = "cloud"
    service, runtime, store, root = build_service(tmp_path, cloud)
    for index in range(40):
        (root / f"fixture-{index}.txt").write_text("fixture", encoding="utf-8")
    try:
        assert service.run("Inspect the synthetic fixtures") == "Done"
        reopened = type(store)(store.path)
        turn = reopened.turns()[0]
        assert turn.outcome.model_requests == turn.outcome.steps == 41
        assert len(turn.settled_calls) == 40 and all(item.result.success for item in turn.settled_calls)
        assert len(turn.outcome.completion_history) == 41
        assert "batch up to seven independent filesystem.stat calls" in cloud.requests[0][0]["content"]
    finally:
        service.shutdown()


@pytest.mark.parametrize("limits, status, requests, executed", [
    (AgentRuntimeLimits(cloud_max_steps=2), AgentRunStatus.STEP_LIMIT, 2, 2),
    (AgentRuntimeLimits(cloud_max_model_requests=2), AgentRunStatus.MODEL_REQUEST_LIMIT, 2, 2),
    (AgentRuntimeLimits(cloud_max_capability_calls=2), AgentRunStatus.CAPABILITY_CALL_LIMIT, 3, 2),
])
def test_cloud_independent_budgets_pause_without_extra_request(tmp_path, limits, status, requests, executed):
    from app.agent.contracts import AgentRunResult
    from tests.test_agent_runtime import build_runtime, capability_call, run
    runtime, model, echo, journal, _ = build_runtime(tmp_path,
        [capability_call(i, str(i)) for i in range(4)], limits=limits)
    model.mode = "cloud"
    try:
        result = run(runtime, tmp_path)
        assert result.status == status and result.completion.incomplete
        assert len(model.requests) == requests and len(echo.values) == executed
        assert len(journal.records) == len(result.settled_calls) == executed
        assert f"{executed} test.echo operations" in result.partial_text
        assert AgentRunResult.model_validate_json(result.model_dump_json()) == result
    finally:
        runtime.shutdown()


def test_cloud_batch_call_budget_and_durable_storage_cover_256_calls(tmp_path):
    from app.agent.contracts import AgentRunResult
    from app.conversation.store import ConversationStore
    from tests.test_agent_runtime import build_runtime, capability_call, run, BatchEchoCapability
    class EightCallEcho(BatchEchoCapability):
        max_calls_per_batch = 8
    batches = [ModelResponse.calls(tuple(capability_call(i, str(i)).capability_calls[0]
        for i in range(start, start + 8))) for start in range(0, 264, 8)]
    runtime, model, echo, journal, _ = build_runtime(tmp_path, batches, capability=EightCallEcho())
    model.mode = "cloud"
    model.context_length = 131_072
    model.max_response_tokens = 512
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.CAPABILITY_CALL_LIMIT
        assert result.capability_calls == len(echo.values) == len(journal.records) == 256
        assert result.model_requests == 33 and len(model.requests) == 33
        assert AgentRunResult.model_validate_json(result.model_dump_json()) == result
        store = ConversationStore(tmp_path / "conversation.json")
        turn = store.begin_turn("Inspect the fixture batches")
        store.finish_turn(turn, result, answer=result.partial_text)
        reopened = ConversationStore(store.path)
        assert len(reopened.turns()[0].settled_calls) == 256
        assert len([m for m in reopened.agent_messages() if m["role"] == "capability"]) == 256
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("field, ceiling", [("cloud_max_steps", 128),
    ("cloud_max_model_requests", 128), ("cloud_max_capability_calls", 256), ("max_steps", 32)])
def test_budget_ceiling_is_enforced(field, ceiling):
    assert getattr(AgentRuntimeLimits(**{field: ceiling}), field) == ceiling
    with pytest.raises(ValidationError):
        AgentRuntimeLimits(**{field: ceiling + 1})


def test_cloud_seeded_call_and_fallback_request_history_fit_full_budget(tmp_path):
    from app.agent.contracts import AgentRunResult
    from tests.test_agent_runtime import build_runtime, capability_call
    from tests.test_opencode_tool_resolution_port import TextOnlyStructuredFallbackModel
    # Seven malformed replies followed by an unknown tool reset the format streak.
    # This consumes the full physical request budget without exceeding either
    # the eight-consecutive-format or 32-semantic-correction guards.
    replies = (["invalid JSON"] * 7 + ['{"tool":"test.unknown","arguments":{}}']) * 16
    model = TextOnlyStructuredFallbackModel(replies)
    model.mode = "cloud"
    model.context_length = 131_072
    model.max_response_tokens = 512
    runtime, _, echo, _, _ = build_runtime(tmp_path, [], model=model,
        limits=AgentRuntimeLimits(max_protocol_failures=8, max_semantic_corrections=32))
    try:
        result = runtime.run([{"role": "user", "content": "Run the required call, then answer."}],
            session_id="session-1", turn_id="turn-1", portable_root=tmp_path,
            allowed_read_roots=(tmp_path,), required_calls=(capability_call(1).capability_calls[0],),
            continue_after_required_calls=True)
        assert result.status == AgentRunStatus.STEP_LIMIT
        assert result.model_requests == result.steps == 128
        assert echo.values == ["hello"] and len(result.settled_calls) == 1
        # A seeded tool step has metadata but does not spend a model request.
        assert len(result.completion_history) == 129
        assert AgentRunResult.model_validate_json(result.model_dump_json()) == result
    finally:
        runtime.shutdown()


def test_budget_pause_after_approved_edit_resumes_without_reapplying(tmp_path):
    from tests.test_turn_outcomes import edit_service, edit_call
    target = tmp_path / "note.txt"
    target.write_bytes(b"old\r\nkeep\r\n")
    service, approvals = edit_service(tmp_path, [edit_call(target), ModelResponse.text("The edit is complete.")])
    service.inference.mode = "cloud"
    service.agent_runtime.limits = AgentRuntimeLimits(cloud_max_steps=1)
    try:
        paused = service.run("Edit the text file")
        assert "1 file edit" in paused and paused.completion.incomplete
        assert target.read_bytes() == b"new\r\nkeep\r\n" and len(approvals) == 1
        store_path = service.store.path
        service.shutdown()
        service, resumed_approvals = edit_service(tmp_path, [ModelResponse.text("The edit is complete.")])
        service.inference.mode = "cloud"
        assert not service.inference.requests
        assert service.store.path == store_path and len(service.store.turns()[0].settled_calls) == 1
        assert service.run("Continue using the completed edit") == "The edit is complete."
        assert resumed_approvals == [] and target.read_bytes() == b"new\r\nkeep\r\n"
        assert len(service.agent_runtime.executor.journal.records) == 1
        assert any(m["role"] == "capability" and m["result"]["success"] for m in service.inference.requests[-1])
    finally:
        service.shutdown()


def test_native_metadata_batch_keeps_each_success_settled(tmp_path):
    calls = tuple(stat_call(f"fixture-{i}.txt", provider_call_id=f"stat-{i}").capability_calls[0]
                  for i in range(7))
    cloud = ScriptedStatModel([ModelResponse.calls(calls), ModelResponse.text("Done")])
    cloud.mode = "cloud"
    cloud.context_length = 131_072
    cloud.max_response_tokens = 512
    service, _, store, root = build_service(tmp_path, cloud)
    for i in range(7):
        (root / f"fixture-{i}.txt").write_bytes(b"fixture")
    try:
        assert service.run("Inspect the synthetic fixtures") == "Done"
        assert len(cloud.requests) == 2
        assert len(store.turns()[0].settled_calls) == 7
        assert all(item.result.success for item in store.turns()[0].settled_calls)
    finally:
        service.shutdown()


def test_cloud_completes_33_approved_edits_with_original_bytes_preserved(tmp_path):
    from tests.test_turn_outcomes import edit_service, edit_call
    targets = [tmp_path / f"note-{i}.txt" for i in range(33)]
    for target in targets:
        target.write_bytes(b"old\r\nkeep\r\n")
    untouched = tmp_path / "untouched.txt"
    untouched.write_bytes(b"preserve exactly\r\n")
    service, approvals = edit_service(tmp_path, [edit_call(target) for target in targets] + [ModelResponse.text("Done")])
    service.inference.mode = "cloud"
    service.inference.context_length = 131_072
    service.inference.max_response_tokens = 512
    try:
        assert service.run("Edit the text files") == "Done"
        assert len(approvals) == 33
        assert all(target.read_bytes() == b"new\r\nkeep\r\n" for target in targets)
        assert untouched.read_bytes() == b"preserve exactly\r\n"
        assert all(service.approval_status(record.approval_id) == "consumed" for record in approvals)
        turn = type(service.store)(service.store.path).turns()[0]
        assert turn.outcome.steps == turn.outcome.model_requests == 34
        assert len(turn.settled_calls) == 33 and all(item.result.success for item in turn.settled_calls)
    finally:
        service.shutdown()


def test_local_prompt_and_mutation_guidance_keep_single_calls():
    from app.conversation.prompt import compact_agent_system_prompt
    from app.security.host_access import HostReadScope
    names = ("filesystem.stat", "filesystem.edit_text")
    local = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, names)
    cloud = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, names, allow_read_batches=True)
    assert "Normally make one tool call at a time" in local and "batch up to" not in local
    assert "Keep all other tool calls single" in cloud
    assert "external approval" in local and "external approval" in cloud


def scripted_model(call_count):
    model = ScriptedStatModel([stat_call(f"fixture-{index}.txt", provider_call_id=f"stat-{index}")
        for index in range(call_count)] + [ModelResponse.text("Done")])
    model.context_length = 131_072
    model.max_response_tokens = 512
    return model


def test_accepted_configuration_and_legacy_settings_keep_local_24_and_cloud_128():
    settings = load_agent_feature_config().runtime_limits
    assert settings.max_steps == 24
    assert settings.cloud_max_steps == MAX_AGENT_STEPS == 128
    assert settings.cloud_max_model_requests == 128
    assert settings.cloud_max_capability_calls == 256
    assert settings.max_model_requests == settings.max_capability_calls == 32
    assert AgentRuntimeLimits.model_validate({"max_steps": 24}).cloud_max_steps == 128
    with pytest.raises(ValidationError):
        AgentRuntimeLimits(cloud_max_steps=MAX_AGENT_STEPS + 1)


def test_real_switch_cloud_local_cloud_applies_budgets_and_retains_history(tmp_path, caplog):
    cloud, local = scripted_model(31), scripted_model(24)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    service, runtime, store, root = build_service(tmp_path, hybrid)
    caplog.set_level(logging.INFO, logger="app.agent.runtime")
    try:
        assert runtime.limits.max_steps == 24 and runtime.effective_max_steps == 128
        assert runtime.effective_max_model_requests == 128 and runtime.effective_max_capability_calls == 256
        assert service.run("Inspect the synthetic fixtures") == "Done"
        outcome = store._conversation.turns[-1].outcome
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.steps == 32
        assert outcome.capability_calls == 31 and len(cloud.requests) == 32
        history = store.messages()
        hybrid.set_mode("local")
        assert runtime.effective_max_model_requests == runtime.effective_max_capability_calls == 32
        assert runtime.effective_max_steps == 24 and store.messages() == history
        with pytest.raises(RuntimeError, match="maximum model-step limit"):
            service.run("Inspect the synthetic fixtures again")
        outcome = store._conversation.turns[-1].outcome
        assert outcome.status == AgentRunStatus.STEP_LIMIT and outcome.steps == 24
        assert outcome.capability_calls == 24 and len(local.requests) == 24
        history = store.messages()
        cloud.responses = scripted_model(31).responses
        hybrid.set_mode("cloud")
        assert runtime.effective_max_steps == 128 and store.messages() == history
        assert service.run("Inspect the synthetic fixtures once more") == "Done"
        assert store._conversation.turns[-1].outcome.steps == 32
        assert "mode=cloud max_steps=128" in caplog.text and "mode=local max_steps=24" in caplog.text
        reopened = type(store)(store.path)
        assert [turn.outcome.steps for turn in reopened._conversation.turns] == [32, 24, 32]
    finally:
        service.shutdown()


def test_cloud_budget_pause_retains_128_results_without_request_129(tmp_path):
    from tests.test_openai_replay import evidence
    from tests.test_openai_tools import function
    cloud = scripted_model(128)
    for index, response in enumerate(cloud.responses[:-1]):
        call = response.capability_calls[0]
        cloud.responses[index] = response.model_copy(update={"openai_response": evidence([
            function(arguments=call.arguments, call_id=call.provider_call_id)], identity=f"resp-{index}")})
    hybrid = HybridInferenceEngine(local=None, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    service, runtime, store, root = build_service(tmp_path, hybrid)
    try:
        answer = service.run("Inspect the synthetic fixtures")
        assert answer.completion.incomplete and answer.completion.finish_reason == "agent_budget_limit"
        assert "Task paused before completion" in answer and "Ask me to continue" in answer
        assert "Unsuccessful operations: 128" in answer  # Missing fixture files are not claimed as successes.
        outcome = store._conversation.turns[-1].outcome
        assert outcome.status == AgentRunStatus.STEP_LIMIT
        assert outcome.steps == outcome.model_requests == outcome.capability_calls == 128
        assert len(cloud.requests) == 128 and len(cloud.responses) == 1
        assert len(store._conversation.turns[-1].settled_calls) == 128
        reopened = type(store)(store.path)
        assert len(reopened.turns()[0].settled_calls) == 128
        assert len(reopened.turns()[0].provider_responses) == 128
        assert reopened._conversation.messages[-1].completion.failure_message == answer.status_message
        assert service.run("Continue using the recorded results") == "Done"
        assert len(cloud.requests) == 129  # Only the explicit follow-up requests another response.
        assert sum(item["role"] == "capability" for item in cloud.requests[-1]) == 128
    finally:
        service.shutdown()


@pytest.mark.parametrize("backend", ["responses", "compatible"])
def test_direct_cloud_adapters_use_cloud_budget_without_a_hybrid(tmp_path, backend):
    if backend == "responses":
        from app.inference.openai_backend import OpenAIResponsesInferenceEngine
        from tests.test_openai_phase1 import config
        engine = OpenAIResponsesInferenceEngine(config(), api_key="fake-never-live")
    else:
        from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
        from tests.test_cloud_inference import cloud_config
        engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="fake-never-live")
    service, runtime, store, root = build_service(tmp_path, engine)
    try:
        assert runtime.effective_max_steps == 128 and runtime.limits.max_steps == 24
    finally:
        service.shutdown()
