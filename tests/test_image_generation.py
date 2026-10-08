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
    ("Generate an Editorial interior design photograph of a minimalist Scandinavian living room.", False, True),
    ("Genereate an Editorial interior design photograph of a minimalist Scandinavian living room.", False, True),
    ("Genereate a photograph of a living room", False, True),
    ("Create two photographs of a forest", False, True),
    ("Describe the photograph", True, False),
    ("Generate a prompt for a photograph of a living room", False, False),
    ("Genereate a prompt for a photograph of a living room", False, False),
    ("How can I generate photographs?", False, False),
    ("generate A clean, professional character modeling reference sheet in a Japanese manga art style", False, True),
    ("Create a professional character-modeling reference sheet for a fictional swordsman", False, True),
    ("Generate a reference sheet for a character's costume and poses", False, True),
    ("Create a model sheet for an animated character", False, True),
    ("Generate a sprite sheet for a running fox", False, True),
    ("Create concept art for a moon base", False, True),
    ("Generate a storyboard for a short film", False, True),
    ("Create an icon of a lantern", False, True),
    ("Generate a stone texture", False, True),
    ("Generate a portrait of a fictional swordsman", False, True),
    ("Create a painting of a mountain landscape", False, True),
    ("Generate a pencil drawing of a tree", False, True),
    ("Create a sketch of a costume", False, True),
    ("Generate a " + "detailed softly lit and carefully composed " * 6 + "image of a room", False, True),
    ("Generate a detailed report containing photographs", False, False),
    ("Create a detailed Python program that processes images", False, False),
    ("Generate a summary of how people create images", False, False),
    ("Write a prompt to generate a character reference sheet", False, False),
    ("Draft a detailed prompt for concept art", False, False),
    ("Generate a reference sheet of Python functions", False, False),
    ("Generate a document about character reference sheets", False, False),
    ("Create a spreadsheet of sprite coordinates", False, False),
    ("Generate a Python file that processes photographs", False, False),
    ("Explain how to generate a character sheet", False, False),
    ("Create a new folder. It will contain images", False, False),
    ("Create an image of a person holding a report", False, True),
    ("Make a detailed report about this image", True, False),
    ("Generate this character from the side for a 3D model reference", True, True),
    ("Generate a side view", True, True),
    ("Generate it again", True, True),
    ("Generate a detailed description of this character", True, False),
    ("Generate a caption for this picture", True, False),
    ("Create this folder", True, False),
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
