import base64
import json
from types import SimpleNamespace

import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.image_generation import image_request
from app.inference.openai_stream import ResponsesStreamState, StreamProtocolError
from tests.test_openai_phase1 import engine_with_transport, response
from tests.test_attachment_processing import image_data


def image_payload(*, count=1):
    return response(output=[{"id": f"ig_{i}", "type": "image_generation_call", "status": "completed",
                            "result": base64.b64encode(image_data()).decode(), "output_format": "png"}
                           for i in range(count)])


def test_native_image_only_pipeline_and_private_sources(monkeypatch, tmp_path, caplog):
    payload = image_payload()
    engine, client, requests, _ = engine_with_transport(monkeypatch, payload)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    activities = []
    try:
        result = service.run("Generate an image of a blue circle", activities.append)
        assert len(result.generated_images) == 1
        ref = result.generated_images[0]
        assert ref.kind == "image"
        with service.store.attachment_store.open(ref) as stream:
            assert stream.read() == image_data()
        body = json.loads(requests[0].content)
        assert body["tool_choice"] == {"type": "image_generation"}
        assert body["tools"][0]["model"] == engine.image_settings.current.model
        assert body["store"] is False
        assert "Generating image…" in activities
        encoded = payload["output"][0]["result"]
        assert encoded not in str(result) and encoded not in caplog.text
        assert encoded not in (tmp_path / "chat.json").read_text()
        reopened = ConversationStore(tmp_path / "chat.json")
        assert reopened.visible_messages()[-1].generated_images == (ref,)
        assert not service.store.attachment_store.discard_draft(ref)
        reopened.attachment_store.verify(ref)
    finally:
        service.shutdown()
    assert client.is_closed()


@pytest.mark.parametrize("text,has_image,expected", [
    ("Draw a blue circle", False, True), ("Create a picture of a forest", False, True),
    ("/image soft landscape", False, True), ("What is in this image?", True, False),
    ("Describe the picture", True, False), ("How do I create an image?", False, False),
    ("Make the background darker", True, True), ("Hello", False, False),
])
def test_generation_intent_preserves_analysis(text, has_image, expected):
    assert image_request(text, has_image=has_image) is expected


def event(**values):
    return SimpleNamespace(model_dump=lambda **_: values)


def test_native_image_events_require_advertisement_and_identity():
    state = ResponsesStreamState(allow_images=True)
    state.accept(event(type="response.created", sequence_number=0, response={"id": "resp"}))
    state.accept(event(type="response.output_item.added", sequence_number=1, output_index=0,
        item={"id": "ig", "type": "image_generation_call"}))
    state.accept(event(type="response.image_generation_call.generating", sequence_number=2,
        output_index=0, item_id="ig"))
    with pytest.raises(StreamProtocolError):
        state.accept(event(type="response.image_generation_call.completed", sequence_number=3,
            output_index=0, item_id="other"))
    plain = ResponsesStreamState()
    plain.accept(event(type="response.created", sequence_number=0, response={"id": "resp"}))
    with pytest.raises(StreamProtocolError):
        plain.accept(event(type="response.output_item.added", sequence_number=1, output_index=0,
            item={"id": "ig", "type": "image_generation_call"}))
