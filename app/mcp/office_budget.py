"""Offline measurement of the actual Responses tool projection; never calls an API."""
from __future__ import annotations

from app.inference.openai_context import estimate_schema_tokens
from app.inference.openai_tools import responses_function_tools
from app.mcp.office_contracts import (
    APPLICATIONS, OfficeExposure, canonical_json, office_catalog, office_manifest,
)


# These ceilings apply to the full Office catalog, not each app.
# Dashboard creation adds four typed native object payloads to excel_edit.
# The ceiling is measured against that expanded catalog, without changing the
# model's context limit or any execution/approval policy.
MAX_SCHEMA_WIRE_BYTES = 20_000
MAX_SCHEMA_RESERVE_TOKENS = 7_200


def measure_office_catalog(exposure: OfficeExposure) -> dict:
    catalog = office_catalog(exposure)
    definitions = catalog.model_definitions()
    tools = responses_function_tools(definitions) if definitions else []
    return {
        "tool_count": len(tools),
        "schema_wire_bytes": len(canonical_json(tools).encode("utf-8")) if tools else 0,
        "schema_reserve_tokens": estimate_schema_tokens(tools),
        "schema_digest": catalog.schema_digest,
    }


def office_budget_report() -> dict:
    cases = {
        "cloud_all": OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1),
        "cloud_disabled": OfficeExposure(backend="cloud"),
        "cloud_not_ready": OfficeExposure(backend="cloud", enabled=True),
        "local": OfficeExposure(backend="local", enabled=True, ready=True, generation=1),
    }
    cases.update({f"cloud_{app}": OfficeExposure(backend="cloud", enabled=True, ready=True,
                  generation=1, applications=(app,)) for app in APPLICATIONS})
    measured = {name: measure_office_catalog(exposure) for name, exposure in cases.items()}
    return {
        "schema_version": 1,
        "measurement": "canonical Responses tools JSON, UTF-8",
        "token_method": "ORSI offline reserve: ceil(wire_bytes / 3) + 48 per tool",
        "billed_tokens_measured": False,
        "verification_model_requests": 0,
        "max_schema_wire_bytes": MAX_SCHEMA_WIRE_BYTES,
        "max_schema_reserve_tokens": MAX_SCHEMA_RESERVE_TOKENS,
        "within_budget": all(case["schema_wire_bytes"] <= MAX_SCHEMA_WIRE_BYTES
                             and case["schema_reserve_tokens"] <= MAX_SCHEMA_RESERVE_TOKENS
                             for case in measured.values()),
        "cases": measured,
    }


def accepted_office_manifest() -> dict:
    return {**office_manifest(), "schema_budget": {
        "max_wire_bytes": MAX_SCHEMA_WIRE_BYTES,
        "max_reserve_tokens": MAX_SCHEMA_RESERVE_TOKENS,
        "token_method": "ORSI offline reserve: ceil(wire_bytes / 3) + 48 per tool",
    }}
