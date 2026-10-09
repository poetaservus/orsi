"""Reviewed public event/code identifiers; no raw SDK fields or exception text."""
from functools import lru_cache
from importlib.metadata import version
import json
import re
from typing import get_args

from app.inference.completion import ResponseFailureReason


# Public Responses event names, reviewed against the reference and SDK 2.54.0.
# Logging a name does not add it to the stream protocol's accepted events.
_EVENT_CATEGORIES = {
    **dict.fromkeys(("response." + s for s in
        ("created", "in_progress", "completed", "failed", "incomplete", "queued")), "lifecycle"),
    **dict.fromkeys(("response." + s for s in
        ("output_item.added", "output_item.done", "content_part.added", "content_part.done")), "output"),
    **dict.fromkeys(("response.output_text." + s for s in
        ("delta", "done", "annotation.added")), "text"),
    **dict.fromkeys(("response.refusal." + s for s in ("delta", "done")), "refusal"),
    **dict.fromkeys(("response.function_call_arguments." + s for s in ("delta", "done")), "function_call"),
    **dict.fromkeys(("response." + s for s in ("reasoning_summary_part.added", "reasoning_summary_part.done",
        "reasoning_summary_text.delta", "reasoning_summary_text.done", "reasoning_text.delta", "reasoning_text.done")), "reasoning"),
    **dict.fromkeys(("response.image_generation_call." + s for s in
        ("in_progress", "generating", "partial_image", "completed")), "image_generation"),
    **dict.fromkeys(("response.audio." + s for s in
        ("delta", "done", "transcript.delta", "transcript.done")), "audio"),
    **dict.fromkeys(("response." + s for s in ("web_search_call.in_progress", "web_search_call.searching",
        "web_search_call.completed", "file_search_call.in_progress", "file_search_call.searching",
        "file_search_call.completed", "code_interpreter_call.in_progress", "code_interpreter_call.interpreting",
        "code_interpreter_call.completed", "code_interpreter_call_code.delta", "code_interpreter_call_code.done",
        "mcp_call.in_progress", "mcp_call.completed", "mcp_call.failed", "mcp_call_arguments.delta",
        "mcp_call_arguments.done", "mcp_list_tools.in_progress", "mcp_list_tools.completed", "mcp_list_tools.failed",
        "custom_tool_call_input.delta", "custom_tool_call_input.done")), "provider_tool"),
    "error": "error", "none": "none",
}
_CODES = frozenset({"context_length_exceeded", "context_window_exceeded", "input_too_long",
    "insufficient_quota", "billing_hard_limit_reached", "billing_not_active", "rate_limit_exceeded",
    "invalid_api_key", "permission_denied", "model_not_found", "server_error", "internal_error",
    "internal_server_error", "invalid_parameter", "invalid_argument", "invalid_request_error"})
_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}(?:(?:a|b|rc)[0-9]{1,4})?\Z")


def event_labels(kind):
    if isinstance(kind, str) and kind in _EVENT_CATEGORIES:
        return kind, _EVENT_CATEGORIES[kind]
    return "unrecognized", "unknown"


@lru_cache(maxsize=1)
def sdk_version():
    try:
        value = version("openai")
    except Exception:
        return "unknown"
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else "unknown"


def record_stream_failure(logger, state, *, origin="stream", reason, code=None):
    """Accept only locally approved labels and numeric protocol counters."""
    event, category = event_labels(state.last_event)
    safe_reason = reason if isinstance(reason, str) and reason in get_args(ResponseFailureReason) else "unknown"
    safe_code = code if isinstance(code, str) and code in _CODES else "unrecognized" if code is not None else "none"
    values = {"origin": origin if isinstance(origin, str) and origin in {"stream", "sdk_envelope", "provider_terminal"} else "unknown",
        "reason": safe_reason, "code": safe_code, "event_type": event, "event_category": category,
        "event_supported": state.last_event_supported is True, "sdk_version": sdk_version()}
    for field, value in (("events", state.events), ("sequence", state.sequence),
            ("bytes", state.bytes), ("text_chars", state.chars)):
        values[field] = value if type(value) is int and -1 <= value <= 2**63 - 1 else None
    try:
        logger.warning("[stream] %s", json.dumps(values, sort_keys=True))
    except Exception:
        pass
