"""Qualification gates reject missing evidence; deterministic tests never promote models."""
from copy import deepcopy
from pathlib import Path

import pytest

from app.infrastructure import openai_qualification as gate
from app.infrastructure import qualification as q


def evidence():
    profiles = gate.profiles(Path.cwd())
    current = {key: "fixture" for key in ("revision", "source_sha256", "suite_sha256", "cloud_manifest_sha256",
        "model_manifest_sha256", "packaging_manifest_sha256", "runtime_sha256", "python_version", "sdk_version")}
    current.update(clean=True, effective_flags={"context_recovery_enabled": False})
    report = {"schema_version": 1, "measurement_kind": "live_openai", "identity": deepcopy(current),
        "finished": True, "all_owned_resources_released": True, "packaging": {key: True for key in
            ("passed", "sdk_transport_fixture_passed", "cloud_native_tools_startup", "ui_startup_passed")},
        "regression": {"passed": 100, "failed": 0, "errors": 0, "exit_code": 0}, "cells": []}
    for profile in profiles:
        for workflow in gate.WORKFLOWS:
            for repetition in range(q.REPETITIONS):
                report["cells"].append({"model_id": profile["id"], "workflow": workflow, "repetition": repetition,
                    "profile": deepcopy(profile), "status": "passed", "terminal_verified": True, "limits_verified": True,
                    "cloud_privacy_acceptances": 2 if workflow == "restart" else 1,
                    "bytes_verified": True, "ui_released": True, "session_preserved": True, "previous_servers_exited": True,
                    "terminal_outcomes": [{"status": s, "ended": True} for s in gate.TERMINALS[workflow]],
                    "request_cost": {"generation_requests": 2, "usage_coverage": 2, "observed_total_tokens": 100}})
    return report, current, profiles


def test_complete_live_matrix_and_packaging_are_required():
    report, current, profiles = evidence()
    assert len(report["cells"]) == 60
    assert not gate.qualification_errors(report, current, profiles)


@pytest.mark.parametrize("defect", ["legacy", "deterministic", "dirty", "uncommitted_evidence", "revision", "sdk", "profiles",
    "packaging_source", "prompts", "limits", "missing", "duplicate", "skip", "access", "terminal", "usage", "resources",
    "regression", "package", "bytes", "cancel_controls", "restart", "switch_leak", "recovery", "consent"])
def test_incomplete_or_stale_evidence_never_qualifies(defect):
    report, current, profiles = evidence()
    cell = report["cells"][0]
    if defect == "legacy": report["measurement_kind"] = "live"
    elif defect == "deterministic": report["measurement_kind"] = "mock"
    elif defect == "dirty": current["clean"] = False
    elif defect == "uncommitted_evidence": report["identity"]["clean"] = False
    elif defect in {"revision", "sdk", "profiles", "packaging_source", "prompts"}:
        current[{"revision": "revision", "sdk": "sdk_version", "profiles": "cloud_manifest_sha256",
            "packaging_source": "packaging_manifest_sha256", "prompts": "suite_sha256"}[defect]] = "changed"
    elif defect == "limits": cell["profile"]["max_output_tokens"] = 1024
    elif defect == "missing": report["cells"].pop()
    elif defect == "duplicate": report["cells"].append(deepcopy(cell))
    elif defect == "skip": cell["status"] = "skipped"
    elif defect == "access": cell["status"] = "blocked"
    elif defect == "terminal": cell["terminal_outcomes"] = []
    elif defect == "usage": cell["request_cost"]["usage_coverage"] = 1
    elif defect == "resources": report["all_owned_resources_released"] = False
    elif defect == "regression": report["regression"]["failed"] = 1
    elif defect == "package": report["packaging"]["passed"] = False
    elif defect == "bytes": next(c for c in report["cells"] if c["workflow"] == "reading")["bytes_verified"] = False
    elif defect == "cancel_controls": next(c for c in report["cells"] if c["workflow"] == "cancel_then_task")["ui_released"] = False
    elif defect == "restart": next(c for c in report["cells"] if c["workflow"] == "restart")["session_preserved"] = False
    elif defect == "switch_leak": next(c for c in report["cells"] if c["workflow"] == "mode_round_trip")["previous_servers_exited"] = False
    elif defect == "recovery": current["effective_flags"]["context_recovery_enabled"] = True
    elif defect == "consent": cell["cloud_privacy_acceptances"] = 0
    assert gate.qualification_errors(report, current, profiles)


def test_offline_sdk_runtime_verification_uses_no_real_credentials(monkeypatch):
    from tools.verify_openai_runtime import verify
    monkeypatch.setenv("OPENAI_API_KEY", "never-export-this")
    report = verify(Path.cwd())
    assert report["passed"] and report["sdk_transport_fixture_passed"]
    assert "never-export-this" not in str(report)


@pytest.mark.parametrize("model_present", [False, True])
def test_cloud_tools_start_without_local_server_or_model(tmp_path, monkeypatch, model_present):
    import app.startup as startup
    from app.settings.paths import RuntimePaths
    from app.settings.agent import AgentFeatureConfig
    from app.runtime.skills import SkillRegistry
    from app.settings.openai_cloud import OpenAICloudConfig
    paths = RuntimePaths(tmp_path, tmp_path / "config", tmp_path / "models", tmp_path / "state")
    paths.ensure_directories()
    config = OpenAICloudConfig.model_validate(__import__("json").loads((Path.cwd() / "config/cloud.json").read_text()))
    monkeypatch.setattr(startup, "PATHS", paths)
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config)
    if model_present:
        from types import SimpleNamespace
        model_path = tmp_path / "models/fixture.gguf"
        model_path.touch()
        monkeypatch.setattr(startup, "load_model_config", lambda: SimpleNamespace(resolved_model_path=model_path,
            maximum_context_length=16384, max_tokens=4096,
            select_context=lambda **kwargs: SimpleNamespace(length=16384)))
        monkeypatch.setattr(startup, "LocalModelCatalog", lambda *args: SimpleNamespace(profiles=None, models=[], current_id="fixture.gguf"))
    registry = SkillRegistry(global_root=tmp_path / "skills")
    service, _, error, inference = startup.build_application(
        agent_config_override=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True),
        skill_registry_override=registry)
    try:
        assert service is not None and error is None
        assert inference.mode == "cloud" and inference.local is None
        assert "filesystem.stat" in service.agent_capabilities and "filesystem.read_text" in service.agent_capabilities
        assert inference.cloud._client is None
    finally:
        service.shutdown()


def test_missing_qualification_report_is_read_only(tmp_path):
    from tools.verify_openai_qualification import verify
    assert verify(tmp_path, tmp_path / "missing.json")
    assert list(tmp_path.iterdir()) == []


def test_fixture_consent_clicks_the_actual_known_dialog():
    from PySide6.QtWidgets import QApplication, QWidget, QMessageBox
    from tools.openai_live_qualification import accept_fixture_cloud_notice
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    timer = accept_fixture_cloud_notice(window, app)
    try:
        assert QMessageBox.question(window, "Use cloud model?", "Synthetic fixture consent",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        assert window._qualification_cloud_consents == 1
    finally:
        timer.stop()
        window.close()
