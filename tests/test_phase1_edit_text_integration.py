from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityContext, CapabilityExecutionError
from app.capabilities.filesystem_edit_text import FilesystemEditTextCapability
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import CapabilityCrashJournal, CallLifecycleState
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.security.permissions import prepare_capability_call
from app.security.write_policy import HostWritePolicy
from app.settings.agent import AgentFeatureConfig
from tests.fixtures.context_reliability import large_css_fixture

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter.")


class EditModel(InferenceEngine):
    def __init__(self):
        self.arguments = {}
        self.seen = []
        self.counter = 0

    def respond(self, messages):
        return "Conversation."

    def respond_with_capabilities(self, messages, capabilities):
        self.seen.append(tuple(item.name for item in capabilities))
        if messages[-1].get("role") == "capability":
            return ModelResponse.text(json.dumps(messages[-1]["result"]))
        self.counter += 1
        return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"edit-{self.counter}",
                                  capability="filesystem.edit_text", arguments=self.arguments),))


@pytest.fixture
def service(tmp_path):
    portable = tmp_path / "portable"
    portable.mkdir()
    model = EditModel()
    runtime = build_agent_runtime(model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_edit_text_enabled=True),
        portable_root=portable, state_directory=portable / "state")
    service = ConversationService(model, ConversationStore(portable / "conversation.json"),
                                   agent_runtime=runtime, portable_root=portable)
    yield service
    service.shutdown()


def setup_target(service, tmp_path, raw=b"old\r\nkeep\r\n"):
    target = tmp_path / "note.txt"
    target.write_bytes(raw)
    service.inference.arguments = {"path": str(target), "old_text": "old", "new_text": "new"}
    return target


def test_exact_approval_compact_result_and_single_use(service, tmp_path):
    target = setup_target(service, tmp_path)
    records = []
    def approve(record):
        assert target.read_bytes() == b"old\r\nkeep\r\n"
        assert record.resource == str(target)
        assert '"-old\\r\\n"' in record.approval_preview
        records.append(record)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    result = json.loads(service.run("Edit the text file"))
    assert result["success"]
    assert target.read_bytes() == b"new\r\nkeep\r\n"
    assert set(result["output"]) == {"path", "replacements", "additions", "deletions", "sha256"}
    assert result["output"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert service.approval_status(records[0].approval_id) == "consumed"
    assert not service.resolve_approval(records[0].approval_id, True)
    assert service.agent_runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED


def test_css_workflow_does_not_send_whole_replacement(service, tmp_path):
    original = large_css_fixture().encode()
    target = setup_target(service, tmp_path, original)
    old = ".phase0-component-001 { color: #123456;"
    service.inference.arguments.update(old_text=old, new_text=old.replace("#123456", "#ffffff"))
    service.set_approval_requester(lambda r: service.resolve_approval(r.approval_id, True))
    result = json.loads(service.run("Edit the CSS color"))
    assert result["success"]
    assert target.read_bytes() == original.replace(b"#123456", b"#ffffff", 1)
    assert len(json.dumps(result["output"])) < 500


@pytest.mark.parametrize("mutation", ["content", "identity", "delete", "parent"])
def test_changes_after_preview_are_rejected(service, tmp_path, mutation):
    directory = tmp_path / "target"
    directory.mkdir()
    target = setup_target(service, directory)
    def mutate(record):
        if mutation == "content":
            target.write_bytes(b"old\r\nchanged\r\n")
        elif mutation == "identity":
            target.rename(directory / "original.txt")
            target.write_bytes(b"old\r\nkeep\r\n")
        elif mutation == "delete":
            target.unlink()
        else:
            directory.rename(tmp_path / "previous")
            directory.mkdir()
            target.write_bytes(b"old\r\nkeep\r\n")
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(mutate)
    result = json.loads(service.run("Edit the file"))
    assert not result["success"]
    assert not target.exists() or b"new" not in target.read_bytes()


@pytest.mark.parametrize("raw, update", [(b"other", {}), (b"old old", {}),
    (b"old", {"expected_sha256": "0" * 64})])
def test_invalid_edits_never_ask_for_approval(service, tmp_path, raw, update):
    target = setup_target(service, tmp_path, raw)
    service.inference.arguments.update(update)
    approvals = []
    service.set_approval_requester(approvals.append)
    assert not json.loads(service.run("Edit the file"))["success"]
    assert approvals == []
    assert target.read_bytes() == raw


@pytest.mark.parametrize("approved", [True, False])
def test_ambiguous_edit_can_be_corrected_but_still_requires_approval(service, tmp_path, monkeypatch, approved):
    raw = b"header {\r\n  background: #222;\r\n}\r\nfooter {\r\n  background: #222;\r\n}\r\n"
    target = setup_target(service, tmp_path, raw)
    old = "header {\r\n  background: #222;\r\n}"
    new = old.replace("#222", "linear-gradient(black, blue)")
    calls = []

    def respond(messages, capabilities):
        if not calls:
            arguments = {"path": str(target), "old_text": "background: #222;",
                         "new_text": "background: linear-gradient(black, blue);"}
        elif len(calls) == 1:
            rejected = messages[-1]["result"]
            assert not rejected["success"] and rejected["error"]["code"] == "invalid_arguments"
            assert target.read_bytes() == raw
            assert not approvals
            arguments = {"path": str(target), "old_text": old, "new_text": new}
        else:
            return ModelResponse.text(json.dumps(messages[-1]["result"]))
        calls.append(arguments)
        return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"correction-{len(calls)}",
                                    capability="filesystem.edit_text", arguments=arguments),))

    monkeypatch.setattr(service.inference, "respond_with_capabilities", respond)
    approvals = []

    def approve(record):
        assert target.read_bytes() == raw
        assert record.resource == str(target)
        assert "linear-gradient" in record.approval_preview
        approvals.append(record)
        service.resolve_approval(record.approval_id, approved)

    service.set_approval_requester(approve)
    result = json.loads(service.run("add a gradient in the header in style.css"))
    assert result["success"] == approved
    assert len(approvals) == 1 and len(calls) == 2
    assert target.read_bytes() == (raw.replace(old.encode(), new.encode(), 1) if approved else raw)
    assert len(service.agent_runtime.executor.journal.records) == 1


