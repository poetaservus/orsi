from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

import app.capabilities.crash_journal as crash_journal_module
from app.capabilities import (
    ApprovalManager,
    ApprovalStatus,
    CallLifecycleState,
    Capability,
    CapabilityContext,
    CapabilityCrashJournal,
    CapabilityErrorCode,
    CapabilityExecutor,
    CapabilityFailure,
    CapabilityResult,
    CrashJournalCorruptionError,
    CrashJournalPersistenceError,
    DuplicateCallIdError,
    ExecutionIsolation,
    FilesystemStatCapability,
    JournaledCapabilityExecutor,
    JournalRetentionPolicy,
    LifecycleTransitionError,
    PermissionClass,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
    prepare_capability_call,
)
from app.runtime.cancellation import CancellationSource


class JournalArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


class RecordingCapability(Capability[JournalArguments]):
    name = "test.journal"
    description = "Record a bounded value for crash-journal tests."
    arguments_model = JournalArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def __init__(self, observer=None):
        self.execution_count = 0
        self.observer = observer

    def execute(self, arguments, context):
        self.execution_count += 1
        if self.observer is not None:
            self.observer()
        return {"value": arguments.value}


class FixedClock:
    def __init__(self, value: int = 1_000):
        self.value = value

    def __call__(self) -> int:
        return self.value


def context(root: Path, *, call_id: str = "call-1") -> CapabilityContext:
    return CapabilityContext(
        call_id=call_id,
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=(root,),
        cancellation=CancellationSource().token,
    )


def prepare(
    root: Path,
    *,
    capability=None,
    call_id: str = "call-1",
    value: str = "hello",
):
    implementation = capability or RecordingCapability()
    return implementation, prepare_capability_call(
        implementation,
        {"value": value},
        context(root, call_id=call_id),
    )


def allow(prepared):
    evaluation = PermissionGate(
        [PermissionRule("allow-journal", PermissionDecision.ALLOW)]
    ).evaluate(prepared)
    return ApprovalManager().authorize(evaluation)


def ask_required(prepared):
    evaluation = PermissionGate(
        [PermissionRule("ask-journal", PermissionDecision.ASK)]
    ).evaluate(prepared)
    return ApprovalManager().authorize(evaluation)


def authorize_for_execution(journal, prepared):
    authorization = allow(prepared)
    journal.record_authorization(prepared, authorization)
    return authorization


def raw_state(path: Path, call_id: str) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    return next(
        record["state"]
        for record in document["records"]
        if record["call_id"] == call_id
    )


def test_prepared_record_persists_only_privacy_safe_identity_digests(tmp_path: Path):
    secret = "PRIVATE-JOURNAL-MARKER"
    target = tmp_path / f"{secret}.txt"
    target.write_text(secret, encoding="utf-8")
    prepared = prepare_capability_call(
        FilesystemStatCapability(),
        {"path": str(target)},
        context(tmp_path),
    )
    path = tmp_path / "calls.json"
    journal = CapabilityCrashJournal(path, clock_ms=FixedClock())

    record = journal.record_prepared(prepared)

    persisted = path.read_text(encoding="utf-8")
    assert record.state == CallLifecycleState.PREPARED
    assert record.arguments_sha256 == prepared.request.arguments_sha256
    assert record.request_sha256 == prepared.request.request_sha256
    assert record.resource_sha256 is not None
    assert secret not in persisted
    assert prepared.request.arguments_json not in persisted
    assert str(target.resolve()) not in persisted
    assert set(json.loads(persisted)) == {"schema_version", "records"}


