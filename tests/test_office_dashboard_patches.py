"""Dashboard patch composition, same-workbook formulas and read packing."""
import json

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.agent.progress import recovery_stop_progress
from app.capabilities.contracts import CapabilityResult
from app.inference.protocol import ModelCapabilityCall
from app.mcp.office_contracts import ReadArguments
from app.mcp.office_excel import OfficeConflict, validate_formula
from tests.test_office_mcp_excel import service, read, mutate
from tests.test_office_mcp_live import tool


def test_value_header_and_currency_overlaps_merge_once_and_restore_exactly():
    live, authority, session = service()
    try:
        snapshot = read(live, authority, session)["snapshot"]
        result = mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot, "changes": [
            {"sheet": "Sheet1", "range": "A1:A2", "values": [["Revenue"], [48525]]},
            {"sheet": "Sheet1", "range": "A1", "bold": True},
            {"sheet": "Sheet1", "range": "A2", "number_format": "0.00"},
            {"sheet": "Sheet1", "range": "A1", "values": [["Revenue"]]}]})
        assert result["affected_items"] == 2 and live.backend.writes == 2
        state = live.backend.sheets["Sheet1"]
        assert state[(1, 1)]["bold"] and state[(2, 1)]["number_format"] == "0.00"
        fresh = read(live, authority, session)["snapshot"]
        restored = mutate(live, authority, "revert", {"session": session, "snapshot": fresh, "recovery": result["recovery"]}, "restore")
        assert restored["affected_items"] == 2
        assert all(cell["value"] is None and not cell["bold"] and cell["number_format"] == "General" for cell in state.values())
    finally:
        live.close()


@pytest.mark.parametrize("first,second", [({"values": [[1]]}, {"values": [[2]]}),
    ({"values": [[True]]}, {"values": [[1]]}), ({"formulas": [["=2+3"]]}, {"values": [[5]]}),
    ({"bold": True}, {"bold": False})])
def test_conflicting_overlaps_reject_every_cell_before_writing(first, second):
    live, authority, session = service()
    try:
        snapshot = read(live, authority, session)["snapshot"]
        with pytest.raises(OfficeConflict, match="Conflicting assignments"):
            mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot, "changes": [
                {"sheet": "Sheet1", "range": "A1", **first}, {"sheet": "Sheet1", "range": "A1", **second}]})
        assert live.backend.writes == 0
    finally:
        live.close()


@pytest.mark.parametrize("formula", ["=SUM(Other!$A$1:$A$35)", "=COUNTA('Sales ''26'!A2:A36)",
    '=SUMPRODUCT(Other!F2:F36,NUMBERVALUE(Other!G2:G36,".",","))', '=NUMBERVALUE("1,200.00",CHAR(46),CHAR(44))'])
def test_bounded_dashboard_formulas_resolve_only_explicit_same_workbook_sheets(formula):
    names = {"Other", "Sales '26"}
    def resolve(name):
        assert name in names
        return name
    validate_formula(formula, resolve)


@pytest.mark.parametrize("formula", ['=[book.xlsx]Other!A1', "='[book.xlsx]Other'!A1", "=S1:S2!A1",
    "=Other!A1:A1001", "=Other!XFE1", '=INDIRECT("Other!A1")', '=WEBSERVICE("https://example.test")',
    "='C:\\secret\\[book.xlsx]Other'!A1", "=Other!A1!B1"])
def test_cross_sheet_support_does_not_accept_external_3d_unbounded_or_dynamic_references(formula):
    with pytest.raises(OfficeConflict):
        validate_formula(formula, lambda name: name)


def test_replaced_reference_sheet_changes_approval_digest_and_rejects_old_guard():
    live, authority, session = service()
    try:
        args = tool("excel_edit").arguments(session=session, snapshot=read(live, authority, session)["snapshot"],
            changes=[{"sheet": "Sheet1", "range": "A1", "formulas": [["=SUM(Other!A1:A2)"]]}])
        binding = live.binding(session=session)
        initial = live.excel.prepare("office.excel_edit", args, binding)
        live.backend.sheets["Other"] = {}
        changed = live.excel.prepare("office.excel_edit", args, binding)
        assert initial["digest"] != changed["digest"]
        with pytest.raises(OfficeConflict, match="referenced worksheet changed"):
            live.call(tool("excel_edit"), args, {**authority, "guard": initial["guard"]}, "edit")
        assert live.backend.writes == 0
    finally:
        live.close()


