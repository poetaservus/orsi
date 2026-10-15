"""Essential ORSI permission/executor/journal and cloud-only MCP integration."""
import json
import os
from pathlib import Path
from threading import Timer

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityContext, CapabilityErrorCode, CapabilityExecutionError
from app.execution.audit import CallLifecycleState
from app.inference.cloud_errors import CloudInferenceError
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.hybrid import HybridInferenceEngine
from app.inference.protocol import ModelProtocolFailureCode, ModelResponse
from app.mcp.office_capabilities import OfficeResourceBinding
from app.mcp.office_contracts import OfficeExposure, office_catalog
from app.runtime.cancellation import CancellationSource, CancellationToken
from app.security.permissions import ApprovalStatus, PermissionDecision, prepare_capability_call
from app.settings.agent import AgentFeatureConfig
from tests.test_office_mcp_connection import ROOT, attach, connection, invoke


class OfflineModel(InferenceEngine):
    def __init__(self, *, mode="cloud", error=None):
        self.mode, self.error, self.calls = mode, error, 0

    def respond(self, messages):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return "fixture"

    def respond_with_capabilities(self, messages, capabilities):
        self.respond(messages)
        return ModelResponse.text("fixture")


def resource_policy(contract, arguments, context):
    return OfficeResourceBinding(None, "synthetic-unsaved-workbook", "Change synthetic workbook")


def runtime_for(bridge, tmp_path, model=None, policy=resource_policy):
    return build_agent_runtime(model or OfflineModel(), config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=ROOT, state_directory=tmp_path, office_connection=bridge, office_resource_policy=policy)


def prepare(runtime, name, arguments, call_id, source=None):
    context = CapabilityContext(call_id=call_id, session_id="session1", turn_id="turn1",
        portable_root=ROOT, allowed_read_roots=(ROOT,), cancellation=(source.token if source else CancellationToken()))
    call = prepare_capability_call(runtime.registry.resolve(name), arguments, context)
    runtime.executor.journal.record_prepared(call)
    return call


def authorize(runtime, prepared, status=ApprovalStatus.APPROVED):
    evaluation = runtime.permission_gate.evaluate(prepared)
    if evaluation.decision == PermissionDecision.ASK:
        approval = runtime.approval_manager.request(evaluation)
        runtime.approval_manager.resolve(approval.approval_id, status)
        result = runtime.approval_manager.authorize(evaluation, approval_id=approval.approval_id)
    else:
        result = runtime.approval_manager.authorize(evaluation)
    runtime.executor.journal.record_authorization(prepared, result)
    return result


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
@pytest.mark.parametrize("approved", [False, True])
def test_exact_approval_controls_the_real_mcp_call_and_journal_is_content_free(tmp_path, approved):
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path)
    try:
        bridge.connect()
        attach(bridge)
        args = {"session": "s1", "snapshot": "snap1", "changes":
                [{"sheet": "Sheet1", "range": "A1", "values": [["SECRET-DOCUMENT-FIXTURE"]]}]}
        prepared = prepare(runtime, "office.excel_edit", args, "edit1")
        assert runtime.permission_gate.evaluate(prepared).decision == PermissionDecision.ASK
        auth = authorize(runtime, prepared, ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED)
        before = bridge.diagnostics["tool_calls"]
        if approved:
            result = runtime.executor.execute(prepared, auth)
            assert result.success
            assert bridge.diagnostics["tool_calls"] == before + 1
            read = invoke(bridge, "office.read", {"session": "s1"}, "read1")
            assert read["items"][0]["values"] == [["SECRET-DOCUMENT-FIXTURE"]]
            assert not runtime.executor.executor.execute(prepared, auth).success
        else:
            assert not runtime.executor.executor.execute(prepared, auth).success
            assert bridge.diagnostics["tool_calls"] == before
        journal = (tmp_path / "capability_journal_v1.json").read_text()
        assert "SECRET-DOCUMENT-FIXTURE" not in journal and "Change synthetic workbook" not in journal
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
def test_live_binding_change_after_approval_prevents_dispatch(tmp_path):
    identity = ["before"]
    def changing_policy(contract, arguments, context):
        return OfficeResourceBinding(None, identity[0])
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, policy=changing_policy)
    try:
        bridge.connect()
        attach(bridge)
        prepared = prepare(runtime, "office.excel_edit", {"session": "s1", "snapshot": "snap1",
            "changes": [{"sheet": "Sheet1", "range": "A1", "bold": True}]}, "edit1")
        auth = authorize(runtime, prepared)
        identity[0] = "after"
        result = runtime.executor.execute(prepared, auth)
        assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
        assert bridge.diagnostics["tool_calls"] == 1
    finally:
        runtime.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
