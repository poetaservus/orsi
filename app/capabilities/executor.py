from __future__ import annotations

import hashlib
import json
import logging
import math
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import replace
from threading import Lock, Thread
from time import monotonic, perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.capabilities.contracts import (
    CapabilityErrorCode,
    CapabilityExecutionError,
    CapabilityFailure,
    CapabilityResult,
    ExecutionIsolation,
)
from app.capabilities.permissions import (
    ApprovalStatus,
    AuthorizationCode,
    PermissionAuthorization,
    PermissionDecision,
    PreparedCapabilityCall,
)
from app.runtime.cancellation import (
    CancellationSource,
    LinkedCancellationToken,
    TaskCancelled,
)


log = logging.getLogger(__name__)


class ExecutorLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_output_bytes: int = Field(default=64 * 1024, ge=512, le=16 * 1024 * 1024)
    max_output_preview_bytes: int = Field(default=8 * 1024, ge=0, le=1024 * 1024)
    max_metadata_bytes: int = Field(default=4 * 1024, ge=256, le=1024 * 1024)
    cancellation_grace_seconds: float = Field(default=0.25, gt=0, le=10)
    poll_interval_seconds: float = Field(default=0.01, gt=0, le=0.1)

    @model_validator(mode="after")
    def validate_preview_limit(self):
        if self.max_output_preview_bytes >= self.max_output_bytes:
            raise ValueError("The output preview must be smaller than the output limit.")
        return self


class ExecutorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    active_call_id: str | None
    completed_call_count: int = Field(ge=0)
    poisoned: bool
    shutdown: bool


class _InvalidCapabilityOutput(ValueError):
    pass


