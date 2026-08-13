from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Event, Thread
from time import monotonic

import pytest
from pydantic import BaseModel, ConfigDict

from app.capabilities import (
    ApprovalManager,
    ApprovalStatus,
    AuthorizationCode,
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    CapabilityExecutor,
    ExecutionIsolation,
    ExecutorLimits,
    PermissionClass,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
    prepare_capability_call,
)
from app.runtime.cancellation import CancellationSource


class ExecutorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


class RecordingCapability(Capability[ExecutorArguments]):
    name = "test.record"
    description = "Return a test value through the isolated capability executor."
    arguments_model = ExecutorArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def __init__(self):
        self.execution_count = 0

    def execute(self, arguments, context):
        self.execution_count += 1
        return {"value": arguments.value}


class ExpectedFailureCapability(RecordingCapability):
    name = "test.expected_failure"

    def execute(self, arguments, context):
        self.execution_count += 1
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested test resource does not exist.",
        )


class UnexpectedFailureCapability(RecordingCapability):
    name = "test.unexpected_failure"

    def execute(self, arguments, context):
        self.execution_count += 1
        raise RuntimeError("private-exception-text")


class InvalidOutputCapability(RecordingCapability):
    name = "test.invalid_output"

    def execute(self, arguments, context):
        self.execution_count += 1
        return {"invalid": {1, 2, 3}}


class OversizedOutputCapability(RecordingCapability):
    name = "test.oversized_output"

    def execute(self, arguments, context):
        self.execution_count += 1
        return {"content": arguments.value * 4_096}


class CooperativeTimeoutCapability(RecordingCapability):
    name = "test.cooperative_timeout"
    timeout_seconds = 0.03

    def execute(self, arguments, context):
        self.execution_count += 1
        while not context.cancellation.wait(0.005):
            pass
        context.cancellation.raise_if_cancelled()
        raise AssertionError("unreachable")


class BlockingCapability(RecordingCapability):
    name = "test.blocking"

    def __init__(self, *, timeout_seconds: float = 1.0):
        super().__init__()
        self.timeout_seconds = timeout_seconds
        self.started = Event()
        self.release = Event()

    def execute(self, arguments, context):
        self.execution_count += 1
        self.started.set()
        self.release.wait(2.0)
        return {"value": arguments.value}


class IsolatedCapability(RecordingCapability):
    name = "test.isolated"
    execution_isolation = ExecutionIsolation.SUBPROCESS_REQUIRED


def context(
    root: Path,
    *,
    call_id: str = "call-1",
    cancellation=None,
) -> CapabilityContext:
    return CapabilityContext(
        call_id=call_id,
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=(root,),
        cancellation=cancellation or CancellationSource().token,
    )


def prepare(
    capability,
    root: Path,
    *,
    call_id: str = "call-1",
    value: str = "hello",
    cancellation=None,
):
    return prepare_capability_call(
        capability,
        {"value": value},
        context(root, call_id=call_id, cancellation=cancellation),
    )


def allow(prepared):
    evaluation = PermissionGate(
        [PermissionRule("allow-test", PermissionDecision.ALLOW)]
    ).evaluate(prepared)
    return ApprovalManager().authorize(evaluation)


def ask(prepared):
    evaluation = PermissionGate(
        [PermissionRule("ask-test", PermissionDecision.ASK)]
    ).evaluate(prepared)
    manager = ApprovalManager(id_factory=lambda: f"approval-{prepared.request.call_id}")
    request = manager.request(evaluation, now=1.0)
    manager.resolve(request.approval_id, ApprovalStatus.APPROVED, now=2.0)
    return manager.authorize(evaluation, approval_id=request.approval_id, now=2.0)


def test_executor_runs_one_exactly_authorized_prepared_call(tmp_path: Path):
    capability = RecordingCapability()
    prepared = prepare(capability, tmp_path)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert result.success
    assert result.output == {"value": "hello"}
    assert result.metadata == {
        "permission": "read",
        "execution_isolation": "in_process_cooperative",
        "result_schema_version": 1,
        "executor_schema_version": 1,
        "output_limited": False,
        "executor_poisoned": False,
        "output_utf8_bytes": len(b'{"value":"hello"}'),
    }
    assert capability.execution_count == 1


