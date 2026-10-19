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


@pytest.mark.parametrize("prompt,attached", [
    ("make her wear sunglasses, also make the camara settings better", False),
    ("generate some blur and focus and some compression", True),
])
def test_photographic_edits_through_composer_keep_source_and_generate(
        native_sdk, tmp_path, prompt, attached):
    from app.agent.bootstrap import build_agent_runtime
    from app.inference.hybrid import HybridInferenceEngine
    from app.settings.agent import AgentFeatureConfig
    from app.ui.main_window import MainWindow
    from tests.test_message_images import wait_for

    app = QApplication.instance() or QApplication([])
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), image_payload()])
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode="cloud", fallback_to_local=False)
    runtime = build_agent_runtime(hybrid, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(hybrid, ConversationStore(tmp_path / "chat.json"),
                                  agent_runtime=runtime, portable_root=tmp_path)
    window = None
    try:
        original = service.run("Generate an image of a fictional adult woman wearing a plain black dress").generated_images
        with service.store.attachment_store.open(original[0]) as source:
            pixels = source.read()
        # A selected photography skill must not hide an explicit visual edit.
        assert service.image_route_decision(prompt, attachments=original if attached else (),
                                             skill_name="photography-flagship").route == "image_generation"
        window = MainWindow(service, "PHOTOGRAPHIC EDIT REGRESSION", inference=hybrid)
        window.show()
        if attached:
            window.attachment_tray.add_references(original)
            wait_for(lambda: window.attachment_tray.ready)
        window.input.setPlainText(prompt)
        window.submit()
        wait_for(lambda: window.thread is None)
        assert len(bodies) == 2 and bodies[-1]["tool_choice"] == {"type": "image_generation"}
        sent = inputs(bodies[-1], "input_image")
        assert len(sent) == 1 and base64.b64decode(sent[0]["image_url"].split(",", 1)[1]) == pixels
        assert service.store.visible_messages()[-2].attachments == original
        assert service.store.visible_messages()[-1].generated_images
        assert not runtime.executor.journal.records
    finally:
        if window is not None:
            window.close()
        service.shutdown()


@pytest.mark.parametrize("prompt,expected", [
    ("Make her wear sunglasses", True),
    ("Generate some bokeh", True),
    ("Adjust the depth of field", True),
    ("Generate some blur and focus and some compression", True),
    ("Explain how to generate blur in this image", False),
    ("Generate a Python script for blur and focus", False),
    ("Make the camera settings button larger", False),
    ("Generate compression code for this image", False),
    ("Make it blue", False),
])
def test_photographic_intent_preserves_analysis_code_and_skill_boundaries(prompt, expected):
    from app.inference.image_generation import image_intent

    decision = image_intent(prompt, has_image=True, skill_name="photography-flagship")
    assert (decision.route == "image_generation") is expected


def test_photographic_effect_requires_a_current_or_submitted_image():
    from app.conversation.image_followup import image_route

    decision = image_route("generate some blur and focus and some compression")
    assert decision.route == "agent" and decision.reason == "no_visual_source"


@pytest.mark.parametrize("prompt", [
    "Generate a new image of a camera with bokeh",
    "Create a new photograph of a forest with blur",
])
def test_new_photographic_output_needs_no_source_and_does_not_inherit_one(native_sdk, tmp_path, prompt):
    from app.conversation.image_followup import image_route

    decision = image_route(prompt)
    assert decision.route == "image_generation" and decision.reason == "visual_creation"
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), image_payload()])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        assert service.run("Generate an image of a blue circle").generated_images
        assert service.run(prompt).generated_images
        assert not inputs(bodies[-1], "input_image")
        assert not service.store.visible_messages()[-2].attachments
    finally:
        service.shutdown()


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


@pytest.mark.parametrize("prompt", [
    "now generate this character from sideway also for 3d model reference",
    "Generate a side view",
    "Generate it again",
])
def test_generate_view_followup_reuses_retained_original(native_sdk, tmp_path, prompt):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), image_payload()])
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        original = service.run("Draw a fictional character").generated_images
        with service.store.attachment_store.open(original[0]) as source:
            expected = source.read()
        assert service.will_generate_images(prompt)
        result = service.run(prompt)
        assert result.generated_images and len(bodies) == 2
        assert bodies[-1]["tool_choice"] == {"type": "image_generation"}
        sent = inputs(bodies[-1], "input_image")
        assert len(sent) == 1 and base64.b64decode(sent[0]["image_url"].split(",", 1)[1]) == expected
        assert service.store.visible_messages()[-2].attachments == original
    finally:
        service.shutdown()


@pytest.mark.parametrize("prompt", ["Create this folder", "Generate a detailed report with photographs",
                                    "Generate a new image of a forest"])
def test_unrelated_creation_does_not_inherit_generated_image(prompt):
    from app.conversation.image_followup import visual_followup
    assert not visual_followup(prompt)


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