def test_journaled_executor_writes_running_before_execution_and_result_before_return(
    tmp_path: Path,
):
    path = tmp_path / "calls.json"
    journal = CapabilityCrashJournal(path, clock_ms=FixedClock())
    observed = []

    def observe_running():
        observed.append(journal.get("call-1").state)
        observed.append(CallLifecycleState(raw_state(path, "call-1")))

    capability = RecordingCapability(observer=observe_running)
    _, prepared = prepare(
        tmp_path,
        capability=capability,
        value="PRIVATE-RESULT-MARKER",
    )
    journal.record_prepared(prepared)
    authorization = authorize_for_execution(journal, prepared)

    result = JournaledCapabilityExecutor(
        CapabilityExecutor(), journal
    ).execute(prepared, authorization)

    assert result.success
    assert capability.execution_count == 1
    assert observed == [CallLifecycleState.RUNNING, CallLifecycleState.RUNNING]
    assert journal.get("call-1").state == CallLifecycleState.COMPLETED
    assert raw_state(path, "call-1") == CallLifecycleState.COMPLETED.value
    assert "PRIVATE-RESULT-MARKER" not in path.read_text(encoding="utf-8")
    assert CapabilityCrashJournal(path, clock_ms=FixedClock()).get(
        "call-1"
    ).state == CallLifecycleState.COMPLETED


@pytest.mark.parametrize(
    "state",
    [
        CallLifecycleState.PREPARED,
        CallLifecycleState.AWAITING_APPROVAL,
        CallLifecycleState.AUTHORIZED,
    ],
)
def test_restart_marks_every_pre_execution_state_interrupted_without_replay(
    tmp_path: Path,
    state: CallLifecycleState,
):
    path = tmp_path / f"{state.value}.json"
    clock = FixedClock()
    journal = CapabilityCrashJournal(path, clock_ms=clock)
    capability, prepared = prepare(tmp_path)
    journal.record_prepared(prepared)
    if state == CallLifecycleState.AWAITING_APPROVAL:
        journal.record_authorization(prepared, ask_required(prepared))
    elif state == CallLifecycleState.AUTHORIZED:
        authorize_for_execution(journal, prepared)

    recovered = CapabilityCrashJournal(path, clock_ms=clock)

    assert recovered.get("call-1").state == CallLifecycleState.INTERRUPTED_BEFORE_EXECUTION
    assert capability.execution_count == 0
    with pytest.raises(LifecycleTransitionError):
        recovered.mark_running(prepared, allow(prepared))
    assert capability.execution_count == 0


class SimulatedProcessCrash(BaseException):
    pass


class CrashAfterSideEffectExecutor(CapabilityExecutor):
    def __init__(self, side_effects: list[str]):
        super().__init__()
        self.side_effects = side_effects

    def execute(self, prepared, authorization):
        self.side_effects.append(prepared.request.call_id)
        raise SimulatedProcessCrash()


class MustNotRunExecutor(CapabilityExecutor):
    def __init__(self):
        super().__init__()
        self.execution_count = 0

    def execute(self, prepared, authorization):
        self.execution_count += 1
        raise AssertionError("Recovered calls must never be replayed.")


class ResultPersistenceFailureJournal(CapabilityCrashJournal):
    def record_result(self, result):
        raise CrashJournalPersistenceError("simulated result persistence failure")


def test_forced_crash_after_side_effect_becomes_unknown_and_cannot_execute_twice(
    tmp_path: Path,
):
    path = tmp_path / "calls.json"
    clock = FixedClock()
    journal = CapabilityCrashJournal(path, clock_ms=clock)
    _, prepared = prepare(tmp_path)
    journal.record_prepared(prepared)
    authorization = authorize_for_execution(journal, prepared)
    side_effects = []

    with pytest.raises(SimulatedProcessCrash):
        JournaledCapabilityExecutor(
            CrashAfterSideEffectExecutor(side_effects), journal
        ).execute(prepared, authorization)

    assert raw_state(path, "call-1") == CallLifecycleState.RUNNING.value
    recovered = CapabilityCrashJournal(path, clock_ms=clock)
    assert recovered.get("call-1").state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
    assert recovered.review_required == (recovered.get("call-1"),)

    executor = MustNotRunExecutor()
    with pytest.raises(LifecycleTransitionError):
        JournaledCapabilityExecutor(executor, recovered).execute(
            prepared,
            authorization,
        )

    assert side_effects == ["call-1"]
    assert executor.execution_count == 0


