from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.agent.goals import TaskGoal
from app.agent.task_completion import CompletionReview
from app.capabilities.contracts import CapabilityResult
from app.capabilities.conversation_read_turn import ConversationReadTurnCapability
from app.conversation.orchestrator import ConversationService
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse, native_chat_messages
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import ScriptedModel
from tests.test_filesystem_read_text import context
from tests.test_context_recovery import CharacterModel


def settle(index, capability="filesystem.read_text", *, text="source", revision="a" * 64, arguments=None):
    return SettledCall(provider_message_id=f"scope-{index}",
        call=ModelCapabilityCall(provider_call_id=f"provider-{index}", capability=capability,
            arguments=arguments or {"path": "C:/project/main.py"}),
        result=CapabilityResult(call_id=f"receipt-{index}", capability=capability, success=True,
            output={"path": "C:/project/main.py", "revision": revision, "text": text}, duration_ms=1))


def finish(store, request, *, completed=True, evidence=(), answer="reported done"):
    turn = store.begin_turn(request)
    for item in evidence:
        store.record_settled(turn, item)
    outcome = AgentRunResult(status=AgentRunStatus.COMPLETED if completed else AgentRunStatus.INCOMPLETE,
        assistant_text=answer if completed else None, partial_text=None if completed else answer,
        message=None if completed else "Unfinished work requires approval.",
        steps=1, capability_calls=len(evidence), protocol_failures=0, settled_calls=tuple(evidence))
    store.finish_turn(turn, outcome, answer)
    return turn


def test_completed_summaries_keep_constraints_unresolved_work_and_durable_evidence(tmp_path):
    store = ConversationStore(tmp_path / "chat.json")
    request = "Standing requirement: never publish; preserve exact TOKEN=π-731. Finish the earlier cleanup."
    finish(store, request, evidence=(settle(1, text="old source\n" * 2000),), answer="Claimed completion. " * 300)
    unresolved = "Unresolved: repair the scroll container after approval."
    finish(store, unresolved, completed=False, evidence=(settle(2, text="still unresolved"),), answer="Blocked by approval.")
    store.begin_turn("Current request: fix broken references; keep the standing constraints.")
    before = store.path.read_bytes()
    original = store.agent_messages()
    summary = store.agent_messages(summarize_completed=True, openai_replay=True)
    assert [m for m in summary if m["role"] == "user"] == [m for m in original if m["role"] == "user"]
    assert request in [m["content"] for m in summary if m["role"] == "user"]
    assert "old source" not in json.dumps(summary)
    assert "still unresolved" in json.dumps(summary)
    notice = json.loads(summary[1]["content"])
    assert notice["turn_id"] == "turn-1" and "conversation.read_turn" in notice["notice"]
    assert store.path.read_bytes() == before
    assert store.agent_messages() == original


def test_recall_pages_recover_original_neutral_history_without_private_replay(tmp_path):
    store = ConversationStore(tmp_path / "chat.json")
    finish(store, "Keep π exact", evidence=(settle(1, text="😀 original\n" * 100),
        settle(2, "skill.read_reference", text="EXPIRED-SKILL-BODY")))
    tool = ConversationReadTurnCapability(store)
    ctx = replace(context(tmp_path), session_id=store.session_id)
    args, pieces = {"turn_id": "turn-1", "max_bytes": 129}, []
    while args:
        result = tool.invoke(args, ctx)
        assert result.success
        pieces.append(result.output["text"])
        args = result.output["next_read"]
    restored = json.loads("".join(pieces))
    assert restored["request"]["content"] == "Keep π exact"
    assert restored["settled_calls"][0]["result"]["output"]["text"] == "😀 original\n" * 100
    assert "EXPIRED-SKILL-BODY" not in "".join(pieces)
    assert "provider_responses" not in restored
    assert not tool.invoke({"turn_id": "turn-1"}, context(tmp_path)).success


