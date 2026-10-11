"""Recovery from uncertain operations without locking ordinary conversation."""
from pathlib import Path

import pytest

from app.agent.contracts import AgentRunStatus
from app.capabilities.contracts import CapabilityErrorCode, CapabilityFailure, PermissionClass
from app.agent.feedback import failure_result
from app.security.permissions import prepare_capability_call
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import (CapabilityCrashJournal, CallLifecycleState,
    CrashJournalPersistenceError, LifecycleTransitionError)
from tests.test_agent_runtime import EchoCapability, build_runtime, capability_call, run
from tests.test_crash_journal import RecordingCapability, allow, context
from app.inference.protocol import ModelResponse


class InterruptedWrite(RecordingCapability):
    permission = PermissionClass.WRITE


def uncertain(journal, root: Path, *, call_id="interrupted-call", capability=None):
    prepared = prepare_capability_call(capability or InterruptedWrite(), {"value": "private"},
        context(root, call_id=call_id))
    journal.record_prepared(prepared)
    authorization = allow(prepared)
    journal.record_authorization(prepared, authorization)
    journal.mark_running(prepared, authorization)
    journal.record_result(failure_result(call_id, prepared.request.capability,
        CapabilityFailure(code=CapabilityErrorCode.OUTCOME_UNKNOWN, message="Interrupted.")))
    return prepared


def test_ordinary_chat_completes_while_an_earlier_write_awaits_review(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [ModelResponse.text("Hello.")])
    uncertain(journal, tmp_path)
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.COMPLETED
        assert result.assistant_text == "Hello."
        assert not capability.values
        assert journal.get("interrupted-call").review_required
    finally:
        runtime.shutdown()


def test_read_only_check_can_inspect_uncertain_changes_without_acknowledging(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path,
        [capability_call(1, "inspection"), ModelResponse.text("Inspected.")])
    uncertain(journal, tmp_path)
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.COMPLETED
        assert capability.values == ["inspection"]
        assert journal.get("interrupted-call").review_required
        assert journal.get("internal-call-1").result_success
    finally:
        runtime.shutdown()


def test_read_only_recovery_keeps_normal_permission_denials(tmp_path):
    from app.security.permissions import PermissionDecision
    runtime, model, capability, journal, _ = build_runtime(tmp_path,
        [capability_call(1), ModelResponse.text("Read denied.")], decision=PermissionDecision.DENY)
    uncertain(journal, tmp_path)
    try:
        result = run(runtime, tmp_path)
        assert result.settled_calls[0].result.error.code == CapabilityErrorCode.PERMISSION_DENIED
        assert journal.get("internal-call-1").state == CallLifecycleState.DENIED
        assert journal.get("interrupted-call").review_required and not capability.values
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("permission", [PermissionClass.WRITE, PermissionClass.EXECUTE, PermissionClass.SYSTEM])
def test_uncertain_outcome_blocks_new_changes_before_approval_or_execution(tmp_path, permission):
    class Mutation(EchoCapability):
        pass
    Mutation.permission = permission
    runtime, model, capability, journal, manager = build_runtime(tmp_path,
        [capability_call(1)], capability=Mutation())
    uncertain(journal, tmp_path)
    try:
        settled = []
        result = runtime.run([{"role": "user", "content": "Try a new operation."}],
            session_id="session-1", turn_id="turn-2", portable_root=tmp_path,
            allowed_read_roots=(tmp_path,), settled_observer=settled.append)
        assert result.status == AgentRunStatus.INTERNAL_FAILURE
        assert "Review interrupted operations" in result.message
        assert len(model.requests) == 1 and not capability.values
        assert len(journal.records) == 1
        assert settled[0].result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    finally:
        runtime.shutdown()


def service_for(runtime, model, root):
    return ConversationService(model, ConversationStore(root / "conversation.json"),
        agent_runtime=runtime, portable_root=root)


def test_explicit_review_retains_unknown_state_and_is_durable_without_replay(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [])
    uncertain(journal, tmp_path)
    service = service_for(runtime, model, tmp_path)
    try:
        snapshot = service.operation_review()
        assert snapshot.required and not snapshot.restart_required
        assert snapshot.operations[0].capability == "test.journal"
        assert "private" not in repr(snapshot)
        uncertain(journal, tmp_path, call_id="another-interruption")
        service.acknowledge_operation_review(tuple(item.call_id for item in snapshot.operations))
        assert journal.get("interrupted-call").state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
        assert not journal.get("interrupted-call").review_required
        assert journal.get("another-interruption").review_required
        recovered = CapabilityCrashJournal(journal.path)
        assert not recovered.get("interrupted-call").review_required
        assert len(recovered.review_required) == 1
        assert not model.requests and not capability.values
    finally:
        service.shutdown()