def test_restoration_cannot_redirect_an_old_formula_to_a_replaced_source_sheet():
    live, authority, session = service()
    try:
        live.backend.sheets["Sheet1"][(1, 1)] = {"value": 5, "formula": "=Other!A1", "number_format": "General", "bold": False, "italic": False}
        snapshot = read(live, authority, session)["snapshot"]
        edited = mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot,
            "changes": [{"sheet": "Sheet1", "range": "A1", "values": [[7]]}]})
        fresh = read(live, authority, session)["snapshot"]
        live.backend.sheets["Other"] = {}
        with pytest.raises(OfficeConflict, match="referenced worksheet changed"):
            mutate(live, authority, "revert", {"session": session, "snapshot": fresh, "recovery": edited["recovery"]})
        assert live.backend.sheets["Sheet1"][(1, 1)]["value"] == 7
    finally:
        live.close()


def test_packed_used_read_obeys_byte_char_and_cell_bounds_and_preserves_edit_coverage():
    live, authority, session = service()
    try:
        for r in range(1, 37):
            for c in range(1, 9):
                live.backend.sheets["Sheet1"][(r, c)] = {"value": '\U0001f642"\\' * 8, "formula": "",
                    "number_format": "General", "bold": False, "italic": False}
        cursor, count, snapshot = None, 0, None
        while True:
            args = ReadArguments(session=session, target="Sheet1!used", cursor=cursor, max_items=100, max_chars=4096)
            page = read(live, authority, session, target=args.target, cursor=cursor)
            result = tool("read").validate_result(args, page)
            assert len(result.model_dump_json().encode()) <= 16384
            count += sum(len(row) for item in page["items"] for row in item["values"])
            assert snapshot is None or snapshot == page["snapshot"]
            snapshot, cursor = page["snapshot"], page["cursor"]
            if cursor is None:
                break
        assert count == 288
        result = mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot,
            "changes": [{"sheet": "Sheet1", "range": "H36", "values": [[9]]}]})
        assert result["affected_items"] == 1
    finally:
        live.close()


@pytest.mark.parametrize("application,label", [("excel", "Excel patch"), ("word", "Word replacement")])
def test_recovery_report_keeps_successful_office_changes_visible(application, label):
    call = ModelCapabilityCall(provider_call_id="patch", capability="office." + application + "_edit", arguments={})
    result = CapabilityResult(call_id="patch", capability=call.capability, success=True, duration_ms=1,
        output={"session": "s", "operation": "patch", "outcome": "applied", "affected_items": 20})
    stopped = AgentRunResult(status=AgentRunStatus.REPEATED_CALL, message="Repeated rejected formatting.",
        steps=2, capability_calls=2, protocol_failures=0,
        settled_calls=(SettledCall(provider_message_id="message", call=call, result=result),))
    report = recovery_stop_progress(stopped)
    assert label in report and "No successful file changes" not in report


def test_owned_patch_recalculation_does_not_masquerade_as_a_source_edit():
    live, authority, session = service()
    try:
        live.backend.sheets["Sheet1"][(2, 1)] = {"value": 1, "formula": "=SUM(A1,1)",
            "number_format": "General", "bold": False, "italic": False}
        original = live.backend.write_excel
        def recalculate(descriptor, state, fields):
            original(descriptor, state, fields)
            if descriptor[2:] == (1, 1):
                live.backend.sheets["Sheet1"][(2, 1)]["value"] = 3
        live.backend.write_excel = recalculate
        snapshot = read(live, authority, session)["snapshot"]
        edited = mutate(live, authority, "excel_edit", {"session": session, "snapshot": snapshot, "changes": [
            {"sheet": "Sheet1", "range": "A1", "values": [[2]]},
            {"sheet": "Sheet1", "range": "A2", "formulas": [["=SUM(A1,2)"]]}]})
        assert edited["affected_items"] == 2 and not live.excel.blocked
    finally:
        live.close()


def test_formula_recalculation_before_dispatch_still_rejects_approved_patch():
    live, authority, session = service()
    try:
        live.backend.sheets["Sheet1"][(2, 1)] = {"value": 1, "formula": "=SUM(A1,1)",
            "number_format": "General", "bold": False, "italic": False}
        args = tool("excel_edit").arguments(session=session, snapshot=read(live, authority, session)["snapshot"],
            changes=[{"sheet": "Sheet1", "range": "A2", "bold": True}])
        guard = live.excel.prepare("office.excel_edit", args, live.binding(session=session))
        live.backend.sheets["Sheet1"][(2, 1)]["value"] = 3
        with pytest.raises(OfficeConflict, match="changed before writing"):
            live.call(tool("excel_edit"), args, {**authority, "guard": guard["guard"]}, "edit")
        assert live.backend.writes == 0
    finally:
        live.close()
