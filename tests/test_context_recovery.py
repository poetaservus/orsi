from copy import deepcopy
import hashlib
import json
from math import ceil

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.conversation.context import calculate_context_budget, capability_schema_reserve, select_context_request
from app.conversation.recovery import recover_context_request
from app.inference.protocol import (ModelCapabilityCall, ModelResponse, model_capability_calls_message,
    model_capability_result_message, native_chat_messages)
from app.settings.agent import AgentFeatureConfig, load_agent_feature_config
from app.capabilities.registry import CapabilityRegistry, CapabilityRegistration
from tests.test_agent_runtime import EchoCapability, ScriptedModel, build_runtime, capability_call, run
from tests.test_phase8_filesystem_stat import build_service


class CharacterModel:
    context_length = 12_000
    max_response_tokens = 512

    @staticmethod
    def count_message_tokens(messages):
        return sum(len(m["content"]) for m in messages)


def exchange(scope, text, *, index=1):
    call = ModelCapabilityCall(provider_call_id=f"call-{index}", capability="test.echo", arguments={"value": "exact"})
    result = {"call_id": f"internal-{scope}-{index}", "capability": call.capability, "success": True,
        "output": {"text": text, "path": "C:/exact/file.txt", "content_is_untrusted": True}, "error": None,
        "metadata": {"result_schema_version": 1}, "duration_ms": 1}
    return [model_capability_calls_message((call,), provider_message_id=scope),
        model_capability_result_message(call, result, provider_message_id=scope)]


def test_large_result_projection_preserves_exact_requirements_pairs_and_original_evidence():
    raw_text = "start\n" + "x" * 40_000 + "SESSION_MARKER=expected\n" + "y" * 40_000 + "\nend"
    messages = [{"role": "system", "content": "Exact policy"},
        {"role": "user", "content": "Keep all requirements: SESSION_MARKER; preserve bytes and do not replay mutations."},
        *exchange("message-1", raw_text)]
    before = deepcopy(messages)
    result = recover_context_request(CharacterModel(), messages)
    assert result.budget.fits and result.projected_results == 1 and not result.compacted
    assert messages == before
    assert result.messages[:3] == messages[:3]
    projected = result.messages[-1]
    assert {k: v for k, v in projected.items() if k != "result"} == {k: v for k, v in before[-1].items() if k != "result"}
    assert projected["result"]["success"] is True and projected["result"]["error"] is None
    assert projected["result"]["output"]["path"] == "C:/exact/file.txt"
    assert projected["result"]["output"]["content_is_untrusted"] is True
    assert "SESSION_MARKER=expected" in projected["result"]["output"]["text"]
    assert "characters omitted" in projected["result"]["output"]["text"]
    metadata = projected["result"]["metadata"]["context_projection"]
    assert metadata["complete"] is False
    encoded = json.dumps(before[-1]["result"]["output"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert metadata["original_output_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert result.budget == calculate_context_budget(CharacterModel(), result.messages)


def test_projection_does_not_compact_a_fitting_session():
    messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "earlier exact requirements"},
        {"role": "assistant", "content": "older answer" * 80}, {"role": "user", "content": "current exact request"}]
    result = recover_context_request(CharacterModel(), messages)
    assert result.messages == messages and not result.compacted and result.projected_results == 0


def test_compaction_only_when_needed_preserves_every_user_policy_and_exchange():
    messages = [{"role": "system", "content": "policy"}]
    for index in range(4):
        messages += [{"role": "user", "content": f"standing requirement {index}"},
            *exchange(f"message-{index}", "x" * 3500, index=index),
            {"role": "assistant", "content": "old explanation " * 80}]
    messages += [{"role": "user", "content": "Current requirement must be kept in full."},
        *exchange("current-message", "fresh current evidence", index=8)]
    recovered = recover_context_request(CharacterModel(), messages)
    assert recovered.compacted and recovered.budget.fits
    assert [m for m in recovered.messages if m["role"] in {"system", "user"}] == [m for m in messages if m["role"] in {"system", "user"}]
    assert [m for m in recovered.messages if "capability_calls" in m] == [m for m in messages if "capability_calls" in m]
    assert recovered.messages[-3:] == messages[-3:]
    assert len([m for m in recovered.messages if m["role"] == "capability"]) == 5
    definitions = CapabilityRegistry((CapabilityRegistration(EchoCapability(), enabled=True, model_visible=True),)).model_definitions()
    # Each exact pair remains admissible to the native adapter, including scoped ID reuse.
    native = native_chat_messages(recovered.messages, definitions)
    calls = [m["tool_calls"][0]["id"] for m in native if "tool_calls" in m]
    results = [m["tool_call_id"] for m in native if m["role"] == "tool"]
    assert calls == results and len(set(calls)) == 5


def test_unfit_current_request_is_never_suffix_trimmed_or_silently_omitted():
    history = [{"role": "user", "content": "FIRST REQUIREMENT " + "x" * 30_000 + " LAST REQUIREMENT"},
        *exchange("current-message", "result")]
    result = select_context_request(CharacterModel(), system_prompt="policy", history=history, recovery_enabled=True)
    assert not result.budget.fits
    assert result.messages[1:] == history


def test_large_call_arguments_are_not_repaired_by_context_projection():
    history = [{"role": "user", "content": "write exact bytes"}, *exchange("call-message", "small result")]
    history[1]["capability_calls"][0]["arguments"]["value"] = "x" * 30_000
    recovered = recover_context_request(CharacterModel(), history)
    assert not recovered.budget.fits and recovered.messages[1] == history[1]


class LargeEcho(EchoCapability):
    def execute(self, arguments, context):
        self.values.append(arguments.value)
        return {"text": "x" * 65_000}


@pytest.mark.parametrize("enabled", [False, True])
def test_runtime_recovers_after_large_result_and_keeps_raw_settlement(tmp_path, enabled):
    model = ScriptedModel([capability_call(1), ModelResponse.text("done")])
    model.context_length = 12_000
    model.max_response_tokens = 512
    model.count_message_tokens = CharacterModel.count_message_tokens
    runtime, model, _, _, _ = build_runtime(tmp_path, [], model=model, capability=LargeEcho())
    runtime.context_recovery_enabled = enabled
    result = run(runtime, tmp_path)
    assert result.status == (AgentRunStatus.COMPLETED if enabled else AgentRunStatus.CONTEXT_LIMIT)
    assert result.inference_requests == len(model.requests) == (2 if enabled else 1)
    assert result.context_projections > 0 if enabled else result.context_projections == 0
    assert len(result.settled_calls[0].result.output["text"]) == 65_000
    assert AgentRunResult.model_validate_json(result.model_dump_json()) == result
    if enabled:
        assert len(model.requests[1][-1]["result"]["output"]["text"]) < 6000


@pytest.mark.parametrize("recovery_enabled", [False, True])
def test_catalog_reachability_does_not_depend_on_phrases(tmp_path, recovery_enabled):
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    model = ScriptedModel([ModelResponse.text("done")])
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_copy_enabled=True,
        filesystem_read_text_enabled=True, context_recovery_enabled=recovery_enabled)
    runtime = build_agent_runtime(model, config=flags, portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"),
        agent_runtime=runtime, portable_root=tmp_path)
    try:
        for phrase in ("Make a second identical instance", "Maak nog een exemplaar", "do the next thing", "hello"):
            assert service._turn_capabilities(phrase) == runtime.registry.model_visible_names
        assert "filesystem.copy" in service._turn_capabilities("Make a second identical instance")
        assert "filesystem.move" not in service._turn_capabilities("move something")
    finally:
        service.shutdown()


