"""Synthetic end-to-end acceptance through the SDK, durable store and Qt viewer."""
import base64

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.agent.bootstrap import build_agent_runtime
from app.inference.hybrid import HybridInferenceEngine
from app.settings.agent import AgentFeatureConfig
from app.ui.main_window import MainWindow
from tests.test_cloud_attachment_input import native_sdk, inputs
from tests.test_image_generation import image_payload
from tests.test_image_generation_presentation import presentation_app
from tests.test_message_images import image_bytes, wait_for


def test_generation_reopen_and_viewer_edit_with_agent_enabled(presentation_app, native_sdk, tmp_path):
    payload = image_payload(count=2)
    payload["output"][1]["result"] = base64.b64encode(image_bytes("green", 640, 480)).decode()
    engine, _, first_bodies, _ = native_sdk(payloads=[payload])
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "state")
    first = ConversationService(engine, ConversationStore(tmp_path / "chat.json"),
                                agent_runtime=runtime, portable_root=tmp_path)
    try:
        result = first.run("Generate two images of a blue circle")
        originals = result.generated_images
        assert len(originals) == 2 and len(first_bodies) == 1 and not runtime.executor.journal.records
        raw = []
        for ref in originals:
            with first.store.attachment_store.open(ref) as source:
                raw.append(source.read())
    finally:
        first.shutdown()

    engine, _, bodies, _ = native_sdk(payloads=[image_payload()])
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode="cloud", fallback_to_local=False)
    runtime = build_agent_runtime(hybrid, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(hybrid, ConversationStore(tmp_path / "chat.json"),
                                  agent_runtime=runtime, portable_root=tmp_path)
    window = MainWindow(service, "SYNTHETIC ACCEPTANCE", inference=hybrid)
    window.show()
    try:
        assert service.store.visible_messages()[-1].generated_images == originals
        assert window.chat._messages[-1].image_strip.references == originals
        window._open_image_viewer(originals, 1)
        viewer = window._image_viewer
        viewer.prompt.setPlainText("Make the background darker")
        wait_for(lambda: viewer.send.isEnabled())
        viewer._submit()
        wait_for(lambda: len(bodies) == 1 and window.thread is None)
        assert window._image_viewer is None
        assert bodies[0]["tool_choice"] == {"type": "image_generation"}
        sent = inputs(bodies[0], "input_image")
        assert len(sent) == 1
        assert base64.b64decode(sent[0]["image_url"].split(",", 1)[1]) == raw[1]
        messages = service.store.visible_messages()
        assert messages[-2].attachments == (originals[1],)
        assert messages[-1].generated_images
        assert not runtime.executor.journal.records
        assert "data:image/" not in service.store.path.read_text()
        for ref, expected in zip(originals, raw):
            with service.store.attachment_store.open(ref) as source:
                assert source.read() == expected
    finally:
        window.close()
        service.shutdown()


def test_application_restart_starts_empty_and_archives_generated_image_chat(presentation_app, native_sdk, monkeypatch, tmp_path):
    from unittest.mock import Mock
    import app.startup as startup
    from app.inference.engine import InferenceUnavailable
    from app.runtime.skills import SkillRegistry
    from app.settings.paths import RuntimePaths
    from tests.test_openai_phase1 import config

    paths = RuntimePaths(tmp_path, tmp_path / "config", tmp_path / "models", tmp_path / "state")
    path = paths.state / "conversation_v1" / "conversation.json"
    engine, _, _, _ = native_sdk(payloads=[image_payload()])
    first = ConversationService(engine, ConversationStore(path))
    try:
        original = first.run("Draw a blue circle").generated_images
        session_id = first.store.session_id
        with first.store.attachment_store.open(original[0]) as source:
            original_bytes = source.read()
    finally:
        first.shutdown()

    engine, _, bodies, _ = native_sdk(payloads=[image_payload()])
    monkeypatch.setattr(startup, "PATHS", paths)
    monkeypatch.setattr(startup, "load_model_config", Mock(side_effect=InferenceUnavailable("no local test model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config(default_mode="cloud"))
    monkeypatch.setattr(startup, "OpenAIResponsesInferenceEngine", lambda *args, **kwargs: engine)
    service, _, error, hybrid = startup.build_application(
        agent_config_override=AgentFeatureConfig(filesystem_stat_enabled=True),
        skill_registry_override=SkillRegistry(global_root=tmp_path / "skills"))
    assert error is None and service is not None
    window = None
    try:
        assert service.store.session_id != session_id
        assert not service.store.visible_messages() and not service.store.turns()
        assert not service.will_generate_images("Make the background darker")
        archives = list((path.parent / "archives").glob("*.json"))
        assert len(archives) == 1
        archived = ConversationStore(archives[0])
        assert archived.session_id == session_id
        assert archived.visible_messages()[-1].generated_images == original
        with archived.attachment_store.open(original[0]) as source:
            assert source.read() == original_bytes
        window = MainWindow(service, "SYNTHETIC RESTART", inference=hybrid)
        window.show()
        assert not window.chat._messages and window.startup_greeting.isVisible()
        window.attachment_tray.add_references(original)
        wait_for(lambda: window.attachment_tray.ready)
        window.input.setPlainText("Make the background darker")
        window.submit()
        wait_for(lambda: len(bodies) == 1 and window.thread is None)
        assert service.store.visible_messages()[-2].attachments == original
        assert service.store.visible_messages()[-1].generated_images
        assert inputs(bodies[0], "input_image")
        window.create_new_session()
        assert not service.store.visible_messages()
    finally:
        if window is not None:
            window.close()
        service.shutdown()


def test_editorial_photograph_request_uses_images_with_agent_enabled(native_sdk, tmp_path):
    prompt = (
        "Genereate an Editorial interior design photograph of a minimalist Scandinavian living room.\n\n"
        "Scene layout: A low-profile, light beige linen modular sofa sits against a soft matte off-white wall, "
        "anchored by a round boucle area rug in cream. A single black-stained oak coffee table stands in "
        "the center with a single ceramic vase and a thin art monograph book resting on it. In the "
        "background corner, a tall fiddle-leaf fig tree in a raw terracotta pot adds a touch of organic green.\n\n"
        "Lighting and atmosphere: Soft, diffused morning daylight streams in from a large off-camera "
        "window on the left, casting gentle, natural shadows across the pale engineered hardwood floor.\n\n"
        "Composition and style: Eye-level straight-on interior shot, clean architectural framing, "
        "photorealistic textures, warm neutral color palette, quiet and serene mood, no extra people."
    )
    engine, _, bodies, _ = native_sdk(payloads=[image_payload()])
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"),
                                  agent_runtime=runtime, portable_root=tmp_path)
    try:
        assert service.will_generate_images(prompt)
        result = service.run(prompt)
        assert result.generated_images and len(bodies) == 1
        assert bodies[0]["tool_choice"] == {"type": "image_generation"}
        assert [item["content"] for item in bodies[0]["input"] if item["role"] == "user"] == [prompt]
        assert not runtime.executor.journal.records
    finally:
        service.shutdown()
