from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable, Iterable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.capabilities.contracts import (
    CapabilityArgumentError,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    CapabilityFailure,
    CapabilityResult,
)
from app.capabilities.crash_journal import JournaledCapabilityExecutor
from app.capabilities.permissions import (
    ApprovalManager,
    ApprovalRecord,
    ApprovalStatus,
    AuthorizationCode,
    PermissionAuthorization,
    PermissionDecision,
    PermissionEvaluation,
    PermissionGate,
    PreparedCapabilityCall,
    prepare_capability_call,
)
from app.capabilities.registry import CapabilityLookupError, CapabilityRegistry
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.protocol import (
    ModelCapabilityCall,
    ModelProtocolFailureCode,
    ModelResponse,
    ModelResponseKind,
    model_capability_calls_message,
    model_capability_result_message,
    native_chat_messages,
)
from app.runtime.cancellation import (
    CancellationToken,
    LinkedCancellationToken,
    TaskCancelled,
)


_STABLE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    STEP_LIMIT = "step_limit"
    REPEATED_CALL = "repeated_call"
    PROTOCOL_FAILURE_LIMIT = "protocol_failure_limit"
    APPROVAL_REQUIRED = "approval_required"
    TRANSCRIPT_LIMIT = "transcript_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    INTERNAL_FAILURE = "internal_failure"


class AgentRuntimeLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_steps: int = Field(default=8, ge=1, le=32)
    max_identical_calls: int = Field(default=2, ge=1, le=8)
    max_protocol_failures: int = Field(default=2, ge=1, le=8)
    overall_timeout_seconds: float = Field(default=120.0, gt=0, le=3_600)
    poll_interval_seconds: float = Field(default=0.01, gt=0, le=1.0)
    max_transcript_bytes: int = Field(
        default=4 * 1024 * 1024,
        ge=1_024,
        le=16 * 1024 * 1024,
    )

    @model_validator(mode="after")
    def validate_finite_durations(self):
        if not math.isfinite(self.overall_timeout_seconds):
            raise ValueError("The runtime timeout must be finite.")
        if not math.isfinite(self.poll_interval_seconds):
            raise ValueError("The runtime polling interval must be finite.")
        return self


