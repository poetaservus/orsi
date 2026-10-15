"""Phase 1: offline Office boundaries, exposure, native wire shape and cost."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pytest
from pydantic import ValidationError

from app.capabilities.catalog import build_builtin_registry
from app.capabilities.contracts import PermissionClass
from app.inference.completion import CompletionMetadata
from app.inference.openai_tools import normalize_responses_calls, responses_function_tools
from app.mcp.office_budget import accepted_office_manifest
from app.mcp.office_contracts import (
    OFFICE_TOOLS, AttachArguments, DocumentsArguments, ExcelEditArguments,
    OfficeExposure, PowerPointEditArguments, ReadArguments, SaveArguments,
    WordEditArguments, office_catalog,
)
from app.settings.agent import AgentFeatureConfig
from tools.verify_office_mcp_contract import verify


ROOT = Path(__file__).resolve().parents[1]


def exposure(**changes):
    return OfficeExposure(**{"backend": "cloud", "enabled": True, "ready": True,
                            "generation": 1, **changes})


def contract(name):
    return next(tool for tool in OFFICE_TOOLS if tool.name == name)


@pytest.mark.parametrize("backend", ["local", "cloud"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("ready", [False, True])
def test_exposure_requires_cloud_enabled_and_ready(backend, enabled, ready):
    value = exposure(backend=backend, enabled=enabled, ready=ready)
    catalog = office_catalog(value)
    assert bool(catalog.tools) == (backend == "cloud" and enabled and ready)
    assert len(catalog.model_definitions()) == len(catalog.tools)


def test_default_and_no_application_exposure_are_empty():
    assert office_catalog(OfficeExposure()).model_definitions() == ()
    assert office_catalog(exposure(applications=())).model_definitions() == ()


@pytest.mark.parametrize("changes", [
    {"backend": "automatic"}, {"enabled": 1}, {"ready": "true"}, {"generation": True},
    {"generation": 0}, {"applications": ("excel", "excel")}, {"applications": ("shell",)},
])
def test_malformed_exposure_is_rejected(changes):
    with pytest.raises(ValidationError):
        exposure(**changes)


@pytest.mark.parametrize("changes", [
    {"backend": "local"}, {"enabled": False}, {"ready": False},
    {"generation": 2}, {"applications": ("excel",)},
])
def test_prepared_call_is_rejected_after_mode_connection_or_scope_changes(changes):
    catalog = office_catalog(exposure())
    with pytest.raises(ValueError, match="exposure changed"):
        catalog.validate_call("office.documents", {}, current=exposure(**changes))


def test_enabled_apps_keep_shared_tools_but_reject_other_apps():
    value = exposure(applications=("excel",))
    catalog = office_catalog(value)
    assert len(catalog.tools) == 6
    assert catalog.validate_call("office.documents", {}, current=value).limit == 20
    for name, arguments in (("office.word_edit", {"session": "s", "snapshot": "r", "changes": []}),
                            ("office.attach", {"application": "word", "document": "d"}),
                            ("office.documents", {"application": "word"}), ("shell.run", {})):
        with pytest.raises(ValueError):
            catalog.validate_call(name, arguments, current=value)


def test_catalog_is_sorted_and_definitions_cannot_mutate_its_snapshot():
    catalog = office_catalog(exposure())
    first = catalog.model_definitions()
    assert tuple(d.name for d in first) == tuple(sorted(t.name for t in OFFICE_TOOLS))
    before = catalog.schema_digest
    first[0].input_schema["properties"]["injected"] = {"type": "string"}
    assert "injected" not in catalog.model_definitions()[0].input_schema["properties"]
    assert office_catalog(exposure()).schema_digest == before


@pytest.mark.parametrize("arguments", [[], "{}", None, {"limit": True}, {"limit": 51},
                                           {"cursor": "../file"}, {"command": "SECRET"}])
def test_calls_reject_nonobjects_coercion_unknown_fields_and_unsafe_identifiers(arguments):
    with pytest.raises(ValueError) as caught:
        office_catalog(exposure()).validate_call("office.documents", arguments, current=exposure())
    assert "SECRET" not in str(caught.value)


@pytest.mark.parametrize("change", [
    {"range": "A1"}, {"range": "A1", "values": [[1]], "formulas": [["=1"]]},
    {"range": "A1", "values": [[1], [1, 2]]},
    {"range": "A1", "values": [[float("nan")]]},
    {"range": "A1", "values": [[float("inf")]]},
    {"range": "A1", "values": [[{"expression": "SECRET"}]]},
    {"range": "A1", "bold": "true"},
])
def test_excel_changes_reject_ambiguous_ragged_nonfinite_and_untyped_payloads(change):
    with pytest.raises(ValidationError):
        ExcelEditArguments(session="s", snapshot="r", changes=[{"sheet": "Sheet1", **change}])


def test_patch_limits_apply_to_combined_cells_and_serialized_utf8_bytes():
    for changes in ([{"range": "A1:A600", "values": [[1] for _ in range(600)]}] * 2,
                    [{"range": "A1", "bold": True}] * 17,
                    [{"range": "A1:I1", "values": [["x" * 4096] * 9]}]):
        with pytest.raises(ValidationError):
            ExcelEditArguments(session="s", snapshot="r", changes=[{"sheet": "Sheet1", **c} for c in changes])
    value = ExcelEditArguments(session="s", snapshot="r", changes=[{"sheet": "Sheet1", "range": "A1:D1", "values": [[True, 1, 1.5, None]]}])
    assert [type(v) for v in value.changes[0].values[0]] == [bool, int, float, type(None)]


@pytest.mark.parametrize("address", ["A:A", "1:1", "A1:A1001", "XFE1", "A1048577", "B2:A1", "=EXEC()"])
def test_formatting_only_edits_still_require_bounded_exact_ranges(address):
    with pytest.raises(ValidationError):
        ExcelEditArguments(session="s", snapshot="r", changes=[{"sheet": "Sheet1", "range": address, "bold": True}])


def test_excel_requires_explicit_worksheet_and_matching_matrix_dimensions():
    for change in ({"range": "A1", "values": [[1]]},
                   {"sheet": "Sheet1", "range": "A1:B2", "values": [[1, 2]]}):
        with pytest.raises(ValidationError):
            ExcelEditArguments(session="s", snapshot="r", changes=[change])
    patch = ExcelEditArguments(session="s", snapshot="r", changes=[
        {"sheet": "Sheet1", "range": "$A$1:$B$2", "values": [[1, 2], [3, 4]]}])
    assert patch.changes[0].values == [[1, 2], [3, 4]]


@pytest.mark.parametrize("model,change", [
    (WordEditArguments, {"target": "p1", "action": "apply_style", "text": "SECRET"}),
    (WordEditArguments, {"target": "p1", "action": "replace_text", "text": "x", "style": "Heading"}),
    (PowerPointEditArguments, {"action": "add_slide", "layout": "blank", "target": "shape1"}),
    (PowerPointEditArguments, {"action": "position", "target": "shape1", "geometry":
                              {"left": 0, "top": 0, "width": 0, "height": 20}}),
])
def test_editor_actions_require_their_exact_payload(model, change):
    with pytest.raises(ValidationError) as caught:
        model(session="s", snapshot="r", changes=[change])
    assert "SECRET" not in str(caught.value)


def test_save_as_is_explicit_and_never_enables_overwrite_by_default():
    assert SaveArguments(session="s").path is None
    assert SaveArguments(session="s", path="C:/Documents/report.xlsx").overwrite is False
    with pytest.raises(ValidationError):
        SaveArguments(session="s", overwrite=True)


@pytest.mark.parametrize("name,arguments", [
    ("office.documents", {"application": None, "cursor": None, "limit": None}),
    ("office.read", {"session": "s", "target": None, "cursor": None, "max_items": None, "max_chars": None}),
    ("office.excel_edit", {"session": "s", "snapshot": "r", "changes": [{"sheet": "Sheet1", "range": "A1:B1", "values": [[True, 1.5]],
        "formulas": None, "number_format": None, "bold": None, "italic": None}]}),
    ("office.word_edit", {"session": "s", "snapshot": "r", "changes": [{"target": "p1", "action": "replace_text",
        "text": "", "style": None, "cells": None}]}),
    ("office.powerpoint_edit", {"session": "s", "snapshot": "r", "changes": [{"action": "add_slide", "target": None,
        "text": None, "layout": "blank", "geometry": None}]}),
])
def test_real_responses_projection_and_normalization_preserve_contract_defaults(name, arguments):
    catalog = office_catalog(exposure())
    definitions = catalog.model_definitions()
    tools = responses_function_tools(definitions)
    index = [d.name for d in definitions].index(name)
    wire = tools[index]
    assert wire["strict"] and "outputSchema" not in wire
    result = normalize_responses_calls([{"call_id": "call1", "name": wire["name"],
        "arguments": json.dumps(arguments)}], definitions, CompletionMetadata())
    assert result.capability_calls
    parsed = catalog.validate_call(name, result.capability_calls[0].arguments, current=exposure())
    if isinstance(parsed, DocumentsArguments):
        assert parsed.limit == 20
    if isinstance(parsed, ReadArguments):
        assert (parsed.target, parsed.max_items, parsed.max_chars) == ("selection", 100, 4096)


@pytest.mark.parametrize("name,arguments,result", [
    ("office.documents", DocumentsArguments(limit=1), {"documents": [
        {"document": str(i), "application": "excel", "title": "x", "dirty": False,
         "has_path": True, "read_only": False} for i in range(2)]}),
    ("office.attach", AttachArguments(application="excel", document="d1"), {"session": "s", "document":
        {"document": "d2", "application": "excel", "title": "x", "dirty": False, "has_path": True, "read_only": False}}),
    ("office.read", ReadArguments(session="s", max_chars=2), {"session": "s", "application": "word", "snapshot": "r",
        "items": [{"target": "p1", "label": "", "text": "SECRET"}]}),
    ("office.read", ReadArguments(session="s", max_items=1), {"session": "s", "application": "excel", "snapshot": "r",
        "items": [{"target": "r1", "label": "", "values": [[1, 2]]}]}),
    ("office.save", SaveArguments(session="s"), {"session": "other", "operation": "op", "saved": True}),
    ("office.save", SaveArguments(session="s"), {"session": "s", "operation": "op", "saved": 1}),
])
def test_results_must_match_the_actual_request(name, arguments, result):
    with pytest.raises(ValueError):
        contract(name).validate_result(arguments, result)


def test_valid_results_support_metadata_unsaved_documents_and_bounded_reads():
    document = {"document": "d1", "application": "word", "title": "Document1",
                "dirty": True, "has_path": False, "read_only": False}
    assert contract("office.documents").validate_result(DocumentsArguments(application="word"),
        {"documents": [document]}).documents[0].dirty
    attached = contract("office.attach").validate_result(AttachArguments(application="word", document="d1"),
        {"session": "s", "document": document})
    assert not attached.document.has_path
    result = contract("office.read").validate_result(ReadArguments(session="s", max_chars=5),
        {"session": "s", "application": "word", "snapshot": "r", "items":
         [{"target": "p1", "label": "Paragraph 1", "text": "hello"}]})
    assert result.items[0].text == "hello" and result.snapshot == "r"
    assert contract("office.save").validate_result(SaveArguments(session="s"),
        {"session": "s", "operation": "op", "saved": True}).saved


def test_explicit_literal_and_formula_edits_have_valid_compact_receipts():
    arguments = ExcelEditArguments(session="s", snapshot="r", changes=[
        {"sheet": "Sheet1", "range": "A1", "values": [["=literal"]]},
        {"sheet": "Sheet1", "range": "B1", "formulas": [["=1+1"]]}])
    result = contract("office.excel_edit").validate_result(arguments,
        {"session": "s", "operation": "op", "outcome": "applied", "affected_items": 2, "recovery": "rec1"})
    assert result.recovery == "rec1"
    # The live adapter must preserve literal strings and verify the formula result.
    # Phase 1 validates the distinction and receipt shape without writing a workbook.
    assert arguments.changes[0].values == [["=literal"]]
    assert arguments.changes[1].formulas == [["=1+1"]]


def test_output_byte_limit_and_outcome_consistency_prevent_unbounded_or_false_receipts():
    arguments = ReadArguments(session="s", max_chars=8192)
    oversized = {"session": "s", "application": "word", "snapshot": "r", "items":
        [{"target": "p1", "label": "", "text": "\U0001f600" * 5000}]}
    with pytest.raises(ValueError, match="byte limit"):
        contract("office.read").validate_result(arguments, oversized)
    arguments = ExcelEditArguments(session="s", snapshot="r", changes=[{"sheet": "Sheet1", "range": "A1", "bold": True}])
    with pytest.raises(ValidationError, match="outcome"):
        contract("office.excel_edit").validate_result(arguments, {"session": "s", "operation": "op",
            "outcome": "applied", "affected_items": 0})


def test_budget_and_accepted_manifest_need_no_network_processes_or_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Contract verification must not connect or start a process")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = verify(ROOT / "config/office_mcp_v1.json")
    assert report["passed"] and not report["billed_tokens_measured"]
    assert report["cases"]["cloud_all"]["tool_count"] == 8
    for case in ("local", "cloud_disabled", "cloud_not_ready"):
        assert report["cases"][case]["schema_wire_bytes"] == report["cases"][case]["schema_reserve_tokens"] == 0
    assert report["verification_model_requests"] == 0
    assert json.loads((ROOT / "config/office_mcp_v1.json").read_text()) == accepted_office_manifest()


def test_verifier_detects_unreviewed_manifest_changes(tmp_path):
    changed = deepcopy(accepted_office_manifest())
    changed["tools"][0]["permission"] = "system"
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed))
    assert not verify(path)["passed"]


def test_phase_one_does_not_register_executable_office_tools(tmp_path):
    registry = build_builtin_registry(AgentFeatureConfig(filesystem_stat_enabled=True),
                                     application_root=tmp_path, state_directory=tmp_path / "state")
    assert not any(name.startswith("office.") for name in registry.names)
    assert {tool.permission for tool in OFFICE_TOOLS if tool.name in
            ("office.documents", "office.attach", "office.read")} == {PermissionClass.READ}
    assert {tool.permission for tool in OFFICE_TOOLS if tool.name not in
            ("office.documents", "office.attach", "office.read")} == {PermissionClass.WRITE}
