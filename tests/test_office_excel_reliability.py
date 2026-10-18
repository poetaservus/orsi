"""Excel batch deadlines, native failure evidence and recalculated formula guards."""
import json

import pytest

from app.mcp.office_capabilities import OfficeCapability
from app.mcp.office_connection import OfficeConnection, EXCEL_MUTATION_TIMEOUT
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_write_diagnostics import safe_write_event
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_excel import service, read, mutate, connection, start, patch
from tests.test_office_mcp_live import tool, execute


@pytest.mark.parametrize("explicit", [None, .2])
def test_excel_mutation_budgets_cover_approval_sdk_and_outer_executor(explicit):
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", call_timeout=explicit)
    bridge._selected_application = "excel"
    for name in ("excel_edit", "revert", "save"):
        contract = tool(name)
        expected = EXCEL_MUTATION_TIMEOUT if explicit is None else explicit
        assert bridge.tool_timeout(contract) == expected
        assert bridge.mutation_timeout(contract) == expected
        capability = OfficeCapability(contract, bridge, None, None, None)
        assert capability.timeout_seconds >= expected * 2 + bridge.call_timeout + 10
    assert bridge.tool_timeout(tool("read")) == bridge.call_timeout
    bridge._selected_application = "word"
    assert bridge.tool_timeout(tool("save")) == bridge.call_timeout
    assert bridge.tool_timeout(tool("revert")) == bridge.call_timeout


def test_registered_shared_tools_follow_later_document_selection():
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud")
    saved = [OfficeCapability(tool(name), bridge, None, None, None) for name in ("save", "revert")]
    assert all(capability.timeout_seconds == 40 for capability in saved)
    bridge._selected_application = "excel"
    assert all(capability.timeout_seconds == 500 for capability in saved)
    bridge._selected_application = "word"
    assert all(capability.timeout_seconds == 40 for capability in saved)


@pytest.mark.parametrize("formula_first", [False, True])
def test_same_patch_can_format_formula_and_change_its_source_without_false_failure(formula_first):
    live, authority, session = service()
    cells = live.backend.sheets["Sheet1"]
    cells[(1, 1)] = {"value": 1, "formula": "", "number_format": "General", "bold": False, "italic": False}
    cells[(2, 1)] = {"value": 2, "formula": "=SUM(A1,1)", "number_format": "General", "bold": False, "italic": False}
    original = live.backend.write_excel
    def write(descriptor, state, fields):
        original(descriptor, state, fields)
        # Native Excel recalculates after either call; a formatting write does
        # not assign the old captured cached formula result back into the cell.
        if cells[(2, 1)]["formula"]:
            cells[(2, 1)]["value"] = cells[(1, 1)]["value"] + 1
    live.backend.write_excel = write
    changes = [{"sheet": "Sheet1", "range": "A1", "values": [[8]]},
               {"sheet": "Sheet1", "range": "A2", "bold": True}]
    if formula_first:
        changes.reverse()
    try:
        receipt = mutate(live, authority, "excel_edit", {"session": session,
            "snapshot": read(live, authority, session)["snapshot"], "changes": changes})
        assert receipt["affected_items"] == 2 and cells[(2, 1)]["value"] == 9
        assert cells[(2, 1)]["bold"] and not live.excel.blocked
        mutate(live, authority, "revert", {"session": session,
            "snapshot": read(live, authority, session)["snapshot"], "recovery": receipt["recovery"]})
        assert cells[(1, 1)]["value"] == 1 and cells[(2, 1)]["value"] == 2
        assert not cells[(2, 1)]["bold"] and not live.excel.blocked
    finally:
        live.close()


def test_formula_result_change_before_dispatch_still_rejects_every_write():
    live, authority, session = service()
    try:
        cells = live.backend.sheets["Sheet1"]
        cells[(1, 1)] = {"value": 2, "formula": "=SUM(A2,2)", "number_format": "General", "bold": False, "italic": False}
        args = tool("excel_edit").arguments.model_validate({"session": session,
            "snapshot": read(live, authority, session)["snapshot"],
            "changes": [{"sheet": "Sheet1", "range": "A1", "bold": True}]})
        guard = live.excel.prepare("office.excel_edit", args, live.binding(session=session))
        cells[(1, 1)]["value"] = 99
        with pytest.raises(OfficeConflict):
            live.call(tool("excel_edit"), args, {**authority, "guard": guard["guard"]}, "edit")
        assert live.backend.writes == 0
    finally:
        live.close()


