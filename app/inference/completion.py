"""Completion state retained alongside text, without changing string callers."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.inference.diagnostics import completion_diagnostics


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CompletionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    finish_reason: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    interrupted: bool = False

    @property
    def incomplete(self) -> bool:
        return self.interrupted or self.finish_reason in {"length", "content_filter", "cancelled", "error"}

    @classmethod
    def from_payload(cls, payload: Any):
        diagnostics = completion_diagnostics(payload)
        usage = payload.get("usage") if isinstance(payload, dict) else None
        total = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(total) is not int or total < 0:
            total = None
        return cls(finish_reason=diagnostics.finish_reason, usage=TokenUsage(
            input_tokens=diagnostics.input_tokens, output_tokens=diagnostics.output_tokens,
            total_tokens=total))


class CompletionText(str):
    """A string-compatible value with immutable completion metadata attached.

    Plain strings from older/custom adapters remain supported. Application code
    must rewrap transformed text explicitly rather than silently dropping state.
    """
    def __new__(cls, content: str, completion: CompletionMetadata | None = None,
                history: tuple[CompletionMetadata, ...] | None = None, *, status_message: str | None = None,
                openai_response=None):
        value = super().__new__(cls, content)
        value.completion = completion or getattr(content, "completion", CompletionMetadata())
        value.completion_history = history if history is not None else getattr(
            content, "completion_history", (value.completion,))
        value.status_message = status_message or getattr(content, "status_message", None)
        value.openai_response = openai_response or getattr(content, "openai_response", None)
        return value

    @property
    def partial_text(self) -> str | None:
        return str(self) if self.completion.incomplete else None


class IncompleteResponseError(RuntimeError):
    def __init__(self, message: str, completion: CompletionMetadata,
                 partial_text: str | None = None, history=()):
        super().__init__(message)
        self.completion = completion
        self.partial_text = partial_text
        self.completion_history = history or (completion,)