class CapabilityExecutor:
    """Sequential fail-closed executor for prepared and authorized calls."""

    def __init__(self, limits: ExecutorLimits | None = None):
        self._limits = limits or ExecutorLimits()
        self._lock = Lock()
        self._active_call_id: str | None = None
        self._active_cancellation: CancellationSource | None = None
        self._active_thread: Thread | None = None
        self._completed_call_ids: set[str] = set()
        self._used_approval_ids: set[str] = set()
        self._poisoned = False
        self._shutdown = False

    @property
    def limits(self) -> ExecutorLimits:
        return self._limits

    @property
    def snapshot(self) -> ExecutorSnapshot:
        with self._lock:
            return ExecutorSnapshot(
                active_call_id=self._active_call_id,
                completed_call_count=len(self._completed_call_ids),
                poisoned=self._poisoned,
                shutdown=self._shutdown,
            )

    def execute(
        self,
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> CapabilityResult:
        if not isinstance(prepared, PreparedCapabilityCall):
            raise TypeError("The executor accepts only PreparedCapabilityCall objects.")
        if not isinstance(authorization, PermissionAuthorization):
            raise TypeError("The executor accepts only PermissionAuthorization objects.")

        started = perf_counter()
        authorization_failure = self._authorization_failure(prepared, authorization)
        if authorization_failure is not None:
            return self._failure(
                prepared,
                started,
                CapabilityErrorCode.PERMISSION_DENIED,
                authorization_failure,
            )

        claim_error = self._claim(prepared, authorization)
        if claim_error is not None:
            code, message = claim_error
            return self._failure(prepared, started, code, message)

        poisoned = False
        try:
            isolation = getattr(prepared.capability, "execution_isolation", None)
            if isolation == ExecutionIsolation.SUBPROCESS_REQUIRED:
                return self._failure(
                    prepared,
                    started,
                    CapabilityErrorCode.ISOLATION_REQUIRED,
                    "The capability requires an isolated worker that is not enabled.",
                )
            if isolation != ExecutionIsolation.IN_PROCESS_COOPERATIVE:
                return self._failure(
                    prepared,
                    started,
                    CapabilityErrorCode.EXECUTOR_UNAVAILABLE,
                    "The capability does not declare a supported execution isolation mode.",
                )

            timeout = self._capability_timeout(prepared)
            if timeout is None:
                return self._failure(
                    prepared,
                    started,
                    CapabilityErrorCode.EXECUTOR_UNAVAILABLE,
                    "The capability does not declare a valid execution deadline.",
                )

            if prepared.context.cancellation.is_cancelled:
                return self._failure(
                    prepared,
                    started,
                    CapabilityErrorCode.CANCELLED,
                    "The capability call was cancelled before execution.",
                )

            control = CancellationSource()
            linked = LinkedCancellationToken(
                prepared.context.cancellation,
                control.token,
            )
            execution_context = replace(prepared.context, cancellation=linked)
            future: Future[tuple[dict[str, Any], int, bool]] = Future()
            worker = Thread(
                target=self._run_worker,
                args=(future, prepared, execution_context),
                name=f"orsi-capability-{prepared.request.call_id}",
                daemon=True,
            )
            with self._lock:
                self._active_cancellation = control
                self._active_thread = worker
            worker.start()

            stop_code: CapabilityErrorCode | None = None
            stop_message = ""
            deadline = monotonic() + timeout
            bounded_output: tuple[dict[str, Any], int, bool] | None = None
            worker_error: BaseException | None = None

            while True:
                if prepared.context.cancellation.is_cancelled:
                    stop_code = CapabilityErrorCode.CANCELLED
                    stop_message = "The capability call was cancelled."
                    break
                if control.token.is_cancelled:
                    stop_code = CapabilityErrorCode.CANCELLED
                    stop_message = "The capability executor cancelled the call."
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    stop_code = CapabilityErrorCode.TIMED_OUT
                    stop_message = "The capability call exceeded its execution deadline."
                    break
                try:
                    bounded_output = future.result(
                        timeout=min(self._limits.poll_interval_seconds, remaining)
                    )
                    break
                except FutureTimeoutError:
                    continue
                except BaseException as exc:
                    worker_error = exc
                    break

            if stop_code is not None:
                control.cancel(stop_message)
                worker.join(self._limits.cancellation_grace_seconds)
                if worker.is_alive():
                    poisoned = True
                return self._failure(
                    prepared,
                    started,
                    stop_code,
                    stop_message,
                    executor_poisoned=poisoned,
                )

            if worker_error is not None:
                return self._normalize_worker_error(prepared, started, worker_error)
            if bounded_output is None:
                return self._failure(
                    prepared,
                    started,
                    CapabilityErrorCode.INTERNAL_ERROR,
                    "The capability completed without a result.",
                )

            output, original_bytes, limited = bounded_output

            metadata = self._metadata(
                prepared,
                output_limited=limited,
                output_bytes=original_bytes,
            )
            return CapabilityResult(
                call_id=prepared.request.call_id,
                capability=prepared.request.capability,
                success=True,
                output=output,
                duration_ms=self._duration_ms(started),
                metadata=metadata,
            )
        finally:
            self._finish(prepared.request.call_id, poisoned=poisoned)

    def shutdown(self) -> ExecutorSnapshot:
        with self._lock:
            self._shutdown = True
            cancellation = self._active_cancellation
            worker = self._active_thread
        if cancellation is not None:
            cancellation.cancel("The capability executor is shutting down.")
        if worker is not None:
            worker.join(self._limits.cancellation_grace_seconds)
            if worker.is_alive():
                with self._lock:
                    self._poisoned = True
        return self.snapshot

    def _claim(
        self,
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> tuple[CapabilityErrorCode, str] | None:
        call_id = prepared.request.call_id
        with self._lock:
            if self._shutdown:
                return (
                    CapabilityErrorCode.EXECUTOR_UNAVAILABLE,
                    "The capability executor has been shut down.",
                )
            if self._poisoned:
                return (
                    CapabilityErrorCode.EXECUTOR_UNAVAILABLE,
                    "The capability executor is unavailable after an unsafe cancellation.",
                )
            if call_id in self._completed_call_ids:
                return (
                    CapabilityErrorCode.CALL_REPLAYED,
                    "The capability call ID has already reached a terminal state.",
                )
            if (
                authorization.approval_id is not None
                and authorization.approval_id in self._used_approval_ids
            ):
                return (
                    CapabilityErrorCode.CALL_REPLAYED,
                    "The capability approval has already been used by the executor.",
                )
            if self._active_call_id is not None:
                return (
                    CapabilityErrorCode.EXECUTOR_BUSY,
                    "Another capability call is already running.",
                )
            self._active_call_id = call_id
            self._completed_call_ids.add(call_id)
            if authorization.approval_id is not None:
                self._used_approval_ids.add(authorization.approval_id)
            return None

    def _finish(self, call_id: str, *, poisoned: bool) -> None:
        with self._lock:
            if self._active_call_id == call_id:
                self._active_call_id = None
                self._active_cancellation = None
                self._active_thread = None
            if poisoned:
                self._poisoned = True

    @staticmethod
    def _authorization_failure(
        prepared: PreparedCapabilityCall,
        authorization: PermissionAuthorization,
    ) -> str | None:
        if not authorization.allowed or authorization.code != AuthorizationCode.ALLOWED:
            return "The capability call was not authorized for execution."
        if authorization.decision not in {
            PermissionDecision.ALLOW,
            PermissionDecision.ASK,
        }:
            return "The permission decision cannot authorize execution."
        if authorization.request_sha256 != prepared.request.request_sha256:
            return "The authorization does not match the prepared capability call."
        if authorization.decision == PermissionDecision.ASK and (
            authorization.approval_id is None
            or authorization.approval_status != ApprovalStatus.CONSUMED
        ):
            return "The capability approval was not consumed for this exact call."
        return None

    @staticmethod
    def _capability_timeout(prepared: PreparedCapabilityCall) -> float | None:
        value = getattr(prepared.capability, "timeout_seconds", None)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            or value > 3_600
        ):
            return None
        return float(value)

    def _run_worker(self, future, prepared, execution_context) -> None:
        try:
            execution_context.cancellation.raise_if_cancelled()
            arguments = prepared.validated_arguments()
            output = prepared.capability.execute(arguments, execution_context)
            execution_context.cancellation.raise_if_cancelled()
            if not isinstance(output, dict):
                raise _InvalidCapabilityOutput()
            future.set_result(self._bound_output(output))
        except BaseException as exc:
            future.set_exception(exc)

    def _normalize_worker_error(
        self,
        prepared: PreparedCapabilityCall,
        started: float,
        error: BaseException,
    ) -> CapabilityResult:
        if isinstance(error, TaskCancelled):
            return self._failure(
                prepared,
                started,
                CapabilityErrorCode.CANCELLED,
                "The capability call was cancelled.",
            )
        if isinstance(error, CapabilityExecutionError):
            return self._failure(prepared, started, error.code, str(error))
        if isinstance(error, _InvalidCapabilityOutput):
            return self._failure(
                prepared,
                started,
                CapabilityErrorCode.INVALID_OUTPUT,
                "The capability returned an invalid structured result.",
            )
        log.error(
            "Unhandled executor capability failure: capability=%s type=%s",
            prepared.request.capability,
            type(error).__name__,
        )
        return self._failure(
            prepared,
            started,
            CapabilityErrorCode.INTERNAL_ERROR,
            "The capability failed unexpectedly.",
        )

    def _bound_output(
        self,
        output: dict[str, Any],
    ) -> tuple[dict[str, Any], int, bool]:
        preview_limit = min(
            self._limits.max_output_preview_bytes,
            self._limits.max_output_bytes // 2,
        )
        encoder = json.JSONEncoder(
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256()
        preview_bytes = bytearray()
        complete_chunks: list[str] = []
        total_bytes = 0
        limited = False
        try:
            for chunk in encoder.iterencode(output):
                encoded_chunk = chunk.encode("utf-8")
                digest.update(encoded_chunk)
                total_bytes += len(encoded_chunk)
                if len(preview_bytes) < preview_limit:
                    remaining = preview_limit - len(preview_bytes)
                    preview_bytes.extend(encoded_chunk[:remaining])
                if not limited:
                    complete_chunks.append(chunk)
                    if total_bytes > self._limits.max_output_bytes:
                        limited = True
                        complete_chunks.clear()
        except (TypeError, ValueError, RecursionError) as exc:
            raise _InvalidCapabilityOutput() from exc

        if not limited:
            return json.loads("".join(complete_chunks)), total_bytes, False

        preview = bytes(preview_bytes).decode("utf-8", errors="ignore")
        while True:
            bounded = {
                "_orsi_output_limited": {
                    "original_utf8_bytes": total_bytes,
                    "sha256": digest.hexdigest(),
                    "preview": preview,
                }
            }
            bounded_bytes = len(
                json.dumps(
                    bounded,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            if bounded_bytes <= self._limits.max_output_bytes:
                return bounded, total_bytes, True
            if not preview:
                raise _InvalidCapabilityOutput()
            preview = preview[: max(0, len(preview) // 2)]

    def _failure(
        self,
        prepared: PreparedCapabilityCall,
        started: float,
        code: CapabilityErrorCode,
        message: str,
        *,
        executor_poisoned: bool = False,
    ) -> CapabilityResult:
        return CapabilityResult(
            call_id=prepared.request.call_id,
            capability=prepared.request.capability,
            success=False,
            error=CapabilityFailure(code=code, message=message),
            duration_ms=self._duration_ms(started),
            metadata=self._metadata(
                prepared,
                executor_poisoned=executor_poisoned,
            ),
        )

    def _metadata(
        self,
        prepared: PreparedCapabilityCall,
        *,
        output_limited: bool = False,
        output_bytes: int | None = None,
        executor_poisoned: bool = False,
    ) -> dict[str, Any]:
        isolation = getattr(prepared.capability, "execution_isolation", None)
        isolation_value = (
            isolation.value
            if isinstance(isolation, ExecutionIsolation)
            else "invalid"
        )
        metadata: dict[str, Any] = {
            "permission": prepared.request.permission.value,
            "execution_isolation": isolation_value,
            "result_schema_version": 1,
            "executor_schema_version": 1,
            "output_limited": output_limited,
            "executor_poisoned": executor_poisoned,
        }
        if output_bytes is not None:
            metadata["output_utf8_bytes"] = output_bytes
        encoded = json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) <= self._limits.max_metadata_bytes:
            return metadata
        return {
            "executor_schema_version": 1,
            "metadata_limited": True,
        }

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))