@pytest.mark.parametrize("mode,stage", [("partial", "excel_write"), ("miswrite", "excel_verification")])
def test_excel_failure_evidence_crosses_sta_sdk_without_leaking_content_or_replaying(mode, stage, tmp_path):
    bridge = connection(mode)
    runtime, session, snapshot = start(bridge, tmp_path)
    try:
        result = execute(runtime, "excel_edit", patch(session, snapshot, values=[[1], [2]]), "edit")
        assert not result.success and result.error.code.value == "outcome_unknown"
        event = bridge.diagnostics["write_outcome"]
        assert event["tool"] == "office.excel_edit" and event["stage"] == stage
        assert event["outcome"] == "unknown" and not event["retry_safe"]
        assert "Excel could not confirm" in result.error.message
        assert ("writing cells" if mode == "partial" else "checking cell values and formatting") in result.error.message
        assert bridge.diagnostics["tool_calls"] == 3
        assert not bridge.exposure.ready and not bridge.diagnostics["worker_alive"]
        assert "SECRET" not in json.dumps(bridge.diagnostics)
    finally:
        runtime.shutdown()


def test_excel_native_hresult_and_only_content_free_details_survive():
    live, authority, session = service()
    def fail(*args):
        error = RuntimeError("PRIVATE cell content and path")
        error.hresult = -2147417846
        raise error
    live.backend.write_excel = fail
    try:
        with pytest.raises(OfficeUnknown) as caught:
            mutate(live, authority, "excel_edit", patch(session, read(live, authority, session)["snapshot"], values=[[1], [2]]))
        event = safe_write_event({**caught.value.diagnostic, "path": "PRIVATE", "arguments": "PRIVATE"})
        assert event["category"] == "busy" and event["hresult"] == -2147417846
        assert event["stage"] == "excel_write" and event["tool"] == "office.excel_edit"
        assert "PRIVATE" not in json.dumps(event)
        assert live.excel.blocked
    finally:
        live.close()


def test_explicit_short_preparation_deadline_never_dispatches_a_write(tmp_path):
    from app.capabilities.contracts import CapabilityExecutionError
    from tests.test_office_mcp_capabilities import prepare
    bridge = connection("slow_prepare", call_timeout=.15)
    runtime, session, snapshot = start(bridge, tmp_path)
    try:
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.excel_edit", patch(session, snapshot, values=[[1], [2]]), "slow-prepare")
        assert bridge.diagnostics["tool_calls"] == 2
        assert not bridge.exposure.ready
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


def test_private_control_deadline_is_independent_of_sdk_connection_default():
    import asyncio
    from types import SimpleNamespace
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", call_timeout=.05)
    async def read_resource(*args, **kwargs):
        await asyncio.sleep(.15)
        return SimpleNamespace(contents=[SimpleNamespace(text='{"complete":true}')])
    client = SimpleNamespace(read_resource=read_resource)
    async def check():
        with pytest.raises(TimeoutError):
            await bridge._control_request(client, "binding", {})
        assert await bridge._control_request(client, "mutation", {}, timeout=1) == {"complete": True}
    asyncio.run(check())


@pytest.mark.parametrize("kind,fill,line,valid", [
    ("line", "#000000", "#267F78", True),
    ("line", "#267F78", "#000000", False),
    ("column", "#000000", "#267F78", False),
    ("column", "#267F78", "#267F78", True),
])
def test_native_chart_palette_checks_visible_stroke_and_filled_chart_areas(kind, fill, line, valid):
    from app.mcp.office_contracts import ExcelChart
    from app.mcp.office_excel_drawing import ExcelDrawing, CHART_TYPES
    geometry = {"left": 10, "top": 10, "width": 240, "height": 120}
    spec = ExcelChart(kind="chart", sheet="Dashboard", name="Chart", geometry=geometry,
        chart_type=kind, source={"snapshot": "source", "sheet": "Data", "range": "A1:B4"},
        title="Revenue", legend=False, colors=["#267F78"])
    state = {"name": "Chart", "geometry": geometry, "chart_type": CHART_TYPES[kind],
        "title": "Revenue", "legend": False, "series": [{"fill": fill, "line": line}]}
    if valid:
        ExcelDrawing().verify_excel_object(spec, state)
    else:
        with pytest.raises(OfficeUnknown, match="palette"):
            ExcelDrawing().verify_excel_object(spec, state)
