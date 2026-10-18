"""Content-free mutation receipts and failure evidence, independent of COM."""
from contextlib import contextmanager
import json
import logging
from time import monotonic, time

log = logging.getLogger(__name__)
STAGES = frozenset({"dispatch", "confirmation", "result_validation", "word_save", "word_save_verify",
    "word_native_insert", "word_readback", "word_verification", "word_document_write",
    "word_document_readback", "insert_xml", "section_layout", "running_matter", "repaginate",
    "fields_update", "recovery_capture", "outcome_verification"})
CATEGORIES = frozenset({"busy", "rejected", "native", "verification", "io", "internal",
    "timeout", "cancelled", "worker_stopped", "transport", "none"})
OUTCOMES = frozenset({"unknown", "not_applied", "applied", "unchanged", "saved"})
TOOLS = frozenset({"office.word_compose", "office.word_edit", "office.save", "office.revert"})
ACTIONS = frozenset({"compose", "replace_text", "insert_after", "apply_style", "edit_table", "save", "revert"})


def category(error):
    code = getattr(error, "hresult", None)
    if type(code) is int:
        return {0x8001010A: "busy", 0x80010001: "rejected"}.get(code & 0xffffffff, "native")
    from app.mcp.office_excel import OfficeUnknown, OfficeConflict
    if isinstance(error, (OfficeUnknown, OfficeConflict)):
        return "verification"
    if isinstance(error, OSError):
        return "io"
    return "internal"


def safe_write_event(value):
    if not isinstance(value, dict):
        return None
    result = {"event": "office_write_outcome"}
    for key, choices, default in (("tool", TOOLS, "office.word_edit"), ("stage", STAGES, "confirmation"),
            ("category", CATEGORIES, "internal"), ("outcome", OUTCOMES, "unknown")):
        result[key] = value.get(key) if isinstance(value.get(key), str) and value[key] in choices else default
    # Unknown means dispatched, not proof of a side effect. No automatic replay.
    result["retry_safe"] = result["outcome"] == "not_applied"
    if isinstance(value.get("action"), str) and value["action"] in ACTIONS:
        result["action"] = value["action"]
    for key in ("duration_ms", "step_ms", "timeout_ms"):
        number = value.get(key)
        if type(number) is int and 0 <= number <= 86_400_000:
            result[key] = number
    code = value.get("hresult")
    if type(code) is int and -(2**31) <= code < 2**32:
        result["hresult"] = code
    if type(value.get("dispatched")) is bool:
        result["dispatched"] = value["dispatched"]
    timestamp = value.get("timestamp_ms")
    if type(timestamp) is int and 0 <= timestamp < 2**63:
        result["timestamp_ms"] = timestamp
    # Use the existing allowlisted plan summary; never retain argument values.
    if isinstance(value.get("shape"), dict):
        from app.inference.word_plan_diagnostics import safe_word_event
        result["shape"] = safe_word_event({"stage": "dispatch_serialized", "shape": value["shape"]})["shape"]
    return result


def record_write_event(value):
    event = safe_write_event({"timestamp_ms": round(time() * 1000), **value})
    log.info("office_write outcome=%s", json.dumps(event, separators=(",", ":")),
             extra={"orsi_write_diagnostic": event})
    return event


@contextmanager
def native_step(stage):
    """Attach the innermost fixed native stage without retaining a COM proxy."""
    started = monotonic()
    try:
        yield
    except Exception as error:
        if getattr(error, "orsi_write_stage", None) not in STAGES:
            error.orsi_write_stage = stage
            error.orsi_write_step_ms = round((monotonic() - started) * 1000)
        raise
