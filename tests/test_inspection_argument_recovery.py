import pytest

from app.agent.contracts import AgentRunStatus
from app.capabilities.project_verification import ProjectInspectCapability
from app.inference.protocol import ModelResponse
from tests.test_bounded_edit_recovery import call, read, edit, RoomyScriptedModel
from tests.test_bounded_edit_recovery import make_service
from tests.test_filesystem_read_text import context


@pytest.mark.parametrize("extra,expected", [
    ({"steps": [{"action": "wait", "timeout_ms": 30000}]}, "steps.0.timeout_ms: Input should be less than or equal to 15000"),
    ({"pid": 42}, "Browser inspection requires a loopback HTTP URL and no PID"),
    ({"url": "https://example.com"}, "Only unauthenticated local loopback HTTP previews"),
    ({"server_arguments": ["run", "dev"]}, "Server arguments require a server executable"),
    ({"steps": [{"action": "model_loaded"}]}, "require an exact selector"),
    ({"steps": [{"action": "wait", "private-submitted-value": "SECRET"}]}, "unexpected field"),
])
def test_inspection_rejection_names_constraint_without_execution(tmp_path, monkeypatch, extra, expected):
    tool = ProjectInspectCapability(tmp_path / "state")
    monkeypatch.setattr(tool, "execute", lambda *args: pytest.fail("Invalid inspection executed"))
    args = {"project_path": str(tmp_path), "kind": "browser", "url": "http://127.0.0.1:8000/", **extra}
    result = tool.invoke(args, context(tmp_path))
    assert not result.success and expected in result.error.message
    assert "SECRET" not in result.error.message and "private-submitted-value" not in result.error.message
    assert result.error.details


def test_required_recovery_read_gets_allowance_after_two_prior_identical_reads(tmp_path, make_service):
    target = tmp_path / "App.tsx"
    target.write_text("animation = false\n", encoding="utf-8")
    service, _, approvals = make_service([
        read(1, target), read(2, target), edit(3, target, "animation = false", "animation = false"),
        read(4, target), edit(5, target, "animation = false", "animation = true"),
        read(6, target), ModelResponse.text("Animation restored; source checked.")])
    service.run("yes the animation was disabled temporary, can you re-enable it")
    assert service._turn_result.status == AgentRunStatus.COMPLETED
    assert service._turn_result.semantic_corrections == 1
    assert len(service._turn_result.settled_calls) == 6
    assert len(approvals) == 1 and target.read_text() == "animation = true\n"


def test_recovery_does_not_renew_unrelated_reads_or_failed_edit_limit(tmp_path, make_service):
    target, unrelated = tmp_path / "App.tsx", tmp_path / "other.tsx"
    target.write_text("old", encoding="utf-8")
    unrelated.write_text("other", encoding="utf-8")
    service, _, _ = make_service([read(1, unrelated), read(2, unrelated),
        edit(3, target, "missing", "new"), read(4, unrelated)])
    from tests.test_bounded_edit_recovery import stopped_report
    stopped_report(service, "Fix App.tsx")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert target.read_text() == "old"


def test_repeated_recovery_still_stops_after_three_failed_patches(tmp_path, make_service):
    target = tmp_path / "App.tsx"
    target.write_text("old", encoding="utf-8")
    service, _, _ = make_service([read(1, target), read(2, target),
        edit(3, target, "missing", "new"), read(4, target),
        edit(5, target, "missing-2", "new"), read(6, target),
        edit(7, target, "missing-3", "new")])
    from tests.test_bounded_edit_recovery import stopped_report
    stopped_report(service, "Fix App.tsx")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert "three rejected edits" in service._turn_result.message
    assert len(service._turn_result.settled_calls) == 7 and target.read_text() == "old"


def test_rejected_already_present_retry_keeps_diagnosis_feedback(tmp_path, make_service):
    target = tmp_path / "App.tsx"
    target.write_text("animation = true", encoding="utf-8")
    service, model, approvals = make_service([
        edit(1, target, "animation = true", "animation = true"), read(2, target),
        edit(3, target, "animation = true", "animation = true"),
        ModelResponse.text("The requested source is already present; visual behavior is unverified.")])
    service.run("yes the animation was disabled temporary, can you re-enable it")
    assert service._turn_result.status == AgentRunStatus.COMPLETED
    assert service._turn_result.semantic_corrections == 2 and not approvals
    feedback = [m["content"] for m in model.requests[3] if m["role"] == "system"][-1]
    assert "Stop repeating that patch" in feedback and "screenshot evidence" in feedback
    assert "obtain fresh source" not in feedback
    assert target.read_text() == "animation = true"


def test_duplicate_project_check_returns_evidence_then_allows_a_concrete_correction(tmp_path, monkeypatch):
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import AgentFeatureConfig
    executions = []
    def inspect(tool, args, ctx):
        executions.append(tool._authorize(args, ctx))
        return {"project_path": str(executions[-1]), "passed": True}
    monkeypatch.setattr(ProjectInspectCapability, "execute", inspect)
    target = tmp_path / "App.tsx"
    target.write_text("animation = false", encoding="utf-8")
    args = {"project_path": str(tmp_path), "kind": "browser", "url": "http://localhost:5173/"}
    model = RoomyScriptedModel([call(1, "project.inspect", **args), call(2, "project.inspect", **args),
        call(3, "project.inspect", **args), read(4, target),
        edit(5, target, "animation = false", "animation = true"),
        call(6, "project.inspect", **args), read(7, target), ModelResponse.text("Restored and rechecked.")])
    portable = tmp_path / "portable"
    portable.mkdir()
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True, project_inspect_enabled=True,
        full_local_read_enabled=True), portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
        portable_root=portable, host_access_policy=policy)
    approvals = []
    def approve(record):
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    try:
        service.run("yes the animation was disabled temporary, can you re-enable it")
        assert service._turn_result.status == AgentRunStatus.COMPLETED
        assert len(executions) == 3 and len(approvals) == 4
        duplicate = service._turn_result.settled_calls[2].result
        assert not duplicate.success and duplicate.error.code.value == "call_replayed"
        assert "No new process was started" in duplicate.error.message
        assert len(duplicate.error.details[0]["prior_receipt_ids"]) == 2
        assert target.read_text() == "animation = true"
    finally:
        service.shutdown()
