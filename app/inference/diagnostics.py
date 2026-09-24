from __future__ import annotations

from typing import Any


def completion_diagnostics(payload: Any) -> tuple[str | None, int | None, int | None]:
    """Extract bounded, content-free completion diagnostics for logs."""
    if not isinstance(payload, dict):
        return None, None, None
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else None
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    if not isinstance(finish_reason, str) or not finish_reason:
        finish_reason = None
    elif len(finish_reason) > 64:
        finish_reason = finish_reason[:64]

    usage = payload.get("usage")
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if isinstance(prompt_tokens, bool) or not isinstance(prompt_tokens, int):
        prompt_tokens = None
    if isinstance(completion_tokens, bool) or not isinstance(completion_tokens, int):
        completion_tokens = None
    return finish_reason, prompt_tokens, completion_tokens
