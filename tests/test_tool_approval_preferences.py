"""Review preferences keep exact-call authorization and file protections intact."""
from copy import copy
import os
from types import SimpleNamespace

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.capabilities.application_launch import ApplicationLaunchCapability
from app.capabilities.contracts import PermissionClass
from app.execution.audit import CallLifecycleState
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.activity import capability_activity
from app.runtime.cancellation import CancellationSource
from app.security.permissions import ApprovalStatus, PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import ScriptedModel, build_runtime, capability_call, run


def test_off_auto_approves_each_exact_call_without_a_review_surface(tmp_path):
    runtime, _, tool, journal, manager = build_runtime(tmp_path,
        [capability_call(1, "one"), capability_call(2, "two"), ModelResponse.text("Done")],
        decision=PermissionDecision.ASK,
        approval_requester_factory=lambda _: lambda record: pytest.fail("Unexpected review"))
    runtime.set_tool_approval_required(False)
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.COMPLETED and tool.values == ["one", "two"]
        assert len(manager.records) == 2
        assert {record.status for record in manager.records} == {ApprovalStatus.CONSUMED}
        assert len({record.binding_sha256 for record in manager.records}) == 2
        assert all(record.state == CallLifecycleState.COMPLETED for record in journal.records)
    finally:
        runtime.shutdown()


def test_reenabling_review_applies_to_the_next_call_and_shared_skill_runtime(tmp_path):
    runtime, model, tool, _, manager = build_runtime(tmp_path,
        [capability_call(1, "automatic"), capability_call(2, "reviewed"), ModelResponse.text("Done")],
        decision=PermissionDecision.ASK)
    scoped = copy(runtime)  # The skill-reference runtime uses this same shallow copy.
    scoped.set_tool_approval_required(False)
    assert not runtime.tool_approval_required
    model.before_request[1] = lambda *_: runtime.set_tool_approval_required(True)
    reviews = []
    def approve(record):
        assert tool.values == ["automatic"]
        reviews.append(record)
        scoped.resolve_approval(record.approval_id, True)
    scoped.set_approval_requester(approve)
    try:
        result = run(scoped, tmp_path)
        assert result.status == AgentRunStatus.COMPLETED and tool.values == ["automatic", "reviewed"]
        assert scoped.tool_approval_required and len(reviews) == 1
        assert len(manager.records) == 2
    finally:
        runtime.shutdown()


def test_disabling_review_does_not_accept_a_request_already_being_reviewed(tmp_path):
    runtime, _, tool, journal, _ = build_runtime(tmp_path,
        [capability_call(1), ModelResponse.text("Denied")], decision=PermissionDecision.ASK)
    def deny(record):
        runtime.set_tool_approval_required(False)
        runtime.resolve_approval(record.approval_id, False)
    runtime.set_approval_requester(deny)
    try:
        assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
        assert not tool.values and journal.records[0].state == CallLifecycleState.DENIED
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("arguments,decision", [({"value": "hello"}, PermissionDecision.DENY),
                                              ({"value": 123}, PermissionDecision.ASK)])
def test_off_does_not_bypass_policy_or_argument_validation(tmp_path, arguments, decision):
    runtime, _, tool, _, manager = build_runtime(tmp_path,
        [capability_call(1, arguments=arguments), ModelResponse.text("Rejected")], decision=decision)
    runtime.set_tool_approval_required(False)
    try:
        assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
        assert not tool.values and not manager.records
    finally:
        runtime.shutdown()


def test_cancellation_during_automatic_authorization_prevents_execution(tmp_path, monkeypatch):
    runtime, _, tool, journal, manager = build_runtime(tmp_path, [capability_call(1)],
                                                       decision=PermissionDecision.ASK)
    runtime.set_tool_approval_required(False)
    cancellation = CancellationSource()
    original = manager.resolve
    def cancel(*args, **kwargs):
        cancellation.cancel()
        return original(*args, **kwargs)
    monkeypatch.setattr(manager, "resolve", cancel)
    try:
        assert run(runtime, tmp_path, cancellation=cancellation.token).status == AgentRunStatus.CANCELLED
        assert not tool.values and journal.records[0].state == CallLifecycleState.CANCELLED
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("value", [None, 0, 1, "false"])
def test_runtime_requires_boolean_preferences(tmp_path, value):
    runtime, *_ = build_runtime(tmp_path, [])
    try:
        with pytest.raises(TypeError):
            runtime.set_tool_approval_required(value)
        assert runtime.tool_approval_required
    finally:
        runtime.shutdown()


def test_off_authorizes_allowlisted_launch_without_showing_review(tmp_path):
    executable = tmp_path / "blender.exe"
    executable.write_bytes(b"synthetic executable")
    launches = []
    launch = ApplicationLaunchCapability(locator=lambda _: executable,
        launcher=lambda command, cwd: launches.append((command, cwd)) or SimpleNamespace(pid=42))
    response = ModelResponse.calls((ModelCapabilityCall(provider_call_id="launch-fixture",
        capability="application.launch", arguments={"application": "blender"}),))
    runtime, _, _, journal, manager = build_runtime(tmp_path, [response, ModelResponse.text("Done")],
        capability=launch, approval_requester_factory=lambda _: lambda record: pytest.fail("Unexpected review"))
    runtime.permission_gate = PermissionGate((PermissionRule("fixture-launch", PermissionDecision.ASK,
        permission=PermissionClass.EXECUTE, capability_pattern="application.launch"),))
    runtime.set_tool_approval_required(False)
    try:
        assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
        assert len(launches) == 1 and launches[0][0] == [str(executable)]
        assert manager.records[0].status == ApprovalStatus.CONSUMED
        assert journal.records[0].state == CallLifecycleState.COMPLETED
    finally:
        runtime.shutdown()


