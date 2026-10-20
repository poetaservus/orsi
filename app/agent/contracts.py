from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference.engine import InferenceUnavailable
from app.inference.completion import CompletionMetadata
from app.inference.protocol import ModelCapabilityCall, model_capability_calls_message, model_capability_result_message
from app.capabilities.contracts import CapabilityResult
from app.agent.goals import TaskGoal
from app.agent.task_completion import CompletionReview
from app.agent.review_diagnostics import ReviewFailure
from app.agent.context_diagnostics import ContextRecoveryFailure
from app.settings.agent_limits import (
    MAX_AGENT_STEPS, MAX_AGENT_MODEL_REQUESTS, MAX_AGENT_CAPABILITY_CALLS, MAX_AGENT_COMPLETIONS,
)


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    STEP_LIMIT = "step_limit"
    CAPABILITY_CALL_LIMIT = "capability_call_limit"
    REPEATED_CALL = "repeated_call"
    PROTOCOL_FAILURE_LIMIT = "protocol_failure_limit"
    SEMANTIC_CORRECTION_LIMIT = "semantic_correction_limit"
    MODEL_REQUEST_LIMIT = "model_request_limit"
    APPROVAL_REQUIRED = "approval_required"
    TRANSCRIPT_LIMIT = "transcript_limit"
    CONTEXT_LIMIT = "context_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    INTERNAL_FAILURE = "internal_failure"


class SettledCall(BaseModel):
    """One settled result, independent of any later model or batch outcome."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    provider_message_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    call: ModelCapabilityCall
    result: CapabilityResult
    assistant_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)

    @model_validator(mode="after")
    def validate_pair(self):
        if self.call.capability != self.result.capability:
            raise ValueError("Settled results must match their generating call.")
        self.messages()  # Enforce the existing transcript size/JSON boundary.
        return self

    def messages(self) -> list[dict]:
        return [model_capability_calls_message((self.call,), provider_message_id=self.provider_message_id,
                                              assistant_text=self.assistant_text),
                model_capability_result_message(self.call, self.result.model_dump(mode="json"),
                                                provider_message_id=self.provider_message_id)]


class BlockedCallAttempt(BaseModel):
    """Content-free diagnosis of a proposed call stopped before dispatch.

    This is deliberately not a ModelCapabilityCall: retaining raw arguments here
    would both expose private content and make an unsettled proposal look replayable.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    capability: str = Field(min_length=3, max_length=128,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    repetition_count: int = Field(ge=1, le=MAX_AGENT_CAPABILITY_CALLS + 1)
    target_kind: Literal["source_file", "project", "office_document", "application", "other"] = "other"
    prerequisite_reason: Literal["source_read_required", "repair_diagnosis_required",
        "current_evidence_required", "unchanged_recovery_state"] | None = None
    evidence_receipt: str | None = Field(default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AgentRunResult(BaseModel):
    """One bounded terminal outcome from an AgentRuntime invocation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: AgentRunStatus
    assistant_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    message: str | None = Field(default=None, min_length=1, max_length=500)
    steps: int = Field(ge=0, le=MAX_AGENT_STEPS)
    capability_calls: int = Field(ge=0, le=MAX_AGENT_CAPABILITY_CALLS)
    protocol_failures: int = Field(ge=0, le=MAX_AGENT_STEPS)
    consecutive_format_failures: int = Field(default=0, ge=0, le=MAX_AGENT_STEPS)
    semantic_corrections: int = Field(default=0, ge=0, le=MAX_AGENT_STEPS + MAX_AGENT_CAPABILITY_CALLS)
    model_requests: int = Field(default=0, ge=0, le=MAX_AGENT_MODEL_REQUESTS)
    # Includes compaction requests; it is accounting, not the execution budget.
    inference_requests: int = Field(default=0, ge=0)
    estimated_input_tokens: int = Field(default=0, ge=0)
    context_projections: int = Field(default=0, ge=0)
    context_compactions: int = Field(default=0, ge=0)
    context_recovery_failure: ContextRecoveryFailure | None = None
    completion: CompletionMetadata = Field(default_factory=CompletionMetadata)
    completion_history: tuple[CompletionMetadata, ...] = Field(default=(), max_length=MAX_AGENT_COMPLETIONS)
    partial_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    # A generated answer can survive continued verification without becoming a
    # successful terminal answer or a replayable capability request.
    proposed_answer: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    blocked_attempt: BlockedCallAttempt | None = None
    settled_calls: tuple[SettledCall, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)
    goal: TaskGoal | None = None
    completion_review: CompletionReview | None = None
    # None preserves the meaning of outcomes saved before evidence anchoring.
    completion_review_current: bool | None = None
    completion_review_receipt_count: int | None = Field(default=None, ge=0, le=MAX_AGENT_CAPABILITY_CALLS)
    delivered_visuals: tuple[str, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS * 5)
    review_failures: tuple[ReviewFailure, ...] = Field(default=(), max_length=MAX_AGENT_STEPS)

    @model_validator(mode="after")
    def validate_terminal_outcome(self):
        if self.completion_review is not None:
            if self.goal is None or self.completion_review.goal_id != self.goal.goal_id:
                raise ValueError("Completion reviews must belong to the current goal.")
            if self.status == AgentRunStatus.COMPLETED and self.completion_review.status != "ready":
                raise ValueError("Unfinished reviews cannot complete a task.")
        if self.status == AgentRunStatus.COMPLETED:
            if (self.assistant_text is None or self.message is not None
                    or self.completion.incomplete or self.partial_text is not None):
                raise ValueError("Completed agent runs require assistant text only.")
        elif self.assistant_text is not None or self.message is None:
            raise ValueError("Stopped agent runs require one bounded status message.")
        return self


def model_unavailable_message(exc: InferenceUnavailable) -> str:
    """Return a bounded user-safe provider failure without suppressing useful detail."""
    detail = str(exc).strip()
    if not detail:
        return "The selected model provider is unavailable."
    return f"The selected model provider is unavailable: {detail}"[:500]
