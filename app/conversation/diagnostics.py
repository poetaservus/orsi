"""Fixed-category turn diagnostics; no content, identities, paths or tool bodies."""
from collections import Counter
import json
import logging
from typing import get_args

from app.agent.contracts import AgentRunStatus
from app.capabilities.contracts import CapabilityErrorCode
from app.inference.completion import ResponseFailureReason


_ROUTES = frozenset({"agent", "image_generation"})
_REASONS = frozenset({"unsupported_backend", "explicit_image", "negated_visual", "image_analysis",
    "analysis", "coding_request", "written_request", "visual_creation", "visual_edit",
    "no_visual_source", "selected_skill", "ordinary_request"})
_SOURCES = frozenset({"none", "submitted", "current_visual_task"})


def _label(value, allowed):
    return value if isinstance(value, str) and value in allowed else "unknown"


def _count(value):
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _record(logger, prefix, values):
    try:
        logger.info("%s %s", prefix, json.dumps(values, sort_keys=True))
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
        "skill_scope": _label(skill_scope, {"none", "message", "session"})})


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
        "tool_error_counts": dict(errors)})
