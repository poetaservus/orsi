"""Dashboard creation must retain the existing snapshot, approval and recovery boundary."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.mcp.office_contracts import ExcelEditArguments
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_live import LiveOffice
from tests.fixtures.office_dashboard_server import DashboardBackend
from tests.test_office_mcp_excel import read, mutate
from tests.test_office_mcp_live import tool


G = {"left": 10, "top": 20, "width": 240, "height": 120}


def setup(mode="normal"):
    live = LiveOffice(lambda: DashboardBackend(mode))
    live.control("configure", {"applications": ["excel"]})
    document = next(iter(live.documents))
    bound = live.binding(document=document)
    authority = {"document": document, "identity": bound["identity"]}
    attached = live.call(tool("attach"), tool("attach").arguments(application="excel", document=document), authority)
    return live, authority, attached["session"]


def shape(**extra):
    return {"kind": "shape", "sheet": "Other", "name": "RevenueCard", "geometry": G, "text": "Revenue", **extra}


def call(live, authority, session, snapshot, objects):
    return mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot, "objects": objects})


def test_native_object_schema_round_trip_and_exact_payloads():
    from app.inference.openai_tools import responses_function_tools, normalize_responses_calls, _arguments
    from app.inference.completion import CompletionMetadata
    from app.mcp.office_contracts import OfficeExposure, office_catalog
    import json
    value = OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1)
    catalog = office_catalog(value)
    definitions = catalog.model_definitions()
    wire = responses_function_tools(definitions)[[d.name for d in definitions].index("office.excel_edit")]
    args = {"session": "s", "snapshot": "r", "objects": [shape()]}
    schema = next(d.input_schema for d in definitions if d.name == "office.excel_edit")
    args = _arguments(schema, args, schema, from_wire=False)
    parsed = normalize_responses_calls([{"call_id": "c", "name": wire["name"], "arguments": json.dumps(args)}], definitions, CompletionMetadata())
    assert parsed.capability_calls
    actual = catalog.validate_call("office.excel_edit", parsed.capability_calls[0].arguments, current=value)
    assert actual.objects[0].geometry.width == 240
    assert actual.changes == []


@pytest.mark.parametrize("obj", [shape(geometry={**G, "width": 0}), shape(fill_color="red"),
    shape(command="not allowed"), shape(link={"snapshot": "s", "sheet": "Sheet1", "range": "A1:A2"}),
    shape(link={"snapshot": "s", "sheet": "Sheet1", "range": "A1"}),
    {"kind": "chart", "sheet": "Other", "name": "Chart", "geometry": G,
     "source": {"snapshot": "s", "sheet": "Sheet1", "range": "A:A"}, "chart_type": "line"}])
def test_malformed_or_ambiguous_native_payloads_reject_before_execution(obj):
    with pytest.raises(ValidationError):
        ExcelEditArguments(session="s", snapshot="r", objects=[obj])


def test_object_creation_recovery_and_manual_changes_are_guarded():
    live, authority, session = setup()
    snapshot = read(live, authority, session, "Other!A1")["snapshot"]
    result = call(live, authority, session, snapshot, [shape()])
    assert result["affected_items"] == 1 and result["recovery"]
    fresh = read(live, authority, session, "Other!A1")["snapshot"]
    live.backend.objects["RevenueCard"]["user_edit"] = True
    with pytest.raises(OfficeConflict, match="Later changes"):
        mutate(live, authority, "revert", {"session": session, "snapshot": fresh, "recovery": result["recovery"]})
    live.backend.objects["RevenueCard"].pop("user_edit")
    restored = mutate(live, authority, "revert", {"session": session, "snapshot": fresh, "recovery": result["recovery"]})
    assert restored["affected_items"] == 1 and not live.backend.objects
    assert not restored["recovery"]  # Object deletion cannot promise a redo.


@pytest.mark.parametrize("race", ["source", "name", "sheet"])
def test_review_binding_rejects_source_inventory_or_sheet_races_without_writes(race):
    live, authority, session = setup()
    source = read(live, authority, session, "Sheet1!A1")["snapshot"]
    snapshot = read(live, authority, session, "Other!A1")["snapshot"]
    spec = shape(text=None, link={"snapshot": source, "sheet": "Sheet1", "range": "A1"})
    args = tool("excel_edit").arguments(session=session, snapshot=snapshot, objects=[spec])
    guard = live.excel.prepare("office.excel_edit", args, live.binding(session=session))
    if race == "source":
        live.backend.sheets["Sheet1"][(1, 1)] = {**live.backend.capture_excel(("cell", live.backend.sheets["Sheet1"], 1, 1)), "value": 7}
    elif race == "name":
        live.backend.objects["RevenueCard"] = {"user_owned": True}
    else:
        live.backend.sheets["Other"] = {}
    with pytest.raises(OfficeConflict):
        live.call(tool("excel_edit"), args, {**authority, "guard": guard["guard"]}, "race")
    assert live.backend.writes == 0


def test_partial_native_creation_blocks_future_writes_without_replaying_or_rollback():
    live, authority, session = setup("partial")
    snapshot = read(live, authority, session, "Other!A1")["snapshot"]
    with pytest.raises(OfficeUnknown):
        call(live, authority, session, snapshot, [shape()])
    assert live.excel.blocked and "RevenueCard" in live.backend.objects
    with pytest.raises(OfficeConflict):
        call(live, authority, session, snapshot, [shape(name="Another")])
    assert live.backend.writes == 1


def test_incomplete_source_snapshot_and_existing_name_never_mutate():
    live, authority, session = setup()
    source = read(live, authority, session, "Sheet1!A1")["snapshot"]
    snapshot = read(live, authority, session, "Other!A1")["snapshot"]
    chart = {"kind": "chart", "sheet": "Other", "name": "Trend", "geometry": G, "chart_type": "line",
             "source": {"snapshot": source, "sheet": "Sheet1", "range": "A1:B2"}}
    with pytest.raises(OfficeConflict):
        call(live, authority, session, snapshot, [chart])
    live.backend.objects["RevenueCard"] = {"user_owned": True}
    with pytest.raises(OfficeConflict, match="already exists"):
        call(live, authority, session, snapshot, [shape()])
    assert live.backend.writes == 0


def test_pivot_reserve_requires_blank_complete_nonoverlapping_cells():
    live, authority, session = setup()
    backend = live.backend
    for row, values in enumerate([["Region", "Revenue"], ["N", 10], ["S", 20]], 1):
        for col, value in enumerate(values, 1):
            backend.sheets["Sheet1"][(row, col)] = {**backend.capture_excel(("cell", backend.sheets["Sheet1"], row, col)), "value": value}
    source = read(live, authority, session, "Sheet1!A1:B3")["snapshot"]
    dest = read(live, authority, session, "Other!A1:B12", max_items=32)["snapshot"]
    spec = {"kind": "pivot", "sheet": "Other", "name": "RegionPivot", "destination": "A1:B12",
            "source": {"snapshot": source, "sheet": "Sheet1", "range": "A1:B3"}, "rows": ["Region"], "value_field": "Revenue"}
    backend.sheets["Other"][(12, 2)] = {**backend.capture_excel(("cell", backend.sheets["Other"], 12, 2)), "value": "preserve me"}
    with pytest.raises(OfficeConflict):
        call(live, authority, session, dest, [spec])
    assert backend.writes == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_office_provider_evidence_survives_additive_dashboard_schema(legacy):
    import json
    from app.inference.openai_tools import _arguments, normalize_responses_calls, responses_input
    from app.inference.completion import CompletionMetadata
    from app.mcp.office_contracts import OfficeExposure, office_catalog
    from tests.test_openai_replay import evidence, history_for
    from tests.test_openai_tools import function
    definitions = office_catalog(OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1)).model_definitions()
    definition = next(d for d in definitions if d.name == "office.excel_edit")
    if legacy:
        schema = deepcopy(definition.input_schema)
        schema["properties"].pop("objects")
        schema["$defs"]["ExcelChange"]["properties"].pop("fill_color")
        definition = definition.model_copy(update={"input_schema": schema})
    schema = definition.input_schema
    arguments = {"session": "s", "snapshot": "r", "changes": [{"sheet": "Sheet1", "range": "A1", "values": [[7]]}]}
    wire_args = _arguments(schema, arguments, schema, from_wire=False)
    output = [function(definition, wire_args)]
    replay = evidence(output)
    response = normalize_responses_calls(output, (definition,), CompletionMetadata())
    assert response.capability_calls
    history = [{"role": "user", "content": "Update the synthetic workbook"}, *history_for(replay, response.capability_calls)]
    projected = responses_input(history, definitions)
    assert projected[1] == output[0]
    assert projected[1]["arguments"] == output[0]["arguments"]


@pytest.mark.parametrize("mode", ["normal", "partial"])
def test_real_stdio_native_object_approval_dispatch_and_journal(tmp_path, mode):
    import sys
    from app.mcp.office_connection import OfficeConnection
    from app.mcp.office_discovery import OfficeDiscovery, OfficeInstallation
    from app.mcp.stdio_transport import OwnedStdioTransport
    from app.security.permissions import ApprovalStatus
    from tests.test_office_mcp_capabilities import runtime_for, prepare, authorize
    from tests.test_office_mcp_connection import ROOT
    from tests.test_office_mcp_live import execute
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=5, call_timeout=5,
        discovery=OfficeDiscovery(lambda: (OfficeInstallation("excel", "fixture", None),)),
        _transport_factory=lambda: OwnedStdioTransport([sys.executable, "-m", "tests.fixtures.office_dashboard_server", mode], root=ROOT))
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        attached = execute(runtime, "attach", {"application": "excel", "document": document["document"]}, "attach")
        session = attached.output["session"]
        snapshot = execute(runtime, "read", {"session": session, "target": "Other!A1"}, "read").output["snapshot"]
        args = {"session": session, "snapshot": snapshot, "objects": [shape()]}
        denied = prepare(runtime, "office.excel_edit", args, "denied")
        assert not runtime.executor.executor.execute(denied, authorize(runtime, denied, ApprovalStatus.DENIED)).success
        assert bridge.diagnostics["tool_calls"] == 2
        approved = prepare(runtime, "office.excel_edit", args, "approved")
        assert "RevenueCard" in approved.request.approval_preview
        result = runtime.executor.execute(approved, authorize(runtime, approved))
        assert result.success == (mode == "normal")
        if mode == "normal":
            fresh = execute(runtime, "read", {"session": session, "target": "Other!A1"}, "fresh").output["snapshot"]
            restored = execute(runtime, "revert", {"session": session, "snapshot": fresh, "recovery": result.output["recovery"]}, "restore")
            assert restored.success
        else:
            assert result.error.code.value == "outcome_unknown"
            assert runtime.executor.journal.review_required
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


def test_scatter_rejects_text_x_values_before_native_creation():
    live, authority, session = setup()
    for row, values in enumerate([["Region", "Revenue"], ["North", 10]], 1):
        for column, value in enumerate(values, 1):
            descriptor = ("cell", live.backend.sheets["Sheet1"], row, column)
            descriptor[1][descriptor[2:]] = {**live.backend.capture_excel(descriptor), "value": value}
    source = read(live, authority, session, "Sheet1!A1:B2")["snapshot"]
    dest = read(live, authority, session, "Other!A1")["snapshot"]
    with pytest.raises(OfficeConflict, match="numeric X"):
        call(live, authority, session, dest, [{"kind": "chart", "name": "Scatter", "sheet": "Other", "geometry": G,
            "chart_type": "scatter", "source": {"sheet": "Sheet1", "range": "A1:B2", "snapshot": source}}])
    assert live.backend.writes == 0


def test_stale_large_pivot_cache_cannot_create_an_unbounded_slicer():
    from types import SimpleNamespace as NS
    from app.mcp.office_com import WindowsOffice
    backend = WindowsOffice.__new__(WindowsOffice)
    backend.check_thread = lambda: None
    pivot = NS(TableRange2=NS(Address="$A$1:$B$4"), PivotCache=lambda: NS(OLAP=False, SourceType=1, RecordCount=1001))
    sheet = NS(Range=lambda address: NS(Address="$A$1:$B$4"), PivotTables=lambda: NS(Count=1, Item=lambda i: pivot))
    with pytest.raises(OfficeConflict, match="record limit"):
        backend.excel_slicer_pivot(None, sheet, "A1:B4", "Region")
