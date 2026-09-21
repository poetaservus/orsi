from __future__ import annotations

import math
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


class AgentRuntimeLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_steps: int = Field(default=8, ge=1, le=32)
    max_capability_calls: int = Field(default=16, ge=1, le=32)
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


def model_unavailable_message(exc: InferenceUnavailable) -> str:
    """Return a bounded user-safe provider failure without suppressing useful detail."""
    detail = str(exc).strip()
    if not detail:
        return "The selected model provider is unavailable."
    return f"The selected model provider is unavailable: {detail}"[:500]
