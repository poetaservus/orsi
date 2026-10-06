"""Pace requests using numeric rate headers and a content-free minute ledger."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import math
import re
from time import monotonic

from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError


log = logging.getLogger(__name__)
_WINDOW = 60.0
_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)(ms|s|m|h))")
_UNITS = {"ms": .001, "s": 1, "m": 60, "h": 3600}
_RESOURCES = ("requests", "tokens", "project-tokens")


def _number(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 12:
        return None
    return int(value)


def _seconds(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    parts = list(_DURATION.finditer(value))
    if not parts or "".join(part.group() for part in parts) != value:
        return None
    seconds = sum(float(part[1]) * _UNITS[part[2]] for part in parts)
    return seconds if math.isfinite(seconds) and 0 <= seconds <= 86_400 else None


@dataclass
class Reservation:
    started: float
    tokens: int


@dataclass
class _Budget:
    requests: int | None = None
    tokens: int | None = None
    ledger: list[Reservation] = field(default_factory=list)
    headers: dict[str, tuple[int, int, float]] = field(default_factory=dict)


class OpenAIRatePacer:
    def __init__(self, configured=None, *, clock=monotonic, sleep=asyncio.sleep):
        self.clock, self.sleep = clock, sleep
        self.budgets = {model: _Budget(limits.requests_per_minute, limits.tokens_per_minute)
            for model, limits in (configured or {}).items()}

    def observe(self, model, headers):
        budget = self.budgets.setdefault(model, _Budget())
        now = self.clock()
        for resource in _RESOURCES:
            limit = _number(headers.get(f"x-ratelimit-limit-{resource}"))
            remaining = _number(headers.get(f"x-ratelimit-remaining-{resource}"))
            reset = _seconds(headers.get(f"x-ratelimit-reset-{resource}"))
            if limit is None or not limit:
                continue
            if resource == "requests":
                budget.requests = limit
            elif resource == "tokens":
                budget.tokens = limit
            if remaining is None or remaining > limit or reset is None:
                continue
            budget.headers[resource] = (limit, remaining, now + reset)
            log.info("OpenAI rate capacity: resource=%s limit=%s remaining=%s reset_seconds=%s",
                resource, limit, remaining, reset)

    def _delay(self, budget, cost, now):
        budget.ledger[:] = [entry for entry in budget.ledger if entry.started + _WINDOW > now]
        waits = []
        for resource, (limit, remaining, reset_at) in list(budget.headers.items()):
            if reset_at <= now:
                del budget.headers[resource]
                continue
            required = 1 if resource == "requests" else cost
            if required > limit:
                raise CloudInferenceError("The request's token allowance exceeds the API token rate limit. "
                    "Use a smaller output allowance or increase the model's API rate limit.",
                    code=CloudErrorCode.RATE_LIMIT)
            if remaining < required:
                waits.append(reset_at - now)
        if budget.tokens is not None and cost > budget.tokens:
            raise CloudInferenceError("The request's token allowance exceeds the API token rate limit. "
                "Use a smaller output allowance or increase the model's API rate limit.",
                code=CloudErrorCode.RATE_LIMIT)
        requests, tokens = len(budget.ledger) + 1, sum(entry.tokens for entry in budget.ledger) + cost
        for entry in budget.ledger:
            if (budget.requests is None or requests <= budget.requests) and (
                    budget.tokens is None or tokens <= budget.tokens):
                break
            waits.append(entry.started + _WINDOW - now)
            requests -= 1
            tokens -= entry.tokens
        return max(waits, default=0)

    async def acquire(self, model, cost):
        budget = self.budgets.setdefault(model, _Budget())
        while True:
            delay = self._delay(budget, cost, self.clock())
            if not delay:
                reservation = Reservation(self.clock(), cost)
                budget.ledger.append(reservation)
                for resource, (limit, remaining, reset_at) in list(budget.headers.items()):
                    budget.headers[resource] = (limit, max(0, remaining - (1 if resource == "requests" else cost)), reset_at)
                return reservation
            log.info("OpenAI rate wait: seconds=%.3f estimated_tokens=%s", delay, cost)
            await self.sleep(delay)

    def settle(self, reservation, usage=None):
        # A completed usage record includes cached input and private reasoning.
        # Unknown usage keeps the reservation; interruptions never refund it.
        if reservation is not None:
            reservation.started = self.clock()
            if usage is not None and usage.total_tokens is not None:
                reservation.tokens = usage.total_tokens