def test_denial_preserves_source(service, tmp_path):
    target = setup_target(service, tmp_path)
    service.set_approval_requester(lambda r: service.resolve_approval(r.approval_id, False))
    assert not json.loads(service.run("Edit the file"))["success"]
    assert target.read_bytes() == b"old\r\nkeep\r\n"


def prepared_edit(tmp_path):
    portable = tmp_path / "portable"
    portable.mkdir()
    target = tmp_path / "edit.txt"
    target.write_bytes(b"old")
    source = CancellationSource()
    context = CapabilityContext("call-1", "session", "turn", portable, (portable,), source.token)
    capability = FilesystemEditTextCapability(HostWritePolicy(portable))
    prepared = prepare_capability_call(capability, {"path": str(target), "old_text": "old", "new_text": "new"}, context)
    authorized = replace(context, authorized_resource=prepared.request.resource,
                         authorized_resource_identity=prepared.request.resource_identity)
    return target, source, prepared, authorized


def test_preparation_uses_one_snapshot_for_preview_and_digest(tmp_path, monkeypatch):
    import app.capabilities.filesystem_edit_text as module
    native = module._snapshot
    seen = []
    def snapshot(path, cancellation):
        result = native(path, cancellation)
        seen.append(result)
        return result
    monkeypatch.setattr(module, "_snapshot", snapshot)
    _, _, prepared, _ = prepared_edit(tmp_path)
    assert len(seen) == 1
    assert hashlib.sha256(b"old").hexdigest() in prepared.request.resource_identity
    assert '"-old"' in prepared.request.approval_preview