def test_stale_revision_bodies_retire_but_pairs_and_same_revision_pages_survive():
    first, page, latest = settle(1, text="OLD REVISION"), settle(2, text="OLD PAGE"), settle(3, text="NEW REVISION", revision="b" * 64)
    messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "standing requirement"},
        *first.messages(), *page.messages(), {"role": "user", "content": "current request"}, *latest.messages()]
    before = deepcopy(messages)
    output = recover_context_request(CharacterModel(), messages)
    assert messages == before
    results = [m["result"]["output"] for m in output.messages if m["role"] == "capability"]
    assert results[0]["source_retired"] and results[1]["source_retired"]
    assert results[-1]["text"] == "NEW REVISION"
    assert [m for m in output.messages if "capability_calls" in m] == [m for m in messages if "capability_calls" in m]
    same = recover_context_request(CharacterModel(), messages[:6]).messages
    assert any("OLD REVISION" in str(m) for m in same)


def test_service_compacts_completed_history_under_pressure_and_scopes_recall(tmp_path):
    model = ScriptedModel([ModelResponse.text("done")])
    model.context_length = 16000
    model.max_response_tokens = 512
    model.count_message_tokens = CharacterModel.count_message_tokens
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True,
        context_recovery_enabled=True, conversation_context_enabled=True)
    store = ConversationStore(tmp_path / "chat.json")
    # Protected old command arguments cannot be excerpted by generic recovery;
    # summarizing the completed exchange retires them atomically.
    finish(store, "Standing: never publish or discard unresolved work.", evidence=(settle(1,
        arguments={"path": "C:/project/main.py", "old_request_literal": "x" * 22000}),))
    store.begin_turn("Latest request remains explicit.")
    runtime = build_agent_runtime(model, config=flags, portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=tmp_path)
    try:
        request = service._model_request(capability_turn=True)
        assert request.budget.fits
        assert "conversation.read_turn" in service.agent_capabilities
        assert any("Historical summary" in str(m) for m in request.messages)
        assert [m["content"] for m in request.messages if m["role"] == "user"] == [
            "Standing: never publish or discard unresolved work.", "Latest request remains explicit."]
        native_chat_messages(request.messages, service.agent_runtime.registry.model_definitions())
        assert store.turns()[0].settled_calls[0].call.arguments["old_request_literal"] == "x" * 22000
    finally:
        service.shutdown()


def test_unfit_standing_constraints_are_explicitly_unfit_not_silently_dropped(tmp_path):
    messages = [{"role": "user", "content": "standing constraint " * 2000},
        {"role": "assistant", "content": "completed"}, {"role": "user", "content": "current request"}]
    result = recover_context_request(CharacterModel(), messages)
    assert not result.budget.fits
    assert [m for m in result.messages if m["role"] == "user"] == [m for m in messages if m["role"] == "user"]


def test_recorded_remaining_work_stays_literal_under_compaction_pressure(tmp_path):
    from tests.test_context_recovery import exchange
    store = ConversationStore(tmp_path / "chat.json")
    request = "Finish the scroll repair when approval is available."
    turn = store.begin_turn(request)
    store.start_goal(turn)
    remaining = ("Unresolved exact scroll constraints: " + "SCROLL_OWNER=#content; " * 35,)
    store.finish_turn(turn, AgentRunResult(status=AgentRunStatus.INCOMPLETE, message="Approval denied.",
        partial_text="Repair remains unfinished.", steps=1, capability_calls=0, protocol_failures=0,
        goal=TaskGoal(goal_id=turn, objective=request, state="stopped"),
        completion_review=CompletionReview(goal_id=turn, status="blocked", remaining=remaining)), "Repair remains unfinished.")
    history = store.agent_messages(preserve_unfinished=True, summarize_completed=True)
    frame = next(m for m in history if m.get("content", "").startswith("Unresolved historical work: "))
    messages = [{"role": "system", "content": "policy"}, *history]
    for index in range(4):
        messages.extend(exchange(f"old-{index}", "x" * 10000, index=index))
    messages.append({"role": "user", "content": "Current request: fix broken references."})
    result = recover_context_request(CharacterModel(), messages)
    assert result.compacted and result.budget.fits
    assert frame in result.messages and remaining[0] in frame["content"]
