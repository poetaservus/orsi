"""Assessment-only streams cannot erase or replace the visible user answer."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from threading import Event

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig
from tests.test_openai_phase1 import response
from tests.test_openai_streaming import make_engine, events, encode
from tests.test_openai_tools import function


def test_review_stream_preserves_preview_replay_and_next_turn(make_engine, tmp_path):
    import httpx
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.ui.chat import ChatView
    from app.ui.worker import ConversationWorker
    from tests.test_attachment_composer import wait_for

    app = QApplication.instance() or QApplication([])
    candidate = ("Project summary.\n\n" + "The source contains the application and its styles. " * 20).rstrip()
    next_answer = "The follow-up answer."
    held, release = Event(), Event()
    requests = []

    class ReviewStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            values = events(response(json.dumps({"goal_id": "turn-1", "status": "ready", "remaining": []}),
                id="resp-3"))
            for value in values[:-1]:
                yield encode([value])
            held.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            yield encode(values[-1:])

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)
        assert body["tool_choice"] == ("none" if index in (3, 5) else "auto")
        if index == 3:
            assert any(item.get("type") == "function_call" for item in body["input"])
            assert any(item.get("type") == "function_call_output" for item in body["input"])
            return httpx.Response(200, stream=ReviewStream(), headers={"content-type": "text/event-stream"})
        if index == 1:
            definition = runtime.registry.model_definitions()[0]
            payload = response(id="resp-2", output=[function(definition, {"path": str(tmp_path)}, call_id="call-2")])
        elif index in (2, 4):
            payload = response(candidate if index == 2 else next_answer, id=f"resp-{index}")
        else:
            assert index == 5
            payload = response(json.dumps({"goal_id": "turn-2", "status": "ready", "remaining": []}), id="resp-5")
        for item in payload["output"]:
            if item["type"] == "message":
                item["id"] = f"msg-{index}"
        return httpx.Response(200, content=encode(events(payload)), headers={"content-type": "text/event-stream"})

    engine = make_engine(handle)
    policy = HostAccessPolicy.full_local(application_root=tmp_path, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True, full_local_read_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state", host_access_policy=policy)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    chat = ChatView()
    chat.resize(800, 500)
    chat.show()
    chat.set_thinking(True)
    worker = ConversationWorker(service, "Summarize the project")
    previews, answers, errors, activities = [], [], [], []
    worker.text_updated.connect(previews.append)
    worker.text_updated.connect(chat.set_stream_preview)
    worker.finished.connect(answers.append)
    worker.failed.connect(errors.append)
    worker.activity.connect(activities.append)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.run)
            try:
                wait_for(lambda: held.is_set() or future.done())
                assert held.is_set() and not future.done()
                assert chat.stream_preview.text() == candidate
                assert previews[-1] == candidate
                assert activities[-1] == "Checking completion…"
            finally:
                release.set()
            wait_for(future.done)
            future.result()
        assert not errors and len(answers) == 1 and candidate in answers[0]
        assert previews[previews.index(candidate):] == [candidate]
        chat.set_thinking(False)
        chat.add_message("Agent", answers[0])
        assert chat.stream_preview.text() == "" and len(chat._messages) == 1
        assert engine._text_observer is None
        follow_up_previews = []
        assert next_answer in service.run("A follow-up request", text_observer=follow_up_previews.append)
        assert next_answer in follow_up_previews and candidate not in follow_up_previews
        assert engine._text_observer is None and len(requests) == 5
    finally:
        release.set()
        chat.close()
        service.shutdown()
        app.processEvents()


def test_noncompliant_review_cursor_is_not_executed_or_replayed(make_engine, tmp_path):
    import httpx
    requests = []
    candidate = "The requested project summary."

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)
        if index == 2:
            assert body["tool_choice"] == "none"
            definition = runtime.registry.model_definitions()[0]
            payload = response(id="resp-rejected-review", output=[function(definition,
                {"path": str(tmp_path / "static"), "cursor": "0", "max_entries": 50}, call_id="bad-review-cursor")])
        else:
            assert index in (1, 3)
            if index == 3:
                assert body["tool_choice"] == "none"
                assert all(item.get("call_id") != "bad-review-cursor" for item in body["input"])
            payload = response(candidate if index == 1 else json.dumps({"goal_id": "turn-1", "status": "ready", "remaining": []}),
                id=f"resp-{index}")
            payload["output"][0]["id"] = f"msg-{index}"
        return httpx.Response(200, content=encode(events(payload)), headers={"content-type": "text/event-stream"})

    engine = make_engine(handle)
    policy = HostAccessPolicy.full_local(application_root=tmp_path, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_list_enabled=True, full_local_read_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state", host_access_policy=policy)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
        portable_root=tmp_path, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    previews = []
    try:
        assert service.run("Summarize the project", text_observer=previews.append) == candidate
        assert service._turn_result.protocol_failures == 1
        assert service._turn_result.capability_calls == 0 and not service._turn_result.settled_calls
        assert previews[previews.index(candidate):] == [candidate]
        assert len(requests) == 3
    finally:
        service.shutdown()
