"""The shipped default must remain usable with the shipped tool catalog."""
import shutil
import sys
from types import SimpleNamespace

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelResponse
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from tests.test_local_models import write_model


MODEL_ID = "Qwen314BQ4KM.gguf"


class AdmissionRecorder(InferenceEngine):
    def __init__(self, config):
        self.context_length = config.context_length
        self.max_response_tokens = config.max_tokens
        self.requests = []

    def respond(self, messages):
        return "Hello."

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append((messages, tuple(capabilities)))
        return ModelResponse.text("Hello.")


@pytest.mark.parametrize("memory,expected_output,expected_gpu", [
    (None, 1024, 0), ((16384, 100), 1024, 0),
    ((16384, 11500), 1024, 0), ((16384, 14000), 4096, -1),
    ((16384, 16000), 4096, -1),
])
def test_default_keeps_full_catalog_and_current_request_under_memory_pressure(
    tmp_path, monkeypatch, memory, expected_output, expected_gpu,
):
    models = tmp_path / "models"
    models.mkdir()
    write_model(models / MODEL_ID, "qwen3")
    manifest = tmp_path / "config" / "model.json"
    manifest.parent.mkdir()
    shutil.copyfile(PATHS.config / "model.json", manifest)
    before = manifest.read_bytes()
    catalog = LocalModelCatalog(models, manifest, load_model_config(), selection_path=tmp_path / "selection.json")
    target = catalog.profiles.get(MODEL_ID)
    monkeypatch.setattr(catalog, "identity", lambda model: {
        "model_id": MODEL_ID, "architecture": "qwen3", "size_bytes": target.size_bytes, "sha256": target.sha256})
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: memory)
    config = catalog.configuration(MODEL_ID)
    assert catalog.selected_id() == MODEL_ID
    assert (config.context_length, config.max_tokens, config.gpu_layers) == (16384, expected_output, expected_gpu)
    assert config.sampling_parameters() == target.configuration.sampling_parameters()
    assert config.cache_type == "q8_0"
    assert config.estimated_kv_bytes_per_token == catalog.models[0].kv_bytes_per_token * 17 // 32
    assert manifest.read_bytes() == before and not catalog.selection_path.exists()
    backend = AdmissionRecorder(config)
    flags = load_agent_feature_config().model_copy(update={"full_local_read_enabled": False})
    runtime = build_agent_runtime(backend, config=flags, portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(backend, ConversationStore(tmp_path / "conversation.json"),
                                  agent_runtime=runtime, portable_root=tmp_path, automatic_skills_enabled=False)
    try:
        assert service.run("hey") == "Hello."
        assert service._turn_result.status.value == "completed"
        messages, tools = backend.requests[-1]
        assert len(tools) == 12
        assert messages[-1] == {"role": "user", "content": "hey"}
        assert service.context_budget().fits
    finally:
        service.shutdown()


@pytest.mark.parametrize("cache_type", ["f16", "q8_0"])
def test_chat_only_backend_uses_the_cache_format_estimated_by_the_guard(tmp_path, monkeypatch, cache_type):
    from app.inference.llama_backend import LlamaCppInferenceEngine
    from app.settings.model import ModelConfig
    model = tmp_path / "model.gguf"
    model.touch()
    calls = []
    def load(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace()
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=load,
        llama_cpp=SimpleNamespace(llama_supports_gpu_offload=lambda: True, GGML_TYPE_Q8_0=8)))
    monkeypatch.setattr("app.inference.llama_backend._configure_portable_cuda_dlls", lambda: None)
    monkeypatch.setattr("app.inference.llama_backend._probe_native_context", lambda *args: 16384)
    config = ModelConfig(model_path=str(model), context_length=16384, maximum_context_length=16384,
                         cache_type=cache_type, gpu_layers=0)
    engine = LlamaCppInferenceEngine(config)
    assert engine.context_length == 16384
    expected = {"model_path": str(model), "n_ctx": 16384, "n_gpu_layers": 0, "verbose": False}
    if cache_type == "q8_0":
        expected.update(type_k=8, type_v=8, flash_attn=True)
    assert calls == [expected]