def test_late_content_race_is_rejected_and_temp_cleaned(tmp_path, monkeypatch):
    import app.capabilities.filesystem_write_text as writer
    target, _, prepared, context = prepared_edit(tmp_path)
    native = writer.os.fsync
    def race(fd):
        native(fd)
        target.write_bytes(b"competitor")
    monkeypatch.setattr(writer.os, "fsync", race)
    with pytest.raises(CapabilityExecutionError, match="changed after"):
        prepared.capability.execute(prepared.validated_arguments(), context)
    assert target.read_bytes() == b"competitor"
    assert not list(tmp_path.glob(".orsi-write-*.tmp"))


def test_cancellation_before_replace_cleans_temp(tmp_path, monkeypatch):
    import app.capabilities.filesystem_write_text as writer
    target, source, prepared, context = prepared_edit(tmp_path)
    native = writer.os.fsync
    def cancel(fd):
        native(fd)
        source.cancel()
    monkeypatch.setattr(writer.os, "fsync", cancel)
    with pytest.raises(TaskCancelled):
        prepared.capability.execute(prepared.validated_arguments(), context)
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".orsi-write-*.tmp"))


def test_unverified_edit_blocks_retry_and_restart(service, tmp_path, monkeypatch):
    import app.capabilities.filesystem_edit_text as module
    target = setup_target(service, tmp_path)
    native = module.atomic_write_text_file
    def interrupted(*args, **kwargs):
        native(*args, **kwargs)
        raise RuntimeError("Interrupted verification")
    monkeypatch.setattr(module, "atomic_write_text_file", interrupted)
    service.set_approval_requester(lambda r: service.resolve_approval(r.approval_id, True))
    with pytest.raises(RuntimeError, match="(?i)review"):
        service.run("Edit the file")
    assert target.read_bytes().startswith(b"new")
    journal = service.agent_runtime.executor.journal
    assert journal.review_required
    assert journal.records[0].state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
    assert CapabilityCrashJournal(service.portable_root / "state" / "capability_journal_v1.json").review_required
    with pytest.raises(RuntimeError, match="review"):
        service.run("Edit again")


@pytest.mark.parametrize("path", [r"relative\file.txt", r"C:\new.txt", r"C:\Windows\file.txt",
    r"C:\Users\name\AppData\file.txt", r"C:\Users\name\NUL.txt", r"C:\Users\name\..\file.txt",
    r"C:\Users\name\file.txt:stream", r"\\server\share\file.txt", r"\\?\C:\Users\name\file.txt"])
def test_edit_uses_protected_path_policy(tmp_path, path):
    capability = FilesystemEditTextCapability(HostWritePolicy(tmp_path))
    context = CapabilityContext("c", "s", "t", tmp_path, (), CancellationSource().token)
    with pytest.raises(CapabilityExecutionError):
        prepare_capability_call(capability, {"path": path, "old_text": "old", "new_text": "new"}, context)


def test_unrequested_edit_still_requires_denied_operation_approval(service, tmp_path):
    target = setup_target(service, tmp_path)
    approvals = []
    def deny(record):
        approvals.append(record)
        assert target.read_bytes() == b"old\r\nkeep\r\n"
        service.resolve_approval(record.approval_id, False)
    service.set_approval_requester(deny)
    # A malicious proposal stays visible but cannot execute without authorization.
    result = json.loads(service.run("Inspect the file metadata"))
    assert all("filesystem.edit_text" in names for names in service.inference.seen)
    assert not result["success"] and len(approvals) == 1
    assert target.read_bytes() == b"old\r\nkeep\r\n"


def test_window_edit_approval(service, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPlainTextEdit, QPushButton
    from app.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    target = setup_target(service, tmp_path)
    window = MainWindow(service, "test")
    window.show()
    def wait_until(predicate):
        for _ in range(250):
            app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("UI did not finish")
    try:
        window.input.setPlainText("Edit the file")
        window.submit()
        wait_until(lambda: window._approval_dialog is not None)
        dialog = window._approval_dialog
        assert dialog.objectName() == "editApproval"
        assert dialog.findChild(QPlainTextEdit, "approvalPath").toPlainText() == str(target)
        preview = dialog.findChild(QPlainTextEdit, "approvalContent")
        assert preview.isReadOnly() and '"-old' in preview.toPlainText()
        assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).isDefault()
        QTest.mouseClick(dialog.findChild(QPushButton, "approveTextEdit"), Qt.MouseButton.LeftButton)
        wait_until(lambda: window.thread is None)
        assert target.read_bytes().startswith(b"new")
    finally:
        service.cancel_current_task()
        wait_until(lambda: window.thread is None)
        window.close()


