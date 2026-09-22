from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference.engine import InferenceUnavailable


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    STEP_LIMIT = "step_limit"
    CAPABILITY_CALL_LIMIT = "capability_call_limit"
    REPEATED_CALL = "repeated_call"
    PROTOCOL_FAILURE_LIMIT = "protocol_failure_limit"
    APPROVAL_REQUIRED = "approval_required"
    TRANSCRIPT_LIMIT = "transcript_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    INTERNAL_FAILURE = "internal_failure"


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


def model_unavailable_message(exc: InferenceUnavailable) -> str:
    """Return a bounded user-safe provider failure without suppressing useful detail."""
    detail = str(exc).strip()
    if not detail:
        return "The selected model provider is unavailable."
    return f"The selected model provider is unavailable: {detail}"[:500]
