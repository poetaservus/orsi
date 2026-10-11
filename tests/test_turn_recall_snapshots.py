"""A history page must not invalidate itself when its receipt is retained."""
from dataclasses import replace
import hashlib
import json
import os

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.capabilities.conversation_read_turn import ConversationReadTurnCapability
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall
from tests.test_filesystem_read_text import context
from tests.test_long_conversation_context import settle, finish


def retain_page(store, turn, result, arguments, index):
    store.record_settled(turn, SettledCall(provider_message_id=f"recall-{index}",
        call=ModelCapabilityCall(provider_call_id=f"recall-call-{index}",
            capability="conversation.read_turn", arguments=arguments), result=result))


def test_active_turn_pages_survive_their_own_receipts_and_later_work(tmp_path):
    store = ConversationStore(tmp_path / "chat.json")
    turn = store.begin_turn("Read this project and summarize it.")
    store.record_settled(turn, settle(1, text="original 😀 source\n" * 80))
    tool = ConversationReadTurnCapability(store)
    ctx = replace(context(tmp_path), session_id=store.session_id)
    arguments, pieces, revision = {"turn_id": turn, "max_bytes": 129}, [], None
    for index in range(100):
        result = tool.invoke(arguments, replace(ctx, call_id=f"recall-receipt-{index}"))
        assert result.success, result.error
        output = result.output
        revision = revision or output["revision"]
        assert output["revision"] == revision
        pieces.append(output["text"])
        retain_page(store, turn, result, arguments, index)
        if index == 0:
            store.record_settled(turn, settle(2, text="later settled work"))
        arguments = output["next_read"]
        if arguments is None:
            break
    else:
        pytest.fail("Recall did not finish within the bounded page count.")
    raw = "".join(pieces)
    assert hashlib.sha256(raw.encode()).hexdigest() == revision
    restored = json.loads(raw)
    assert restored["status"] == "active"
    assert len(restored["settled_calls"]) == 1
    assert restored["settled_calls"][0]["result"]["output"]["text"] == "original 😀 source\n" * 80
    assert len(store.turns()[0].settled_calls) == len(pieces) + 2
    # A fresh read sees new work, while the original revision stays available.
    fresh = tool.invoke({"turn_id": turn, "max_bytes": 16384}, ctx).output
    assert fresh["revision"] != revision
    latest = json.loads(fresh["text"])
    assert latest["settled_calls"][2]["result"]["output"]["text"] == "later settled work"
    assert tool.invoke({"turn_id": turn, "max_bytes": 16384, "expected_revision": revision}, ctx).output["text"] == raw


def test_recalled_history_omits_nested_recall_bodies(tmp_path):
    store = ConversationStore(tmp_path / "chat.json")
    turn = store.begin_turn("Summarize the project.")
    store.record_settled(turn, settle(1))
    tool = ConversationReadTurnCapability(store)
    result = tool.invoke({"turn_id": turn}, replace(context(tmp_path), session_id=store.session_id))
    assert result.success
    retain_page(store, turn, result, {"turn_id": turn}, 1)
    original = store.path.read_bytes()
    restored = store.recall_turn(turn)
    receipt = restored["settled_calls"][1]
    assert receipt["capability"] == "conversation.read_turn"
    assert receipt["call_id"] == result.call_id and receipt["success"]
    assert "text" not in receipt and "result" not in receipt
    assert "omitted" in receipt["notice"].lower()
    assert store.path.read_bytes() == original


def test_context_projection_can_continue_a_retained_active_snapshot(tmp_path):
    from app.conversation.recovery import recover_context_request
    from tests.test_context_recovery import CharacterModel
    store = ConversationStore(tmp_path / "chat.json")
    turn = store.begin_turn("Recover original evidence.")
    store.record_settled(turn, settle(1, text="😀 original source\n" * 300))
    tool = ConversationReadTurnCapability(store)
    ctx = replace(context(tmp_path), session_id=store.session_id)
    arguments = {"turn_id": turn, "max_bytes": 16384}
    result = tool.invoke(arguments, ctx)
    assert result.success and result.output["complete_document"]
    retain_page(store, turn, result, arguments, 1)
    receipt = store.turns()[0].settled_calls[-1]
    recovered = recover_context_request(CharacterModel(), [
        {"role": "user", "content": "Recover original evidence."}, *receipt.messages()])
    projected = next(m["result"]["output"] for m in recovered.messages if m["role"] == "capability")
    assert not projected["complete_document"] and projected["has_more"]
    assert len(projected["text"]) < len(result.output["text"])
    continuation = tool.invoke(projected["next_read"], replace(ctx, call_id="continuation"))
    assert continuation.success
    end = continuation.output["end_offset"]
    assert (projected["text"] + continuation.output["text"]).encode() == result.output["text"].encode()[:end]
    assert store.turns()[0].settled_calls[-1].result.output == result.output


