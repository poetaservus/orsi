"""Cloud settings switch the actual runtime without losing the conversation."""
import json
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_errors import CloudInferenceError
from app.inference.engine import InferenceUnavailable
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.settings.openai_cloud import OpenAIModelCatalog, OpenAIModelProfile
from app.ui.main_window import MainWindow
from tests.test_openai_phase1 import config, engine_with_transport


def make_service(monkeypatch, tmp_path):
    small = OpenAIModelProfile(id="gpt-6.1-sol", context_length=8192,
                              max_input_tokens=7168, max_output_tokens=1024, reasoning_effort="medium")
    cloud, client, requests, _ = engine_with_transport(
        monkeypatch, engine_config=config(profiles=(OpenAIModelProfile(id="gpt-6-luna", temperature=0.1), small)))
    cloud.catalog = OpenAIModelCatalog(cloud.config, tmp_path / "selection.json")
    local = LazyInferenceEngine(lambda: None, context_length=16384, max_response_tokens=4096)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    service = ConversationService(hybrid, ConversationStore(tmp_path / "conversation.json"))
    return service, hybrid, cloud, client, requests


def test_service_switch_away_and_back_preserves_history_and_actual_wire_limits(monkeypatch, tmp_path):
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    before_config = cloud.config.model_dump_json()
    try:
        service.run("Synthetic first turn")
        before_history = service.store.messages()
        assert service.reported_context_tokens() is not None
        first_identity = hybrid.context_identity
        service.select_cloud_model("gpt-6.1-sol")
        assert service.reported_context_tokens() is None
        assert hybrid.context_identity != first_identity
        assert (hybrid.context_length, hybrid.max_response_tokens) == (8192, 1024)
        assert service.store.messages() == before_history
        assert OpenAIModelCatalog(cloud.config, tmp_path / "selection.json").current_id == "gpt-6.1-sol"
        service.run("Synthetic second turn")
        service.select_cloud_model("gpt-6-luna")
        assert (hybrid.context_length, hybrid.max_response_tokens) == (32768, 4096)
        service.run("Synthetic third turn")
        bodies = [json.loads(request.content) for request in requests]
        assert [body["model"] for body in bodies] == ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-luna"]
        assert bodies[1]["max_output_tokens"] == 1024 and "temperature" not in bodies[1]
        assert bodies[1]["reasoning"] == {"effort": "medium"}
        assert cloud.config.model_dump_json() == before_config
        assert len(service.store.messages()) == 6
    finally:
        service.shutdown()
    assert client.is_closed()


def test_switch_is_rejected_while_busy_closed_or_local(monkeypatch, tmp_path):
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    try:
        service._run_lock.acquire()
        try:
            with pytest.raises(RuntimeError, match="current response"):
                service.select_cloud_model("gpt-6.1-sol")
        finally:
            service._run_lock.release()
        assert cloud.active_model == "gpt-6-luna" and not requests
        hybrid.set_mode("local")
        with pytest.raises(InferenceUnavailable, match="Switch to Cloud"):
            service.select_cloud_model("gpt-6.1-sol")
        assert (hybrid.context_length, hybrid.max_response_tokens) == (16384, 4096)
    finally:
        service.shutdown()
    with pytest.raises(RuntimeError, match="closed"):
        service.select_cloud_model("gpt-6.1-sol")
    with pytest.raises(InferenceUnavailable, match="closed"):
        hybrid.select_cloud_model("gpt-6.1-sol")


def test_qt_selector_applies_reverts_and_disables_without_network(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    window = MainWindow(service, "SYNTHETIC-HOST", inference=hybrid)
    try:
        window.resize(760, 600)
        window.show()
        window.settings_button.click()
        app.processEvents()
        selector = window.cloud_model_selector
        assert selector.currentText() == "GPT-6 Luna" and selector.isEnabled()
        assert selector.isVisible() and window.local_model_selector.isHidden()
        assert window.settings_panel.rect().contains(window.skills_button.geometry())
        assert window.settings_panel.rect().contains(window.activity.geometry())
        assert window.settings_panel.geometry().bottom() < window.height()
        sol = selector.findData("gpt-6.1-sol")
        selector.setCurrentIndex(sol)
        assert cloud.active_model == "gpt-6.1-sol"
        assert window.context_window.size.text() == "8,192"
        assert "1,024 reply limit" in window.cloud_model_details.text()
        assert "Verification pending" in window.cloud_model_details.text()
        monkeypatch.setattr(cloud.catalog._store, "save", Mock(side_effect=OSError("private-storage-detail")))
        selector.setCurrentIndex(selector.findData("gpt-6-luna"))
        assert cloud.active_model == "gpt-6.1-sol" and selector.currentIndex() == sol
        assert window.context_window.size.text() == "8,192"
        window._set_busy(True)
        assert not selector.isEnabled()
        window._set_busy(False)
        assert selector.isEnabled()
        hybrid.set_mode("local")
        window._sync_cloud_model_selector()
        window._sync_local_model_selector()
        assert not selector.isEnabled()
        app.processEvents()
        assert selector.isHidden() and window.local_model_selector.isVisible()
        assert not requests
    finally:
        window.close()
        app.processEvents()
    assert not cloud.has_api_key


def test_shared_error_contract_keeps_legacy_import_compatible():
    from app.inference.cloud_backend import CloudInferenceError as LegacyError
    assert LegacyError is CloudInferenceError


def test_cloud_baseline_records_only_profile_settings(monkeypatch, tmp_path):
    from app.infrastructure.baseline import BaselineRecorder
    from app.settings.agent import AgentFeatureConfig
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    monkeypatch.setattr("app.infrastructure.baseline.detect_nvidia_memory_mib", lambda: None)
    monkeypatch.setattr("app.infrastructure.baseline.source_revision", lambda root: {})
    path = tmp_path / "baseline.json"
    hybrid.baseline_observer = BaselineRecorder(tmp_path, path, AgentFeatureConfig(), agent_available=False)
    try:
        service.select_cloud_model("gpt-6.1-sol")
        record = json.loads(path.read_text())
        assert record["cloud_model"] == {
            "id": "gpt-6.1-sol", "context_length": 8192, "max_input_tokens": 7168,
            "max_output_tokens": 1024, "reasoning_effort": "medium", "temperature": None, "qualified": False}
        assert record["active_limits"] == {"context_length": 8192, "max_response_tokens": 1024}
        assert "test-key-never-live" not in path.read_text()
        assert not requests
    finally:
        service.shutdown()
