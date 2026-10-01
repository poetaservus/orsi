from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import struct
from threading import Event
from time import monotonic
from types import SimpleNamespace

import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.settings.local_models import LocalModelCatalog, inspect_model, read_model_metadata
from app.settings.model import ModelConfig


def write_model(path, architecture="qwen3vl", *, tools=True):
    def string(text):
        encoded = text.encode()
        return struct.pack("<Q", len(encoded)) + encoded

    values = {
        "general.architecture": architecture,
        "general.name": f"Test {architecture}",
        "general.file_type": 15,
        f"{architecture}.context_length": 262144,
        f"{architecture}.block_count": 36,
        f"{architecture}.embedding_length": 2560,
        f"{architecture}.attention.head_count": 32,
        f"{architecture}.attention.head_count_kv": 8,
        f"{architecture}.attention.key_length": 128,
        f"{architecture}.attention.value_length": 128,
        "tokenizer.chat_template": "tools tool_call" if tools else "plain chat",
    }
    payload = b"GGUF" + struct.pack("<IQQ", 3, 0, len(values))
    for key, value in values.items():
        payload += string(key)
        if isinstance(value, str):
            payload += struct.pack("<I", 8) + string(value)
        else:
            payload += struct.pack("<II", 4, value)
    path.write_bytes(payload)
    return path


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    directory = tmp_path / "models"
    directory.mkdir()
    old = write_model(directory / "old.gguf", "qwen3")
    write_model(directory / "new.gguf")
    current = ModelConfig(model_path=str(old), context_length=8192, max_tokens=2048)
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: (16384, 15000))
    config_path = tmp_path / "config" / "model.json"
    config_path.parent.mkdir()
    config_path.write_text(current.model_dump_json())
    result = LocalModelCatalog(directory, config_path, current)
    result.save(current)
    return result


def test_discovery_uses_metadata_and_skips_unsupported_or_incomplete_files(tmp_path):
    model = write_model(tmp_path / "renamed.gguf")
    write_model(tmp_path / "projector.gguf", "clip")
    write_model(tmp_path / "no-tools.gguf", tools=False)
    (tmp_path / "partial.gguf").write_bytes(b"GGUF")
    catalog = LocalModelCatalog(tmp_path, tmp_path / "config.json", ModelConfig(model_path=str(model)))
    assert [item.id for item in catalog.models] == ["renamed.gguf"]
    assert len(catalog.unavailable) == 3
    assert catalog.models[0].kv_bytes_per_token == 147456
    assert catalog.models[0].text_only


def test_metadata_parser_rejects_oversized_values_without_loading_tensors(tmp_path):
    model = tmp_path / "bad.gguf"
    model.write_bytes(b"GGUF" + struct.pack("<IQQQ", 3, 0, 1, 2**40))
    with pytest.raises(ValueError, match="too large"):
        read_model_metadata(model)


def test_profile_replaces_all_previous_settings_and_respects_cpu_fallback(catalog, monkeypatch):
    catalog.current_config = catalog.current_config.model_copy(update={
        "temperature": 1.8, "top_p": 0.2, "top_k": 2, "min_p": 0.9,
        "repeat_penalty": 1.9, "presence_penalty": 2.0, "cache_type": "q8_0",
        "gpu_layers": 7, "context_length": 65536, "max_tokens": 16384,
    })
    config = catalog.configuration("new.gguf")
    assert config.context_length == 16384 and config.max_tokens == 4096
    assert config.temperature == 0.2 and config.top_p == 0.9 and config.top_k == 40
    assert config.min_p == 0.0 and config.repeat_penalty == 1.0 and config.presence_penalty == 0.0
    assert config.cache_type == "f16" and config.gpu_layers == -1
    assert config.estimated_kv_bytes_per_token == 147456
    monkeypatch.setattr("app.settings.local_models.detect_nvidia_memory_mib", lambda: None)
    cpu = catalog.configuration("new.gguf")
    assert cpu.gpu_layers == 0 and cpu.context_length == 4096 and cpu.max_tokens == 1024


def test_selection_persists_only_identity_and_preserves_profile_for_restart(catalog):
    before = catalog.config_path.read_bytes()
    config = catalog.configuration("new.gguf")
    catalog.save(config)
    assert catalog.config_path.read_bytes() == before
    assert json.loads(catalog.selection_path.read_text()) == {"schema_version": 1, "model_id": "new.gguf"}
    restarted = LocalModelCatalog(catalog.models_directory, catalog.config_path, catalog._legacy_config)
    restarted.current_config = restarted.configuration(restarted.selected_id())
    assert restarted.current_id == "new.gguf"
    assert restarted.current_config == config


