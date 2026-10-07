import base64
import pytest
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.ui.image_settings import ImageSettingsDialog
from tests.test_cloud_attachment_input import native_sdk, inputs
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import response


def test_edit_after_restart_uses_original_bytes_and_analysis_stays_normal(native_sdk, tmp_path):
    engine, _, generations, _ = native_sdk(payloads=[image_payload(count=2)])
    first = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    result = first.run("Generate two images of a blue circle")
    originals = result.generated_images
    expected = []
    for ref in originals:
        with first.store.attachment_store.open(ref) as stream:
            expected.append(stream.read())
    first.shutdown()
    second_engine, counts, generations, _ = native_sdk(payloads=[image_payload(), response("A blue circle")])
    second = ConversationService(second_engine, ConversationStore(tmp_path / "chat.json"))
    try:
        edited = second.run("Make the background darker")
        assert edited.generated_images
        sent = inputs(generations[0], "input_image")
        assert [base64.b64decode(part["image_url"].split(",", 1)[1]) for part in sent] == expected
        assert second.store.visible_messages()[-2].attachments == originals
        analysis = second.run("Describe this image")
        assert str(analysis) == "A blue circle" and not analysis.generated_images
        assert "tools" not in generations[1]
        assert inputs(generations[1], "input_image")
        assert counts
    finally:
        second.shutdown()


def test_image_settings_dialog_preserves_choices_and_busy_guard(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = ImageSettingsStore(ImageGenerationSettings(), tmp_path / "images.json")
    dialog = ImageSettingsDialog(store, store.select)
    try:
        dialog.choices["size"].setCurrentText("1024x1536")
        dialog.choices["output_format"].setCurrentText("webp")
        dialog._save()
        assert ImageSettingsStore(ImageGenerationSettings(), tmp_path / "images.json").current.output_format == "webp"
        assert store.current.size == "1024x1536"
    finally:
        dialog.close()
    app.processEvents()


def test_settings_apply_to_next_image_request_without_changing_chat_profile(native_sdk, tmp_path):
    engine, _, generations, _ = native_sdk(payloads=[image_payload()])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    before = engine.catalog.current_profile
    chosen = ImageGenerationSettings(size="1024x1536", quality="low")
    try:
        service._run_lock.acquire()
        try:
            with pytest.raises(RuntimeError):
                service.select_image_settings(chosen)
        finally:
            service._run_lock.release()
        assert engine.image_settings.current != chosen
        service.select_image_settings(chosen)
        service.run("Draw a blue circle")
        assert generations[0]["tools"][0]["size"] == "1024x1536"
        assert generations[0]["tools"][0]["quality"] == "low"
        assert engine.catalog.current_profile == before
    finally:
        service.shutdown()
