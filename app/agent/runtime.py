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
    SettledCall,
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
from app.inference.diagnostics import record_context_budget
from app.inference.completion import CompletionMetadata, CompletionText, IncompleteResponseError
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


@dataclass(slots=True)
class _RecoveryUsage:
    model_requests: int = 0
    consecutive_format_failures: int = 0
    semantic_corrections: int = 0
    context_projections: int = 0
    context_compactions: int = 0
    inference_requests: int = 0
    estimated_input_tokens: int = 0


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
        context_recovery_enabled: bool = False,
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
        if type(context_recovery_enabled) is not bool:
            raise TypeError("Context recovery requires an explicit boolean.")
        self.context_recovery_enabled = context_recovery_enabled

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
            ).model_copy(update={"model_requests": 1})
        if isinstance(response, str) and CompletionText(response).completion.incomplete:
            text = CompletionText(response)
            return self._stopped(self._incomplete_status(text.completion),
                "The response is incomplete.", steps=1, capability_calls=0, protocol_failures=0,
                completion=text.completion, partial_text=str(text) if text.strip() else None).model_copy(update={"model_requests": 1})
        if not isinstance(response, str) or not response.strip():
            return self._stopped(
                AgentRunStatus.INTERNAL_FAILURE,
                "The model returned an invalid conversational response.",
                steps=1,
                capability_calls=0,
                protocol_failures=0,
            ).model_copy(update={"model_requests": 1})
        text = CompletionText(response)
        return AgentRunResult(
            status=AgentRunStatus.COMPLETED,
            assistant_text=response.strip(),
            steps=1,
            capability_calls=0,
            protocol_failures=0,
            model_requests=1,
            completion=text.completion, completion_history=text.completion_history,
        )

    def run(
        self, messages: Iterable[dict[str, Any]], **kwargs,
    ) -> AgentRunResult:
        history = []
        settled = []
        recovery = _RecoveryUsage()
        result = self._run(messages, _completion_history=history, _settled_calls=settled,
                           _recovery=recovery, **kwargs)
        return result.model_copy(update={"completion_history": tuple(history),
            "settled_calls": tuple(settled),
            "model_requests": recovery.model_requests,
            "consecutive_format_failures": recovery.consecutive_format_failures,
            "semantic_corrections": recovery.semantic_corrections,
            "context_projections": recovery.context_projections,
            "context_compactions": recovery.context_compactions,
            "inference_requests": recovery.inference_requests,
            "estimated_input_tokens": recovery.estimated_input_tokens,
            "completion": result.completion if result.completion.incomplete or not history else history[-1]})

    def _run(
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
        _completion_history: list[CompletionMetadata] | None = None,
        _settled_calls: list[SettledCall] | None = None,
        settled_observer: Callable[[SettledCall], None] | None = None,
        response_observer: Callable[[str, Any], None] | None = None,
        continuation_guard: Callable[[], str | None] | None = None,
        _recovery: _RecoveryUsage | None = None,
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
        if settled_observer is not None and not callable(settled_observer):
            raise TypeError("Settled-call observers must be callable when supplied.")
        if response_observer is not None and not callable(response_observer):
            raise TypeError("Response observers must be callable when supplied.")
        if continuation_guard is not None and not callable(continuation_guard):
            raise TypeError("Continuation guards must be callable when supplied.")
        if self.executor.review_required:
            return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                "A previous write outcome requires review before another operation can run.",
                steps=0, capability_calls=0, protocol_failures=0)
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
        recovery = _recovery if _recovery is not None else _RecoveryUsage()
        capability_calls = 0
        protocol_failures = 0
        repeated: dict[str, int] = {}
        used_call_ids: set[str] = set()
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
            if recovery.semantic_corrections >= self.limits.max_semantic_corrections:
                return self._stopped(AgentRunStatus.SEMANTIC_CORRECTION_LIMIT,
                    "The agent stopped after reaching its semantic-correction limit.",
                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
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
            if continuation_guard is not None:
                try:
                    message = continuation_guard()
                except TaskCancelled:
                    return self._stopped(AgentRunStatus.CANCELLED, "The agent task was cancelled.",
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                except Exception:
                    message = "The active request scope could not be validated safely."
                if message is not None:
                    return self._stopped(AgentRunStatus.INTERNAL_FAILURE, str(message)[:500],
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            if steps >= self.limits.max_steps:
                return self._stopped(
                    AgentRunStatus.STEP_LIMIT,
                    "The agent stopped after reaching its maximum model-step limit.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            if planned_response is None and recovery.model_requests >= self.limits.max_model_requests:
                return self._stopped(AgentRunStatus.MODEL_REQUEST_LIMIT,
                    "The agent stopped after reaching its total model-request limit.",
                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            if planned_response is None:
                recovery.model_requests += 1
                if not self._recover_transcript(transcript, definitions, recovery):
                    return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                        "Context recovery failed safely; settled operations were retained.",
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
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
                    _request_usage=recovery,
                )
            else:
                response, model_stop = self._model_step(
                    transcript,
                    definitions,
                    started,
                    user_cancellation,
                    deadline_cancellation,
                    _request_usage=recovery,
                )
                if (
                    model_stop is None
                    and response is not None
                    and not response.completion.incomplete
                    and response.kind == ModelResponseKind.PROTOCOL_FAILURE
                    and response.protocol_failure.code
                    == ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS
                ):
                    structured_fallback = True
                    if _completion_history is not None:
                        _completion_history.append(response.completion)
                    if recovery.model_requests >= self.limits.max_model_requests:
                        return self._stopped(AgentRunStatus.MODEL_REQUEST_LIMIT,
                            "The agent stopped before exceeding its total model-request limit.",
                            steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                    recovery.model_requests += 1
                    response, model_stop = self._fallback_model_step(
                        transcript,
                        definitions,
                        started,
                        user_cancellation,
                        deadline_cancellation,
                        _request_usage=recovery,
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
            if _completion_history is not None:
                _completion_history.append(response.completion)
            if response.completion.incomplete:
                message = response.completion.failure_message or (
                    "The response was cut off." if response.kind != ModelResponseKind.ASSISTANT_TEXT
                    else "The response is incomplete.")
                if response.kind != ModelResponseKind.ASSISTANT_TEXT:
                    message += " The incomplete tool generation was not executed."
                return self._stopped(self._incomplete_status(response.completion),
                    message,
                    steps=steps, capability_calls=capability_calls,
                    protocol_failures=protocol_failures + int(response.kind == ModelResponseKind.PROTOCOL_FAILURE),
                    completion=response.completion,
                    partial_text=response.partial_text or response.assistant_text)
            provider_message_id = uuid4().hex
            if response.openai_response is not None:
                try:
                    if response_observer is not None:
                        response_observer(provider_message_id, response.openai_response)
                except Exception:
                    # Persistence exceptions can contain response data. Never log them.
                    log.error("OpenAI response evidence could not be retained durably.")
                    return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                        "The model response could not be retained durably. No new tool calls were executed.",
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            if response.kind == ModelResponseKind.ASSISTANT_TEXT:
                filename_feedback = filename_disambiguation_feedback(
                    transcript,
                    advertised_names,
                )
                if filename_feedback is not None:
                    self._retain_response_text(transcript, response)
                    recovery.consecutive_format_failures = 0
                    recovery.semantic_corrections += 1
                    transcript.append(filename_feedback)
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(
                            steps,
                            capability_calls,
                            protocol_failures,
                        )
                    continue
                if required_set - completed_required:
                    self._retain_response_text(transcript, response)
                    recovery.consecutive_format_failures = 0
                    recovery.semantic_corrections += 1
                    transcript.append(required_calls_feedback())
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(
                            steps,
                            capability_calls,
                            protocol_failures,
                        )
                    continue
                recovery.consecutive_format_failures = 0
                return AgentRunResult(
                    status=AgentRunStatus.COMPLETED,
                    assistant_text=response.assistant_text,
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            if response.kind == ModelResponseKind.PROTOCOL_FAILURE:
                protocol_failures += 1
                if (
                    response.protocol_failure.code
                    == ModelProtocolFailureCode.OUTPUT_TRUNCATED
                ):
                    return self._stopped(
                        AgentRunStatus.INCOMPLETE,
                        "The model response was cut off before it could complete the requested "
                        "action. The incomplete tool generation was not executed.",
                        steps=steps,
                        capability_calls=capability_calls,
                        protocol_failures=protocol_failures,
                        completion=response.completion.model_copy(update={"interrupted": True}),
                        partial_text=response.partial_text,
                    )
                semantic_failure = response.protocol_failure.code == ModelProtocolFailureCode.UNKNOWN_CAPABILITY
                if semantic_failure:
                    recovery.consecutive_format_failures = 0
                    recovery.semantic_corrections += 1
                else:
                    recovery.consecutive_format_failures += 1
                if recovery.consecutive_format_failures >= self.limits.max_protocol_failures:
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
                recovery.consecutive_format_failures = 0
                recovery.semantic_corrections += 1
                transcript.append(required_calls_feedback())
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(
                        steps,
                        capability_calls,
                        protocol_failures,
                    )
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
            if len(set(provider_call_ids)) != len(provider_call_ids):
                capability_calls += len(calls)
                protocol_failures += 1
                recovery.consecutive_format_failures += 1
                if recovery.consecutive_format_failures >= self.limits.max_protocol_failures:
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

            recovery.consecutive_format_failures = 0

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
                if outcome.stop_status is not None and outcome.result is None:
                    code = (CapabilityErrorCode.OUTCOME_UNKNOWN if self.executor.review_required else
                            CapabilityErrorCode.CANCELLED if outcome.stop_status == AgentRunStatus.CANCELLED else
                            CapabilityErrorCode.TIMED_OUT if outcome.stop_status == AgentRunStatus.TIMED_OUT else
                            CapabilityErrorCode.INTERNAL_ERROR)
                    outcome = _CallOutcome(result=failure_result(internal_call_id, call.capability,
                        CapabilityFailure(code=code, message=outcome.stop_message or "The call stopped safely.")),
                        stop_status=outcome.stop_status, stop_message=outcome.stop_message)
                if outcome.result is not None:
                    settled = SettledCall(provider_message_id=provider_message_id,
                                          call=call, result=outcome.result,
                                          assistant_text=response.assistant_text if not results else None)
                    if _settled_calls is not None:
                        _settled_calls.append(settled)
                    try:
                        if settled_observer is not None:
                            settled_observer(settled)
                        if result_observer is not None:
                            result_observer((call,), (outcome.result,))
                    except Exception:
                        log.exception("Settled capability result observation failed unexpectedly.")
                        return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                            "The settled capability result could not be retained durably. Review its outcome before retrying.",
                            steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
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
                if outcome.result.error is not None and outcome.result.error.code in {
                    CapabilityErrorCode.INVALID_ARGUMENTS, CapabilityErrorCode.UNKNOWN_CAPABILITY,
                }:
                    recovery.semantic_corrections += 1
                    if recovery.semantic_corrections >= self.limits.max_semantic_corrections:
                        return self._stopped(AgentRunStatus.SEMANTIC_CORRECTION_LIMIT,
                            "The agent stopped after reaching its semantic-correction limit.",
                            steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            completed_required.update(
                fingerprint
                for fingerprint in fingerprints
                if fingerprint in required_set
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
                transcript.append(model_capability_calls_message(calls, provider_message_id=provider_message_id, assistant_text=response.assistant_text))
                if response.openai_response is not None:
                    transcript[-1]["openai_response"] = response.openai_response.model_dump(mode="python")
                for call, result in zip(calls, results, strict=True):
                    transcript.append(
                        model_capability_result_message(
                            call,
                            result.model_dump(mode="json"),
                            provider_message_id=provider_message_id,
                        )
                    )
            except (TypeError, ValueError):
                return self._transcript_limited(
                    steps,
                    capability_calls,
                    protocol_failures,
                )
            if not self._recover_transcript(transcript, definitions, recovery):
                return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                    "Context recovery failed safely; settled operations were retained.",
                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            if not self._transcript_within_limit(transcript):
                return self._transcript_limited(steps, capability_calls, protocol_failures)

    @staticmethod
    def _retain_response_text(transcript, response):
        if response.openai_response is not None:
            transcript.append({"role": "assistant", "content": response.assistant_text,
                               "openai_response": response.openai_response.model_dump(mode="python")})

    def _recover_transcript(self, transcript, definitions, usage):
        if not self.context_recovery_enabled:
            return True
        from app.conversation.context import capability_schema_reserve
        from app.conversation.recovery import recover_context_request
        try:
            recovered = recover_context_request(self.model, transcript,
                reserved_tokens=capability_schema_reserve(definitions, inference=self.model))
        except Exception:
            log.exception("Context request projection failed safely.")
            return False
        transcript[:] = recovered.messages
        usage.context_projections += recovered.projected_results
        usage.context_compactions += int(recovered.compacted)
        return True

    @staticmethod
    def _record_request_usage(usage, budget):
        if usage is not None:
            usage.inference_requests += 1
            usage.estimated_input_tokens += (budget.system_message_tokens + budget.conversation_tokens
                + budget.structured_tool_history_tokens + budget.capability_schema_reserve)

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
            return _CallOutcome(result=result, stop_status=AgentRunStatus.INTERNAL_FAILURE,
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
                    result=result,
                    stop_status=AgentRunStatus.TIMED_OUT,
                    stop_message="The agent task exceeded its overall deadline.",
                )
            return _CallOutcome(
                result=result,
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

    @staticmethod
    def _incomplete_status(completion):
        return {"cancelled": AgentRunStatus.CANCELLED, "deadline": AgentRunStatus.TIMED_OUT}.get(
            completion.finish_reason, AgentRunStatus.INCOMPLETE)

    @staticmethod
    def _stop_completion(completion, stop):
        reason = "deadline" if stop[0] == AgentRunStatus.TIMED_OUT else "cancelled"
        return completion.model_copy(update={"finish_reason": reason, "interrupted": True})

    def _model_step(
        self,
        transcript: list[dict[str, Any]],
        definitions,
        started: float,
        user_cancellation: CancellationToken,
        deadline_cancellation: _DeadlineCancellationToken,
        *, _request_usage: _RecoveryUsage | None = None,
    ) -> tuple[
        ModelResponse | None,
        tuple[AgentRunStatus, str] | None,
    ]:
        from app.conversation.context import (
            calculate_context_budget,
            capability_schema_reserve,
        )

        budget = calculate_context_budget(
            self.model,
            transcript,
            reserved_tokens=capability_schema_reserve(definitions, inference=self.model),
        )
        record_context_budget(log, budget, request_kind="agent-capability-step")
        if not budget.fits:
            return None, (
                AgentRunStatus.CONTEXT_LIMIT,
                "The agent stopped before sending a request that exceeded the active model "
                "context window.",
            )
        self._record_request_usage(_request_usage, budget)
        future: Future[ModelResponse] = Future()

        def invoke() -> None:
            try:
                user_cancellation.raise_if_cancelled()
                deadline_cancellation.raise_if_cancelled()
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
                if getattr(self.model, "supports_text_streaming", False) is True:
                    try:
                        interrupted = future.result(timeout=0.5)
                        if isinstance(interrupted, ModelResponse) and interrupted.completion.incomplete:
                            return interrupted.model_copy(update={"completion": self._stop_completion(interrupted.completion, stop)}), None
                    except IncompleteResponseError as exc:
                        return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                            "The model generation was stopped.").model_copy(
                                update={"completion": self._stop_completion(exc.completion, stop), "partial_text": exc.partial_text}), None
                    except Exception:
                        pass
                return None, stop
            remaining = self._remaining(started)
            try:
                response = future.result(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except FutureTimeoutError:
                continue
            except IncompleteResponseError as exc:
                return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                    "The model generation was incomplete.").model_copy(
                        update={"completion": exc.completion, "partial_text": exc.partial_text}), None
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
        *, _request_usage: _RecoveryUsage | None = None,
    ) -> tuple[str | None, tuple[AgentRunStatus, str] | None]:
        from app.conversation.context import calculate_context_budget

        budget = calculate_context_budget(self.model, transcript)
        record_context_budget(log, budget, request_kind="agent-text-step")
        if not budget.fits:
            return None, (
                AgentRunStatus.CONTEXT_LIMIT,
                "The agent stopped before sending a request that exceeded the active model "
                "context window.",
            )
        self._record_request_usage(_request_usage, budget)
        future: Future[str] = Future()

        def invoke() -> None:
            try:
                user_cancellation.raise_if_cancelled()
                deadline_cancellation.raise_if_cancelled()
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
                if getattr(self.model, "supports_text_streaming", False) is True:
                    try:
                        interrupted = future.result(timeout=0.5)
                        if isinstance(interrupted, str) and CompletionText(interrupted).completion.incomplete:
                            return CompletionText(interrupted, self._stop_completion(CompletionText(interrupted).completion, stop)), None
                    except IncompleteResponseError as exc:
                        return CompletionText(exc.partial_text or "", self._stop_completion(exc.completion, stop)), None
                    except Exception:
                        pass
                return None, stop
            remaining = self._remaining(started)
            try:
                response = future.result(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except FutureTimeoutError:
                continue
            except IncompleteResponseError as exc:
                return CompletionText(exc.partial_text or "", exc.completion), None
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
        *, _request_usage: _RecoveryUsage | None = None,
    ) -> tuple[ModelResponse | None, tuple[AgentRunStatus, str] | None]:
        from app.inference.openai_replay import neutral_messages
        fallback_messages = constrained_fallback_messages(neutral_messages(transcript), definitions)
        raw, stop = self._text_model_step(
            fallback_messages,
            started,
            user_cancellation,
            deadline_cancellation,
            _request_usage=_request_usage,
        )
        if stop is not None:
            return None, stop
        completion = CompletionText(raw).completion if isinstance(raw, str) else CompletionMetadata()
        if completion.incomplete:
            return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                "The constrained response was cut off before decoding.").model_copy(
                    update={"completion": completion,
                            "partial_text": str(raw) if raw.strip() and len(raw) <= 1_000_000 else None}), None
        try:
            decision = decode_constrained_decision(raw)
        except StructuredCallDecodeError:
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The constrained fallback did not return one valid JSON decision.",
            ).model_copy(update={"completion": completion}), None

        requested_name = decision["tool"]
        if requested_name is None:
            return ModelResponse.text(decision["response"]).model_copy(update={"completion": completion}), None
        names = {definition.name.casefold(): definition.name for definition in definitions}
        capability = names.get(requested_name.casefold())
        if capability is None:
            return ModelResponse.failure(
                ModelProtocolFailureCode.UNKNOWN_CAPABILITY,
                "The constrained fallback requested a capability that was not advertised.",
            ).model_copy(update={"completion": completion}), None
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
            ).model_copy(update={"completion": completion}), None
        return ModelResponse.calls((call,)).model_copy(update={"completion": completion}), None

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
        completion: CompletionMetadata | None = None,
        partial_text: str | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            status=status,
            message=message,
            steps=steps,
            capability_calls=capability_calls,
            protocol_failures=protocol_failures,
            completion=completion or CompletionMetadata(), partial_text=partial_text,
            completion_history=(completion,) if completion is not None else (),
        )
