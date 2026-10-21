"""Bounded agent loop with behavior adapted from OpenCode's session processor.

Portions of this file are substantially derived from OpenCode's tool-call
continuation and invalid-tool feedback patterns: https://github.com/anomalyco/opencode
(MIT License, Copyright (c) 2025 opencode). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import logging
import math
import json
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable, Iterable
from uuid import uuid4

from app.agent.contracts import (
    AgentRunResult,
    AgentRunStatus,
    BlockedCallAttempt,
    SettledCall,
    model_unavailable_message,
)
from app.settings.agent import AgentRuntimeLimits
from app.agent.progress import (WORK_BUDGET_STATUSES, WORK_BUDGET_MESSAGE, work_budget_progress,
    RECOVERY_STOP_STATUSES, recovery_stop_progress)
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
from app.agent.read_progress import ReadProgressTracker
from app.agent.project_progress import ProjectProgressTracker
from app.agent.edit_progress import EditProgressTracker
from app.agent.office_read_progress import OfficeReadProgress
from app.agent.office_progress import OfficeProgress
from app.runtime.diagnostic_context import current_turn_id, run_in_turn
from app.agent.prerequisite_retries import PrerequisiteRetries, repetition_fingerprint
from app.agent.recovery_progress import RecoveryProgress, recovery_scope
from app.agent.completion_evidence import compile_review_evidence, validate_review_evidence
from app.agent.review_diagnostics import ReviewFailure, record_review_event
from app.agent.context_diagnostics import (ContextRecoveryFailure, context_recovery_failure,
    record_context_failure)
from app.agent.goals import TaskGoal, observe_goal, finish_goal, goal_feedback, evidence_report
from app.agent.task_completion import (CompletionReview, task_context_message,
    completion_review_message, parse_completion_review, looks_like_completion_review, resume_answer_message,
    ReviewValidationError)
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
from app.runtime.activity import capability_activity, report_activity
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
    review_failures: list[ReviewFailure] = field(default_factory=list)
    context_projections: int = 0
    context_compactions: int = 0
    context_recovery_failure: ContextRecoveryFailure | None = None
    inference_requests: int = 0
    estimated_input_tokens: int = 0
    proposed_answer: str | None = None
    review_receipt_count: int | None = None


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
        conversation_context_enabled: bool = False,
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
        # Scoped skill runtimes share this flag through their shallow runtime copy.
        self._approval_review = Event()
        self._approval_review.set()
        if type(context_recovery_enabled) is not bool:
            raise TypeError("Context recovery requires an explicit boolean.")
        self.context_recovery_enabled = context_recovery_enabled
        if type(conversation_context_enabled) is not bool:
            raise TypeError("Conversation context requires an explicit boolean.")
        self.conversation_context_enabled = conversation_context_enabled

    @property
    def effective_max_steps(self) -> int:
        """Select the per-turn step budget from the active inference mode."""
        return self.limits.cloud_max_steps if getattr(self.model, "mode", None) == "cloud" else self.limits.max_steps

    @property
    def effective_max_model_requests(self) -> int:
        return self.limits.cloud_max_model_requests if getattr(self.model, "mode", None) == "cloud" else self.limits.max_model_requests

    @property
    def effective_max_capability_calls(self) -> int:
        return self.limits.cloud_max_capability_calls if getattr(self.model, "mode", None) == "cloud" else self.limits.max_capability_calls

    def purge_terminal_records(self) -> tuple[str, ...]:
        """Apply the journal's explicit privacy retention policy."""
        return self.executor.journal.purge()

    def set_approval_requester(self, requester: Callable[[ApprovalRecord], None]) -> None:
        if not callable(requester):
            raise TypeError("The approval requester must be callable.")
        self._approval_requester = requester

    @property
    def tool_approval_required(self) -> bool:
        return self._approval_review.is_set()

    def set_tool_approval_required(self, required: bool) -> None:
        """Select human review for future requests; leave pending reviews intact."""
        if type(required) is not bool:
            raise TypeError("Tool approval preferences require an explicit boolean.")
        if required:
            self._approval_review.set()
        else:
            self._approval_review.clear()

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
        try:
            self.executor.executor.shutdown()
        finally:
            for name in self.registry.enabled_names:
                close = getattr(self.registry.resolve(name), "shutdown", None)
                if callable(close):
                    close()

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
        objective = kwargs.pop("goal_request", None)
        goal = [TaskGoal(goal_id=kwargs["turn_id"], objective=objective, evidence_version=2)] if objective is not None else []
        reviews = []
        visuals = set()
        result = self._run(messages, _completion_history=history, _settled_calls=settled,
                           _recovery=recovery, _goal=goal, _reviews=reviews, _visuals=visuals, **kwargs)
        result = result.model_copy(update={"completion_history": tuple(history),
            "proposed_answer": recovery.proposed_answer if result.status != AgentRunStatus.COMPLETED else None,
            "settled_calls": tuple(settled),
            "delivered_visuals": tuple(sorted(visuals)),
            "review_failures": tuple(recovery.review_failures),
            "model_requests": recovery.model_requests,
            "consecutive_format_failures": recovery.consecutive_format_failures,
            "semantic_corrections": recovery.semantic_corrections,
            "context_projections": recovery.context_projections,
            "context_compactions": recovery.context_compactions,
            "context_recovery_failure": recovery.context_recovery_failure,
            "inference_requests": recovery.inference_requests,
            "estimated_input_tokens": recovery.estimated_input_tokens,
            "completion": result.completion if result.completion.incomplete or not history else history[-1]})
        if getattr(self.model, "mode", None) == "cloud" and result.status in WORK_BUDGET_STATUSES:
            result = result.model_copy(update={"message": WORK_BUDGET_MESSAGE,
                "partial_text": work_budget_progress(result),
                "completion": result.completion.model_copy(update={
                    "finish_reason": "agent_budget_limit", "interrupted": True})})
        if result.status in RECOVERY_STOP_STATUSES:
            result = result.model_copy(update={"partial_text": recovery_stop_progress(result),
                "completion": result.completion.model_copy(update={
                    "finish_reason": "agent_recovery_stop", "interrupted": True})})
        if result.status == AgentRunStatus.INTERNAL_FAILURE and result.context_recovery_failure is not None:
            result = result.model_copy(update={"partial_text": recovery_stop_progress(result),
                "completion": result.completion.model_copy(update={
                    "finish_reason": "agent_context_recovery_failed", "interrupted": True})})
        if result.status == AgentRunStatus.INCOMPLETE and reviews and reviews[-1].status == "blocked":
            result = result.model_copy(update={"completion": result.completion.model_copy(update={
                "finish_reason": "agent_task_unfinished", "interrupted": True})})
        if goal:
            final_goal = finish_goal(goal[0], completed=result.status == AgentRunStatus.COMPLETED)
            result = result.model_copy(update={"goal": final_goal,
                "completion_review": reviews[-1] if reviews else None,
                "completion_review_receipt_count": recovery.review_receipt_count if reviews else None,
                "completion_review_current": recovery.review_receipt_count == len(settled) if reviews else None})
            report = evidence_report(final_goal)
            if result.status in RECOVERY_STOP_STATUSES and reviews and reviews[-1].remaining:
                result = result.model_copy(update={"partial_text": (result.partial_text or '')
                    + ('\n\nRemaining completion requirements (model assessment):\n'
                        if result.completion_review_current else
                        '\n\nEarlier completion assessment (predates later tool results; requires reassessment):\n')
                    + '\n'.join('- ' + item for item in reviews[-1].remaining)})
            if report and result.partial_text is not None and result.status in RECOVERY_STOP_STATUSES | WORK_BUDGET_STATUSES:
                result = result.model_copy(update={"partial_text": (result.partial_text + "\n\n" + report)[:1_000_000]})
        from app.agent.word_evidence import word_stop_report
        word_report = word_stop_report(result)
        if word_report:
            result = result.model_copy(update={"partial_text":
                ((result.partial_text or result.message or "") + "\n\n" + word_report).strip()})
        return result

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
        activity_observer: Callable[[str], None] | None = None,
        completion_review_observer: Callable[[bool], None] | None = None,
        _recovery: _RecoveryUsage | None = None,
        _goal: list[TaskGoal] | None = None,
        _reviews: list[CompletionReview] | None = None,
        _visuals: set[str] | None = None,
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
        if activity_observer is not None and not callable(activity_observer):
            raise TypeError("Activity observers must be callable when supplied.")
        if completion_review_observer is not None and not callable(completion_review_observer):
            raise TypeError("Completion-review observers must be callable when supplied.")
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
        task_context_index = 1 if transcript and transcript[0].get("role") == "system" else 0
        if _goal:
            transcript.insert(task_context_index, task_context_message(_goal[0]))
        try:
            native_chat_messages(transcript, definitions,
                allow_attachments=getattr(self.model, "supports_native_attachment_tools", False) is True)
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
        project_repeat_recovery_used = False
        project_receipts: dict[str, list[str]] = {}
        read_progress = ReadProgressTracker()
        project_progress = ProjectProgressTracker()
        edit_progress = EditProgressTracker()
        office_read_progress = OfficeReadProgress()
        from app.agent.word_evidence import WordTurnProgress
        word_progress = WordTurnProgress()
        office_progress = OfficeProgress()
        repair_loop = project_progress.repair_loop
        prerequisite_retries = PrerequisiteRetries()
        recovery_progress = RecoveryProgress()
        pending_visuals = set()
        used_call_ids: set[str] = set()
        advertised_names = {item.name for item in definitions}
        required_fingerprints = tuple(call_fingerprint(call) for call in required_calls)
        if (
            len(required_calls) > self.effective_max_capability_calls
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
        proposed_answer = None
        review_started = False
        log.info("Agent step budget: mode=%s max_steps=%s max_model_requests=%s max_capability_calls=%s",
            "cloud" if getattr(self.model, "mode", None) == "cloud" else "local", self.effective_max_steps,
            self.effective_max_model_requests, self.effective_max_capability_calls)

        while True:
            if recovery_progress.exhausted(self.limits.max_semantic_corrections):
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
            if steps >= self.effective_max_steps:
                return self._stopped(
                    AgentRunStatus.STEP_LIMIT,
                    "The agent stopped after reaching its maximum model-step limit.",
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                )

            if planned_response is None and recovery.model_requests >= self.effective_max_model_requests:
                return self._stopped(AgentRunStatus.MODEL_REQUEST_LIMIT,
                    "The agent stopped after reaching its total model-request limit.",
                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            if planned_response is None:
                recovery.model_requests += 1
                report_activity(activity_observer, "Preparing the next step…")
                if not self._recover_transcript(transcript, definitions, recovery):
                    return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                        "Context recovery failed safely; settled operations were retained.",
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                if completion_review_observer is not None:
                    try:
                        completion_review_observer(proposed_answer is not None)
                    except Exception:
                        log.error("The completion-review phase could not be reported.")
                        return self._stopped(AgentRunStatus.INTERNAL_FAILURE,
                            "The completion-review phase could not be reported safely.",
                            steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            native_request = planned_response is None and not structured_fallback
            if planned_response is not None:
                response = planned_response
                planned_response = None
                model_stop = None
            elif structured_fallback:
                report_activity(activity_observer, "Checking completion…" if proposed_answer is not None else "Thinking…")
                response, model_stop = self._fallback_model_step(
                    transcript,
                    definitions,
                    started,
                    user_cancellation,
                    deadline_cancellation,
                    _request_usage=recovery,
                    _completion_review=proposed_answer is not None,
                )
            else:
                report_activity(activity_observer, "Checking completion…" if proposed_answer is not None else "Thinking…")
                response, model_stop = self._model_step(
                    transcript,
                    definitions,
                    started,
                    user_cancellation,
                    deadline_cancellation,
                    _request_usage=recovery,
                    _completion_review=proposed_answer is not None,
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
                    native_request = False
                    if _completion_history is not None:
                        _completion_history.append(response.completion)
                    if recovery.model_requests >= self.effective_max_model_requests:
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
                        _completion_review=proposed_answer is not None,
                    )
            if model_stop is not None:
                status, message = model_stop
                return self._stopped(
                    status,
                    message,
                    steps=steps,
                    capability_calls=capability_calls,
                    protocol_failures=protocol_failures,
                    partial_text=proposed_answer,
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
            if native_request and _visuals is not None:
                _visuals.update(pending_visuals)
                pending_visuals.clear()
            if response.completion.incomplete:
                message = response.completion.failure_message or (
                    "The response was cut off." if response.kind != ModelResponseKind.ASSISTANT_TEXT
                    else "The response is incomplete.")
                review_interrupted = response.completion.request_phase == 'completion_review' or (
                    response.completion.request_phase is None and proposed_answer is not None)
                if review_interrupted:
                    message += ' The completion review was interrupted; the proposed answer is retained and task completion remains unverified.'
                elif response.completion.observed_function_call is True:
                    message += " The incomplete tool generation was not executed."
                else:
                    message += ' The reply was interrupted before completion.'
                return self._stopped(self._incomplete_status(response.completion),
                    message,
                    steps=steps, capability_calls=capability_calls,
                    protocol_failures=protocol_failures + int(response.kind == ModelResponseKind.PROTOCOL_FAILURE),
                    completion=response.completion,
                    partial_text=proposed_answer if proposed_answer is not None else response.partial_text or response.assistant_text)
            if proposed_answer is not None and response.kind != ModelResponseKind.ASSISTANT_TEXT:
                # A checker cannot start another tool chain, even if an adapter
                # ignores its provider's tool-choice restriction. No settlement,
                # approval or provider call replay is recorded for a rejected proposal.
                protocol_failures += 1
                recovery.consecutive_format_failures += 1
                recovery.review_failures.append(ReviewFailure(reason='tool_proposal', model_request=recovery.model_requests,
                    response_chars=len(response.assistant_text or '')))
                record_review_event('exhausted' if recovery.consecutive_format_failures >= self.limits.max_protocol_failures
                    else 'rejected', 'tool_proposal', model_request=recovery.model_requests,
                    response_chars=len(response.assistant_text or ''), receipt_count=len(_settled_calls or ()),
                    failure_count=len(recovery.review_failures))
                if recovery.consecutive_format_failures >= self.limits.max_protocol_failures:
                    return self._stopped(AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                        "The completion check cannot call tools and did not return a valid assessment.",
                        completion=CompletionMetadata(finish_reason="agent_review_invalid", interrupted=True),
                        partial_text=proposed_answer, steps=steps, capability_calls=capability_calls,
                        protocol_failures=protocol_failures)
                transcript.append(completion_review_message(_goal[0],
                    edit_progress.pending_recovery() or edit_progress.completion_blocker(),
                    browser_inspection_available='project.inspect' in advertised_names,
                    settled_calls=_settled_calls or (), delivered_visuals=_visuals or (), ledger_version=2))
                transcript[-1]['content'] += '\nAssessment correction: Return the JSON assessment only; tool calls are unavailable during review.'
                continue
            provider_message_id = uuid4().hex
            assessment_text = (bool(_goal) and review_started and response.kind == ModelResponseKind.ASSISTANT_TEXT
                and looks_like_completion_review(response.assistant_text))
            if response.openai_response is not None and not (
                    assessment_text or proposed_answer is not None and response.kind == ModelResponseKind.ASSISTANT_TEXT):
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
                if proposed_answer is None and not assessment_text:
                    unfinished_word = word_progress.before_final()
                    if unfinished_word is not None:
                        retry, message = unfinished_word
                        if not retry:
                            return self._stopped(AgentRunStatus.INCOMPLETE,
                                "Word verification/finalization remains unfinished; completed work and save receipts are retained.",
                                partial_text=message, steps=steps, capability_calls=capability_calls,
                                protocol_failures=protocol_failures)
                        self._retain_response_text(transcript, response)
                        transcript.append({"role": "system", "content": message})
                        if not self._transcript_within_limit(transcript):
                            return self._transcript_limited(steps, capability_calls, protocol_failures)
                        continue
                    unfinished = office_read_progress.before_final()
                    if unfinished is not None:
                        retry, message = unfinished
                        if not retry:
                            return self._stopped(AgentRunStatus.INCOMPLETE, "The workbook read remains unfinished.",
                                partial_text=office_read_progress.unfinished_summary(), steps=steps, capability_calls=capability_calls,
                                protocol_failures=protocol_failures)
                        self._retain_response_text(transcript, response)
                        transcript.append({"role": "system", "content": message})
                        if not self._transcript_within_limit(transcript):
                            return self._transcript_limited(steps, capability_calls, protocol_failures)
                        continue
                filename_feedback = filename_disambiguation_feedback(
                    transcript,
                    advertised_names,
                )
                if filename_feedback is not None:
                    self._retain_response_text(transcript, response)
                    recovery.consecutive_format_failures = 0
                    recovery.semantic_corrections += 1
                    recovery_progress.correct('filename')
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
                    recovery_progress.correct('required')
                    transcript.append(required_calls_feedback())
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(
                            steps,
                            capability_calls,
                            protocol_failures,
                        )
                    continue
                if _goal:
                    if proposed_answer is None and assessment_text:
                        recovery.consecutive_format_failures += 1
                        protocol_failures += 1
                        if recovery.consecutive_format_failures >= self.limits.max_protocol_failures:
                            return self._stopped(AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                                "The task remains unfinished because an updated answer was not provided.",
                                steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                        transcript.append(resume_answer_message())
                    elif proposed_answer is None:
                        proposed_answer = response.assistant_text
                        recovery.proposed_answer = proposed_answer
                        review_started = True
                        recovery.consecutive_format_failures = 0
                        self._retain_response_text(transcript, response)
                        transcript.append(completion_review_message(_goal[0],
                            edit_progress.pending_recovery() or edit_progress.completion_blocker(),
                            browser_inspection_available='project.inspect' in advertised_names,
                            settled_calls=_settled_calls or (), delivered_visuals=_visuals or (), ledger_version=2))
                    else:
                        try:
                            review = parse_completion_review(response.assistant_text, _goal[0].goal_id)
                            review = review.model_copy(update={'evidence': compile_review_evidence(_goal[0], _settled_calls or (), ledger_version=2),
                                'evidence_origin': 'runtime', 'ledger_version': 2})
                            validate_review_evidence(review, _goal[0], _settled_calls or (), _visuals or ())
                        except ValueError as exc:
                            recovery.consecutive_format_failures += 1
                            protocol_failures += 1
                            reason = exc.reason if isinstance(exc, ReviewValidationError) else 'evidence_invalid'
                            recovery.review_failures.append(ReviewFailure(reason=reason, model_request=recovery.model_requests,
                                response_chars=len(response.assistant_text)))
                            exhausted = recovery.consecutive_format_failures >= self.limits.max_protocol_failures
                            record_review_event('exhausted' if exhausted else 'rejected', reason,
                                model_request=recovery.model_requests, response_chars=len(response.assistant_text),
                                receipt_count=len(_settled_calls or ()), failure_count=len(recovery.review_failures))
                            if recovery.consecutive_format_failures >= self.limits.max_protocol_failures:
                                return self._stopped(AgentRunStatus.PROTOCOL_FAILURE_LIMIT,
                                    'The automatic completion review was invalid (' + reason + '). '
                                    'Settled work and the proposed report are retained; task completion remains unverified.',
                                    completion=CompletionMetadata(finish_reason="agent_review_invalid", interrupted=True),
                                    partial_text=proposed_answer,
                                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                            transcript.append(completion_review_message(_goal[0],
                                edit_progress.pending_recovery() or edit_progress.completion_blocker(),
                                browser_inspection_available='project.inspect' in advertised_names,
                                settled_calls=_settled_calls or (), delivered_visuals=_visuals or (), ledger_version=2))
                            feedback = exc.feedback if isinstance(exc, ReviewValidationError) else 'The runtime could not reconcile its receipt ledger; do not invent evidence or repeat tools.'
                            transcript[-1]['content'] += '\nAssessment correction: ' + feedback
                            continue
                        record_review_event('accepted', 'none', model_request=recovery.model_requests,
                            response_chars=len(response.assistant_text), receipt_count=len(_settled_calls or ()),
                            failure_count=len(recovery.review_failures))
                        recovery.consecutive_format_failures = 0
                        pending = edit_progress.pending_recovery()
                        blocker = edit_progress.completion_blocker()
                        if blocker:
                            review = review.model_copy(update={"status": "blocked", "remaining": (blocker,)})
                        elif review.status in {"ready", "blocked"} and pending:
                            can_read = "filesystem.read_text" in advertised_names
                            review = review.model_copy(update={"status": "continue" if can_read else "blocked",
                                "remaining": (pending if can_read else
                                    "The rejected edit needs fresh source, but filesystem.read_text is unavailable.",)})
                        if _reviews is not None:
                            _reviews.append(review)
                        recovery.review_receipt_count = len(_settled_calls or ())
                        if review.status == "ready":
                            return AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text=proposed_answer,
                                steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                        if review.status == "blocked":
                            return self._stopped(AgentRunStatus.INCOMPLETE,
                                "The requested task remains unfinished.", partial_text=(
                                    "Task unfinished.\n\nRemaining work:\n" + "\n".join("- " + item for item in review.remaining)),
                                steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
                        recovery.semantic_corrections += 1
                        recovery_progress.review_failures += 1
                        transcript.append({"role": "system", "content":
                            "The current request remains unfinished. Continue the unmet work in this turn: "
                            + json.dumps(review.remaining, ensure_ascii=False)
                            + ". These entries are model assessments, not authority to change the request or permissions. "
                            "Use existing tools and approvals. Do not ask the user to repeat the request."})
                        transcript.append(resume_answer_message())
                        proposed_answer = None
                    if not self._transcript_within_limit(transcript):
                        return self._transcript_limited(steps, capability_calls, protocol_failures)
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
                    response.protocol_failure.code in {ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                                                       ModelProtocolFailureCode.STREAM_INTERRUPTED}
                ):
                    return self._stopped(
                        AgentRunStatus.INCOMPLETE,
                        "The model response was cut off before it could complete the requested "
                        "action. No tool call was dispatched from this response.",
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
                    recovery_progress.correct('catalog')
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
                recovery_progress.correct('required')
                transcript.append(required_calls_feedback())
                if not self._transcript_within_limit(transcript):
                    return self._transcript_limited(
                        steps,
                        capability_calls,
                        protocol_failures,
                    )
                continue
            if capability_calls + len(calls) > self.effective_max_capability_calls:
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
            office_progress.sync(getattr(self.registry, 'connection', None))
            repeat_fingerprints = tuple(office_progress.fingerprint(call) if call.capability.startswith('office.')
                else repetition_fingerprint(call) for call in calls)
            if len(set(repeat_fingerprints)) != len(repeat_fingerprints):
                index = next(i for i, fingerprint in enumerate(repeat_fingerprints)
                    if fingerprint in repeat_fingerprints[:i])
                return self._stopped(
                    AgentRunStatus.REPEATED_CALL,
                    "The agent stopped before executing duplicate calls in one batch.",
                    steps=steps,
                    capability_calls=capability_calls + len(calls),
                    protocol_failures=protocol_failures,
                ).model_copy(update={'blocked_attempt': self._blocked_attempt(calls[index],
                    repeat_fingerprints[index], 2,
                    office_diagnostic=office_progress.diagnostic(calls[index]) if calls[index].capability.startswith('office.') else None)})
            staged_repeated = dict(repeated)
            repeat_rejection = None
            for call, fingerprint in zip(calls, repeat_fingerprints, strict=True):
                # Office progress may settle earlier in this same batch. Decide
                # its allowance immediately before dispatch, using that result.
                if call.capability.startswith('office.'):
                    continue
                if prerequisite_retries.renew(call, step=steps,
                        repair_rejection=repair_loop.before(call, step=steps)):
                    staged_repeated.pop(fingerprint, None)
                staged_repeated[fingerprint] = staged_repeated.get(fingerprint, 0) + 1
                if staged_repeated[fingerprint] > self.limits.max_identical_calls:
                    if (not project_repeat_recovery_used and len(calls) == 1
                            and calls[0].capability in {"project.verify", "project.inspect"}):
                        project_repeat_recovery_used = True
                        repeat_rejection = CapabilityFailure(code=CapabilityErrorCode.CALL_REPLAYED,
                            message="This exact project check has already been attempted twice without a settled project change. "
                            "No new process was started. Use its recorded receipts and screenshots to diagnose the result, "
                            "complete the task, or choose a changed check for a concrete unmet requirement. "
                            "Another identical request will stop this turn.",
                            details=[{"prior_receipt_ids": project_receipts.get(fingerprint, [])[-2:]}])
                        continue
                    message = "The agent stopped after repeating an identical capability call."
                    return self._stopped(
                        AgentRunStatus.REPEATED_CALL,
                        message,
                        steps=steps,
                        capability_calls=capability_calls + len(calls),
                        protocol_failures=protocol_failures,
                    ).model_copy(update={'blocked_attempt': self._blocked_attempt(call, fingerprint,
                        staged_repeated[fingerprint], prerequisite_retries.reason(call),
                        repair_loop.prerequisite(call, step=steps))})

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
            recovery_feedback: list[str] = []
            semantic_stop = False
            for call, internal_call_id in zip(calls, internal_call_ids, strict=True):
                if call.capability.startswith('office.') and not linked.is_cancelled:
                    office_progress.sync(getattr(self.registry, 'connection', None))
                    fingerprint = office_progress.fingerprint(call)
                    if office_progress.renew(call, step=steps):
                        # This prerequisite earns one additional dispatch, not
                        # another full identical-call allowance.
                        repeated[fingerprint] = self.limits.max_identical_calls - 1
                        recovery_progress.review_failures = 0
                    repeated[fingerprint] = repeated.get(fingerprint, 0) + 1
                    if repeated[fingerprint] > self.limits.max_identical_calls:
                        message = 'The agent stopped after repeating an identical capability call.'
                        if call.capability == 'office.read':
                            from app.mcp.office_read_diagnostics import record_read_failure
                            shape = record_read_failure(call.arguments, {'stage': 'repeat_guard', 'reason': 'identical_call'})
                            message += f" office.read target={shape['target_kind']}; this call was not dispatched."
                        return self._stopped(AgentRunStatus.REPEATED_CALL, message,
                            steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures
                            ).model_copy(update={'blocked_attempt': self._blocked_attempt(call, fingerprint,
                                repeated[fingerprint], office_diagnostic=office_progress.diagnostic(call))})
                rejection = edit_progress.before(call, step=steps, assistant_text=response.assistant_text) if not linked.is_cancelled else None
                if rejection is None and not linked.is_cancelled:
                    rejection = repair_loop.before(call, step=steps)
                if rejection is None and not linked.is_cancelled:
                    rejection = word_progress.before(call)
                if repeat_rejection is not None and not linked.is_cancelled:
                    outcome = _CallOutcome(result=failure_result(internal_call_id, call.capability, repeat_rejection))
                elif rejection is not None:
                    blocked = failure_result(internal_call_id, call.capability,
                        CapabilityFailure(code=CapabilityErrorCode.INVALID_ARGUMENTS, message=rejection.message))
                    outcome = _CallOutcome(result=blocked.model_copy(update={"metadata": {
                        **blocked.metadata, "edit_recovery": rejection.reason}}))
                else:
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
                        activity_observer=activity_observer,
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
                    if _goal:
                        prior_goal = _goal[0]
                        _goal[0] = observe_goal(prior_goal, settled, prior_calls=(_settled_calls or [])[:-1])
                        if _goal[0] != prior_goal:
                            transcript[task_context_index] = task_context_message(_goal[0])
                            recovery_feedback.append(goal_feedback(_goal[0]))
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
                if call.capability in {"project.verify", "project.inspect"} and repeat_rejection is None:
                    project_receipts.setdefault(call_fingerprint(call), []).append(outcome.result.call_id)
                read_progress.observe(call, outcome.result, repeated)
                office_read_progress.observe(call, outcome.result)
                word_feedback = word_progress.observe(call, outcome.result)
                if word_feedback:
                    recovery_feedback.append(word_feedback)
                office_changed = office_progress.observe(call, outcome.result, repeated, step=steps)
                diagnosis_feedback = project_progress.observe(call, outcome.result, repeated, step=steps)
                office_scope = office_progress.scope(call) if call.capability.startswith('office.') else None
                recovery_progress.observe(call, outcome.result, repeated, scope=office_scope, office_changed=office_changed)
                prerequisite_retries.observe(call, outcome.result, step=steps)
                if diagnosis_feedback:
                    recovery_feedback.append(diagnosis_feedback)
                if rejection is not None and rejection.reason == 'inspection_diagnosis':
                    recovery_feedback.append(rejection.message)
                edit_observation = edit_progress.observe(call, outcome.result, step=steps)
                if edit_observation.refresh_source:
                    project_progress.renew_source(call.arguments.get("path"), repeated)
                if edit_observation.feedback is not None:
                    recovery_feedback.append(edit_observation.feedback)
                if outcome.result.error is not None and outcome.result.error.code in {
                    CapabilityErrorCode.INVALID_ARGUMENTS, CapabilityErrorCode.UNKNOWN_CAPABILITY,
                }:
                    recovery.semantic_corrections += 1
                    recovery_progress.correct(office_scope or recovery_scope(call))
                    if recovery_progress.exhausted(self.limits.max_semantic_corrections):
                        semantic_stop = True
                        break
                if edit_observation.stop_message is not None:
                    return self._stopped(AgentRunStatus.REPEATED_CALL, edit_observation.stop_message,
                        steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
            completed_required.update(
                fingerprint
                for fingerprint in fingerprints[:len(results)]
                if fingerprint in required_set
            )

            if required_set and completed_required == required_set and not semantic_stop:
                recovery_progress.failures.pop('required', None)
                if not continue_after_required_calls and not _goal:
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
                settled_batch = calls[:len(results)]
                # Keep the native call/result pairing adjacent and the final message
                # a capability result, including for older structured adapters.
                for feedback in dict.fromkeys(recovery_feedback):
                    transcript.append({"role": "system", "content": feedback})
                transcript.append(model_capability_calls_message(settled_batch, provider_message_id=provider_message_id, assistant_text=response.assistant_text))
                if response.openai_response is not None and not semantic_stop:
                    transcript[-1]["openai_response"] = response.openai_response.model_dump(mode="python")
                for call, result in zip(settled_batch, results, strict=True):
                    transcript.append(
                        model_capability_result_message(
                            call,
                            result.model_dump(mode="json"),
                            provider_message_id=provider_message_id,
                        )
                    )
                for call, result in zip(settled_batch, results, strict=True):
                    if call.capability == "project.inspect" and result.success:
                        from app.agent.inspection_images import inspection_image_message
                        message = inspection_image_message(self.registry.resolve(call.capability), result, self.model)
                        if message is not None:
                            transcript.append(message)
                            if message.get('role') == 'user':
                                output = result.output or {}
                                pending_visuals.update(observation['screenshot_sha256']
                                    for observation in [*output.get('checkpoints', []), output]
                                    if isinstance(observation.get('screenshot_sha256'), str))
                    elif call.capability == "office.read" and result.success:
                        from app.agent.office_images import word_image_message
                        message = word_image_message(self.registry.resolve(call.capability), call, result, self.model)
                        if message is not None:
                            transcript.append(message)
                            word_progress.images_delivered(call, result, message)
            except (TypeError, ValueError):
                return self._transcript_limited(
                    steps,
                    capability_calls,
                    protocol_failures,
                )
            if semantic_stop:
                return self._stopped(AgentRunStatus.SEMANTIC_CORRECTION_LIMIT,
                    ("The agent stopped after reaching its semantic-correction limit. "
                     + calls[len(results) - 1].capability + ": " + results[-1].error.message)[:500],
                    steps=steps, capability_calls=capability_calls, protocol_failures=protocol_failures)
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
        if not (self.context_recovery_enabled or self.conversation_context_enabled):
            return True
        from app.conversation.context import capability_schema_reserve
        from app.conversation.recovery import recover_context_request
        stage = 'schema_reserve'
        def observe_stage(value):
            nonlocal stage
            if isinstance(value, str) and value in {'budget', 'projection', 'compaction'}:
                stage = value
        try:
            reserved_tokens = capability_schema_reserve(definitions, inference=self.model)
            stage = 'projection'
            recovered = recover_context_request(self.model, transcript,
                reserved_tokens=reserved_tokens, stage_observer=observe_stage)
        except Exception as exc:
            usage.context_recovery_failure = context_recovery_failure(stage, exc)
            record_context_failure(usage.context_recovery_failure)
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
        activity_observer: Callable[[str], None] | None = None,
    ) -> _CallOutcome:
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

        # Gate changes before preparation: a stale patch may fail preparation,
        # but it must still point to human review instead of starting retries.
        blocked = self.executor.blocked_reason(capability.permission)
        if blocked is not None:
            # The new call never started. Uncertainty belongs to the old one.
            return _CallOutcome(result=failure_result(internal_call_id, call.capability,
                CapabilityFailure(code=CapabilityErrorCode.PERMISSION_DENIED, message=blocked)),
                stop_status=AgentRunStatus.INTERNAL_FAILURE, stop_message=blocked)

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
            report_activity(activity_observer, "Checking permissions…")
            self.executor.journal.record_prepared(prepared)
            evaluation = self.permission_gate.evaluate(prepared)
            authorization_outcome = self._authorize(
                evaluation,
                prepared=prepared,
                cancellation=cancellation,
                started=started,
                user_cancellation=user_cancellation,
                deadline_cancellation=deadline_cancellation,
                activity_observer=activity_observer,
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
            report_activity(activity_observer, capability_activity(
                call.capability, prepared.validated_arguments().model_dump(mode="json")))
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
        activity_observer: Callable[[str], None] | None = None,
    ) -> _AuthorizationOutcome:
        if evaluation.decision != PermissionDecision.ASK:
            return _AuthorizationOutcome(
                authorization=self.approval_manager.authorize(
                    evaluation,
                    cancellation=cancellation,
                ),
                record_final_authorization=True,
            )

        review_required = self.tool_approval_required
        if review_required:
            report_activity(activity_observer, "Waiting for your approval…")
        record = self.approval_manager.request(
            evaluation,
            cancellation=cancellation,
        )
        if not review_required:
            # OFF changes the review surface, not the policy or exact-call binding.
            self.approval_manager.resolve(record.approval_id, ApprovalStatus.APPROVED)
            return _AuthorizationOutcome(
                authorization=self.approval_manager.authorize(
                    evaluation, approval_id=record.approval_id, cancellation=cancellation),
                record_final_authorization=True,
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
        *, _request_usage: _RecoveryUsage | None = None, _completion_review: bool = False,
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
                method = self.model.review_completion if _completion_review else self.model.respond_with_capabilities
                future.set_result(
                    method(
                        deepcopy(transcript),
                        definitions,
                    )
                )
            except BaseException as exc:
                future.set_exception(exc)

        Thread(target=run_in_turn, args=(current_turn_id(), invoke,
               'completion_review' if _completion_review else 'reply'),
               name="orsi-agent-model-step", daemon=True).start()
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
        *, _request_usage: _RecoveryUsage | None = None, cloud_only: bool = False, _completion_review: bool = False,
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
                respond = getattr(self.model, "respond_cloud_only", None) if cloud_only else self.model.respond
                if not callable(respond):
                    raise InferenceUnavailable("Office recovery requires a cloud-only model adapter.")
                future.set_result(respond(deepcopy(transcript)))
            except BaseException as exc:
                future.set_exception(exc)

        Thread(target=run_in_turn, args=(current_turn_id(), invoke,
               'completion_review' if _completion_review else 'reply'),
               name="orsi-conversation-model-step", daemon=True).start()
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
        *, _request_usage: _RecoveryUsage | None = None, _completion_review: bool = False,
    ) -> tuple[ModelResponse | None, tuple[AgentRunStatus, str] | None]:
        from app.inference.openai_replay import neutral_messages
        fallback_messages = constrained_fallback_messages(neutral_messages(transcript), definitions)
        raw, stop = self._text_model_step(
            fallback_messages,
            started,
            user_cancellation,
            deadline_cancellation,
            _request_usage=_request_usage,
            cloud_only=any(definition.name.startswith("office.") for definition in definitions),
            _completion_review=_completion_review,
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
        from app.inference.local_images import image_accounting_messages
        if json_size(image_accounting_messages(transcript)) > self.limits.max_transcript_bytes:
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
    def _blocked_attempt(call, fingerprint, count, rejection_reason=None, repair_requirement=None, *, office_diagnostic=None):
        target = ('source_file' if call.capability.startswith('filesystem.') else
            'project' if call.capability.startswith('project.') else
            'office_document' if call.capability.startswith('office.') else 'other')
        reason = ('repair_diagnosis_required' if rejection_reason == 'inspection_diagnosis' else
            'source_read_required' if rejection_reason in {'fresh_source_required', 'read_before_patch_required',
                'target_not_in_read', 'read_digest_mismatch'} else 'unchanged_recovery_state')
        receipt = None
        if repair_requirement is not None:
            reason, receipt = repair_requirement
        if office_diagnostic is not None:
            return BlockedCallAttempt(capability=call.capability, fingerprint=fingerprint,
                repetition_count=count, target_kind=target, **office_diagnostic)
        return BlockedCallAttempt(capability=call.capability, fingerprint=fingerprint,
            repetition_count=count, target_kind=target, prerequisite_reason=reason, evidence_receipt=receipt)

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
