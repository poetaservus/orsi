from concurrent.futures import ThreadPoolExecutor
import base64
from copy import deepcopy

import pytest
import httpx
import json

from app.agent.contracts import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.attachments import AttachmentError
from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError
from app.inference.completion import IncompleteResponseError
from app.inference.image_generation import image_request
from app.inference.hybrid import HybridInferenceEngine
from app.ui.main_window import MainWindow
from tests.test_image_generation_presentation import presentation_app
from tests.test_message_images import wait_for
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import engine_with_transport
from tests.test_openai_streaming import make_engine, Stream, events, streaming_response


@pytest.mark.parametrize("status,code,expected", [(403, "model_not_found", CloudErrorCode.PERMISSION),
    (429, "rate_limit_exceeded", CloudErrorCode.RATE_LIMIT)])
def test_image_access_and_rate_failures_preserve_manual_request(monkeypatch, tmp_path, status, code, expected):
    engine, _, requests, _ = engine_with_transport(monkeypatch,
        {"error": {"code": code, "message": "PRIVATE PROVIDER BODY"}}, status=status)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        with pytest.raises(CloudInferenceError) as error:
            service.run("Generate an image of a blue circle")
        assert error.value.code == expected
        assert len(requests) == 1
        restored = ConversationStore(tmp_path / "chat.json")
        assert restored.visible_messages()[0].content == "Generate an image of a blue circle"
        assert not restored.visible_messages()[-1].generated_images
        assert "PRIVATE" not in restored.path.read_text()
    finally:
        service.shutdown()


@pytest.mark.parametrize("change", ["duplicate", "corrupt", "unfinished", "too_many", "wrong_type"])
def test_invalid_results_publish_no_images(monkeypatch, tmp_path, change):
    payload = image_payload()
    if change == "duplicate":
        payload["output"].append(deepcopy(payload["output"][0]))
    elif change == "corrupt":
        payload["output"][0]["result"] = base64.b64encode(b"\x89PNG\r\n\x1a\ninvalid").decode()
    elif change == "unfinished":
        payload["output"][0]["status"] = "in_progress"
    elif change == "too_many":
        payload = image_payload(count=9)
    else:
        payload["output"].append({"type": "function_call", "id": "unadvertised"})
    engine, _, _, _ = engine_with_transport(monkeypatch, payload)
    store = ConversationStore(tmp_path / "chat.json")
    service = ConversationService(engine, store)
    try:
        with pytest.raises(AttachmentError):
            service.run("Draw a blue circle")
        assert not store.visible_messages()[-1].generated_images
        assert not list(store.attachment_store.root.glob("att-*"))
    finally:
        service.shutdown()


def test_image_cancellation_closes_stream_and_never_replays_started_request(make_engine, tmp_path):
    stream = Stream(events(image_payload(), terminal=False), hold=True)
    requests = []
    def handle(request):
        requests.append(request)
        return streaming_response(stream)
    engine = make_engine(handle)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(service.run, "Draw a blue circle")
            assert stream.waiting.wait(10)
            assert service.cancel_current_task()
            with pytest.raises(IncompleteResponseError) as error:
                task.result(timeout=10)
            assert error.value.completion.finish_reason == "cancelled"
        assert stream.closed.is_set() and len(requests) == 1
        assert service.store.turns()[-1].outcome.status == AgentRunStatus.CANCELLED
        assert not service.store.visible_messages()[-1].generated_images
        assert not list(service.store.attachment_store.root.glob("att-*"))
    finally:
        runner = engine._runner
        service.shutdown()
    assert not runner._thread.is_alive()


@pytest.mark.parametrize("text", ["Generate a list of image files", "Create a Python script to edit images", "How do I draw a circle?"])
def test_text_tasks_do_not_start_image_generation(text):
    assert not image_request(text)


def test_image_requests_never_use_sdk_automatic_retries(make_engine, tmp_path):
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded", "message": "PRIVATE"}})
    engine = make_engine(handle, max_retries=3)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        with pytest.raises(CloudInferenceError):
            service.run("Draw a blue circle")
        assert len(requests) == 1
        assert requests[0]["max_output_tokens"] == min(engine.catalog.current_profile.max_output_tokens, 4096)
        assert engine.config.max_retries == 3
    finally:
        service.shutdown()


def test_failed_image_prompt_returns_to_composer_for_manual_retry(presentation_app, monkeypatch, tmp_path):
    engine, _, requests, _ = engine_with_transport(monkeypatch,
        {"error": {"code": "model_not_found", "message": "PRIVATE"}}, status=403)
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode="cloud", fallback_to_local=False)
    service = ConversationService(hybrid, ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "SYNTHETIC", inference=hybrid)
    window.show()
    prompt = "Generate an image of a blue circle"
    try:
        window.input.setPlainText(prompt)
        window.submit()
        wait_for(lambda: window.thread is None)
        assert len(requests) == 1
        assert window.input.toPlainText() == prompt
        frame = window.chat._messages[-1].image_strip
        assert frame.status == "Image generation failed" and not frame.active and not frame.timer.isActive()
        assert "PRIVATE" not in str(window.chat._messages[-1]._content)
    finally:
        window.close()
        service.shutdown()


def test_stop_keeps_prompt_and_late_activity_cannot_restart_animation(presentation_app, make_engine, tmp_path):
    stream = Stream(events(image_payload(), terminal=False), hold=True)
    engine = make_engine(lambda request: streaming_response(stream))
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode="cloud", fallback_to_local=False)
    service = ConversationService(hybrid, ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "SYNTHETIC", inference=hybrid)
    window.show()
    prompt = "Draw a blue circle"
    try:
        window.input.setPlainText(prompt)
        window.submit()
        wait_for(lambda: stream.waiting.is_set() and window.chat.generation_frame is not None)
        frame = window.chat.generation_frame
        window.cancel_current_task()
        window._set_working_activity("Generating image…")
        assert not frame.active and not frame.timer.isActive()
        wait_for(lambda: window.thread is None)
        assert window.input.toPlainText() == prompt
        assert window.chat._messages[-1].image_strip.status == "Image generation stopped"
        assert service.store.turns()[-1].outcome.status == AgentRunStatus.CANCELLED
    finally:
        window.close()
        service.shutdown()
