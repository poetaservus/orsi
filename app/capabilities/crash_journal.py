from __future__ import annotations

import hashlib
import json
import os
from enum import StrEnum
from pathlib import Path
from threading import RLock
from time import time_ns
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.capabilities.contracts import (
    CapabilityErrorCode,
    CapabilityResult,
    PermissionClass,
)
from app.capabilities.executor import CapabilityExecutor
from app.capabilities.permissions import (
    AuthorizationCode,
    PermissionAuthorization,
    PreparedCapabilityCall,
)


_JOURNAL_SCHEMA_VERSION = 1
_MAX_JOURNAL_BYTES = 8 * 1024 * 1024
_MAX_RECORDS = 10_000
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_CAPABILITY_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"


class CallLifecycleState(StrEnum):
    PREPARED = "prepared"
    AWAITING_APPROVAL = "awaiting_approval"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED_BEFORE_EXECUTION = "interrupted_before_execution"
    INTERRUPTED_UNKNOWN_OUTCOME = "interrupted_unknown_outcome"


_PRE_EXECUTION_STATES = {
    CallLifecycleState.PREPARED,
    CallLifecycleState.AWAITING_APPROVAL,
    CallLifecycleState.AUTHORIZED,
}
_RESULT_TERMINAL_STATES = {
    CallLifecycleState.COMPLETED,
    CallLifecycleState.FAILED,
    CallLifecycleState.DENIED,
    CallLifecycleState.CANCELLED,
    CallLifecycleState.TIMED_OUT,
}
_TERMINAL_STATES = _RESULT_TERMINAL_STATES | {
    CallLifecycleState.INTERRUPTED_BEFORE_EXECUTION,
    CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME,
}
_ALLOWED_TRANSITIONS = {
    CallLifecycleState.PREPARED: {
        CallLifecycleState.AWAITING_APPROVAL,
        CallLifecycleState.AUTHORIZED,
        CallLifecycleState.DENIED,
        CallLifecycleState.CANCELLED,
        CallLifecycleState.TIMED_OUT,
    },
    CallLifecycleState.AWAITING_APPROVAL: {
        CallLifecycleState.AUTHORIZED,
        CallLifecycleState.DENIED,
        CallLifecycleState.CANCELLED,
        CallLifecycleState.TIMED_OUT,
    },
    CallLifecycleState.AUTHORIZED: {CallLifecycleState.RUNNING},
    CallLifecycleState.RUNNING: _RESULT_TERMINAL_STATES,
}


class CrashJournalError(RuntimeError):
    """Base class for stable, fail-closed crash-journal failures."""


class CrashJournalCorruptionError(CrashJournalError):
    pass


class CrashJournalPersistenceError(CrashJournalError):
    pass


class DuplicateCallIdError(CrashJournalError):
    pass


class LifecycleTransitionError(CrashJournalError):
    pass


class CallLifecycleRecord(BaseModel):
    """Privacy-safe durable identity and state for one capability call."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    call_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    session_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    turn_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    capability: str = Field(min_length=3, max_length=128, pattern=_CAPABILITY_PATTERN)
    permission: PermissionClass
    arguments_sha256: str = Field(pattern=_SHA256_PATTERN)
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    resource_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    authorization_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    state: CallLifecycleState
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    transition_sequence: int = Field(ge=0)
    outcome_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    result_success: bool | None = None
    error_code: CapabilityErrorCode | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    recovery_acknowledged_at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_lifecycle_fields(self):
        if self.updated_at_ms < self.created_at_ms:
            raise ValueError("Lifecycle update timestamps cannot precede creation.")

        has_outcome = self.outcome_sha256 is not None
        if self.state in _RESULT_TERMINAL_STATES:
            if not has_outcome or self.result_success is None or self.duration_ms is None:
                raise ValueError("Result terminal states require a bounded outcome identity.")
            if self.state == CallLifecycleState.COMPLETED:
                if not self.result_success or self.error_code is not None:
                    raise ValueError("Completed calls require a successful outcome.")
            elif self.result_success or self.error_code is None:
                raise ValueError("Failed terminal calls require a stable error code.")
        elif has_outcome or self.result_success is not None or self.error_code is not None or self.duration_ms is not None:
            raise ValueError("Non-result states cannot contain result details.")

        expected_errors = {
            CallLifecycleState.DENIED: CapabilityErrorCode.PERMISSION_DENIED,
            CallLifecycleState.CANCELLED: CapabilityErrorCode.CANCELLED,
            CallLifecycleState.TIMED_OUT: CapabilityErrorCode.TIMED_OUT,
        }
        expected_error = expected_errors.get(self.state)
        if expected_error is not None and self.error_code != expected_error:
            raise ValueError("The terminal state does not match its stable error code.")

        if self.state in {CallLifecycleState.AUTHORIZED, CallLifecycleState.RUNNING} and self.authorization_sha256 is None:
            raise ValueError("Authorized and running calls require an authorization digest.")
        if self.recovery_acknowledged_at_ms is not None:
            if self.state != CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME:
                raise ValueError("Only unknown outcomes can be recovery-acknowledged.")
            if self.recovery_acknowledged_at_ms < self.updated_at_ms:
                raise ValueError("Recovery acknowledgement cannot precede the record update.")
        return self

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    @property
    def review_required(self) -> bool:
        return (
            self.state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
            and self.recovery_acknowledged_at_ms is None
        )


class JournalRetentionPolicy(BaseModel):
    """Explicit privacy retention applied only when purge() is requested."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    terminal_retention_seconds: int = Field(default=0, ge=0, le=2_592_000)
    acknowledged_unknown_retention_seconds: int = Field(
        default=0,
        ge=0,
        le=2_592_000,
    )