def test_result_is_not_returned_when_terminal_persistence_fails(tmp_path: Path):
    path = tmp_path / "calls.json"
    journal = ResultPersistenceFailureJournal(path, clock_ms=FixedClock())
    capability, prepared = prepare(tmp_path)
    journal.record_prepared(prepared)
    authorization = authorize_for_execution(journal, prepared)
    wrapped = JournaledCapabilityExecutor(CapabilityExecutor(), journal)

    with pytest.raises(CrashJournalPersistenceError):
        wrapped.execute(prepared, authorization)

    assert capability.execution_count == 1
    assert raw_state(path, "call-1") == CallLifecycleState.RUNNING.value
    with pytest.raises(LifecycleTransitionError):
        wrapped.execute(prepared, authorization)
    assert capability.execution_count == 1
    assert CapabilityCrashJournal(path, clock_ms=FixedClock()).get(
        "call-1"
    ).state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME


@pytest.mark.parametrize(
    ("error_code", "expected_state"),
    [
        (CapabilityErrorCode.NOT_FOUND, CallLifecycleState.FAILED),
        (CapabilityErrorCode.PERMISSION_DENIED, CallLifecycleState.DENIED),
        (CapabilityErrorCode.CANCELLED, CallLifecycleState.CANCELLED),
        (CapabilityErrorCode.TIMED_OUT, CallLifecycleState.TIMED_OUT),
    ],
)
def test_normalized_results_map_to_stable_terminal_states(
    tmp_path: Path,
    error_code: CapabilityErrorCode,
    expected_state: CallLifecycleState,
):
    path = tmp_path / f"{error_code.value}.json"
    journal = CapabilityCrashJournal(path, clock_ms=FixedClock())
    _, prepared = prepare(tmp_path)
    journal.record_prepared(prepared)
    authorization = authorize_for_execution(journal, prepared)
    journal.mark_running(prepared, authorization)
    result = CapabilityResult(
        call_id="call-1",
        capability="test.journal",
        success=False,
        error=CapabilityFailure(code=error_code, message="A stable failure."),
        duration_ms=7,
    )

    record = journal.record_result(result)
    reopened = CapabilityCrashJournal(path, clock_ms=FixedClock())

    assert record.state == expected_state
    assert record.error_code == error_code
    assert record.outcome_sha256 is not None
    assert reopened.get("call-1") == record


def test_permission_outcomes_cover_waiting_denial_cancellation_and_expiry(
    tmp_path: Path,
):
    outcomes = {}
    for suffix in ("waiting", "denied", "cancelled", "expired"):
        path = tmp_path / f"{suffix}.json"
        journal = CapabilityCrashJournal(path, clock_ms=FixedClock())
        _, prepared = prepare(tmp_path, call_id=f"call-{suffix}")
        journal.record_prepared(prepared)
        evaluation = PermissionGate(
            [PermissionRule("ask-journal", PermissionDecision.ASK)]
        ).evaluate(prepared)
        manager = ApprovalManager(id_factory=lambda: f"approval-{suffix}")

        if suffix == "waiting":
            authorization = manager.authorize(evaluation)
        elif suffix == "denied":
            request = manager.request(evaluation, now=1.0)
            manager.resolve(request.approval_id, ApprovalStatus.DENIED, now=2.0)
            authorization = manager.authorize(
                evaluation, approval_id=request.approval_id, now=2.0
            )
        elif suffix == "cancelled":
            request = manager.request(evaluation, now=1.0)
            source = CancellationSource()
            source.cancel("stop")
            authorization = manager.authorize(
                evaluation,
                approval_id=request.approval_id,
                cancellation=source.token,
                now=2.0,
            )
        else:
            request = manager.request(evaluation, ttl_seconds=1.0, now=1.0)
            authorization = manager.authorize(
                evaluation, approval_id=request.approval_id, now=2.0
            )

        outcomes[suffix] = journal.record_authorization(
            prepared, authorization
        ).state

    assert outcomes == {
        "waiting": CallLifecycleState.AWAITING_APPROVAL,
        "denied": CallLifecycleState.DENIED,
        "cancelled": CallLifecycleState.CANCELLED,
        "expired": CallLifecycleState.TIMED_OUT,
    }


