"""Fixed-category turn diagnostics; no content, identities, paths or tool bodies."""
from collections import Counter
import json
import logging
from typing import get_args

from app.agent.contracts import AgentRunStatus
from app.capabilities.contracts import CapabilityErrorCode
from app.inference.completion import ResponseFailureReason
from app.runtime.diagnostic_context import current_turn_id, safe_local_id, safe_phase


_ROUTES = frozenset({"agent", "image_generation"})
_REASONS = frozenset({"unsupported_backend", "explicit_image", "negated_visual", "image_analysis",
    "analysis", "coding_request", "written_request", "visual_creation", "visual_edit",
    "no_visual_source", "selected_skill", "ordinary_request", "editable_document"})
_SOURCES = frozenset({"none", "submitted", "current_visual_task"})
_ATTACHMENTS = frozenset({"none", "image", "file", "mixed"})


def _label(value, allowed):
    return value if isinstance(value, str) and value in allowed else "unknown"


def _count(value):
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def safe_conversation_event(value):
    """Revalidate the fixed schema at the personal-storage boundary."""
    if not isinstance(value, dict):
        return None
    event = value.get("event")
    if event == "route_decision":
        result = {"event": event, "route": _label(value.get("route"), _ROUTES),
            "reason": _label(value.get("reason"), _REASONS),
            "source": _label(value.get("source"), _SOURCES),
            "attachments": _label(value.get("attachments"), _ATTACHMENTS),
            "skill_scope": _label(value.get("skill_scope"), {"none", "message", "session"})}
        for field in ("submitted_count", "selected_count", "image_count", "file_count"):
            result[field] = _count(value.get(field))
    elif event == "agent_turn":
        errors = value.get("tool_error_counts")
        allowed_errors = {e.value for e in CapabilityErrorCode} | {"unknown"}
        result = {"event": event,
            "terminal_status": _label(value.get("terminal_status"), {s.value for s in AgentRunStatus}),
            "failure_reason": _label(value.get("failure_reason"), set(get_args(ResponseFailureReason)) | {"none"}),
            "request_phase": safe_phase(value.get("request_phase")),
            "observed_function_call": value.get("observed_function_call") is True,
            "tool_error_counts": {key: count for key in allowed_errors
                if isinstance(errors, dict) and (count := _count(errors.get(key))) is not None}}
        for field in ("steps", "model_requests", "capability_calls", "settled_calls", "successful_calls",
                      "failed_calls", "semantic_corrections", "protocol_failures"):
            result[field] = _count(value.get(field))
    else:
        return None
    result["turn_id"] = safe_local_id(value.get("turn_id"))
    return result


def _record(logger, prefix, values, *, event, completion=None):
    try:
        structured = {**values, "event": event, "turn_id": current_turn_id()}
        if completion is not None:
            structured.update(request_phase=safe_phase(getattr(completion, "request_phase", None)),
                observed_function_call=getattr(completion, "observed_function_call", False) is True)
        logger.info("%s %s", prefix, json.dumps(values, sort_keys=True),
                    extra={"orsi_conversation_diagnostic": safe_conversation_event(structured)})
    except Exception:
        # Diagnostics cannot fail a turn, provoke retries or expose an exception.
        pass


def record_route(logger, decision, *, submitted_count, skill_scope):
    """Record the execution decision once; previews do not call this function."""
    if not logger.isEnabledFor(logging.INFO):
        return
    images = sum(r.kind == "image" for r in decision.references)
    files = sum(r.kind == "file" for r in decision.references)
    category = "mixed" if images and files else "image" if images else "file" if files else "none"
    _record(logger, "[route]", {"route": _label(decision.route, _ROUTES),
        "reason": _label(decision.reason, _REASONS),
        "source": _label(decision.source, _SOURCES) if decision.references else "none",
        "attachments": category, "submitted_count": _count(submitted_count),
        "selected_count": len(decision.references), "image_count": images, "file_count": files,
        "skill_scope": _label(skill_scope, {"none", "message", "session"})}, event="route_decision")


def record_turn(logger, result):
    """Use settled counts and fixed codes, never a result's text or metadata."""
    if not logger.isEnabledFor(logging.INFO):
        return
    errors = Counter(_label(c.result.error.code.value, {e.value for e in CapabilityErrorCode})
        for c in result.settled_calls if c.result.error is not None)
    failed = sum(not c.result.success for c in result.settled_calls)
    reason = result.completion.failure_reason
    _record(logger, "[turn]", {
        "terminal_status": _label(result.status.value, {s.value for s in AgentRunStatus}),
        "steps": _count(result.steps), "model_requests": _count(result.model_requests),
        "capability_calls": _count(result.capability_calls), "settled_calls": len(result.settled_calls),
        "successful_calls": len(result.settled_calls) - failed, "failed_calls": failed,
        "semantic_corrections": _count(result.semantic_corrections),
        "protocol_failures": _count(result.protocol_failures),
        "failure_reason": _label(reason, get_args(ResponseFailureReason)) if reason is not None else "none",
        "tool_error_counts": dict(errors)}, event="agent_turn", completion=result.completion)