def test_snapshot_survives_finish_then_refreshes_on_next_user_turn(tmp_path):
    store = ConversationStore(tmp_path / "chat.json")
    turn = store.begin_turn("Original request")
    store.record_settled(turn, settle(1, text="source\n" * 100))
    tool = ConversationReadTurnCapability(store)
    ctx = replace(context(tmp_path), session_id=store.session_id)
    first = tool.invoke({"turn_id": turn, "max_bytes": 128}, ctx).output
    store.finish_turn(turn, AgentRunResult(status=AgentRunStatus.COMPLETED,
        assistant_text="Finished answer", steps=1, capability_calls=1, protocol_failures=0), "Finished answer")
    assert tool.invoke(first["next_read"], ctx).output["revision"] == first["revision"]
    next_turn = store.begin_turn("Next request")
    ctx = replace(ctx, turn_id=next_turn)
    stale = tool.invoke(first["next_read"], ctx)
    assert not stale.success and stale.error.code.value == "invalid_arguments"
    refreshed = tool.invoke({"turn_id": turn, "max_bytes": 16384}, ctx).output
    assert refreshed["revision"] != first["revision"]
    assert json.loads(refreshed["text"])["assistant"]["content"] == "Finished answer"


@pytest.mark.parametrize("boundary", ["new_session", "forget_protected_state"])
def test_snapshot_cache_does_not_outlive_session_or_protected_memory(tmp_path, boundary):
    store = ConversationStore(tmp_path / "chat.json")
    finish(store, "private original request")
    store.recall_turn_snapshot("turn-1")
    assert store._recall_snapshots
    getattr(store, boundary)()
    assert not store._recall_snapshots
    if boundary == "new_session":
        store.begin_turn("different conversation")
        raw = store.recall_turn_snapshot("turn-1")[1]
        assert b"private original request" not in raw
        assert b"different conversation" in raw
    else:
        from app.conversation.store import TurnHistoryError
        with pytest.raises(TurnHistoryError):
            store.recall_turn_snapshot("turn-1")


@pytest.mark.parametrize("budget", ["count", "bytes"])
def test_snapshot_limits_do_not_evict_pages_already_in_progress(tmp_path, monkeypatch, budget):
    import app.conversation.store as store_module
    store = ConversationStore(tmp_path / "chat.json")
    finish(store, "first original request " * 50)
    finish(store, "second original request " * 50)
    tool = ConversationReadTurnCapability(store)
    ctx = replace(context(tmp_path), session_id=store.session_id)
    first = tool.invoke({"turn_id": "turn-1", "max_bytes": 128}, ctx).output
    if budget == "count":
        monkeypatch.setattr(store_module, "MAX_TURN_RECALL_SNAPSHOTS", 1)
    else:
        monkeypatch.setattr(store_module, "MAX_TURN_RECALL_BYTES", first["total_text_bytes"])
    rejected = tool.invoke({"turn_id": "turn-2"}, ctx)
    assert not rejected.success and rejected.error.code.value == "output_limited"
    continued = tool.invoke(first["next_read"], ctx)
    assert continued.success and continued.output["revision"] == first["revision"]


@pytest.mark.parametrize("arguments,code", [
    ({"turn_id": "turn-99"}, "not_found"),
    ({"turn_id": "turn-1", "offset": 1}, "invalid_arguments"),
    ({"turn_id": "turn-1", "offset": 100000, "expected_revision": "0" * 64}, "invalid_arguments"),
    ({"turn_id": "turn-1", "expected_revision": "0" * 64}, "invalid_arguments"),
])
def test_snapshot_reads_keep_existing_argument_and_revision_guards(tmp_path, arguments, code):
    store = ConversationStore(tmp_path / "chat.json")
    finish(store, "Original request")
    result = ConversationReadTurnCapability(store).invoke(arguments,
        replace(context(tmp_path), session_id=store.session_id))
    assert not result.success and result.error.code.value == code


