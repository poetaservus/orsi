from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference.engine import InferenceUnavailable
from app.inference.completion import CompletionMetadata
from app.inference.protocol import ModelCapabilityCall, model_capability_calls_message, model_capability_result_message
from app.capabilities.contracts import CapabilityResult


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    STEP_LIMIT = "step_limit"
    CAPABILITY_CALL_LIMIT = "capability_call_limit"
    REPEATED_CALL = "repeated_call"
    PROTOCOL_FAILURE_LIMIT = "protocol_failure_limit"
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

    @model_validator(mode="after")
    def validate_pair(self):
        if self.call.capability != self.result.capability:
            raise ValueError("Settled results must match their generating call.")
        self.messages()  # Enforce the existing transcript size/JSON boundary.
        return self

    def messages(self) -> list[dict]:
        return [model_capability_calls_message((self.call,), provider_message_id=self.provider_message_id),
                model_capability_result_message(self.call, self.result.model_dump(mode="json"),
                                                provider_message_id=self.provider_message_id)]


class AgentRunResult(BaseModel):
    """One bounded terminal outcome from an AgentRuntime invocation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: AgentRunStatus
    assistant_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    message: str | None = Field(default=None, min_length=1, max_length=500)
    steps: int = Field(ge=0, le=32)
    capability_calls: int = Field(ge=0, le=32)
    protocol_failures: int = Field(ge=0, le=32)
    completion: CompletionMetadata = Field(default_factory=CompletionMetadata)
    completion_history: tuple[CompletionMetadata, ...] = Field(default=(), max_length=64)
    partial_text: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    settled_calls: tuple[SettledCall, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_terminal_outcome(self):
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