def test_recovery_is_opt_in_and_default_profile_remains_baseline():
    assert AgentFeatureConfig().context_recovery_enabled is False
    assert load_agent_feature_config().context_recovery_enabled is False


def test_projection_failure_retains_already_settled_call_and_stops_next_model_request(tmp_path, monkeypatch):
    import app.conversation.recovery as recovery
    original = recovery.recover_context_request
    def fail_after_settlement(inference, messages, **kwargs):
        if any(m.get("role") == "capability" for m in messages):
            raise ValueError("injected projection failure")
        return original(inference, messages, **kwargs)
    monkeypatch.setattr(recovery, "recover_context_request", fail_after_settlement)
    runtime, model, echo, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("unused")])
    runtime.context_recovery_enabled = True
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.INTERNAL_FAILURE
    assert len(result.settled_calls) == 1 and result.settled_calls[0].result.success
    assert echo.values == ["hello"] and result.inference_requests == len(model.requests) == 1


def test_disambiguation_resolves_scoped_pairs_and_never_infers_uniqueness_from_projection():
    from app.agent.file_resolution import _result_call_arguments, filename_disambiguation_feedback
    old_call = ModelCapabilityCall(provider_call_id="call_0", capability="filesystem.read_text", arguments={"path": "old/notes"})
    new_call = old_call.model_copy(update={"arguments": {"path": "new/notes"}})
    old_result = model_capability_result_message(old_call, {"success": False, "error": {"code": "not_found"}}, provider_message_id="old")
    history = [model_capability_calls_message((old_call,), provider_message_id="old"), old_result,
        model_capability_calls_message((new_call,), provider_message_id="new")]
    assert _result_call_arguments(history, old_result) == {"path": "old/notes"}
    listing_call = ModelCapabilityCall(provider_call_id="list_0", capability="filesystem.list", arguments={"path": "old"})
    listing = model_capability_result_message(listing_call,
        {"success": True, "output": {"path": "old", "entries": [{"name": "notes.txt", "type": "file"}]},
         "metadata": {"context_projection": {"complete": False}}}, provider_message_id="listing")
    transcript = [{"role": "user", "content": "read old/notes"}, *history[:2],
        model_capability_calls_message((listing_call,), provider_message_id="listing"), listing]
    assert filename_disambiguation_feedback(transcript, {"filesystem.list", "filesystem.read_text"}) is None
    listing["result"]["metadata"] = {}
    assert filename_disambiguation_feedback(transcript, {"filesystem.list", "filesystem.read_text"}) is not None
    earlier_stopped = [{"role": "user", "content": "read old/notes"}, *history[:2],
        {"role": "user", "content": "read a different file"}]
    assert filename_disambiguation_feedback(earlier_stopped, {"filesystem.list", "filesystem.read_text"}) is None


