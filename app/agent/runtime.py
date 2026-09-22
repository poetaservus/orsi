"""Bounded agent loop with behavior adapted from OpenCode's session processor.

Portions of this file are substantially derived from OpenCode's tool-call
continuation and invalid-tool feedback patterns: https://github.com/anomalyco/opencode
(MIT License, Copyright (c) 2025 opencode). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable, Iterable
from uuid import uuid4

from app.agent.contracts import (
    AgentRunResult,
    AgentRunStatus,
    model_unavailable_message,
)
from app.settings.agent import AgentRuntimeLimits
from app.agent.feedback import (
    call_fingerprint,
    constrained_fallback_messages,
    failure_result,
    json_size,
    protocol_feedback,
    required_calls_feedback,
    safe_identifier,
    single_call_feedback,
)
from app.agent.file_resolution import filename_disambiguation_feedback
from app.capabilities.contracts import (
    CapabilityArgumentError,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    CapabilityFailure,
    CapabilityResult,
)
from app.security.host_access import HostAccessPolicy
from app.execution.audit import JournaledCapabilityExecutor
from app.security.permissions import (
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
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponse,
    ModelResponseKind,
    model_capability_calls_message,
    model_capability_result_message,
    native_chat_messages,
)
from app.inference.tool_repair import (
    StructuredCallDecodeError,
    decode_constrained_decision,
)
from app.runtime.cancellation import (
    CancellationToken,
    LinkedCancellationToken,
    TaskCancelled,
)


log = logging.getLogger(__name__)


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
    """Optional safety deadline; ordinary agent runs rely on bounded operations."""

    def __init__(self, clock: Callable[[], float], deadline: float | None):
        self._clock = clock
        self._deadline = deadline
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._deadline is not None and self._clock() >= self._deadline

    @property
    def reason(self) -> str:
        return "The agent task exceeded its overall deadline."

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is not None and timeout < 0:
            raise ValueError("Cancellation wait timeouts cannot be negative.")
        if self._deadline is None:
            return self._event.wait(timeout)
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
        fallback_call_id_factory: Callable[[], str] = lambda: f"fallback-{uuid4().hex}",
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
        if (
            not callable(clock)
            or not callable(call_id_factory)
            or not callable(fallback_call_id_factory)
        ):
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
        self._fallback_call_id_factory = fallback_call_id_factory
        self._approval_requester = approval_requester

    def purge_terminal_records(self) -> tuple[str, ...]:
        """Apply the journal's explicit privacy retention policy."""
        return self.executor.journal.purge()

    def set_approval_requester(self, requester: Callable[[ApprovalRecord], None]) -> None:
        if not callable(requester):
            raise TypeError("The approval requester must be callable.")
        self._approval_requester = requester

    def resolve_approval(self, approval_id: str, approved: bool) -> None:
        if not isinstance(approved, bool):
            raise TypeError("Approval must be an explicit boolean.")
        self.approval_manager.resolve(
            approval_id, ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        )

    def approval_status(self, approval_id: str) -> str:
        return self.approval_manager.get(approval_id).status.value

    def shutdown(self) -> None:
        """Resolve pending approval waits and stop capability execution."""
        self.approval_manager.shutdown()
        self.executor.executor.shutdown()

    def run_conversation(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        cancellation: CancellationToken | None = None,
    ) -> AgentRunResult:
        """Run one bounded model step without advertising computer capabilities."""
        user_cancellation = cancellation or CancellationToken()
        if not isinstance(user_cancellation, CancellationToken):
            raise TypeError("Conversation cancellation must be a CancellationToken.")
        transcript = deepcopy(tuple(messages))
        if not all(
            isinstance(message, dict)
            and set(message) == {"role", "content"}
            and message.get("role") in {"system", "user", "assistant"}
            and isinstance(message.get("content"), str)
            and bool(message["content"].strip())
            for message in transcript
        ):
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The conversational model transcript is invalid.",
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )
        transcript = [deepcopy(message) for message in transcript]
        try:
            self._check_transcript_size(transcript)
        except (TypeError, ValueError):
            return self._stopped(
                AgentRunStatus.TRANSCRIPT_LIMIT,
                "The conversational model transcript reached the size limit.",
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )

        started = self._timestamp()
        deadline_cancellation = _DeadlineCancellationToken(
            self._clock,
            self._deadline(started),
        )
        response, stop = self._text_model_step(
            transcript,
            started,
            user_cancellation,
            deadline_cancellation,
        )
        if stop is not None:
            status, message = stop
            return self._stopped(
                status,
                message,
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )
        if not isinstance(response, str) or not response.strip():
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The model returned an invalid conversational response.",
                steps=1,
                capability_calls=0,
                protocol_failures=0,
            )
        return AgentRunResult(
            status=AgentRunStatus.COMPLETED,
            assistant_text=response.strip(),
            steps=1,
            capability_calls=0,
            protocol_failures=0,
        )

    def run(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        session_id: str,
        turn_id: str,
        portable_root: Path,
        allowed_read_roots: Iterable[Path],
        host_access_policy: HostAccessPolicy | None = None,
        cancellation: CancellationToken | None = None,
        result_observer: Callable[
            [tuple[ModelCapabilityCall, ...], tuple[CapabilityResult, ...]], None
        ]
        | None = None,
        required_calls: tuple[ModelCapabilityCall, ...] = (),
        capability_names: tuple[str, ...] | None = None,
        continue_after_required_calls: bool = False,
    ) -> AgentRunResult:
        if not safe_identifier(session_id) or not safe_identifier(turn_id):
            raise ValueError("Agent session and turn IDs must use bounded stable syntax.")
        if not isinstance(portable_root, Path):
            raise TypeError("The portable root must be a pathlib.Path.")
        roots = tuple(allowed_read_roots)
        if not all(isinstance(root, Path) for root in roots):
            raise TypeError("Allowed read roots must be pathlib.Path values.")
        if host_access_policy is not None and not isinstance(
            host_access_policy, HostAccessPolicy
        ):
            raise TypeError("Agent host access must be a HostAccessPolicy.")
        user_cancellation = cancellation or CancellationToken()
        if not isinstance(user_cancellation, CancellationToken):
            raise TypeError("Agent cancellation must be a CancellationToken.")
        if result_observer is not None and not callable(result_observer):
            raise TypeError("Agent result observers must be callable when supplied.")
        if (
            not isinstance(required_calls, tuple)
            or not all(isinstance(call, ModelCapabilityCall) for call in required_calls)
        ):
            raise TypeError("Required agent calls must be a tuple of model capability calls.")
        if type(continue_after_required_calls) is not bool:
            raise TypeError("Required-call continuation must be an explicit boolean.")

        definitions = self.registry.model_definitions()
        if capability_names is not None:
            if not isinstance(capability_names, tuple) or not set(capability_names).issubset(
                self.registry.model_visible_names
            ):
                raise ValueError("The turn capability catalog must be a subset of the visible registry.")
            definitions = tuple(item for item in definitions if item.name in capability_names)
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
            self._deadline(started),
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
        required_fingerprints = tuple(call_fingerprint(call) for call in required_calls)
        if (
            len(required_calls) > self.limits.max_capability_calls
            or len(set(required_fingerprints)) != len(required_fingerprints)
            or any(call.capability not in advertised_names for call in required_calls)
        ):
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The required capability-call plan is invalid.",
                steps=0,
                capability_calls=0,
                protocol_failures=0,
            )
        required_set = set(required_fingerprints)
        completed_required: set[str] = set()
        planned_response = ModelResponse.calls(required_calls) if required_calls else None
        structured_fallback = False

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

            if planned_response is not None:
                response = planned_response
                planned_response = None
                model_stop = None
            elif structured_fallback:
                response, model_stop = self._fallback_model_step(
                    transcript,
                    definitions,
                    started,
                    user_cancellation,
                    deadline_cancellation,
                )
            else:
                response, model_stop = self._model_step(
                    transcript,
                    definitions,
                    started,
                    user_cancellation,
                    deadline_cancellation,
                )
                if (
                    model_stop is None
                    and response is not None
                    and response.kind == ModelResponseKind.PROTOCOL_FAILURE
                    and response.protocol_failure.code
                    == ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS
                ):
                    structured_fallback = True
                    response, model_stop = self._fallback_model_step(
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
                filename_feedback = filename_disambiguation_feedback(
                    transcript,
                    advertised_names,
                )
                if filename_feedback is not None:
                    transcript.append(filename_feedback)
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(
                            steps,
                            capability_calls,
                            protocol_failures,
                        )
                    continue
                if required_set - completed_required:
                    transcript.append(required_calls_feedback())
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(
                            steps,
                            capability_calls,
                            protocol_failures,
                        )
                    continue
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
                transcript.append(protocol_feedback(code.value))
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(steps, capability_calls, protocol_failures)
                continue

            calls = response.capability_calls
            call_fingerprints = [call_fingerprint(call) for call in calls]
            if required_set and any(
                fingerprint not in required_set or fingerprint in completed_required
                for fingerprint in call_fingerprints
            ):
                transcript.append(required_calls_feedback())
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(
                        steps,
                        capability_calls,
                        protocol_failures,
                    )
                continue
            batch_allowed = True
            if len(calls) > 1:
                batch_names = {call.capability for call in calls}
                if len(batch_names) != 1:
                    batch_allowed = False
                else:
                    try:
                        batch_capability = self.registry.resolve(calls[0].capability)
                    except CapabilityLookupError:
                        batch_allowed = False
                    except Exception:
                        log.exception("Capability batch lookup failed unexpectedly.")
                        return self._stopped(
                            AgentRunStatus.INTERNAL_FAILURE,
                            "The capability registry failed unexpectedly.",
                            steps=steps,
                            capability_calls=capability_calls,
                            protocol_failures=protocol_failures,
                        )
                    else:
                        batch_allowed = (
                            len(calls) <= batch_capability.max_calls_per_batch
                        )
            if not batch_allowed:
                protocol_failures += 1
                if protocol_failures >= self.limits.max_protocol_failures:
                    return self._stopped(
                        AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                        "The agent stopped after repeated unsupported call batches.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                transcript.append(single_call_feedback())
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(steps, capability_calls, protocol_failures)
                continue

            if capability_calls + len(calls) > self.limits.max_capability_calls:
                return self._stopped(
                    AgentRunStatus.CAPABILITY_CALL_LIMIT,
                    "The agent stopped before exceeding its capability-call limit.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            provider_call_ids = [call.provider_call_id for call in calls]
            if len(set(provider_call_ids)) != len(provider_call_ids) or any(
                provider_call_id in used_provider_call_ids
                for provider_call_id in provider_call_ids
            ):
                capability_calls += len(calls)
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
                    protocol_feedback(
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

            fingerprints = call_fingerprints
            if len(set(fingerprints)) != len(fingerprints):
                return self._stopped(
                    AgentRunStatus.REPEATED_CALL,
                    "The agent stopped before executing duplicate calls in one batch.",
                    steps=steps,
                    capability_calls=capability_calls + len(calls),
                    protocol_failures=protocol_failures,
                )
            staged_repeated = dict(repeated)
            for fingerprint in fingerprints:
                staged_repeated[fingerprint] = staged_repeated.get(fingerprint, 0) + 1
                if staged_repeated[fingerprint] > self.limits.max_identical_calls:
                    return self._stopped(
                        AgentRunStatus.REPEATED_CALL,
                        "The agent stopped after repeating an identical capability call.",
                        steps=steps,
                        capability_calls=capability_calls + len(calls),
                        protocol_failures=protocol_failures,
                    )

            internal_call_ids: list[str] = []
            for _call in calls:
                internal_call_id = self._new_call_id(used_call_ids)
                if internal_call_id is None:
                    return self._stopped(
                        AgentRunStatus.INTERNAL_FAILURE,
                        "The agent could not allocate a safe capability-call ID.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                internal_call_ids.append(internal_call_id)

            capability_calls += len(calls)
            used_provider_call_ids.update(provider_call_ids)
            repeated = staged_repeated
            results: list[CapabilityResult] = []
            for call, internal_call_id in zip(calls, internal_call_ids, strict=True):
                outcome = self._process_call(
                    call,
                    internal_call_id=internal_call_id,
                    advertised_names=advertised_names,
                    session_id=session_id,
                    turn_id=turn_id,
                    portable_root=portable_root,
                    allowed_read_roots=roots,
                    host_access_policy=host_access_policy,
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
                results.append(outcome.result)
            completed_required.update(
                fingerprint
                for fingerprint in fingerprints
                if fingerprint in required_set
            )

            if result_observer is not None:
                try:
                    result_observer(tuple(calls), tuple(results))
                except Exception:
                    log.exception("Capability result observation failed unexpectedly.")
                    return self._stopped(
                        AgentRunStatus.INTERNAL_FAILURE,
                        "The capability context could not be retained safely.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )

            if required_set and completed_required == required_set:
                if not continue_after_required_calls:
                    return AgentRunResult(
                        status=AgentRunStatus.COMPLETED,
                        assistant_text="The requested capability calls completed.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                    )
                required_set = set()
                completed_required = set()

            try:
                transcript.append(model_capability_calls_message(calls))
                for call, result in zip(calls, results, strict=True):
                    transcript.append(
                        model_capability_result_message(
                            call,
                            result.model_dump(mode="json"),
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
        host_access_policy: HostAccessPolicy | None,
        cancellation: CancellationToken,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> _CallOutcome:
        if self.executor.review_required:
            return _CallOutcome(stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="A previous write outcome requires review before another operation can run.")
        if call.capability not in advertised_names:
            return _CallOutcome(
                result=failure_result(
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
                result=failure_result(internal_call_id, call.capability, exc.failure)
            )
        except Exception:
            log.exception("Capability lookup failed unexpectedly.")
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
            host_access_policy=host_access_policy,
        )
        try:
            prepared = prepare_capability_call(capability, call.arguments, context)
        except CapabilityArgumentError as exc:
            return _CallOutcome(
                result=failure_result(internal_call_id, call.capability, exc.failure)
            )
        except TaskCancelled:
            return _CallOutcome(
                stop_status=AgentRunStatus.CANCELLED,
                stop_message="The agent task was cancelled.",
            )
        except CapabilityExecutionError as exc:
            return _CallOutcome(
                result=failure_result(
                    internal_call_id,
                    call.capability,
                    CapabilityFailure(code=exc.code, message=str(exc)),
                )
            )
        except Exception:
            log.exception("Capability call preparation failed unexpectedly.")
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
            log.exception("Capability lifecycle persistence failed unexpectedly.")
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
                result=failure_result(
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
            log.exception("Capability result persistence failed unexpectedly.")
            return _CallOutcome(
                stop_status=AgentRunStatus.INTERNAL_FAILURE,
                stop_message="The capability result could not be persisted safely. Review its outcome before retrying.",
            )
        if result.error is not None and result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN:
            return _CallOutcome(stop_status=AgentRunStatus.INTERNAL_FAILURE,
                                stop_message=result.error.message)
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
            log.exception("The approval UI failed while presenting a request.")
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
                if not future.done():
                    cancel = getattr(self.model, "cancel_current_request", None)
                    if callable(cancel):
                        try:
                            cancel()
                        except Exception:
                            log.debug("Model cancellation cleanup failed.", exc_info=True)
                return None, stop
            remaining = self._remaining(started)
            try:
                response = future.result(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except FutureTimeoutError:
                continue
            except InferenceUnavailable as exc:
                return None, (
                    AgentRunStatus.MODEL_UNAVAILABLE,
                    model_unavailable_message(exc),
                )
            except Exception:
                log.exception("Text model request failed unexpectedly.")
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

    def _text_model_step(
        self,
        transcript: list[dict[str, Any]],
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> tuple[str | None, tuple[AgentRunStatus, str] | None]:
        future: Future[str] = Future()

        def invoke() -> None:
            try:
                future.set_result(self.model.respond(deepcopy(transcript)))
            except BaseException as exc:
                future.set_exception(exc)

        Thread(target=invoke, name="orsi-conversation-model-step", daemon=True).start()
        while True:
            stop = self._stop_status(started, user_cancellation, deadline_cancellation)
            if stop is not None:
                if not future.done():
                    cancel = getattr(self.model, "cancel_current_request", None)
                    if callable(cancel):
                        try:
                            cancel()
                        except Exception:
                            log.debug("Model cancellation cleanup failed.", exc_info=True)
                return None, stop
            remaining = self._remaining(started)
            try:
                response = future.result(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except FutureTimeoutError:
                continue
            except InferenceUnavailable as exc:
                return None, (
                    AgentRunStatus.MODEL_UNAVAILABLE,
                    model_unavailable_message(exc),
                )
            except Exception:
                log.exception("Native capability-model request failed unexpectedly.")
                return None, (
                    AgentRunStatus.INTERNAL_FAILURE,
                    "The model provider failed unexpectedly.",
                )
            return response, None

    def _fallback_model_step(
        self,
        transcript: list[dict[str, Any]],
        definitions: tuple[ModelCapabilityDefinition, ...],
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
    ) -> tuple[ModelResponse | None, tuple[AgentRunStatus, str] | None]:
        fallback_messages = constrained_fallback_messages(transcript, definitions)
        raw, stop = self._text_model_step(
            fallback_messages,
            started,
            user_cancellation,
            deadline_cancellation,
        )
        if stop is not None:
            return None, stop
        try:
            decision = decode_constrained_decision(raw)
        except StructuredCallDecodeError:
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The constrained fallback did not return one valid JSON decision.",
            ), None

        requested_name = decision["tool"]
        if requested_name is None:
            return ModelResponse.text(decision["response"]), None
        names = {definition.name.casefold(): definition.name for definition in definitions}
        capability = names.get(requested_name.casefold())
        if capability is None:
            return ModelResponse.failure(
                ModelProtocolFailureCode.UNKNOWN_CAPABILITY,
                "The constrained fallback requested a capability that was not advertised.",
            ), None
        provider_call_id = str(self._fallback_call_id_factory())
        try:
            call = ModelCapabilityCall(
                provider_call_id=provider_call_id,
                capability=capability,
                arguments=deepcopy(decision["arguments"]),
            )
        except (TypeError, ValueError):
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_CALL_ID,
                "The constrained fallback could not create a safe call identity.",
            ), None
        return ModelResponse.calls((call,)), None

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
        timeout = self.limits.overall_timeout_seconds
        if timeout is None:
            return math.inf
        return max(0.0, timeout - (self._timestamp() - started))

    def _deadline(self, started: float) -> float | None:
        timeout = self.limits.overall_timeout_seconds
        return None if timeout is None else started + timeout

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
            if safe_identifier(candidate) and candidate not in used:
                used.add(candidate)
                return candidate
        return None

    def _check_transcript_size(self, transcript: list[dict[str, Any]]) -> None:
        if json_size(transcript) > self.limits.max_transcript_bytes:
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