class AgentRunResult(BaseModel):
    """One bounded terminal outcome from an AgentRuntime invocation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: AgentRunStatus
    assistant_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    message: str | None = Field(default=None, min_length=1, max_length=500)
    steps: int = Field(ge=0, le=32)
    capability_calls: int = Field(ge=0, le=32)
    protocol_failures: int = Field(ge=0, le=32)

    @model_validator(mode="after")
    def validate_terminal_outcome(self):
        if self.status == AgentRunStatus.COMPLETED:
            if self.assistant_text is None or self.message is not None:
                raise ValueError("Completed agent runs require assistant text only.")
        elif self.assistant_text is not None or self.message is None:
            raise ValueError("Stopped agent runs require one bounded status message.")
        return self


@dataclass(frozen=True, slots=True)
class _CallOutcome:
    result: CapabilityResult | None = None
    stop_status: AgentRunStatus | None = None
    stop_message: str | None = None


@dataclass(frozen=True, slots=True)
class _AuthorizationOutcome:
    authorization: PermissionAuthorization | None
    record_final_authorization: bool


class _DeadlineCancellationToken(CancellationToken):
    """Read-only token that becomes cancelled when the runtime clock reaches a deadline."""

    def __init__(self, clock: Callable[[], float], deadline: float):
        self._clock = clock
        self._deadline = deadline
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._clock() >= self._deadline

    @property
    def reason(self) -> str:
        return "The agent task exceeded its overall deadline."

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is not None and timeout < 0:
            raise ValueError("Cancellation wait timeouts cannot be negative.")
        remaining = max(0.0, self._deadline - self._clock())
        if remaining <= 0:
            return True
        interval = remaining if timeout is None else min(timeout, remaining)
        self._event.wait(interval)
        return self.is_cancelled


class AgentRuntime:
    """Sequential, bounded capability loop used only behind an explicit gate."""

    def __init__(
        self,
        *,
        model: InferenceEngine,
        registry: CapabilityRegistry,
        permission_gate: PermissionGate,
        approval_manager: ApprovalManager,
        executor: JournaledCapabilityExecutor,
        limits: AgentRuntimeLimits | None = None,
        clock: Callable[[], float] = monotonic,
        call_id_factory: Callable[[], str] = lambda: uuid4().hex,
        approval_requester: Callable[[ApprovalRecord], None] | None = None,
    ):
        if not isinstance(model, InferenceEngine):
            raise TypeError("AgentRuntime requires an InferenceEngine.")
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("AgentRuntime requires a CapabilityRegistry.")
        if not isinstance(permission_gate, PermissionGate):
            raise TypeError("AgentRuntime requires a PermissionGate.")
        if not isinstance(approval_manager, ApprovalManager):
            raise TypeError("AgentRuntime requires an ApprovalManager.")
        if not isinstance(executor, JournaledCapabilityExecutor):
            raise TypeError("AgentRuntime requires a JournaledCapabilityExecutor.")
        if not callable(clock) or not callable(call_id_factory):
            raise TypeError("AgentRuntime clocks and ID factories must be callable.")
        if approval_requester is not None and not callable(approval_requester):
            raise TypeError("The approval requester must be callable when supplied.")
        self.model = model
        self.registry = registry
        self.permission_gate = permission_gate
        self.approval_manager = approval_manager
        self.executor = executor
        self.limits = limits or AgentRuntimeLimits()
        self._clock = clock
        self._call_id_factory = call_id_factory
        self._approval_requester = approval_requester

    def purge_terminal_records(self) -> tuple[str, ...]:
        """Apply the journal's explicit privacy retention policy."""
        return self.executor.journal.purge()

    def shutdown(self) -> None:
        """Resolve pending approval waits and stop capability execution."""
        self.approval_manager.shutdown()
        self.executor.executor.shutdown()

    def run(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        session_id: str,
        turn_id: str,
        portable_root: Path,
        allowed_read_roots: Iterable[Path],
        cancellation: CancellationToken | None = None,
    ) -> AgentRunResult:
        if not _safe_identifier(session_id) or not _safe_identifier(turn_id):
            raise ValueError("Agent session and turn IDs must use bounded stable syntax.")
        if not isinstance(portable_root, Path):
            raise TypeError("The portable root must be a pathlib.Path.")
        roots = tuple(allowed_read_roots)
        if not all(isinstance(root, Path) for root in roots):
            raise TypeError("Allowed read roots must be pathlib.Path values.")
        user_cancellation = cancellation or CancellationToken()
        if not isinstance(user_cancellation, CancellationToken):
            raise TypeError("Agent cancellation must be a CancellationToken.")

        definitions = self.registry.model_definitions()
        if not definitions:
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The agent has no model-visible capability definitions.",
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )
        transcript = deepcopy(tuple(messages))
        if not all(isinstance(message, dict) for message in transcript):
            raise TypeError("Agent model messages must be objects.")
        transcript = [deepcopy(message) for message in transcript]
        try:
            native_chat_messages(transcript, definitions)
            self._check_transcript_size(transcript)
        except (TypeError, ValueError):
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The initial model transcript is invalid.",
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )

        started = self._timestamp()
        deadline_cancellation = _DeadlineCancellationToken(
            self._clock,
            started + self.limits.overall_timeout_seconds,
        )
        linked = LinkedCancellationToken(
            user_cancellation,
            deadline_cancellation,
        )
        steps = 0
        capability_calls = 0
        protocol_failures = 0
        repeated: dict[str, int] = {}
        used_call_ids: set[str] = set()
        used_provider_call_ids: set[str] = set()
        advertised_names = {item.name for item in definitions}

        while True:
            stop = self._stop_status(started, user_cancellation, deadline_cancellation)
            if stop is not None:
                status, message = stop
                return self._stopped(
                    status,
                    message,
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )
            if steps >= self.limits.max_steps:
                return self._stopped(
                    AgentRunStatus.STEP_LIMIT,
                    "The agent stopped after reaching its maximum model-step limit.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            response, model_stop = self._model_step(
                transcript,
                definitions,
                started,
                user_cancellation,
                deadline_cancellation,
            )
            if model_stop is not None:
                status, message = model_stop
                return self._stopped(
                    status,
                    message,
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )
            steps += 1
            if response is None:
                return self._stopped(
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The model step completed without a response.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )
            if response.kind == ModelResponseKind.ASSISTANT_TEXT:
                return AgentRunResult(
                    status=AgentRunStatus.COMPLETED,
                    assistant_text=response.assistant_text,
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            if response.kind == ModelResponseKind.PROTOCOL_FAILURE:
                protocol_failures += 1
                if protocol_failures >= self.limits.max_protocol_failures:
                    return self._stopped(
                        AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                        "The agent stopped after repeated malformed model responses.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                code = response.protocol_failure.code
                transcript.append(_protocol_feedback(code.value))
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(steps, capability_calls, protocol_failures)
                continue

            if len(response.capability_calls) != 1:
                protocol_failures += 1
                if protocol_failures >= self.limits.max_protocol_failures:
                    return self._stopped(
                        AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                        "The agent stopped after repeated multi-call model responses.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                transcript.append(_single_call_feedback())
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(steps, capability_calls, protocol_failures)
                continue

            call = response.capability_calls[0]
            capability_calls += 1
            if call.provider_call_id in used_provider_call_ids:
                protocol_failures += 1
                if protocol_failures >= self.limits.max_protocol_failures:
                    return self._stopped(
                        AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                        "The agent stopped after repeated provider call IDs.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                transcript.append(
                    _protocol_feedback(
                        ModelProtocolFailureCode.DUPLICATE_CALL_ID.value
                    )
                )
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(
                        steps,
                        capability_calls,
                        protocol_failures,
                    )
                continue
            used_provider_call_ids.add(call.provider_call_id)
            fingerprint = _call_fingerprint(call)
            repeated[fingerprint] = repeated.get(fingerprint, 0) + 1
            if repeated[fingerprint] > self.limits.max_identical_calls:
                return self._stopped(
                    AgentRunStatus.REPEATED_CALL,
                    "The agent stopped after repeating an identical capability call.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            internal_call_id = self._new_call_id(used_call_ids)
            if internal_call_id is None:
                return self._stopped(
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The agent could not allocate a safe capability-call ID.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )
            outcome = self._process_call(
                call,
                internal_call_id=internal_call_id,
                advertised_names=advertised_names,
                session_id=session_id,
                turn_id=turn_id,
                portable_root=portable_root,
                allowed_read_roots=roots,
                cancellation=linked,
                started=started,
                user_cancellation=user_cancellation,
                deadline_cancellation=deadline_cancellation,
            )
            if outcome.stop_status is not None:
                return self._stopped(
                    outcome.stop_status,
                    outcome.stop_message or "The agent stopped safely.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )
            if outcome.result is None:
                return self._stopped(
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The capability step completed without a normalized result.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            try:
                transcript.append(model_capability_calls_message((call,)))
                transcript.append(
                    model_capability_result_message(
                        call,
                        outcome.result.model_dump(mode="json"),
                    )
                )
            except (TypeError, ValueError):
                return self._transcript_limited(
                    steps,
                    capability_calls,
                    protocol_failures,
                )
            if not self._transcript_within_limit(transcript):
                return self._transcript_limited(steps, capability_calls, protocol_failures)

    def _process_call(
        self,
        call: ModelCapabilityCall,
        *,
        internal_call_id: str,
        advertised_names: set[str],
        session_id: str,
        turn_id: str,
        portable_root: Path,
        allowed_read_roots: tuple[Path, ...],
        cancellation: CancellationToken,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> _CallOutcome:
        if call.capability not in advertised_names:
            return _CallOutcome(
                result=_failure_result(
                    internal_call_id,
                    call.capability,
                    CapabilityFailure(
                        code=CapabilityErrorCode.UNKNOWN_CAPABILITY,
                        message="The requested capability was not advertised.",
                    ),
                )
            )
        try:
            capability = self.registry.resolve(call.capability)
        except CapabilityLookupError as exc:
            return _CallOutcome(
                result=_failure_result(internal_call_id, call.capability, exc.failure)
            )
        except Exception:
            return _CallOutcome(
                stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="The capability registry failed unexpectedly.",
            )

        context = CapabilityContext(
            call_id=internal_call_id,
            session_id=session_id,
            turn_id=turn_id,
            portable_root=portable_root,
            allowed_read_roots=allowed_read_roots,
            cancellation=cancellation,
        )
        try:
            prepared = prepare_capability_call(capability, call.arguments, context)
        except CapabilityArgumentError as exc:
            return _CallOutcome(
                result=_failure_result(internal_call_id, call.capability, exc.failure)
            )
        except TaskCancelled:
            return _CallOutcome(
                stop_status=AgentRunStatus.CANCELLED,
                stop_message="The agent task was cancelled.",
            )
        except CapabilityExecutionError as exc:
            return _CallOutcome(
                result=_failure_result(
                    internal_call_id,
                    call.capability,
                    CapabilityFailure(code=exc.code, message=str(exc)),
                )
            )
        except Exception:
            return _CallOutcome(
                stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="The capability call could not be prepared safely.",
            )

        try:
            self.executor.journal.record_prepared(prepared)
            evaluation = self.permission_gate.evaluate(prepared)
            authorization_outcome = self._authorize(
                evaluation,
                prepared=prepared,
                cancellation=cancellation,
                started=started,
                user_cancellation=user_cancellation,
                deadline_cancellation=deadline_cancellation,
            )
            authorization = authorization_outcome.authorization
            if authorization is None:
                return _CallOutcome(
                    stop_status=AgentRunStatus.APPROVAL_REQUIRED,
                    stop_message="The capability call is waiting for explicit approval.",
                )
            if authorization_outcome.record_final_authorization:
                self.executor.journal.record_authorization(prepared, authorization)
        except Exception:
            return _CallOutcome(
                stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="The capability lifecycle could not be persisted safely.",
            )

        if not authorization.allowed:
            if (
                deadline_cancellation.is_cancelled
                and not user_cancellation.is_cancelled
            ):
                return _CallOutcome(
                    stop_status=AgentRunStatus.TIMED_OUT,
                    stop_message="The agent task exceeded its overall deadline.",
                )
            if authorization.code in {
                AuthorizationCode.CANCELLED,
                AuthorizationCode.SHUTDOWN,
            }:
                return _CallOutcome(
                    stop_status=AgentRunStatus.CANCELLED,
                    stop_message="The agent task was cancelled before capability execution.",
                )
            if authorization.code == AuthorizationCode.APPROVAL_EXPIRED:
                return _CallOutcome(
                    stop_status=AgentRunStatus.TIMED_OUT,
                    stop_message="The capability approval expired before execution.",
                )
            return _CallOutcome(
                result=_failure_result(
                    internal_call_id,
                    call.capability,
                    CapabilityFailure(
                        code=CapabilityErrorCode.PERMISSION_DENIED,
                        message="The capability call was denied by permission policy.",
                    ),
                )
            )

        try:
            result = self.executor.execute(prepared, authorization)
        except Exception:
            return _CallOutcome(
                stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="The capability result could not be persisted safely.",
            )
        if (
            result.error is not None
            and result.error.code == CapabilityErrorCode.CANCELLED
        ):
            if (
                deadline_cancellation.is_cancelled
                and not user_cancellation.is_cancelled
            ):
                return _CallOutcome(
                    stop_status=AgentRunStatus.TIMED_OUT,
                    stop_message="The agent task exceeded its overall deadline.",
                )
            return _CallOutcome(
                stop_status=AgentRunStatus.CANCELLED,
                stop_message="The agent task was cancelled during capability execution.",
            )
        return _CallOutcome(result=result)

    def _authorize(
        self,
        evaluation: PermissionEvaluation,
        *,
        prepared: PreparedCapabilityCall,
        cancellation: CancellationToken,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> _AuthorizationOutcome:
        if evaluation.decision != PermissionDecision.ASK:
            return _AuthorizationOutcome(
                authorization=self.approval_manager.authorize(
                    evaluation,
                    cancellation=cancellation,
                ),
                record_final_authorization=True,
            )

        record = self.approval_manager.request(
            evaluation,
            cancellation=cancellation,
        )
        initial = self.approval_manager.authorize(
            evaluation,
            approval_id=record.approval_id,
            cancellation=cancellation,
        )
        self.executor.journal.record_authorization(
            prepared,
            initial,
        )
        if initial.code != AuthorizationCode.APPROVAL_REQUIRED:
            return _AuthorizationOutcome(
                authorization=initial,
                record_final_authorization=False,
            )
        if self._approval_requester is None:
            return _AuthorizationOutcome(
                authorization=None,
                record_final_authorization=False,
            )
        try:
            self._approval_requester(record)
        except Exception:
            self.approval_manager.resolve(
                record.approval_id,
                status=ApprovalStatus.CANCELLED,
            )

        while True:
            stop = self._stop_status(started, user_cancellation, deadline_cancellation)
            authorization = self.approval_manager.authorize(
                evaluation,
                approval_id=record.approval_id,
                cancellation=cancellation,
            )
            if authorization.code != AuthorizationCode.APPROVAL_REQUIRED:
                return _AuthorizationOutcome(
                    authorization=authorization,
                    record_final_authorization=True,
                )
            if stop is not None:
                return _AuthorizationOutcome(
                    authorization=self.approval_manager.authorize(
                        evaluation,
                        approval_id=record.approval_id,
                        cancellation=cancellation,
                    ),
                    record_final_authorization=True,
                )
            cancellation.wait(self.limits.poll_interval_seconds)

    def _model_step(
        self,
        transcript: list[dict[str, Any]],
        definitions,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> tuple[
        ModelResponse | None,
        tuple[AgentRunStatus, str] | None,
    ]:
        future: Future[ModelResponse] = Future()

        def invoke() -> None:
            try:
                future.set_result(
                    self.model.respond_with_capabilities(
                        deepcopy(transcript),
                        definitions,
                    )
                )
            except BaseException as exc:
                future.set_exception(exc)

        Thread(target=invoke, name="orsi-agent-model-step", daemon=True).start()
        while True:
            stop = self._stop_status(started, user_cancellation, deadline_cancellation)
            if stop is not None:
                return None, stop
            remaining = self._remaining(started)
            try:
                response = future.result(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except FutureTimeoutError:
                continue
            except InferenceUnavailable:
                return None, (
                    AgentRunStatus.MODEL_UNAVAILABLE,
                    "The selected model provider is unavailable.",
                )
            except Exception:
                return None, (
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The model provider failed unexpectedly.",
                )
            if not isinstance(response, ModelResponse):
                return None, (
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The model adapter returned an invalid response type.",
                )
            return response, None

    def _stop_status(
        self,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> tuple[AgentRunStatus, str] | None:
        if user_cancellation.is_cancelled:
            return AgentRunStatus.CANCELLED, "The agent task was cancelled."
        if deadline_cancellation.is_cancelled or self._remaining(started) <= 0:
            return AgentRunStatus.TIMED_OUT, "The agent task exceeded its overall deadline."
        return None

    def _remaining(self, started: float) -> float:
        return max(0.0, self.limits.overall_timeout_seconds - (self._timestamp() - started))

    def _timestamp(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("AgentRuntime clocks must return finite numbers.")
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError("AgentRuntime clocks must return finite non-negative numbers.")
        return value

    def _new_call_id(self, used: set[str]) -> str | None:
        for _ in range(8):
            candidate = str(self._call_id_factory())
            if _safe_identifier(candidate) and candidate not in used:
                used.add(candidate)
                return candidate
        return None

    def _check_transcript_size(self, transcript: list[dict[str, Any]]) -> None:
        if _json_size(transcript) > self.limits.max_transcript_bytes:
            raise ValueError("The agent transcript exceeds its safe size limit.")

    def _transcript_within_limit(self, transcript: list[dict[str, Any]]) -> bool:
        try:
            self._check_transcript_size(transcript)
            return True
        except ValueError:
            return False

    def _transcript_limited(
        self,
        steps: int,
        capability_calls: int,
        protocol_failures: int,
    ) -> AgentRunResult:
        return self._stopped(
            AgentRunStatus.TRANSCRIPT_LIMIT,
            "The agent stopped because its structured transcript reached the size limit.",
            steps=steps,
            capability_calls=capability_calls,
            protocol_failures=protocol_failures,
        )

    @staticmethod
    def _stopped(
        status: AgentRunStatus,
        message: str,
        *,
        steps: int,
        capability_calls: int,
        protocol_failures: int,
    ) -> AgentRunResult:
        return AgentRunResult(
            status=status,
            message=message,
            steps=steps,
            capability_calls=capability_calls,
            protocol_failures=protocol_failures,
        )


def _failure_result(
    call_id: str,
    capability: str,
    failure: CapabilityFailure,
) -> CapabilityResult:
    return CapabilityResult(
        call_id=call_id,
        capability=capability,
        success=False,
        error=failure,
        duration_ms=0,
        metadata={"result_schema_version": 1},
    )


def _call_fingerprint(call: ModelCapabilityCall) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "arguments": call.arguments,
                "capability": call.capability,
            }
        ).encode("utf-8")
    ).hexdigest()


def _protocol_feedback(code: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            f"The prior structured response was rejected ({code}). "
            "Return either assistant text or exactly one valid native capability call."
        ),
    }


def _single_call_feedback() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "The prior structured response requested multiple capability calls. "
            "Return at most one native capability call in this step."
        ),
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_size(value: Any) -> int:
    try:
        return len(_canonical_json(value).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Agent runtime values must contain bounded JSON data.") from exc


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _STABLE_IDENTIFIER.fullmatch(value) is not None