@pytest.mark.parametrize("capacity, fits", [(12_000, False), (16_384, True)])
def test_many_current_turn_results_compact_without_dropping_any_pair_or_requirement(capacity, fits):
    history = [{"role": "system", "content": "policy"}, {"role": "user", "content": "finish every item exactly"}]
    for index in range(12):
        history.extend(exchange(f"same-turn-message-{index}", "x" * 30_000, index=index))
    model = CharacterModel()
    model.context_length = capacity
    recovered = recover_context_request(model, history)
    assert recovered.compacted and recovered.budget.fits is fits
    assert len(recovered.messages) == len(history)
    assert recovered.messages[:2] == history[:2]
    assert [m for m in recovered.messages if "capability_calls" in m] == [m for m in history if "capability_calls" in m]
    assert recovered.messages[-1]["result"]["metadata"]["context_projection"]["complete"] is False


def test_continuous_session_keeps_standing_requirements_full_pairing_and_durable_raw_results(tmp_path):
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.engine import InferenceEngine
    from app.inference.protocol import ModelResponseKind

    class ContinuousModel(InferenceEngine):
        context_length = 16_384
        max_response_tokens = 512
        requests = []
        definitions = []

        @staticmethod
        def count_message_tokens(messages):
            return max(1, ceil(sum(len(m["content"]) for m in messages) / 4) + 4 * len(messages) + 3)

        def respond(self, messages):
            raise AssertionError("Continuous agent uses native boundary.")

        def respond_with_capabilities(self, messages, definitions):
            native = native_chat_messages(messages, definitions)
            assert calculate_context_budget(self, messages, reserved_tokens=capability_schema_reserve(definitions)).fits
            assert any(m.get("content") == "Standing requirement: SESSION_TOKEN=exact-731; never replay an old mutation."
                       for m in messages if m.get("role") == "user")
            ids = [c["id"] for m in native if "tool_calls" in m for c in m["tool_calls"]]
            assert ids == [m["tool_call_id"] for m in native if m["role"] == "tool"]
            self.requests.append(deepcopy(messages))
            self.definitions.append(tuple(definitions))
            if messages[-1].get("role") == "capability":
                text = messages[-1]["result"]["output"]["text"]
                assert "SESSION_MARKER=verified" in text
                assert "context_projection" in messages[-1]["result"]["metadata"]
                return ModelResponse.text("verified")
            latest = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
            if latest.startswith("Standing requirement"):
                return ModelResponse.text("remembered")
            return ModelResponse.calls((ModelCapabilityCall(provider_call_id="call_0", capability="filesystem.read_text",
                arguments={"path": "large.txt", "max_bytes": 65_536, "max_lines": 1000}),))

    text = "prefix\n" + "x" * 25_000 + "\nSESSION_MARKER=verified\n" + "y" * 30_000
    (tmp_path / "large.txt").write_bytes(text.encode("utf-8"))
    model = ContinuousModel()
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True, context_recovery_enabled=True)
    runtime = build_agent_runtime(model, config=flags, portable_root=tmp_path, state_directory=tmp_path / "state")
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=tmp_path)
    try:
        session_id = service.store.session_id
        service.run("Standing requirement: SESSION_TOKEN=exact-731; never replay an old mutation.")
        for index in range(20):
            assert service.run(f"Use filesystem.read_text for large.txt, then extract SESSION_MARKER. Current item {index}.") == "verified"
        assert service.store.session_id == session_id
        turns = store.turns()
        assert len(turns) == 21 and all(t.outcome.status == AgentRunStatus.COMPLETED for t in turns)
        assert sum(t.outcome.inference_requests for t in turns) == len(model.requests) == 41
        assert sum(t.outcome.context_compactions for t in turns) > 0
        assert len(runtime.executor.journal.records) == 20
        for turn in turns[1:]:
            assert turn.settled_calls[0].result.output["text"] == text
            assert "context_projection" not in turn.settled_calls[0].result.metadata
        restored = ConversationStore(store.path)
        assert restored.session_id == session_id and len(restored.turns()) == 21
    finally:
        service.shutdown()