class Backend(InferenceEngine):
    def __init__(self, name, events, prepare=None):
        self.name, self.events, self.on_prepare = name, events, prepare

    def prepare(self):
        self.events.append(f"prepare:{self.name}")
        if self.on_prepare:
            self.on_prepare()

    def respond(self, messages):
        return self.name

    def close(self):
        self.events.append(f"close:{self.name}")


def hybrid(catalog, prepare=None):
    events = []
    previous = LazyInferenceEngine(lambda: Backend("old", events), context_length=8192,
                                   max_response_tokens=2048)
    previous.respond([])

    def factory(config):
        events.append("create:new")
        result = Backend("new", events, prepare)
        result.context_length, result.max_response_tokens = config.context_length, config.max_tokens
        return result

    return HybridInferenceEngine(local=previous, cloud=None, model_catalog=catalog,
                                 local_factory=factory), events


def test_switch_releases_old_model_before_creating_new_and_keeps_history(catalog, tmp_path):
    inference, events = hybrid(catalog)
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    service.store.append("user", "Keep this conversation")
    history = service.store.messages()
    try:
        service.select_local_model("new.gguf")
        assert events == ["close:old", "create:new", "prepare:new"]
        assert inference.context_length == 16384 and inference.max_response_tokens == 4096
        assert inference.respond([]) == "new"
        assert catalog.current_id == "new.gguf"
        assert service.store.messages() == history
        service.select_local_model("new.gguf")
        assert len(events) == 3
    finally:
        service.shutdown()
    assert events[-1] == "close:new"


@pytest.mark.parametrize("failure", ["load", "save", "missing"])
def test_failed_switch_releases_candidate_and_preserves_previous_profile(catalog, monkeypatch, failure):
    def fail():
        raise OSError("test failure")

    inference, events = hybrid(catalog, fail if failure == "load" else None)
    before = catalog.config_path.read_bytes()
    selection_before = catalog.selection_path.read_bytes()
    if failure == "save":
        monkeypatch.setattr(catalog, "save", lambda config: fail())
    elif failure == "missing":
        (catalog.models_directory / "new.gguf").unlink()
    try:
        with pytest.raises(OSError):
            inference.select_local_model("new.gguf")
        assert catalog.current_id == "old.gguf"
        assert catalog.config_path.read_bytes() == before
        assert catalog.selection_path.read_bytes() == selection_before
        assert inference._pending_local is None
        assert inference.context_length == 8192
        assert inference.respond([]) == "old"
        if failure != "missing":
            assert "close:new" in events
    finally:
        inference.close()


def test_close_during_model_preparation_does_not_save_or_resurrect_backend(catalog):
    started, release = Event(), Event()

    def prepare():
        started.set()
        assert release.wait(3)

    inference, events = hybrid(catalog, prepare)
    before = catalog.config_path.read_bytes()
    with ThreadPoolExecutor(1) as pool:
        switching = pool.submit(inference.select_local_model, "new.gguf")
        try:
            assert started.wait(3)
            inference.close()
        finally:
            release.set()
        with pytest.raises(InferenceUnavailable, match="closed"):
            switching.result(3)
    assert catalog.config_path.read_bytes() == before
    assert events.count("close:new") == 1


def test_busy_conversation_cannot_switch_models(catalog, tmp_path):
    inference, events = hybrid(catalog)
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    service._run_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="current response"):
            service.select_local_model("new.gguf")
        assert not events
    finally:
        service._run_lock.release()
        service.shutdown()


def test_settings_switch_runs_in_worker_and_updates_profile_display(catalog, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    inference, events = hybrid(catalog)
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "TEST", inference=inference)
    window.show()
    try:
        selector = window.local_model_selector
        assert selector.currentData() == "old.gguf"
        assert selector.itemText(selector.findData("new.gguf")).startswith("Experimental ·")
        selector.setCurrentIndex(selector.findData("new.gguf"))
        assert window.thread is not None
        assert not selector.isEnabled()
        deadline = monotonic() + 5
        while window.thread is not None and monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert window.thread is None
        assert selector.isEnabled() and selector.currentData() == "new.gguf"
        assert "16,384 context" in window.local_model_details.text()
        assert "Experimental: file editing may fail" in window.local_model_details.text()
        assert window.context_window.bar.maximum() == 16384
    finally:
        window.close()
