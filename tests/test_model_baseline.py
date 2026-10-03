import hashlib
import json
from types import SimpleNamespace

import pytest

from app.infrastructure.baseline import BaselineRecorder, source_revision
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.settings.agent import AgentFeatureConfig
from app.settings.local_models import LocalModelCatalog
from app.settings.model import ModelConfig
from app.settings.model_profiles import LocalModelProfile, LocalModelProfiles
from app.state.storage import JsonStore
from tests.test_local_models import write_model, Backend


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    old = write_model(models / "old.gguf", "qwen3")
    new = write_model(models / "new.gguf", "qwen2")
    config = ModelConfig(model_path=str(old), context_length=16384,
                         maximum_context_length=16384, cpu_context_length=4096, max_tokens=4096)
    entries = tuple(LocalModelProfile(model_id=p.name, architecture=a, qualification="accepted",
        size_bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        configuration=config.model_copy(update={"model_path": str(p), "temperature": temp}))
        for p, a, temp in [(old, "qwen3", 0.1), (new, "qwen2", 0.3)])
    path = tmp_path / "config/model.json"
    JsonStore(path).save(LocalModelProfiles(default_model_id=old.name, profiles=entries).model_dump())
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 15000))
    return LocalModelCatalog(models, path, config)


def test_roundtrip_restores_exact_target_and_sampling_without_mutating_manifest(profiles):
    before = profiles.config_path.read_bytes()
    original = profiles.configuration("old.gguf")
    events = []
    local = LazyInferenceEngine(lambda: Backend("old", events), context_length=original.context_length,
                                max_response_tokens=original.max_tokens)
    def factory(config):
        engine = Backend(config.model_path, events)
        engine.context_length, engine.max_response_tokens = config.context_length, config.max_tokens
        return engine
    inference = HybridInferenceEngine(local=local, cloud=None, model_catalog=profiles, local_factory=factory)
    try:
        local.respond([])
        inference.select_local_model("new.gguf")
        assert profiles.current_config.temperature == 0.3
        inference.select_local_model("old.gguf")
        assert profiles.current_config == original
        assert inference.context_length == 16384 and inference.max_response_tokens == 4096
        assert profiles.config_path.read_bytes() == before
        assert profiles.selected_id() == "old.gguf"
    finally:
        inference.close()


def test_memory_reduction_preserves_target_and_does_not_halve_output_automatically(profiles, monkeypatch):
    # Metadata gives 147456 B/token; this memory permits 8K but not 16K.
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 2900))
    constrained = profiles.configuration("old.gguf")
    assert constrained.context_length == 8192 and constrained.max_tokens == 4096
    assert profiles.profiles.get("old.gguf").configuration.context_length == 16384
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 15000))
    assert profiles.configuration("old.gguf").context_length == 16384


@pytest.mark.parametrize("memory", [None, (16384, 100)])
def test_cpu_fallback_never_attempts_gpu_when_minimum_context_cannot_fit(profiles, monkeypatch, memory):
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: memory)
    config = profiles.configuration("old.gguf")
    assert (config.gpu_layers, config.context_length, config.max_tokens) == (0, 4096, 1024)


def test_quantized_cache_guard_counts_scales_and_matches_allocation_diagnostic(profiles, monkeypatch):
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 2900))
    f16 = profiles.configuration("old.gguf")
    assert f16.context_length == 8192
    old = profiles.profiles.get("old.gguf")
    q8 = old.model_copy(update={"configuration": old.configuration.model_copy(update={"cache_type": "q8_0"})})
    profiles.profiles = profiles.profiles.model_copy(update={"profiles": (q8, profiles.profiles.get("new.gguf"))})
    effective = profiles.configuration("old.gguf")
    assert (effective.context_length, effective.max_tokens, effective.gpu_layers) == (16384, 4096, -1)
    assert effective.estimated_kv_bytes_per_token == 78336  # 147456 FP16 bytes * 34/64
    record = profiles._resolutions["old.gguf"]
    assert record["memory_guard"]["estimated_kv_bytes_per_token"] == 78336
    expected = (record["size_bytes"] / 1048576 * effective.context_model_size_multiplier
                + effective.context_fixed_reserve_mib + 16384 * 78336 / 1048576)
    assert record["estimated_allocation_mib"] == round(expected, 2)
    assert effective.sampling_parameters() == f16.sampling_parameters()


def test_replaced_weights_rejected_even_when_metadata_is_unchanged(profiles):
    old = profiles.models_directory / "old.gguf"
    data = old.read_bytes()
    old.write_bytes(data + b"changed tensor data")
    with pytest.raises(ValueError, match="does not match"):
        profiles.configuration("old.gguf")
    assert not profiles.selection_path.exists()


def test_invalid_runtime_selection_falls_back_without_mutating_settings(profiles):
    before = profiles.config_path.read_bytes()
    profiles.selection_path.parent.mkdir(parents=True)
    profiles.selection_path.write_text('{"schema_version":1,"model_id":"../../secret"}')
    assert profiles.selected_id() == "old.gguf"
    profiles.selection_path.write_text("not json")
    assert profiles.selected_id() == "old.gguf"
    assert profiles.config_path.read_bytes() == before


