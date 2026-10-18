"""Allowlisted read structure and failure categories; never retain target text."""
import json
import logging
import re


log = logging.getLogger(__name__)
_TARGETS = frozenset({"selection", "workbook", "document", "authoring", "layout", "styles", "tables",
    "table", "text", "render", "slides", "slide", "excel_used", "excel_objects", "excel_range", "unknown"})
_STAGES = frozenset({"read_execute", "result_validation", "word_plan", "word_capture", "word_piece",
    "word_render", "repeat_guard", "bridge"})
_REASONS = frozenset({"unsupported_target", "outside_document", "table_index", "read_bound", "read_limit",
    "cursor_limit", "unavailable", "native", "io", "internal", "invalid_result", "conflict", "render_setup", "identical_call",
    "timeout", "cancelled", "worker_stopped", "transport"})
_NUMBERS = {"max_items": 1000, "max_chars": 8192, "first": 1_000_000, "last": 1_000_000, "timeout_ms": 60_000}


def _choice(value, choices, default):
    return value if isinstance(value, str) and value in choices else default


def read_shape(arguments):
    arguments = arguments if isinstance(arguments, dict) else {}
    target = arguments.get("target", "selection")
    kind, numbers = "unknown", []
    if isinstance(target, str) and len(target) <= 256:
        if target in _TARGETS - {"table", "text", "render", "slide", "excel_used", "excel_objects", "excel_range", "unknown"}:
            kind = target
        else:
            match = re.fullmatch(r"(render|text):([0-9]{1,7}):([0-9]{1,7})|(table|slide):([0-9]{1,7})", target)
            if match:
                kind = match[1] or match[4]
                numbers = [int(match[2]), int(match[3])] if match[1] else [int(match[5])]
            elif "!" in target:
                suffix = target.rsplit("!", 1)[1]
                kind = "excel_used" if suffix == "used" else "excel_objects" if suffix == "objects" else "excel_range"
    shape = {"target_kind": kind, "cursor": arguments.get("cursor") is not None,
             "max_items": arguments.get("max_items", 100), "max_chars": arguments.get("max_chars", 4096)}
    if numbers:
        shape["first"] = min(numbers[0], 1_000_000)
    if len(numbers) > 1:
        shape["last"] = min(numbers[1], 1_000_000)
    return {key: value for key, value in safe_read_event(shape).items() if key != "event"}


def safe_read_event(value):
    if not isinstance(value, dict):
        return None
    # Explicit fields only: exception messages, identifiers and paths cannot
    # enter persisted diagnostics, even through forged logging extras/meta.
    event = {"event": "office_read_failure",
        "target_kind": _choice(value.get("target_kind"), _TARGETS, "unknown"),
        "stage": _choice(value.get("stage"), _STAGES, "bridge"),
        "reason": _choice(value.get("reason"), _REASONS, "unavailable"),
        "cursor": value.get("cursor") is True}
    for key, limit in _NUMBERS.items():
        number = value.get(key)
        if type(number) is int and 0 <= number <= limit:
            event[key] = number
    number = value.get("hresult")
    if type(number) is int and -(2**31) <= number < 2**32:
        event["hresult"] = number
    return event


def read_call(stage, function, *args, **kwargs):
    """Annotate a failure's fixed stage without changing its type or message."""
    try:
        return function(*args, **kwargs)
    except Exception as error:
        if _choice(getattr(error, "orsi_read_stage", None), _STAGES, None) is None:
            try:
                error.orsi_read_stage = stage
            except (AttributeError, TypeError):
                pass
        raise


def failure_data(error, stage):
    from app.mcp.office_com import OfficeUnavailable
    from app.mcp.office_excel import OfficeConflict
    reason = "internal"
    if isinstance(error, OfficeConflict):
        reason = "conflict"
    elif isinstance(error, OfficeUnavailable):
        reason = {
            "Use selection, document or text:start:end for Word.": "unsupported_target",
            "Use SheetName!A1:B2 for an Excel target.": "unsupported_target",
            "Use selection, slides or slide:index for PowerPoint.": "unsupported_target",
            "The Word range is outside the document.": "outside_document",
            "The Word table index is outside the discovery bound.": "table_index",
            "The Word reader exceeded its bound.": "read_bound",
            "The Word item cannot fit the read limits.": "read_bound",
            "The Word read fragment limit was reached. Read a smaller target.": "read_limit",
            "The Word snapshot memory limit was reached. Reconnect explicitly.": "read_limit",
            "The Word cursor limit was reached. Reconnect explicitly.": "cursor_limit",
        }.get(str(error), "unavailable")
    elif stage == "result_validation":
        reason = "invalid_result"
    elif type(getattr(error, "hresult", None)) is int:
        reason = "native"
    elif isinstance(error, OSError):
        reason = "io"
    event = safe_read_event({"stage": getattr(error, "orsi_read_stage", stage), "reason": reason,
                            "hresult": getattr(error, "hresult", None)})
    return {key: value for key, value in event.items() if key in {"stage", "reason", "hresult"}}


def record_read_failure(arguments, failure):
    fields = {**read_shape(arguments), **{key: failure.get(key) for key in ("stage", "reason", "hresult", "timeout_ms")}}
    event = safe_read_event(fields)
    log.warning("office_read failure=%s", json.dumps(event, separators=(",", ":")),
                extra={"orsi_read_diagnostic": event})
    return event


def read_failure_message(arguments, failure):
    event = safe_read_event({**read_shape(arguments), **{key: failure.get(key) for key in ("stage", "reason", "hresult")}})
    message = (f"Office read failed (target={event['target_kind']}, stage={event['stage']}, reason={event['reason']}"
        + (f", HRESULT={event['hresult']}" if "hresult" in event else "") + "). ")
    if event["reason"] == "unsupported_target":
        message += ("Word targets: document, authoring, layout, styles, tables, table:index, text:start:end, "
            "render:first:last (1-3 pages). Excel: workbook, SheetName!used or SheetName!A1:B2. PowerPoint: slides or slide:index. Correct the target before retrying.")
    elif event["reason"] in {"outside_document", "table_index"}:
        message += "Read a fresh document/tables index and use an existing range or table."
    elif event["reason"] in {"read_bound", "read_limit", "cursor_limit"}:
        message += "Use a smaller target or reconnect explicitly. Do not repeat this request unchanged."
    elif event["reason"] in {"native", "io", "internal", "invalid_result"}:
        message += "No document change was established. Check the Office connection or render setup before retrying."
    else:
        message += "Read a fresh target or refresh the connection. Word also supports authoring, layout and render:first:last (1-3 pages)."
    return message[:500]
