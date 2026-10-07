import json

from tools import verify_image_generation as gate
from tests.test_cloud_attachment_input import native_sdk
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import config, engine_with_transport


def test_live_gate_reports_generation_restart_and_edit_without_secrets(native_sdk, tmp_path, monkeypatch):
    key_file = tmp_path / "authorized-key.txt"
    key_file.write_text("fake-first-line\nMUST-NOT-BE-USED", encoding="utf-8")
    calls = []
    def factory(configuration, *, api_key):
        assert api_key == "fake-first-line"
        assert configuration.image_generation.quality == "low"
        engine, _, bodies, _ = native_sdk(payloads=[image_payload()])
        calls.append(bodies)
        return engine
    monkeypatch.setattr(gate, "load_cloud_config", config)
    monkeypatch.setattr(gate, "OpenAIResponsesInferenceEngine", factory)
    report = gate.verify(tmp_path / "live", key_file)
    assert all(report[stage] == "passed" for stage in ("generation", "restart", "edit"))
    assert report["passed"] and report["transport_released"] and len(calls) == 2
    saved = (tmp_path / "live" / "summary.json").read_text()
    assert json.loads(saved) == report
    assert "fake-first-line" not in saved and "MUST-NOT" not in saved and "blue circle" not in saved


def test_live_gate_records_failed_access_and_skips_dependent_checks(tmp_path, monkeypatch):
    key_file = tmp_path / "authorized-key.txt"
    key_file.write_text("fake-first-line", encoding="utf-8")
    engine, _, requests, _ = engine_with_transport(monkeypatch,
        {"error": {"code": "model_not_found", "message": "PRIVATE PROVIDER BODY"}}, status=403)
    monkeypatch.setattr(gate, "load_cloud_config", config)
    monkeypatch.setattr(gate, "OpenAIResponsesInferenceEngine", lambda *args, **kwargs: engine)
    report = gate.verify(tmp_path / "live", key_file)
    assert report["generation"] == "failed" and report["error_category"] == "permission"
    assert report["edit"] == report["restart"] == "skipped_no_generated_source"
    assert not report["passed"] and report["transport_released"] and len(requests) == 1
    assert "PRIVATE" not in (tmp_path / "live" / "summary.json").read_text()
