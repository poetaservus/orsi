from __future__ import annotations

import logging
import re
from typing import Any, NamedTuple


_SAFE_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")


class CompletionDiagnostics(NamedTuple):
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None


def completion_diagnostics(payload: Any) -> CompletionDiagnostics:
    """Extract bounded, content-free completion diagnostics for logs."""
    if not isinstance(payload, dict):
        return CompletionDiagnostics(None, None, None)
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else None
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    if not isinstance(finish_reason, str) or _SAFE_LABEL.fullmatch(finish_reason) is None:
        finish_reason = None

    usage = payload.get("usage")
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if (
        isinstance(prompt_tokens, bool)
        or not isinstance(prompt_tokens, int)
        or prompt_tokens < 0
    ):
        prompt_tokens = None
    if (
        isinstance(completion_tokens, bool)
        or not isinstance(completion_tokens, int)
        or completion_tokens < 0
    ):
        completion_tokens = None
    return CompletionDiagnostics(finish_reason, prompt_tokens, completion_tokens)


def record_completion_diagnostics(
    logger: logging.Logger,
    payload: Any,
    *,
    provider: str,
) -> CompletionDiagnostics:
    """Record provider metadata without retaining generated text or request content."""
    if not isinstance(logger, logging.Logger):
        raise TypeError("Completion diagnostics require a logger.")
    provider = _safe_label(provider)
    values = completion_diagnostics(payload)
    logger.info(
        "Inference completion diagnostics: provider=%s finish_reason=%s "
        "input_tokens=%s output_tokens=%s.",
        provider,
        values.finish_reason,
        values.input_tokens,
        values.output_tokens,
    )
    return values


def record_context_budget(
    logger: logging.Logger,
    budget,
    *,
    request_kind: str,
) -> None:
    """Record only numeric context-budget components for one physical request."""
    if not isinstance(logger, logging.Logger):
        raise TypeError("Context diagnostics require a logger.")
    values = budget.diagnostic_values()
    if set(values) != {
        "model_context_limit",
        "system_message_tokens",
        "conversation_tokens",
        "structured_tool_history_tokens",
        "capability_schema_reserve",
        "requested_output_reserve",
        "safety_buffer",
        "total_estimated_request_tokens",
        "remaining_tokens",
    } or any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in values.values()
    ):
        raise TypeError("Context diagnostics require one validated numeric budget.")
    request_kind = _safe_label(request_kind)
    logger.info(
        "Context budget: kind=%s limit=%d system=%d conversation=%d tool_history=%d "
        "capability_schema=%d output_reserve=%d safety_buffer=%d total=%d remaining=%d.",
        request_kind,
        values["model_context_limit"],
        values["system_message_tokens"],
        values["conversation_tokens"],
        values["structured_tool_history_tokens"],
        values["capability_schema_reserve"],
        values["requested_output_reserve"],
        values["safety_buffer"],
        values["total_estimated_request_tokens"],
        values["remaining_tokens"],
    )


def _safe_label(value: Any) -> str:
    candidate = str(value).strip()
    return candidate if _SAFE_LABEL.fullmatch(candidate) is not None else "unknown"
