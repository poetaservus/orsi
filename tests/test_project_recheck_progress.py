from hashlib import sha256
from pathlib import Path
import sys

import pytest

from app.agent.feedback import call_fingerprint
from app.agent.project_progress import ProjectProgressTracker
from app.capabilities.contracts import CapabilityResult
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.settings.agent import AgentFeatureConfig
from app.security.host_access import HostAccessPolicy
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call, edit


def observe(tracker, repeated, tool, arguments, output, success=True):
    request = ModelCapabilityCall(provider_call_id="probe", capability=tool, arguments=arguments)
    from app.capabilities.contracts import CapabilityFailure, CapabilityErrorCode
    result = CapabilityResult(call_id="receipt", capability=tool, success=success,
        output=output if success else None,
        error=None if success else CapabilityFailure(code=CapabilityErrorCode.INVALID_ARGUMENTS, message="Rejected"),
        duration_ms=0)
    tracker.observe(request, result, repeated)
    return call_fingerprint(request)


@pytest.mark.parametrize("tool", ["project.verify", "project.inspect"])
@pytest.mark.parametrize("mutation,changed", [
    ("edit", True), ("create", True), ("write", True), ("noop", False),
    ("unknown_write", False), ("failed", False), ("unrelated", False), ("read", False)])
def test_only_proven_changes_in_the_checked_project_renew_checks(tmp_path, tool, mutation, changed):
    tracker, repeated = ProjectProgressTracker(), {}
    project = tmp_path / "project"
    fingerprint = observe(tracker, repeated, tool, {"project_path": str(project)}, {"project_path": str(project)})
    repeated[fingerprint] = 2
    path = str((tmp_path / "project-other" if mutation == "unrelated" else project) / "main.py")
    digest = sha256(b"old").hexdigest()
    if mutation not in {"unknown_write", "create"}:
        observe(tracker, repeated, "filesystem.read_text", {"path": path}, {"path": path, "sha256": digest})
    output = {"path": path, "sha256": digest if mutation == "noop" else sha256(b"new").hexdigest(),
        "operation": "created" if mutation == "create" else "replaced"}
    capability = ("filesystem.read_text" if mutation == "read" else
        "filesystem.write_text" if mutation in {"create", "write", "noop", "unknown_write"} else "filesystem.edit_text")
    observe(tracker, repeated, capability, {"path": path}, output, success=mutation != "failed")
    assert (fingerprint not in repeated) is changed


def test_new_visual_evidence_renews_only_project_reads_once(tmp_path):
    tracker, repeated = ProjectProgressTracker(), {}
    project = tmp_path / "project"
    read = observe(tracker, repeated, "filesystem.read_text", {"path": str(project / "App.tsx")},
        {"path": str(project / "App.tsx"), "sha256": "1" * 64})
    other = observe(tracker, repeated, "filesystem.read_text", {"path": str(tmp_path / "other.tsx")},
        {"path": str(tmp_path / "other.tsx"), "sha256": "1" * 64})
    check_args = {"project_path": str(project)}
    check = observe(tracker, repeated, "project.inspect", check_args, {"project_path": str(project)})
    repeated.update({read: 2, other: 2, check: 2})
    snapshot = {"project_path": str(project), "inspection_complete": True, "screenshot_sha256": "2" * 64}
    observe(tracker, repeated, "project.inspect", check_args, snapshot)
    assert read not in repeated and repeated[other] == repeated[check] == 2
    repeated[read] = 2
    observe(tracker, repeated, "project.inspect", check_args, snapshot)
    assert repeated[read] == 2  # Identical screenshots cannot reset a stalled loop.


@pytest.mark.parametrize("tool", ["project.verify", "project.inspect"])
@pytest.mark.parametrize("stalled", [False, True])
def test_guard_renews_checks_after_edits_through_the_runtime(tmp_path, monkeypatch, tool, stalled):
    from app.capabilities.project_verification import ProjectInspectCapability
    if tool == "project.inspect":
        # Exercise runtime counting independently of Chromium startup, covered by
        # the real readiness and image-delivery tests.
        monkeypatch.setattr(ProjectInspectCapability, "execute", lambda self, args, ctx:
            {"project_path": str(self._authorize(args, ctx)), "passed": True})
    path = tmp_path / "main.py"
    path.write_text("version 0", encoding="utf-8")
    arguments = ({"kind": "build", "executable": str(Path(sys.executable).resolve()), "arguments": ["-c", "pass"]}
        if tool == "project.verify" else {"kind": "browser", "url": "http://127.0.0.1:8000/"})
    responses = [
        call(1, tool, project_path=str(tmp_path), **arguments),
        edit(2, path, "version 0", "version 1"),
        call(3, tool, project_path=str(tmp_path), **arguments),
        edit(4, path, "version 1", "version 2"),
        call(5, tool, project_path=str(tmp_path), **arguments)]
    if stalled:
        responses.extend(call(i, tool, project_path=str(tmp_path), **arguments) for i in (6, 7, 8))
    else:
        responses.append(ModelResponse.text("Done"))
    model = RoomyScriptedModel(responses)
    portable = tmp_path / "portable"
    portable.mkdir()
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_edit_text_enabled=True, full_local_read_enabled=True, project_verify_enabled=True, project_inspect_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    runtime.set_tool_approval_required(False)
    result = runtime.run([{"role": "user", "content": "Fix and recheck the project after each change."}],
        session_id="session", turn_id="turn", portable_root=portable, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    assert result.status == (AgentRunStatus.REPEATED_CALL if stalled else AgentRunStatus.COMPLETED), result
    assert result.capability_calls == (8 if stalled else 5)
    assert len(result.settled_calls) == (7 if stalled else 5)
    if stalled:
        assert result.settled_calls[-1].result.error.code.value == "call_replayed"
        assert len(result.settled_calls[-1].result.error.details[0]["prior_receipt_ids"]) == 2
    assert path.read_text() == "version 2"