def test_executor_rejects_denied_authorization_without_executing(tmp_path: Path):
    capability = RecordingCapability()
    prepared = prepare(capability, tmp_path)
    denied = PermissionGate().evaluate(prepared)
    authorization = ApprovalManager().authorize(denied)

    result = CapabilityExecutor().execute(prepared, authorization)

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    assert capability.execution_count == 0


def test_executor_rejects_authorization_for_a_different_call(tmp_path: Path):
    capability = RecordingCapability()
    first = prepare(capability, tmp_path, call_id="call-1")
    second = prepare(capability, tmp_path, call_id="call-2")

    result = CapabilityExecutor().execute(second, allow(first))

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    assert capability.execution_count == 0


def test_ask_approval_executes_once_and_executor_rejects_replay(tmp_path: Path):
    capability = RecordingCapability()
    prepared = prepare(capability, tmp_path)
    authorization = ask(prepared)
    executor = CapabilityExecutor()

    first = executor.execute(prepared, authorization)
    replay = executor.execute(prepared, authorization)

    assert first.success
    assert not replay.success
    assert replay.error.code == CapabilityErrorCode.CALL_REPLAYED
    assert capability.execution_count == 1


def test_expected_capability_failure_is_normalized(tmp_path: Path):
    capability = ExpectedFailureCapability()
    prepared = prepare(capability, tmp_path)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert not result.success
    assert result.error.model_dump(mode="json") == {
        "code": "not_found",
        "message": "The requested test resource does not exist.",
        "details": [],
    }


def test_unexpected_failure_does_not_leak_raw_exception_text(tmp_path: Path):
    capability = UnexpectedFailureCapability()
    prepared = prepare(capability, tmp_path)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert not result.success
    assert result.error.code == CapabilityErrorCode.INTERNAL_ERROR
    assert "private-exception-text" not in result.model_dump_json()


def test_non_json_output_is_rejected(tmp_path: Path):
    capability = InvalidOutputCapability()
    prepared = prepare(capability, tmp_path)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert not result.success
    assert result.error.code == CapabilityErrorCode.INVALID_OUTPUT