def test_review_is_atomic_and_failure_preserves_pending_records(tmp_path, monkeypatch):
    import app.execution.audit as audit
    journal = CapabilityCrashJournal(tmp_path / "journal.json")
    uncertain(journal, tmp_path, call_id="first")
    uncertain(journal, tmp_path, call_id="second")
    before = journal.path.read_bytes()
    with pytest.raises(LifecycleTransitionError):
        journal.acknowledge_unknown_outcomes(("first", "missing"))
    assert journal.path.read_bytes() == before
    def fail(*args):
        raise OSError("private storage path")
    monkeypatch.setattr(audit, "_atomic_replace", fail)
    with pytest.raises(CrashJournalPersistenceError):
        journal.acknowledge_unknown_outcomes(("first", "second"))
    assert journal.path.read_bytes() == before and len(journal.review_required) == 2


@pytest.mark.parametrize("ids", [(), ("one", "one"), ["one"], (1,)])
def test_review_requires_an_explicit_valid_operation_snapshot(tmp_path, ids):
    journal = CapabilityCrashJournal(tmp_path / "journal.json")
    with pytest.raises(ValueError):
        journal.acknowledge_unknown_outcomes(ids)


def test_service_rejects_review_during_turn_after_close_or_before_restart(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [])
    uncertain(journal, tmp_path)
    service = service_for(runtime, model, tmp_path)
    try:
        service._run_lock.acquire()
        with pytest.raises(RuntimeError, match="Finish or stop"):
            service.acknowledge_operation_review(("interrupted-call",))
        service._run_lock.release()
        runtime.executor._persistence_failed = True
        assert service.operation_review().restart_required
        with pytest.raises(RuntimeError, match="Restart"):
            service.acknowledge_operation_review(("interrupted-call",))
        assert journal.get("interrupted-call").review_required
        service.shutdown()
        with pytest.raises(RuntimeError, match="closed"):
            service.acknowledge_operation_review(("interrupted-call",))
    finally:
        service.shutdown()


def test_persistence_failure_still_allows_chat_but_blocks_tools_until_restart(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path,
        [ModelResponse.text("Hello."), capability_call(1)])
    runtime.executor._persistence_failed = True
    try:
        assert run(runtime, tmp_path).status == AgentRunStatus.COMPLETED
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INTERNAL_FAILURE
        assert "Restart O.R.S.I" in result.message
        assert not capability.values and not journal.records
    finally:
        runtime.shutdown()


def test_executor_guard_cannot_be_bypassed_and_review_does_not_reauthorize_old_call(tmp_path):
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [])
    interrupted = uncertain(journal, tmp_path)
    new_write = prepare_capability_call(InterruptedWrite(), {"value": "fresh"}, context(tmp_path, call_id="new"))
    journal.record_prepared(new_write)
    authorization = allow(new_write)
    journal.record_authorization(new_write, authorization)
    try:
        with pytest.raises(LifecycleTransitionError, match="Review interrupted"):
            runtime.executor.execute(new_write, authorization)
        assert journal.get("new").state == CallLifecycleState.AUTHORIZED
        journal.acknowledge_unknown_outcome(interrupted.request.call_id)
        with pytest.raises(LifecycleTransitionError):
            runtime.executor.execute(interrupted, allow(interrupted))
        assert journal.get("interrupted-call").state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
    finally:
        runtime.shutdown()


def test_restart_review_then_fresh_write_keeps_normal_approval_and_prior_task_unfinished(tmp_path):
    from tests.test_turn_outcomes import edit_service, edit_call
    target = tmp_path / "note.txt"
    target.write_bytes(b"old")
    service, _ = edit_service(tmp_path, [])
    uncertain(service.agent_runtime.executor.journal, service.portable_root)
    service.shutdown()
    service, approvals = edit_service(tmp_path, [ModelResponse.text("Hello."),
        edit_call(target), edit_call(target), ModelResponse.text("The edit succeeded.")])
    try:
        assert service.run("Hello") == "Hello."
        with pytest.raises(RuntimeError, match="Review interrupted operations"):
            service.run("Edit the text file")
        blocked_turn = service.store.turns()[-1]
        assert blocked_turn.outcome.status == AgentRunStatus.INTERNAL_FAILURE
        assert approvals == [] and target.read_bytes() == b"old"
        snapshot = service.operation_review()
        service.acknowledge_operation_review(tuple(item.call_id for item in snapshot.operations))
        assert not service.operation_review().required
        assert service.run("Edit the text file") == "The edit succeeded."
        assert len(approvals) == 1 and target.read_bytes() == b"new"
        assert service.store.turns()[1].outcome.status == AgentRunStatus.INTERNAL_FAILURE
        record = service.agent_runtime.executor.journal.get("interrupted-call")
        assert record.state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
        assert record.result_success is None and not record.review_required
    finally:
        service.shutdown()