class _JournalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1] = _JOURNAL_SCHEMA_VERSION
    records: tuple[CallLifecycleRecord, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_RECORDS,
    )

    @model_validator(mode="after")
    def reject_duplicate_call_ids(self):
        call_ids = [record.call_id for record in self.records]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("The crash journal contains duplicate call IDs.")
        return self


class CapabilityCrashJournal:
    """Atomic single-owner lifecycle journal that never stores raw call data."""

    def __init__(
        self,
        path: Path,
        *,
        clock_ms: Callable[[], int] = lambda: time_ns() // 1_000_000,
    ):
        self.path = Path(path)
        self._clock_ms = clock_ms
        self._lock = RLock()
        self._records = self._load()
        with self._lock:
            self._recover_incomplete_locked()

    @property
    def records(self) -> tuple[CallLifecycleRecord, ...]:
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))

    @property
    def review_required(self) -> tuple[CallLifecycleRecord, ...]:
        return tuple(record for record in self.records if record.review_required)

    def get(self, call_id: str) -> CallLifecycleRecord:
        with self._lock:
            record = self._records.get(str(call_id))
            if record is None:
                raise LifecycleTransitionError("The capability call is not recorded in the crash journal.")
            return record

    def record_prepared(self, prepared: PreparedCapabilityCall) -> CallLifecycleRecord:
        if not isinstance(prepared, PreparedCapabilityCall):
            raise TypeError("The crash journal accepts only PreparedCapabilityCall objects.")
        timestamp = self._timestamp()
        try:
            record = CallLifecycleRecord(
                **_prepared_identity(prepared),
                state=CallLifecycleState.PREPARED,
                created_at_ms=timestamp,
                updated_at_ms=timestamp,
                transition_sequence=0,
            )
        except ValidationError:
            raise LifecycleTransitionError(
                "The prepared call identity is not safe for durable storage."
            ) from None
        with self._lock:
            if record.call_id in self._records:
                raise DuplicateCallIdError("The capability call ID is already present in the crash journal.")
            if len(self._records) >= _MAX_RECORDS:
                raise CrashJournalPersistenceError("The capability crash journal reached its record limit.")
            proposed = dict(self._records)
            proposed[record.call_id] = record
            self._commit_locked(proposed)
            return record

    def record_authorization(
        self,
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> CallLifecycleRecord:
        if not isinstance(prepared, PreparedCapabilityCall):
            raise TypeError("Authorization journaling requires a prepared capability call.")
        if not isinstance(authorization, PermissionAuthorization):
            raise TypeError("Authorization journaling requires a PermissionAuthorization.")
        authorization_sha256 = _digest_json(
            authorization.model_dump(mode="json")
        )
        with self._lock:
            current = self._matching_record_locked(prepared)
            if authorization.request_sha256 != current.request_sha256:
                raise LifecycleTransitionError("The authorization does not match the journaled call.")

            if authorization.allowed:
                target = CallLifecycleState.AUTHORIZED
                outcome: dict[str, Any] = {}
            elif authorization.code == AuthorizationCode.APPROVAL_REQUIRED:
                target = CallLifecycleState.AWAITING_APPROVAL
                outcome = {}
            else:
                target, error_code = _authorization_terminal_state(authorization.code)
                outcome = {
                    "outcome_sha256": _digest_json(
                        {
                            "authorization_sha256": authorization_sha256,
                            "state": target.value,
                        }
                    ),
                    "result_success": False,
                    "error_code": error_code,
                    "duration_ms": 0,
                }

            return self._transition_locked(
                current,
                target,
                authorization_sha256=authorization_sha256,
                **outcome,
            )

    def mark_running(
        self,
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> CallLifecycleRecord:
        if not isinstance(prepared, PreparedCapabilityCall):
            raise TypeError("Running transitions require a prepared capability call.")
        if not isinstance(authorization, PermissionAuthorization):
            raise TypeError("Running transitions require a PermissionAuthorization.")
        authorization_sha256 = _digest_json(
            authorization.model_dump(mode="json")
        )
        with self._lock:
            current = self._matching_record_locked(prepared)
            if (
                not authorization.allowed
                or authorization.request_sha256 != current.request_sha256
                or authorization_sha256 != current.authorization_sha256
            ):
                raise LifecycleTransitionError("Execution requires the exact journaled authorization.")
            return self._transition_locked(current, CallLifecycleState.RUNNING)

    def record_result(self, result: CapabilityResult) -> CallLifecycleRecord:
        if not isinstance(result, CapabilityResult):
            raise TypeError("Result journaling requires a normalized CapabilityResult.")
        with self._lock:
            current = self._records.get(result.call_id)
            if current is None:
                raise LifecycleTransitionError("The result call is not recorded in the crash journal.")
            if result.capability != current.capability:
                raise LifecycleTransitionError("The result capability does not match the journaled call.")
            target = _result_terminal_state(result)
            return self._transition_locked(
                current,
                target,
                outcome_sha256=_digest_json(result.model_dump(mode="json")),
                result_success=result.success,
                error_code=result.error.code if result.error is not None else None,
                duration_ms=result.duration_ms,
            )

    def acknowledge_unknown_outcome(self, call_id: str) -> CallLifecycleRecord:
        with self._lock:
            current = self._records.get(str(call_id))
            if current is None:
                raise LifecycleTransitionError("The capability call is not recorded in the crash journal.")
            if current.state != CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME:
                raise LifecycleTransitionError("Only an unknown interrupted outcome can be acknowledged.")
            if current.recovery_acknowledged_at_ms is not None:
                return current
            timestamp = max(self._timestamp(), current.updated_at_ms)
            updated = _updated_record(
                current,
                updated_at_ms=timestamp,
                transition_sequence=current.transition_sequence + 1,
                recovery_acknowledged_at_ms=timestamp,
            )
            proposed = dict(self._records)
            proposed[current.call_id] = updated
            self._commit_locked(proposed)
            return updated

    def purge(
        self,
        policy: JournalRetentionPolicy | None = None,
        *,
        now_ms: int | None = None,
    ) -> tuple[str, ...]:
        retention = policy or JournalRetentionPolicy()
        if not isinstance(retention, JournalRetentionPolicy):
            raise TypeError("Crash-journal purge requires a JournalRetentionPolicy.")
        timestamp = self._timestamp(now_ms)
        removed: list[str] = []
        with self._lock:
            for call_id, record in self._records.items():
                if record.state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME:
                    acknowledged = record.recovery_acknowledged_at_ms
                    if acknowledged is None:
                        continue
                    age_ms = timestamp - acknowledged
                    keep_ms = retention.acknowledged_unknown_retention_seconds * 1_000
                elif record.terminal:
                    age_ms = timestamp - record.updated_at_ms
                    keep_ms = retention.terminal_retention_seconds * 1_000
                else:
                    continue
                if age_ms >= keep_ms:
                    removed.append(call_id)

            if not removed:
                return ()
            proposed = {
                call_id: record
                for call_id, record in self._records.items()
                if call_id not in removed
            }
            self._commit_locked(proposed)
            return tuple(sorted(removed))

    def _matching_record_locked(
        self,
        prepared: PreparedCapabilityCall,
    ) -> CallLifecycleRecord:
        current = self._records.get(prepared.request.call_id)
        if current is None:
            raise LifecycleTransitionError("The prepared call has no durable intent record.")
        if _prepared_identity(prepared) != {
            field: getattr(current, field)
            for field in _prepared_identity(prepared)
        }:
            raise LifecycleTransitionError("The prepared call does not match its durable identity.")
        return current

    def _transition_locked(
        self,
        current: CallLifecycleRecord,
        target: CallLifecycleState,
        **updates: Any,
    ) -> CallLifecycleRecord:
        allowed = _ALLOWED_TRANSITIONS.get(current.state, set())
        if target not in allowed:
            raise LifecycleTransitionError(
                f"The capability call cannot transition from {current.state.value} to {target.value}."
            )
        timestamp = max(self._timestamp(), current.updated_at_ms)
        updated = _updated_record(
            current,
            state=target,
            updated_at_ms=timestamp,
            transition_sequence=current.transition_sequence + 1,
            **updates,
        )
        proposed = dict(self._records)
        proposed[current.call_id] = updated
        self._commit_locked(proposed)
        return updated

    def _recover_incomplete_locked(self) -> None:
        timestamp = self._timestamp()
        proposed = dict(self._records)
        changed = False
        for call_id, record in self._records.items():
            if record.state in _PRE_EXECUTION_STATES:
                target = CallLifecycleState.INTERRUPTED_BEFORE_EXECUTION
            elif record.state == CallLifecycleState.RUNNING:
                target = CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
            else:
                continue
            proposed[call_id] = _updated_record(
                record,
                state=target,
                updated_at_ms=max(timestamp, record.updated_at_ms),
                transition_sequence=record.transition_sequence + 1,
            )
            changed = True
        if changed:
            self._commit_locked(proposed)

    def _load(self) -> dict[str, CallLifecycleRecord]:
        try:
            if not self.path.exists():
                return {}
            if self.path.stat().st_size > _MAX_JOURNAL_BYTES:
                raise CrashJournalCorruptionError(
                    "The capability crash journal exceeds its safe size limit."
                )
            raw = self.path.read_text(encoding="utf-8")
        except CrashJournalCorruptionError:
            raise
        except OSError as exc:
            raise CrashJournalPersistenceError(
                "The capability crash journal could not be read safely."
            ) from exc

        try:
            document = _JournalDocument.model_validate_json(raw)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            raise CrashJournalCorruptionError(
                "The capability crash journal is corrupted and cannot be used safely."
            ) from exc
        return {record.call_id: record for record in document.records}

    def _commit_locked(self, proposed: dict[str, CallLifecycleRecord]) -> None:
        document = _JournalDocument(
            records=tuple(proposed[key] for key in sorted(proposed))
        )
        encoded = (
            json.dumps(
                document.model_dump(mode="json"),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > _MAX_JOURNAL_BYTES:
            raise CrashJournalPersistenceError(
                "The capability crash journal exceeds its safe size limit."
            )
        try:
            _atomic_replace(self.path, encoded)
        except OSError as exc:
            raise CrashJournalPersistenceError(
                "The capability crash journal transition could not be persisted atomically."
            ) from exc
        self._records = proposed

    def _timestamp(self, supplied: int | None = None) -> int:
        value = self._clock_ms() if supplied is None else supplied
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Crash-journal timestamps must be non-negative integer milliseconds.")
        return value


class JournaledCapabilityExecutor:
    """Persists running and result boundaries around an isolated executor."""

    def __init__(
        self,
        executor: CapabilityExecutor,
        journal: CapabilityCrashJournal,
    ):
        if not isinstance(executor, CapabilityExecutor):
            raise TypeError("Journaled execution requires a CapabilityExecutor.")
        if not isinstance(journal, CapabilityCrashJournal):
            raise TypeError("Journaled execution requires a CapabilityCrashJournal.")
        self.executor = executor
        self.journal = journal

    def execute(
        self,
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> CapabilityResult:
        self.journal.mark_running(prepared, authorization)
        result = self.executor.execute(prepared, authorization)
        self.journal.record_result(result)
        return result


def _prepared_identity(prepared: PreparedCapabilityCall) -> dict[str, Any]:
    resource = prepared.request.resource
    return {
        "call_id": prepared.request.call_id,
        "session_id": prepared.context.session_id,
        "turn_id": prepared.context.turn_id,
        "capability": prepared.request.capability,
        "permission": prepared.request.permission,
        "arguments_sha256": prepared.request.arguments_sha256,
        "request_sha256": prepared.request.request_sha256,
        "resource_sha256": _sha256_text(resource) if resource is not None else None,
    }


def _authorization_terminal_state(
    code: AuthorizationCode,
) -> tuple[CallLifecycleState, CapabilityErrorCode]:
    if code == AuthorizationCode.APPROVAL_EXPIRED:
        return CallLifecycleState.TIMED_OUT, CapabilityErrorCode.TIMED_OUT
    if code in {AuthorizationCode.CANCELLED, AuthorizationCode.SHUTDOWN}:
        return CallLifecycleState.CANCELLED, CapabilityErrorCode.CANCELLED
    return CallLifecycleState.DENIED, CapabilityErrorCode.PERMISSION_DENIED


def _result_terminal_state(result: CapabilityResult) -> CallLifecycleState:
    if result.success:
        return CallLifecycleState.COMPLETED
    code = result.error.code
    if code == CapabilityErrorCode.PERMISSION_DENIED:
        return CallLifecycleState.DENIED
    if code == CapabilityErrorCode.CANCELLED:
        return CallLifecycleState.CANCELLED
    if code == CapabilityErrorCode.TIMED_OUT:
        return CallLifecycleState.TIMED_OUT
    return CallLifecycleState.FAILED


def _updated_record(
    record: CallLifecycleRecord,
    **updates: Any,
) -> CallLifecycleRecord:
    values = record.model_dump(mode="python")
    values.update(updates)
    return CallLifecycleRecord.model_validate(values)


def _digest_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_replace(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
