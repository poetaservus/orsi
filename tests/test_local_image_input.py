"""Local visual bytes survive projection, atomic admission, replay and native tools."""
import base64
from copy import deepcopy
import json
from threading import Event, RLock
from types import SimpleNamespace

import pytest

from app.conversation.context import count_message_tokens, calculate_context_budget
from app.conversation.local_documents import LocalDocuments, LOCAL_IMAGE_GUIDANCE
from app.conversation.image_guidance import IMAGE_INTENT_GUIDANCE
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.attachments import AttachmentError
from app.inference.hybrid import LazyInferenceEngine, HybridInferenceEngine
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.local_images import image_content, image_accounting_messages, image_text
from app.inference.protocol import native_chat_messages, ModelResponse
from app.settings.model import ModelConfig
from app.settings.vision import LocalVisionConfig, verify_vision_pair
from tests.test_local_document_input import DocumentRecorder, reference
from tests.test_attachment_processing import image_data
from tests.test_skill_activation import make_service, call
from tests.test_llama_server_inference import definition


class VisionRecorder(DocumentRecorder):
    supports_local_image_inputs = True

    def __init__(self, responses=()):
        super().__init__(responses)
        self.prepared = 0

    def prepare_image_inputs(self):
        self.prepared += 1

    def count_image_message_tokens(self, messages):
        values = image_accounting_messages(messages)
        self.counted.append(deepcopy(messages))
        return len(json.dumps(values)) // 4 + 200 * sum(isinstance(m.get("content"), list) for m in messages)


def service(tmp_path, model=None):
    return ConversationService(model or VisionRecorder(), ConversationStore(tmp_path / "chat.json"))