def test_snapshot_records_effective_flags_limits_identity_and_never_content(profiles, tmp_path, monkeypatch):
    monkeypatch.setattr("app.infrastructure.baseline.detect_nvidia_memory_mib", lambda: (16384, 12000))
    monkeypatch.setattr("app.infrastructure.baseline.source_revision", lambda root: {
        "commit": "a" * 40, "tracked_changes": False})
    config = profiles.configuration("old.gguf")
    profiles.current_config = config
    local = LazyInferenceEngine(lambda: Backend("secret conversation", []),
        context_length=config.context_length, max_response_tokens=config.max_tokens)
    inference = HybridInferenceEngine(local=local, cloud=None, model_catalog=profiles)
    local.respond([{"role": "user", "content": "private file contents API_KEY=secret"}])
    output = tmp_path / "diagnostic.json"
    recorder = BaselineRecorder(tmp_path, output, AgentFeatureConfig(filesystem_stat_enabled=True),
                                agent_available=True)
    try:
        recorder(inference)
        data = json.loads(output.read_text())
        assert data["revision"]["commit"] == "a" * 40
        assert data["effective_flags"]["filesystem_stat_enabled"] is True
        assert data["effective_flags"]["full_local_read_enabled"] is False
        assert data["local_backend_loaded"] is True
        assert data["local_model"]["sha256"] == profiles.profiles.get("old.gguf").sha256
        assert data["active_limits"] == {"context_length": 16384, "max_response_tokens": 4096}
        text = output.read_text()
        assert not any(value in text for value in ["secret", "private", str(tmp_path), "API_KEY"])
        monkeypatch.setattr("app.infrastructure.baseline.JsonStore.save", lambda *args: (_ for _ in ()).throw(OSError()))
        recorder(inference)  # A failed diagnostic write is non-fatal.
    finally:
        inference.close()


def test_reload_rechecks_memory_without_overwriting_the_profile(profiles, monkeypatch):
    initial = profiles.configuration("old.gguf")
    def factory(config):
        backend = Backend("ready", [])
        backend.config = config
        backend.context_length, backend.max_response_tokens = config.context_length, config.max_tokens
        return backend
    inference = HybridInferenceEngine(local=LazyInferenceEngine(lambda: factory(initial),
        context_length=16384, max_response_tokens=4096), cloud=None, model_catalog=profiles,
        local_factory=factory)
    try:
        inference.select_local_model("new.gguf")
        assert inference.context_length == 16384
        inference.local.unload()
        monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 2900))
        assert inference.respond([]) == "ready"
        assert inference.context_length == profiles.current_config.context_length == 8192
        assert inference.max_response_tokens == 4096
        assert profiles.profiles.get("new.gguf").configuration.context_length == 16384
    finally:
        inference.close()


def test_startup_restores_selection_and_rechecks_memory_at_delayed_load(profiles, tmp_path, monkeypatch):
    import app.startup as startup
    selected = profiles.configuration("new.gguf")
    profiles.save(selected)
    paths = SimpleNamespace(root=tmp_path, models=profiles.models_directory,
        config=profiles.config_path.parent, state=tmp_path / "state")
    server = tmp_path / "runtime/llama-server/llama-server.exe"
    server.parent.mkdir(parents=True)
    server.touch()
    monkeypatch.setattr(startup, "PATHS", paths)
    monkeypatch.setattr(startup, "load_model_config", lambda: profiles._legacy_config)
    monkeypatch.setattr(startup, "load_cloud_config", lambda: (_ for _ in ()).throw(ValueError("disabled")))
    monkeypatch.setattr("app.infrastructure.baseline.detect_nvidia_memory_mib", lambda: (16384, 2900))
    created = []
    def backend(config):
        created.append(config)
        result = Backend("ready", [])
        result.config = config
        result.context_length, result.max_response_tokens = config.context_length, config.max_tokens
        return result
    monkeypatch.setattr(startup, "LlamaServerInferenceEngine", backend)
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, full_local_read_enabled=True)
    before = profiles.config_path.read_bytes()
    service, _, error, inference = startup.build_application(agent_config_override=flags)
    try:
        assert error is None and inference.model_catalog.current_id == "new.gguf"
        assert not created and inference.context_length == 16384
        snapshot = paths.state / "diagnostics/effective_baseline_v1.json"
        data = json.loads(snapshot.read_text())
        assert data["effective_flags"]["full_local_read_enabled"] is False
        assert data["local_backend_loaded"] is False
        monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 2900))
        assert inference.respond([]) == "ready"
        assert created[0].context_length == inference.context_length == 8192
        data = json.loads(snapshot.read_text())
        assert data["local_model"]["model_id"] == "new.gguf"
        assert data["local_model"]["target"]["context_length"] == 16384
        assert data["active_limits"]["context_length"] == 8192
        assert data["local_backend_loaded"] is True
        assert profiles.config_path.read_bytes() == before
    finally:
        service.shutdown()


def test_source_revision_identifies_untracked_changes_without_persisting_paths(tmp_path, monkeypatch):
    def run(command, **kwargs):
        output = "b" * 40 + "\n" if command[1] == "rev-parse" else " M app/changed.py\n?? private-name.py\n"
        return SimpleNamespace(returncode=0, stdout=output)
    monkeypatch.setattr("app.infrastructure.baseline.subprocess.run", run)
    assert source_revision(tmp_path) == {"commit": "b" * 40, "tracked_changes": True,
                                         "untracked_files": True}