def test_atomic_replace_failure_preserves_previous_file_and_memory_state(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "calls.json"
    journal = CapabilityCrashJournal(path, clock_ms=FixedClock())
    _, prepared = prepare(tmp_path)
    journal.record_prepared(prepared)
    previous = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(crash_journal_module.os, "replace", fail_replace)

    with pytest.raises(CrashJournalPersistenceError):
        journal.record_authorization(prepared, allow(prepared))

    assert journal.get("call-1").state == CallLifecycleState.PREPARED
    assert path.read_bytes() == previous
    assert not path.with_name(path.name + ".tmp").exists()


def test_corrupted_journal_fails_closed_without_overwriting_evidence(tmp_path: Path):
    path = tmp_path / "calls.json"
    corrupted = b'{"schema_version":1,"records":[PRIVATE-CORRUPTION]}'
    path.write_bytes(corrupted)

    with pytest.raises(CrashJournalCorruptionError) as caught:
        CapabilityCrashJournal(path)

    assert "corrupted" in str(caught.value)
    assert path.read_bytes() == corrupted


def test_duplicate_call_ids_and_changed_call_identity_are_rejected(tmp_path: Path):
    path = tmp_path / "calls.json"
    journal = CapabilityCrashJournal(path, clock_ms=FixedClock())
    _, first = prepare(tmp_path, value="first")
    _, changed = prepare(tmp_path, value="changed")
    journal.record_prepared(first)

    with pytest.raises(DuplicateCallIdError):
        journal.record_prepared(changed)

    authorization = authorize_for_execution(journal, first)
    with pytest.raises(LifecycleTransitionError):
        journal.mark_running(changed, authorization)
    assert journal.get("call-1").state == CallLifecycleState.AUTHORIZED


def test_unsafe_identifiers_cannot_be_written_to_durable_state(tmp_path: Path):
    journal = CapabilityCrashJournal(tmp_path / "calls.json", clock_ms=FixedClock())
    _, prepared = prepare(tmp_path, call_id="PRIVATE ID WITH SPACES")

    with pytest.raises(LifecycleTransitionError, match="not safe"):
        journal.record_prepared(prepared)

    assert journal.records == ()
    assert not journal.path.exists()


def test_purge_keeps_unknown_outcome_until_explicit_review_and_retention(
    tmp_path: Path,
):
    path = tmp_path / "calls.json"
    clock = FixedClock()
    journal = CapabilityCrashJournal(path, clock_ms=clock)
    _, before = prepare(tmp_path, call_id="call-before")
    _, running = prepare(tmp_path, call_id="call-running")
    journal.record_prepared(before)
    journal.record_prepared(running)
    authorization = authorize_for_execution(journal, running)
    journal.mark_running(running, authorization)

    recovered = CapabilityCrashJournal(path, clock_ms=clock)
    assert recovered.get("call-before").state == CallLifecycleState.INTERRUPTED_BEFORE_EXECUTION
    assert recovered.get("call-running").review_required

    assert recovered.purge(now_ms=1_000) == ("call-before",)
    assert recovered.get("call-running").review_required
    acknowledged = recovered.acknowledge_unknown_outcome("call-running")
    assert not acknowledged.review_required

    policy = JournalRetentionPolicy(
        acknowledged_unknown_retention_seconds=10
    )
    assert recovered.purge(policy, now_ms=10_999) == ()
    assert recovered.purge(policy, now_ms=11_000) == ("call-running",)
    assert recovered.records == ()


def test_production_entrypoints_remain_disconnected_from_crash_journal():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "app/main.py",
        "app/conversation/service.py",
        "app/conversation/prompt.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "CapabilityCrashJournal" not in text
        assert "JournaledCapabilityExecutor" not in text
        assert "app.capabilities" not in text