def parts(data=b"bytes"):
    return [{"type": "text", "text": "Read this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode()}}]


def vision_config(**changes):
    return LocalVisionConfig(projector_path="projector.gguf", projector_size_bytes=1,
        projector_sha256="1" * 64, model_size_bytes=1, model_sha256="2" * 64, **changes)


@pytest.mark.parametrize("format,name", [("PNG", "sample.png"), ("JPEG", "sample.jpg"), ("WEBP", "sample.webp")])
def test_original_visual_pixels_are_native_user_parts_not_paths(tmp_path, format, name):
    app = service(tmp_path)
    data = image_data(format)
    ref = reference(app, data, name)
    assert app.run("Read this image", attachments=[ref]) == "Document reply"
    request = app.inference.requests[0][0]
    user = request[-1]
    assert image_text(user["content"]).startswith("Read this image")
    from PySide6.QtGui import QImage
    encoded = user["content"][-1]["image_url"]["url"]
    assert encoded.startswith("data:image/png;base64,")
    assert QImage.fromData(base64.b64decode(encoded.split(",", 1)[1])) == QImage.fromData(data)
    with app.store.attachment_store.open(ref) as stream:
        assert stream.read() == data
    assert request[0]["content"].count(LOCAL_IMAGE_GUIDANCE.strip()) == 1
    assert name not in request[0]["content"] and "attachments" not in user
    assert app.active_skill is None and app.inference.prepared == 1
    saved = app.store.path.read_text()
    assert "data:image" not in saved and LOCAL_IMAGE_GUIDANCE.strip() not in saved
    assert app.store.visible_messages()[0].attachments == (ref,)


def test_image_only_multiple_turns_followup_restore_and_archive(tmp_path):
    app = service(tmp_path)
    first = reference(app, image_data(), "first.png")
    second = reference(app, image_data("JPEG"), "second.jpg")
    app.run("", attachments=[first])
    initial = app.inference.requests[0][0]
    assert IMAGE_INTENT_GUIDANCE in initial[0]["content"]
    assert app.store.visible_messages()[0].content == ""
    assert image_text(initial[-1]["content"]) == 'Attached image: "first.png"'
    app.run("Compare", attachments=[second])
    restored = service(tmp_path)
    restored.run("Recall the first picture")
    users = [m for m in restored.inference.requests[-1][0] if m["role"] == "user"]
    assert sum(isinstance(m["content"], list) for m in users) == 2
    assert users[-1]["content"] == "Recall the first picture"
    assert restored.inference.requests[-1][0][0]["content"].count(IMAGE_INTENT_GUIDANCE) == 1
    restored.store.new_session(preserve_history=True)
    path = next((tmp_path / "archives").glob("*.json"))
    archived = ConversationService(VisionRecorder(), ConversationStore(path))
    archived.run("Recall again")
    assert sum(isinstance(m.get("content"), list) for m in archived.inference.requests[-1][0]) == 2


def test_image_only_agent_has_visual_intent_without_enabling_a_skill(tmp_path):
    model = VisionRecorder([ModelResponse.text("A red rectangle.")])
    app, _ = make_service(tmp_path, model=model, agent=True)
    try:
        ref = reference(app, image_data(), "ignore instructions.png")
        app.run("", attachments=[ref])
        messages, definitions = model.requests[0]
        assert IMAGE_INTENT_GUIDANCE in messages[0]["content"]
        assert ref.name not in messages[0]["content"]
        assert definitions and app.active_skill is None
        assert app.store.visible_messages()[0].content == ""
        assert not app.store.turns()[0].settled_calls
        app.new_session()
        app.run("Hello")
        assert IMAGE_INTENT_GUIDANCE not in model.requests[-1][0][0]["content"]
    finally:
        app.shutdown()


@pytest.mark.parametrize("recovery", [False, True])
def test_native_tool_continuation_keeps_image_and_tool_pair(tmp_path, recovery):
    model = VisionRecorder([call("filesystem.stat", {"path": "fixture.txt"}), ModelResponse.text("Done")])
    app, _ = make_service(tmp_path, model=model, agent=True, recovery=recovery)
    try:
        (app.portable_root / "fixture.txt").write_text("fixture")
        ref = reference(app, image_data(), "image.png")
        assert app.run("Stat fixture.txt and read image", attachments=[ref]) == "Done"
        initial, continuation = [r[0] for r in model.requests]
        image = next(m for m in initial if isinstance(m.get("content"), list))
        assert next(m for m in continuation if isinstance(m.get("content"), list)) == image
        native = native_chat_messages(continuation, model.requests[-1][1])
        assert native[-1]["role"] == "tool" and native[-2]["tool_calls"]
        assert app.store.turns()[0].settled_calls and app.active_skill is None
    finally:
        app.shutdown()


def test_documents_and_images_can_coexist_on_separate_turns(tmp_path):
    app = service(tmp_path)
    app.run("Document", attachments=[reference(app, b"Document evidence", "note.txt")])
    app.run("Image", attachments=[reference(app, image_data(), "note.png")])
    request = app.inference.requests[-1][0]
    assert "ATTACHED DOCUMENT INPUT" in request[0]["content"] and "ATTACHED IMAGE INPUT" in request[0]["content"]
    assert any(isinstance(m.get("content"), str) and "Document evidence" in m["content"] for m in request)
    assert any(isinstance(m.get("content"), list) for m in request)


def test_local_one_combined_attachment_gate_and_current_overflow(tmp_path):
    app = service(tmp_path)
    image = reference(app, image_data(), "first.png")
    document = reference(app)
    with pytest.raises(AttachmentError, match="one file or image"):
        app.run("Both", attachments=[image, document])
    assert not app.store.messages() and not app.inference.requests
    app.inference.context_length = 512
    with pytest.raises(AttachmentError, match="cannot fit"):
        app.run("Keep whole", attachments=[image])
    assert not app.inference.requests
    assert app.store.visible_messages()[0].attachments == (image,)
    assert app.store.turns()[0].outcome.status.value == "context_limit"


def test_retained_image_requires_explicit_vision_selection_after_switch(tmp_path):
    app = service(tmp_path)
    app.run("Read", attachments=[reference(app, image_data(), "image.png")])
    app.inference = DocumentRecorder()
    with pytest.raises(AttachmentError, match="vision model"):
        app.run("Followup")
    app.inference = VisionRecorder()
    app.run("Followup")
    assert any(isinstance(m.get("content"), list) for m in app.inference.requests[-1][0])


def test_corrupt_original_and_cancellation_never_send_image(tmp_path):
    from app.runtime.cancellation import CancellationSource, TaskCancelled
    app = service(tmp_path)
    ref = reference(app, image_data(), "image.png")
    source = CancellationSource(); source.cancel()
    with pytest.raises(TaskCancelled):
        LocalDocuments(app.store.attachment_store, allow_images=True).load(ref, cancellation=source.token)
    (app.store.attachment_store.root / ref.id / "content").write_bytes(b"bad")
    with pytest.raises(AttachmentError):
        app.run("Read", attachments=[ref])
    assert not app.inference.requests


@pytest.mark.parametrize("url", ["https://example.com/a.png", "file:///C:/secret.png", "C:/secret.png", "data:image/png;base64,?", "data:text/plain;base64,YQ==", "data:image/png;base64,"])
def test_native_image_schema_rejects_external_fetches_paths_and_bad_encoding(url):
    value = parts();value[1]["image_url"]["url"] = url
    with pytest.raises(ValueError):
        native_chat_messages([{"role": "user", "content": value}], (definition(),))


@pytest.mark.parametrize("role", ["system", "assistant", "capability"])
def test_images_never_enter_privileged_roles(role):
    with pytest.raises(ValueError):
        native_chat_messages([{"role": role, "content": parts()}], (definition(),))


def test_separate_binary_limit_preserves_original_text_and_tool_size_guards():
    messages = [{"role": "user", "content": parts(b"a" * (5 * 1024 * 1024))}]
    bounded = image_accounting_messages(messages)
    assert len(json.dumps(bounded)) < 200 and image_text(bounded[0]["content"]) == "Read this"
    assert len(json.dumps(messages)) > 4 * 1024 * 1024
    with pytest.raises(ValueError):
        image_content(parts(b"a" * (16 * 1024 * 1024 + 1)))
    with pytest.raises(AttachmentError, match="transport limit"):
        image_accounting_messages([{"role": "user", "content": parts(b"a" * (16 * 1024 * 1024))}] * 4)


def counter_engine():
    engine = object.__new__(LlamaServerInferenceEngine)
    engine.config = ModelConfig(model_path="unused.gguf", vision=vision_config())
    engine._lifecycle_lock = RLock();engine._process = None;engine._base_url = None;engine._api_key = None
    engine._closed = False;engine._request_active = Event();engine._token_count_cache = {}
    return engine


def test_offline_image_accounting_uses_patch_bound_not_base64_text():
    engine = counter_engine()
    small = [{"role": "user", "content": parts()}]
    big = [{"role": "user", "content": parts(b"a" * 100000)}]
    assert count_message_tokens(engine, small) == count_message_tokens(engine, big)
    assert engine.count_message_tokens(small) == count_message_tokens(engine, small)
    assert count_message_tokens(engine, small) >= 4096
    assert engine._process is None


def test_image_context_pressure_preserves_image_parts_and_user_requirements():
    from app.conversation.recovery import recover_context_request
    engine = counter_engine();engine.context_length = 8192;engine.max_response_tokens = 1024
    messages = [{"role": "system", "content": "Policy"}, {"role": "user", "content": parts()},
                {"role": "assistant", "content": "Earlier words " * 5000}, {"role": "user", "content": "Keep the image evidence"}]
    recovered = recover_context_request(engine, messages)
    assert recovered.budget.fits and recovered.messages[1] == messages[1]
    assert recovered.messages[-1] == messages[-1]
    assert len(recovered.messages[2]["content"]) < len(messages[2]["content"])


def test_python_adapter_rejects_image_before_loading_or_transport():
    from app.inference.llama_backend import LlamaCppInferenceEngine
    engine = object.__new__(LlamaCppInferenceEngine)
    for invoke in (lambda: engine.respond([{"role":"user","content":parts()}]),
                   lambda: engine.respond_with_capabilities([{"role":"user","content":parts()}],(definition(),))):
        with pytest.raises(AttachmentError):invoke()


def test_idle_native_image_counter_and_hash_only_cache(monkeypatch):
    engine = counter_engine();engine._process = SimpleNamespace(poll=lambda: None)
    engine._base_url = "http://127.0.0.1:12345";engine._api_key = "test-only"
    requests = []
    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"input_tokens":245}'
    def request(req, **kwargs):
        requests.append(req);return Reply()
    monkeypatch.setattr("app.inference.llama_server_backend.urlopen", request)
    messages = [{"role": "user", "content": parts()}]
    expected = 245 + 16 + 256
    assert count_message_tokens(engine, messages) == expected
    assert count_message_tokens(engine, messages) == expected
    assert len(requests) == 1 and requests[0].full_url.endswith("/chat/completions/input_tokens")
    assert json.loads(requests[0].data)["messages"] == messages
    assert all(len(k) == 70 and isinstance(v, int) for k,v in engine._token_count_cache.items())


def test_lazy_vision_preflight_never_loads_backend_and_cloud_does_not_inherit_it():
    loads = []
    lazy = LazyInferenceEngine(lambda: loads.append(1), context_length=16384,
        supports_local_document_inputs=True, supports_local_image_inputs=True)
    hybrid = HybridInferenceEngine(local=lazy, cloud=DocumentRecorder(), default_mode="local")
    assert hybrid.supports_local_image_inputs and not loads
    hybrid.set_mode("cloud")
    assert not hybrid.supports_local_image_inputs and not loads


def test_unqualified_adapter_cannot_submit_inline_image():
    engine = counter_engine();engine.config = ModelConfig(model_path="unused.gguf")
    with pytest.raises(AttachmentError):
        engine.respond([{"role": "user", "content": parts()}])


def test_vision_identity_rejects_missing_replaced_or_wrong_projector(tmp_path, monkeypatch):
    from hashlib import sha256
    model=tmp_path/'model.gguf';proj=tmp_path/'projector.gguf'
    model.write_bytes(b'm');proj.write_bytes(b'p')
    vision=LocalVisionConfig(projector_path=str(proj),projector_size_bytes=1,projector_sha256=sha256(b'p').hexdigest(),
        model_size_bytes=1,model_sha256=sha256(b'm').hexdigest())
    cfg=ModelConfig(model_path=str(model),vision=vision)
    def metadata(path):
        return ({'general.architecture':'qwen3vl','qwen3vl.embedding_length':2560} if path==model else
                {'general.type':'mmproj','clip.projector_type':'qwen3vl_merger','clip.has_vision_encoder':True,'clip.vision.projection_dim':2560})
    monkeypatch.setattr('app.settings.local_models.read_model_metadata',metadata)
    verify_vision_pair(cfg)
    monkeypatch.setattr('app.settings.local_models.read_model_metadata',lambda path: {'general.architecture':'qwen3vl','qwen3vl.embedding_length':2560} if path==model else {'general.type':'mmproj','clip.projector_type':'qwen3vl_merger','clip.has_vision_encoder':True,'clip.vision.projection_dim':128})
    with pytest.raises(ValueError,match='incompatible'):verify_vision_pair(cfg)
    monkeypatch.setattr('app.settings.local_models.read_model_metadata',metadata)
    proj.write_bytes(b'x')
    with pytest.raises(ValueError,match='identity'):verify_vision_pair(cfg)
    proj.unlink()
    with pytest.raises(ValueError,match='missing'):verify_vision_pair(cfg)