def test_interrupted_write_enters_existing_journal_review_gate(tmp_path):
    bridge = connection("hang_write", call_timeout=2)
    runtime = runtime_for(bridge, tmp_path)
    source = CancellationSource()
    timer = Timer(0.1, source.cancel)
    try:
        bridge.connect()
        attach(bridge)
        prepared = prepare(runtime, "office.excel_edit", {"session": "s1", "snapshot": "snap1",
            "changes": [{"sheet": "Sheet1", "range": "A1", "bold": True}]}, "edit1", source)
        auth = authorize(runtime, prepared)
        timer.start()
        result = runtime.executor.execute(prepared, auth)
        assert result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN
        assert runtime.executor.review_required
        assert runtime.executor.journal.records[0].state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
    finally:
        timer.cancel()
        runtime.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
def test_office_visibility_tracks_actual_model_mode_and_preserves_skill_extension(tmp_path):
    model = OfflineModel()
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, model)
    try:
        assert not any(n.startswith("office.") for n in runtime.registry.model_visible_names)
        bridge.connect()
        assert "office.excel_edit" in runtime.registry.model_visible_names
        assert runtime.registry.extended(()).model_visible_names == runtime.registry.model_visible_names
        model.mode = "local"
        assert not any(n.startswith("office.") for n in runtime.registry.model_visible_names)
        assert "filesystem.stat" in runtime.registry.model_visible_names
        model.mode = "cloud"
        assert "office.excel_edit" in runtime.registry.model_visible_names
    finally:
        runtime.shutdown()


def test_office_turn_never_falls_back_to_local_or_reaches_local_with_stale_schemas():
    local = OfflineModel(mode="local")
    cloud = OfflineModel(error=CloudInferenceError("fixture outage", allow_local_fallback=True))
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=True)
    definitions = office_catalog(OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1)).model_definitions()
    with pytest.raises(CloudInferenceError):
        hybrid.respond_with_capabilities([{"role": "user", "content": "fixture"}], definitions)
    assert cloud.calls == 1 and local.calls == 0
    with pytest.raises(CloudInferenceError):
        hybrid.respond_cloud_only([{"role": "user", "content": "fixture recovery"}])
    assert local.calls == 0
    hybrid.set_mode("local")
    with pytest.raises(InferenceUnavailable):
        hybrid.respond_with_capabilities([{"role": "user", "content": "fixture"}], definitions)
    assert local.calls == 0
    hybrid.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
def test_constrained_office_recovery_uses_cloud_only_in_the_real_agent_loop(tmp_path):
    class UnsupportedCloud(OfflineModel):
        def respond_with_capabilities(self, messages, capabilities):
            self.calls += 1
            return ModelResponse.failure(ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS, "fixture native failure")
    cloud = UnsupportedCloud(error=CloudInferenceError("fixture recovery outage", allow_local_fallback=True))
    local = OfflineModel(mode="local")
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=True)
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, hybrid)
    try:
        bridge.connect()
        result = runtime.run([{"role": "user", "content": "synthetic Office task"}], session_id="s", turn_id="t",
                             portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert result.status.value == "model_unavailable"
        assert cloud.calls == 2 and local.calls == 0
        assert bridge.diagnostics["tool_calls"] == 0
    finally:
        runtime.shutdown()
        hybrid.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP integration")
def test_missing_host_policy_and_protected_save_as_fail_before_mcp_execution(tmp_path):
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, policy=None)
    try:
        bridge.connect()
        assert not any(name.startswith("office.") for name in runtime.registry.model_visible_names)
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.documents", {}, "read1")
        assert bridge.diagnostics["tool_calls"] == 0
        runtime = runtime_for(bridge, tmp_path / "other")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.save", {"session": "s1", "path": str(ROOT / "app/main.py")}, "save1")
        assert bridge.diagnostics["tool_calls"] == 0
    finally:
        runtime.shutdown()


def test_document_write_policy_keeps_ordinary_paths_and_rejects_protected_paths(tmp_path):
    from app.security.write_policy import HostWritePolicy
    (tmp_path / "application").mkdir()
    policy = HostWritePolicy(tmp_path / "application", (tmp_path / "state",))
    ordinary = tmp_path / "documents/report.xlsx"
    assert policy.resolve_document_file(str(ordinary)) == ordinary
    for path in (tmp_path / "application/report.xlsx", tmp_path / "state/report.xlsx"):
        with pytest.raises(CapabilityExecutionError):
            policy.resolve_document_file(str(path))