def test_expired_edit_approval_and_changed_arguments_cannot_authorize(tmp_path):
    from app.security.permissions import (ApprovalManager, ApprovalStatus, AuthorizationCode,
        PermissionDecision, PermissionGate, PermissionRule)
    target, _, prepared, _ = prepared_edit(tmp_path)
    gate = PermissionGate([PermissionRule("edit-ask", PermissionDecision.ASK,
                                          capability_pattern="filesystem.edit_text")])
    evaluation = gate.evaluate(prepared)
    manager = ApprovalManager()
    record = manager.request(evaluation, ttl_seconds=5.0, now=10.0)
    manager.resolve(record.approval_id, ApprovalStatus.APPROVED, now=11.0)
    changed = prepare_capability_call(prepared.capability,
        {"path": str(target), "old_text": "old", "new_text": "different"}, prepared.context)
    assert manager.authorize(gate.evaluate(changed), approval_id=record.approval_id,
                             now=12.0).code == AuthorizationCode.APPROVAL_MISMATCH
    assert manager.authorize(evaluation, approval_id=record.approval_id,
                             now=16.0).code == AuthorizationCode.APPROVAL_EXPIRED
    assert target.read_bytes() == b"old"


def test_atomic_replace_failure_preserves_source_and_cleans_temp(tmp_path, monkeypatch):
    import app.capabilities.filesystem_write_text as writer
    target, _, prepared, context = prepared_edit(tmp_path)
    def fail(*args):
        raise PermissionError("Fixture denied replace")
    monkeypatch.setattr(writer.os, "replace", fail)
    with pytest.raises(CapabilityExecutionError, match="unavailable"):
        prepared.capability.execute(prepared.validated_arguments(), context)
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".orsi-write-*.tmp"))


def test_direct_execute_without_authorization_is_denied(tmp_path):
    target, _, prepared, _ = prepared_edit(tmp_path)
    with pytest.raises(CapabilityExecutionError, match="authorization"):
        prepared.capability.execute(prepared.validated_arguments(), prepared.context)
    assert target.read_bytes() == b"old"


def test_reparse_target_is_rejected(tmp_path):
    target, _, prepared, _ = prepared_edit(tmp_path)
    link = tmp_path / "redirect.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Host cannot create test symbolic links")
    with pytest.raises(CapabilityExecutionError):
        prepare_capability_call(prepared.capability,
            {"path": str(link), "old_text": "old", "new_text": "new"}, prepared.context)
    assert target.read_bytes() == b"old"


def test_registration_is_default_off_and_explicitly_gated(tmp_path, monkeypatch):
    from app.capabilities.catalog import build_builtin_registry
    from app.settings.agent import load_agent_feature_config
    import app.settings.agent as settings
    monkeypatch.setattr(settings, "load_json", lambda *a, **k: {"filesystem_stat_enabled": True})
    monkeypatch.delenv("ORSI_ENABLE_FILESYSTEM_EDIT_TEXT", raising=False)
    disabled = load_agent_feature_config()
    registry = build_builtin_registry(disabled, application_root=tmp_path, state_directory=tmp_path / "state")
    assert "filesystem.edit_text" not in registry.model_visible_names
    monkeypatch.setenv("ORSI_ENABLE_FILESYSTEM_EDIT_TEXT", "1")
    enabled = load_agent_feature_config()
    registry = build_builtin_registry(enabled, application_root=tmp_path, state_directory=tmp_path / "state")
    assert "filesystem.edit_text" in registry.model_visible_names