@pytest.mark.skipif(os.name != "nt", reason="Native host source read")
def test_first_cloud_turn_can_recall_project_evidence_after_streamed_candidate(tmp_path, monkeypatch):
    """Real SDK/stream normalization and durable receipts, with no network call."""
    import httpx
    import openai
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.inference.openai_backend import OpenAIResponsesInferenceEngine
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import AgentFeatureConfig
    from tests.fixtures.completion_reviews import ready_review_for
    from tests.test_openai_phase1 import config, response
    from tests.test_openai_streaming import events, encode
    from tests.test_openai_tools import function

    path = tmp_path / "project.py"
    source = "# original project source 😀\n" * 300
    path.write_bytes(source.encode("utf-8"))
    bodies, pieces = [], []
    candidate, final = "Initial project summary.", "Completed project summary with original source recovered."

    def handle(request):
        body = json.loads(request.content)
        bodies.append(body)
        index = len(bodies)
        assert index < 20, "Cloud recall must finish within existing turn budgets."

        def tool_call(name, arguments):
            definition = next(d for d in service.agent_runtime.registry.model_definitions() if d.name == name)
            # Strict Responses tools send nullable sentinels for domain defaults.
            wire = {key: arguments.get(key) for key in definition.input_schema["properties"]}
            return response(id=f"resp-{index}", output=[function(definition, wire, call_id=f"call-{index}")])

        if index == 1:
            payload = tool_call("filesystem.read_text", {"path": str(path), "max_bytes": 16384, "max_lines": 1000})
        elif index == 2:
            payload = response(candidate, id=f"resp-{index}")
        elif index == 3:
            # Completion checking is allowed to recover evidence after a candidate.
            assert ready_review_for(body["input"]) is not None
            payload = tool_call("conversation.read_turn", {"turn_id": "turn-1", "max_bytes": 4096})
        elif ready_review_for(body["input"]) is not None:
            payload = response(ready_review_for(body["input"]).assistant_text, id=f"resp-{index}")
        else:
            receipt = json.loads([m for m in body["input"] if m.get("type") == "function_call_output"][-1]["output"])
            assert receipt["success"], receipt.get("error")
            page = receipt["output"]
            pieces.append(page["text"])
            if page["has_more"]:
                payload = tool_call("conversation.read_turn", page["next_read"])
            else:
                restored = json.loads("".join(pieces))
                assert restored["settled_calls"][0]["result"]["output"]["text"] == source
                payload = response(final, id=f"resp-{index}")
        for item in payload["output"]:
            if item["type"] == "message":
                item["id"] = f"msg-{index}"
        return httpx.Response(200, content=encode(events(payload)), headers={"content-type": "text/event-stream"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = openai.AsyncOpenAI(api_key="synthetic-never-live", max_retries=0, http_client=http)
    def http_factory(**kwargs):
        http.event_hooks = kwargs["event_hooks"]
        return http
    monkeypatch.setattr(openai, "DefaultAsyncHttpxClient", http_factory)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: client)
    engine = OpenAIResponsesInferenceEngine(config(), api_key="synthetic-never-live")
    policy = HostAccessPolicy.full_local(application_root=tmp_path, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True,
        full_local_read_enabled=True, context_recovery_enabled=True, conversation_context_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state", host_access_policy=policy)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    previews = []
    try:
        answer = service.run("Please read this project and summarize it to me: " + str(path), text_observer=previews.append)
        assert answer == final
        assert candidate in previews and len(pieces) > 1
        outcome = service._turn_result
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.completion_review.status == "ready"
        assert all(item.result.success for item in outcome.settled_calls)
        recall = [item.result.output for item in outcome.settled_calls if item.call.capability == "conversation.read_turn"]
        assert len({item["revision"] for item in recall}) == 1
        assert recall[0]["has_more"] and len(recall) == len(pieces)
        restored = ConversationStore(service.store.path)
        assert len(restored.turns()) == 1 and restored.turns()[0].outcome.status == AgentRunStatus.COMPLETED
        assert restored.visible_messages()[-1].content == final
    finally:
        service.shutdown()
        engine.close()