def test_oversized_output_is_replaced_by_bounded_preview_and_digest(tmp_path: Path):
    capability = OversizedOutputCapability()
    prepared = prepare(capability, tmp_path, value="ø")
    limits = ExecutorLimits(
        max_output_bytes=1_024,
        max_output_preview_bytes=128,
    )

    result = CapabilityExecutor(limits).execute(prepared, allow(prepared))

    full_output = {"content": "ø" * 4_096}
    canonical = json.dumps(
        full_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    limited = result.output["_orsi_output_limited"]
    assert result.success
    assert result.metadata["output_limited"] is True
    assert result.metadata["output_utf8_bytes"] == len(canonical)
    assert limited["original_utf8_bytes"] == len(canonical)
    assert limited["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert len(result.model_dump_json().encode("utf-8")) < len(canonical)


def test_cooperative_timeout_returns_stable_failure_without_poisoning(tmp_path: Path):
    capability = CooperativeTimeoutCapability()
    prepared = prepare(capability, tmp_path)
    executor = CapabilityExecutor(
        ExecutorLimits(cancellation_grace_seconds=0.1)
    )

    result = executor.execute(prepared, allow(prepared))

    assert not result.success
    assert result.error.code == CapabilityErrorCode.TIMED_OUT
    assert not executor.snapshot.poisoned


def test_pre_execution_cancellation_never_starts_capability(tmp_path: Path):
    source = CancellationSource()
    source.cancel("stop")
    capability = RecordingCapability()
    prepared = prepare(capability, tmp_path, cancellation=source.token)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert result.error.code == CapabilityErrorCode.CANCELLED
    assert capability.execution_count == 0


def test_in_flight_cancellation_reaches_cooperative_capability(tmp_path: Path):
    source = CancellationSource()
    capability = CooperativeTimeoutCapability()
    capability.timeout_seconds = 1.0
    prepared = prepare(capability, tmp_path, cancellation=source.token)
    executor = CapabilityExecutor()
    holder = {}

    thread = Thread(
        target=lambda: holder.setdefault(
            "result", executor.execute(prepared, allow(prepared))
        )
    )
    thread.start()
    deadline = monotonic() + 1.0
    while capability.execution_count == 0 and monotonic() < deadline:
        Event().wait(0.005)
    source.cancel("stop")
    thread.join(1.0)

    assert not thread.is_alive()
    assert holder["result"].error.code == CapabilityErrorCode.CANCELLED
    assert not executor.snapshot.poisoned


def test_uncooperative_timeout_poisons_executor_until_restart(tmp_path: Path):
    capability = BlockingCapability(timeout_seconds=0.02)
    prepared = prepare(capability, tmp_path, call_id="call-blocked")
    executor = CapabilityExecutor(
        ExecutorLimits(cancellation_grace_seconds=0.01)
    )

    result = executor.execute(prepared, allow(prepared))
    capability.release.set()
    next_capability = RecordingCapability()
    next_prepared = prepare(next_capability, tmp_path, call_id="call-next")
    rejected = executor.execute(next_prepared, allow(next_prepared))

    assert result.error.code == CapabilityErrorCode.TIMED_OUT
    assert result.metadata["executor_poisoned"] is True
    assert executor.snapshot.poisoned
    assert rejected.error.code == CapabilityErrorCode.EXECUTOR_UNAVAILABLE
    assert next_capability.execution_count == 0


def test_executor_is_sequential_and_busy_call_can_retry_later(tmp_path: Path):
    blocking = BlockingCapability()
    first = prepare(blocking, tmp_path, call_id="call-first")
    second_capability = RecordingCapability()
    second = prepare(second_capability, tmp_path, call_id="call-second")
    executor = CapabilityExecutor()
    holder = {}

    thread = Thread(
        target=lambda: holder.setdefault(
            "result", executor.execute(first, allow(first))
        )
    )
    thread.start()
    assert blocking.started.wait(1.0)
    busy = executor.execute(second, allow(second))
    blocking.release.set()
    thread.join(1.0)
    retried = executor.execute(second, allow(second))

    assert holder["result"].success
    assert busy.error.code == CapabilityErrorCode.EXECUTOR_BUSY
    assert retried.success
    assert second_capability.execution_count == 1


def test_subprocess_required_capability_fails_closed_without_running(tmp_path: Path):
    capability = IsolatedCapability()
    prepared = prepare(capability, tmp_path)

    result = CapabilityExecutor().execute(prepared, allow(prepared))

    assert result.error.code == CapabilityErrorCode.ISOLATION_REQUIRED
    assert capability.execution_count == 0


def test_shutdown_cancels_active_call_and_rejects_future_calls(tmp_path: Path):
    capability = CooperativeTimeoutCapability()
    capability.timeout_seconds = 1.0
    prepared = prepare(capability, tmp_path, call_id="call-active")
    executor = CapabilityExecutor()
    holder = {}
    thread = Thread(
        target=lambda: holder.setdefault(
            "result", executor.execute(prepared, allow(prepared))
        )
    )
    thread.start()
    deadline = monotonic() + 1.0
    while capability.execution_count == 0 and monotonic() < deadline:
        Event().wait(0.005)

    executor.shutdown()
    thread.join(1.0)
    later = RecordingCapability()
    later_prepared = prepare(later, tmp_path, call_id="call-later")
    rejected = executor.execute(later_prepared, allow(later_prepared))

    assert not thread.is_alive()
    assert holder["result"].error.code == CapabilityErrorCode.CANCELLED
    assert rejected.error.code == CapabilityErrorCode.EXECUTOR_UNAVAILABLE
    assert later.execution_count == 0


@pytest.mark.parametrize(
    "limits",
    [
        {"max_output_bytes": 511},
        {"max_output_bytes": 1_024, "max_output_preview_bytes": 1_024},
        {"cancellation_grace_seconds": 0},
        {"poll_interval_seconds": 1},
    ],
)
def test_executor_limits_reject_unsafe_configuration(limits):
    with pytest.raises(ValueError):
        ExecutorLimits(**limits)


def test_production_entrypoints_remain_disconnected_from_executor():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "app/main.py",
        "app/conversation/service.py",
        "app/conversation/prompt.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "CapabilityExecutor" not in text
        assert "app.capabilities" not in text