def native_runtime(tmp_path, capability, arguments):
    portable = tmp_path / "portable"
    portable.mkdir()
    model = ScriptedModel([ModelResponse.calls((ModelCapabilityCall(provider_call_id="fixture-call",
        capability=capability, arguments=arguments),)), ModelResponse.text("Done")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_mkdir_enabled=True, filesystem_write_text_enabled=True, filesystem_edit_text_enabled=True,
        filesystem_copy_enabled=True, filesystem_move_enabled=True),
        portable_root=portable, state_directory=portable / "state")
    runtime.set_tool_approval_required(False)
    runtime.set_approval_requester(lambda _: pytest.fail("Automatic tool opened a review"))
    return runtime


@pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter.")
@pytest.mark.parametrize("operation", ["write_text", "edit_text", "mkdir", "copy", "move"])
def test_automatic_native_operations_keep_receipts_and_report_names(tmp_path, operation):
    source = tmp_path / "Documents" / "xyz.py"
    target = tmp_path / "Desktop" / "xyz.py"
    source.parent.mkdir()
    target.parent.mkdir()
    source.write_bytes(b"before\n")
    arguments = {"path": str(target), "text": "after\n"}
    if operation == "edit_text":
        target.write_bytes(b"before\n")
        arguments = {"path": str(target), "old_text": "before", "new_text": "after"}
    elif operation == "mkdir":
        arguments = {"path": str(target)}
    elif operation in {"copy", "move"}:
        arguments = {"source_path": str(source), "destination_path": str(target)}
    runtime = native_runtime(tmp_path, f"filesystem.{operation}", arguments)
    stages = []
    try:
        result = runtime.run([{"role": "user", "content": "Synthetic automatic operation"}],
            session_id="fixture", turn_id="fixture-turn", portable_root=tmp_path,
            allowed_read_roots=(tmp_path,), activity_observer=stages.append)
        assert result.status == AgentRunStatus.COMPLETED
        records = runtime.executor.journal.records
        assert len(records) == 1 and records[0].state == CallLifecycleState.COMPLETED
        assert runtime.approval_manager.records[0].status == ApprovalStatus.CONSUMED
        assert "Waiting for your approval…" not in stages
        assert any("xyz.py" in stage for stage in stages)
        assert not any("after" in stage or "before" in stage for stage in stages)
        if operation == "mkdir":
            assert target.is_dir()
        else:
            assert target.read_bytes() == (b"before\n" if operation in {"copy", "move"} else b"after\n")
        assert source.exists() is (operation != "move")
        journal_text = runtime.executor.journal.path.read_text(encoding="utf-8")
        assert "xyz.py" not in journal_text and "after" not in journal_text
    finally:
        runtime.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter.")
def test_automatic_write_still_refuses_a_target_changed_after_preparation(tmp_path, monkeypatch):
    target = tmp_path / "xyz.py"
    target.write_bytes(b"original")
    runtime = native_runtime(tmp_path, "filesystem.write_text", {"path": str(target), "text": "new"})
    original = runtime.approval_manager.resolve
    def replace_target(*args, **kwargs):
        target.rename(tmp_path / "original.py")
        target.write_bytes(b"changed by another process")
        return original(*args, **kwargs)
    monkeypatch.setattr(runtime.approval_manager, "resolve", replace_target)
    try:
        run(runtime, tmp_path)
        assert target.read_bytes() == b"changed by another process"
        assert (tmp_path / "original.py").read_bytes() == b"original"
        assert runtime.executor.journal.records[0].state == CallLifecycleState.DENIED
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("name,arguments,expected", [
    ("filesystem.write_text", {"path": r"C:\Desktop\xyz.py", "text": "secret"}, "Writing xyz.py…"),
    ("filesystem.edit_text", {"path": r"C:\Desktop\xyz.py", "old_text": "secret"}, "Editing xyz.py…"),
    ("filesystem.copy", {"source_path": r"C:\Documents\xyz.py", "destination_path": r"C:\Desktop\xyz.py"},
     "Copying xyz.py from Documents to Desktop…"),
    ("filesystem.move", {"source_path": r"C:\Documents\xyz.py", "destination_path": r"C:\Desktop\new.py"},
     "Moving xyz.py from Documents to Desktop as new.py…"),
    ("filesystem.trash", {"path": r"C:\Desktop\xyz.py"}, "Recycling xyz.py…"),
    ("filesystem.write_text", {"path": r"C:\Desktop\two  spaces.py"}, "Writing two  spaces.py…"),
    ("filesystem.read_text", {"path": r"C:\Desktop\secret.py"}, "Reading files…"),
    ("unknown.tool", {"path": "secret"}, "Running a tool…"),
])
def test_operation_status_uses_only_relevant_file_names(name, arguments, expected):
    assert capability_activity(name, arguments) == expected
