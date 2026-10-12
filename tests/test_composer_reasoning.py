"""Composer choices reach actual request construction and remain per-model preferences."""
import json
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from app.inference.engine import InferenceUnavailable
from app.settings.openai_cloud import OpenAIModelCatalog
from app.ui.main_window import MainWindow
from tests.test_openai_selection import make_service


def test_reasoning_switch_reaches_wire_and_restores_sampling_and_history(monkeypatch, tmp_path):
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    before = cloud.config.model_dump_json()
    try:
        service.run("Synthetic baseline")
        history = service.store.messages()
        identity = hybrid.context_identity
        service.select_cloud_reasoning("medium")
        assert service.store.messages() == history
        assert service.reported_context_tokens() is None
        assert hybrid.context_identity != identity
        assert (hybrid.context_length, hybrid.max_response_tokens) == (32768, 4096)
        service.run("Synthetic reasoning turn")
        service.select_cloud_model("gpt-6.1-sol")
        service.select_cloud_reasoning("high")
        service.run("Synthetic alternate model")
        service.select_cloud_model("gpt-6-luna")
        assert cloud.catalog.current_profile.reasoning_effort == "medium"
        service.select_cloud_reasoning("none")
        service.run("Synthetic restored baseline")
        bodies = [json.loads(request.content) for request in requests]
        assert [body['reasoning']['effort'] for body in bodies] == ['none', 'medium', 'high', 'none']
        assert 'temperature' not in bodies[1] and 'temperature' not in bodies[2]
        assert bodies[0]['temperature'] == bodies[3]['temperature'] == .1
        assert [body['max_output_tokens'] for body in bodies] == [4096, 4096, 1024, 4096]
        assert cloud.config.model_dump_json() == before
        reloaded = OpenAIModelCatalog(cloud.config, tmp_path / 'selection.json')
        assert reloaded.current_profile.reasoning_effort == 'none'
        reloaded.select('gpt-6.1-sol')
        assert reloaded.current_profile.reasoning_effort == 'high'
    finally:
        service.shutdown()
    assert client.is_closed() and cloud._runner is None


def test_reasoning_selection_is_atomic_and_rejects_busy_local_closed(monkeypatch, tmp_path):
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    try:
        service._run_lock.acquire()
        try:
            with pytest.raises(RuntimeError, match='current response'):
                service.select_cloud_reasoning('medium')
        finally:
            service._run_lock.release()
        with pytest.raises(ValueError):
            service.select_cloud_reasoning('unsupported')
        monkeypatch.setattr(cloud.catalog._reasoning_store, 'save', Mock(side_effect=OSError('private-storage')))
        with pytest.raises(OSError):
            service.select_cloud_reasoning('medium')
        assert cloud.catalog.current_profile.reasoning_effort == 'none'
        hybrid.set_mode('local')
        with pytest.raises(InferenceUnavailable, match='Switch to Cloud'):
            service.select_cloud_reasoning('medium')
        assert not requests
    finally:
        service.shutdown()
    with pytest.raises(RuntimeError, match='closed'):
        service.select_cloud_reasoning('medium')


def test_composer_changes_model_and_reasoning_for_next_api_request(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    service, hybrid, cloud, client, requests = make_service(monkeypatch, tmp_path)
    window = MainWindow(service, 'SYNTHETIC-HOST', inference=hybrid)
    try:
        window.resize(760, 600)
        window.show()
        app.processEvents()
        models, reasoning = window.composer_model_selector, window.reasoning_selector
        assert models.currentText() == 'GPT-6 Luna'
        assert reasoning.currentData() == 'none'
        assert not window.microphone_placeholder.isEnabled()
        reasoning.setCurrentIndex(reasoning.findData('medium'))
        service.run('Synthetic composer request')
        assert json.loads(requests[-1].content)['reasoning'] == {'effort': 'medium'}
        models.setCurrentIndex(models.findData('cloud:gpt-6.1-sol'))
        assert cloud.active_model == 'gpt-6.1-sol'
        assert reasoning.findData('none') == -1
        reasoning.setCurrentIndex(reasoning.findData('xhigh'))
        service.run('Synthetic composer alternate model')
        body = json.loads(requests[-1].content)
        assert body['model'] == 'gpt-6.1-sol' and body['reasoning'] == {'effort': 'xhigh'}
        models.setCurrentIndex(models.findData('cloud:gpt-6-luna'))
        assert reasoning.currentData() == 'medium'
        window._set_busy(True)
        assert not models.isEnabled() and not reasoning.isEnabled()
        window._set_busy(False)
        assert models.isEnabled() and reasoning.isEnabled()
        for widget in (models, reasoning, window.microphone_placeholder, window.action_slot):
            rectangle = QRect(widget.mapTo(window.composer, QPoint()), widget.size())
            assert window.composer.rect().contains(rectangle)
            assert rectangle.top() > window.input.mapTo(window.composer, QPoint()).y()
        monkeypatch.setattr(cloud.catalog._reasoning_store, 'save', Mock(side_effect=OSError('private-storage')))
        reasoning.setCurrentIndex(reasoning.findData('high'))
        assert reasoning.currentData() == 'medium'
        assert 'private-storage' not in window.chat._messages[-1]._content
        hybrid.set_mode('local')
        window._sync_cloud_model_selector()
        assert not reasoning.isEnabled()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize('saved', [
    {'schema_version': 1, 'efforts': {'gpt-6.1-sol': 'none'}},
    {'schema_version': 1, 'efforts': {'unknown-model': 'high'}},
])
def test_invalid_saved_reasoning_is_rejected_without_rewriting(tmp_path, saved):
    from tests.test_openai_phase1 import config
    path = tmp_path / 'cloud_reasoning_selection_v1.json'
    original = json.dumps(saved)
    path.write_text(original)
    with pytest.raises(ValueError):
        OpenAIModelCatalog(config(), tmp_path / 'selection.json')
    assert path.read_text() == original


def test_selected_luna_reasoning_applies_to_native_tools(monkeypatch):
    from tests.test_openai_tools import scripted_sdk, response, function, capability_definition
    from app.inference.protocol import ModelResponseKind
    payload = response(output=[{'type': 'reasoning', 'id': 'rs_1', 'summary': [],
                               'encrypted_content': 'synthetic-opaque'}, function()])
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [payload])
    try:
        engine.select_reasoning_effort('high')
        result = engine.respond_with_capabilities([{'role': 'user', 'content': 'Synthetic inspection'}], (capability_definition(),))
        assert result.kind == ModelResponseKind.CAPABILITY_CALLS
        assert bodies[0]['model'] == 'gpt-6-luna'
        assert bodies[0]['reasoning'] == {'effort': 'high'}
        assert 'temperature' not in bodies[0]
        assert result.openai_response.items() == payload['output']
    finally:
        engine.close()
