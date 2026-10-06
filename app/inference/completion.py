"""Completion state retained alongside text, without changing string callers."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.inference.diagnostics import completion_diagnostics
from app.inference.openai_metrics import OpenAIRequestMetrics


ResponseFailureReason = Literal[
    "stream_ended", "stream_timeout", "stream_connection", "invalid_stream",
    "protocol_limit", "invalid_sequence", "invalid_identity", "missing_creation",
    "invalid_terminal", "contradictory_output", "invalid_output_item", "invalid_message_part",
    "invalid_text", "text_limit", "orphan_tool_arguments", "unknown_completed_item",
    "unsupported_event", "provider_failed", "provider_incomplete", "unfinished_tool_call",
    "output_limit", "content_filter", "cancelled",
    "provider_stream_error", "provider_rate_limit", "provider_quota", "provider_context_overflow",
    "provider_authentication", "provider_permission", "provider_unavailable", "provider_bad_request",
    "sdk_response_validation",
]
# Fixed local wording only: provider messages, event values and exception text
# must never become a diagnostic or status message.
_FAILURE_MESSAGES = {
    "stream_ended": "The cloud stream ended without a completion event.",
    "stream_timeout": "The cloud stream timed out before completion.",
    "stream_connection": "The cloud connection was interrupted before completion.",
    "invalid_stream": "The cloud response stream could not be decoded.",
    "protocol_limit": "The cloud stream exceeded its protocol limit for events or size.",
    "invalid_sequence": "The cloud stream had an invalid event sequence.",
    "invalid_identity": "The cloud stream had an invalid response identity.",
    "missing_creation": "The cloud stream was missing its creation event.",
    "invalid_terminal": "The cloud completion event did not match its response.",
    "contradictory_output": "The cloud completion event contradicted earlier output.",
    "invalid_output_item": "The cloud stream contained an invalid output item.",
    "invalid_message_part": "The cloud stream contained an invalid message part.",
    "invalid_text": "The cloud stream contained an invalid text event.",
    "text_limit": "The cloud stream exceeded its text size limit.",
    "orphan_tool_arguments": "The cloud stream contained tool arguments without a matching call.",
    "unknown_completed_item": "The cloud stream completed an unknown output item.",
    "unsupported_event": "The cloud stream contained an event Orsi does not support.",
    "provider_failed": "The cloud provider reported a failed response.",
    "provider_incomplete": "The cloud provider reported an incomplete response.",
    "unfinished_tool_call": "The cloud provider returned an unfinished tool call.",
    "output_limit": "The cloud response reached its output token limit.",
    "content_filter": "The cloud response was interrupted by the provider's content filter.",
    "cancelled": "The cloud response was stopped.",
    "provider_stream_error": "The cloud provider reported an error during streaming.",
    "provider_rate_limit": "The cloud provider's rate limit was reached during streaming. Try again later.",
    "provider_quota": "The cloud provider reported a quota or billing limit during streaming.",
    "provider_context_overflow": "The cloud provider reported that the request exceeds its context limit.",
    "provider_authentication": "The cloud provider rejected authentication during streaming.",
    "provider_permission": "The cloud provider rejected access to the request or model during streaming.",
    "provider_unavailable": "The cloud provider reported an internal error during streaming. Try again later.",
    "provider_bad_request": "The cloud provider rejected the request during streaming.",
    "sdk_response_validation": "The cloud response did not match the SDK's expected format.",
}


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class CompletionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    finish_reason: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    interrupted: bool = False
    request_metrics: OpenAIRequestMetrics | None = None
    failure_reason: ResponseFailureReason | None = None

    @property
    def failure_message(self) -> str | None:
        return _FAILURE_MESSAGES.get(self.failure_reason)

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
