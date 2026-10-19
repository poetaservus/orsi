"""Content-free mutation receipts and failure evidence, independent of COM."""
from contextlib import contextmanager
import json
import logging
from time import monotonic, time

log = logging.getLogger(__name__)
STAGES = frozenset({"dispatch", "confirmation", "result_validation", "word_save", "word_save_verify",
    "word_native_insert", "word_readback", "word_verification", "word_document_write",
    "word_document_readback", "insert_xml", "section_layout", "running_matter", "repaginate",
    "fields_update", "recovery_capture", "outcome_verification", "excel_preflight", "excel_write",
    "excel_verification", "excel_objects", "excel_save"})
CATEGORIES = frozenset({"busy", "rejected", "native", "verification", "io", "internal",
    "timeout", "cancelled", "worker_stopped", "transport", "none"})
OUTCOMES = frozenset({"unknown", "not_applied", "applied", "unchanged", "saved"})
TOOLS = frozenset({"office.word_compose", "office.word_edit", "office.excel_edit", "office.save", "office.revert"})
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


def excel_failure_message(value):
    """Explain the verified failure stage without native error text or contents."""
    event = safe_write_event(value) or {}
    stage = {"excel_write": "writing cells", "excel_verification": "checking cell values and formatting",
        "excel_objects": "creating or checking dashboard objects", "excel_save": "saving the workbook",
        "confirmation": "waiting for Excel", "result_validation": "checking the completion receipt"}.get(
            event.get("stage"), "applying the edit")
    reason = {"busy": " Excel was busy.", "rejected": " Excel rejected the request.",
        "timeout": " Excel exceeded the operation deadline.",
        "verification": " The readback did not match the approved result."}.get(event.get("category"), "")
    return f"Excel could not confirm the edit while {stage}.{reason} Inspect the workbook before another edit; no automatic retry was made."


def word_failure_message(value):
    """Expose bounded failure evidence without inferring an uncertain write's outcome."""
    event = safe_write_event(value) or {}
    stage = event.get("stage", "confirmation")
    category = event.get("category", "internal")
    evidence = f"stage={stage}, reason={category}"
    if "hresult" in event:
        evidence += f", HRESULT={event['hresult']}"
    return (f"Word could not confirm the operation ({evidence}). "
            "Changes may already be present. Inspect the document before another write; "
            "no automatic retry was made.")


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
