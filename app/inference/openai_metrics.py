"""Content-free measurements for one SDK operation, including its bounded retries."""
from __future__ import annotations

from time import monotonic
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenAIRequestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    outcome: Literal["completed", "incomplete", "cancelled", "error"]
    attempts: int = Field(ge=0)
    queue_ms: float = Field(ge=0, allow_inf_nan=False)
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    first_event_ms: float | None = Field(None, ge=0, allow_inf_nan=False)
    first_text_ms: float | None = Field(None, ge=0, allow_inf_nan=False)


class RequestMeasurement:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.queued = clock()
        self.started = None
        self.first_event = None
        self.first_text = None
        self.attempts = 0

    def start(self):
        self.started = self.clock()

    async def request_hook(self, request):
        del request  # Never retain or inspect headers, URL, input or identities.
        self.attempts += 1

    def observe(self, state):
        now = self.clock()
        if self.first_event is None:
            self.first_event = now
        if self.first_text is None and state.partial_text:
            self.first_text = now

    def finish(self, outcome):
        ended = self.clock()
        started = self.started if self.started is not None else ended
        def elapsed(value):
            return round(max(0, value - started) * 1000, 3) if value is not None else None
        return OpenAIRequestMetrics(outcome=outcome, attempts=self.attempts,
            queue_ms=round(max(0, started - self.queued) * 1000, 3), duration_ms=elapsed(ended),
            first_event_ms=elapsed(self.first_event), first_text_ms=elapsed(self.first_text))


def record_request_metrics(logger, metrics, usage):
    logger.info("OpenAI request metrics: outcome=%s attempts=%s queue_ms=%s duration_ms=%s "
        "first_event_ms=%s first_text_ms=%s input_tokens=%s output_tokens=%s total_tokens=%s "
        "cached_input_tokens=%s cache_write_tokens=%s reasoning_tokens=%s",
        metrics.outcome, metrics.attempts, metrics.queue_ms, metrics.duration_ms,
        metrics.first_event_ms, metrics.first_text_ms, usage.input_tokens, usage.output_tokens,
        usage.total_tokens, usage.cached_input_tokens, usage.cache_write_tokens, usage.reasoning_tokens)
