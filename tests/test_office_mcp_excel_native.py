"""Opt-in live Excel gate; creates and changes only test-owned synthetic workbooks."""
import gc
import json
import os
from time import monotonic
from uuid import uuid4

import pytest

from app.capabilities.contracts import CapabilityExecutionError
from app.mcp.office_connection import OfficeConnection
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_capabilities import runtime_for, prepare
from tests.test_office_mcp_live import execute


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in synthetic native Excel read gate")
def test_large_used_range_read_pages_with_production_deadline(tmp_path):
    import pythoncom
    import win32com.client
    import win32process
    import psutil

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
    application = document = sheet = owned = None
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud")
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    diagnostics = {"synthetic_only": True, "provider_requests": 0, "pages": [], "passed": False}
    try:
        application = win32com.client.DispatchEx("Excel.Application")
        pid = win32process.GetWindowThreadProcessId(int(application.Hwnd))[1]
        assert pid not in prior
        owned = psutil.Process(pid)
        diagnostics.update(owned_pid=pid, owned_created=owned.create_time())
        document = application.Workbooks.Add()
        sheet = document.Worksheets.Item(1)
        sheet.Name = "ORSIReadProbe"
        sheet.Range("A1:J100").Value2 = tuple(tuple(row * 10 + column for column in range(10)) for row in range(100))
        path = tmp_path / ("ORSIRead-" + uuid4().hex[:12] + ".xlsx")
        document.SaveAs(str(path), 51)
        application.Visible = True
        assert bridge.call_timeout == 10.0
        bridge.connect()
        found = [item for item in bridge.list_documents() if item["application"] == "excel" and item["title"] == path.name]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        attached = execute(runtime, "attach", {"application": "excel", "document": found[0]["document"]}, "attach")
        assert attached.success
        session = attached.output["session"]
        cursor, seen, snapshots = None, [], set()
        while True:
            started = monotonic()
            result = execute(runtime, "read", {"session": session, "target": "ORSIReadProbe!used",
                "cursor": cursor, "max_items": 1000}, "read" + str(len(diagnostics["pages"])))
            assert result.success, result.error
            page = result.output
            values = [value for item in page["items"] for row in item["values"] for value in row]
            assert values and bridge.exposure.ready
            seen.extend(values)
            snapshots.add(page["snapshot"])
            cursor = page["cursor"]
            diagnostics["pages"].append({"cells": len(values), "has_cursor": cursor is not None,
                                         "duration_ms": round((monotonic() - started) * 1000)})
            if cursor is None:
                break
        assert seen == list(range(1000)) and len(snapshots) == 1
        assert len(diagnostics["pages"]) > 1 and diagnostics["pages"][0]["has_cursor"]
        diagnostics["passed"] = True
    finally:
        runtime.shutdown()
        sheet = None
        if document is not None:
            document.Close(False)
        document = None
        if application is not None and owned is not None:
            application.Quit()
        application = None
        gc.collect()
        pythoncom.CoUninitialize()
        if owned is not None:
            try:
                owned.wait(timeout=10)
                diagnostics["owned_excel_released"] = True
            except psutil.TimeoutExpired:
                diagnostics["owned_excel_released"] = False
        diagnostics["worker_released"] = not bridge.diagnostics["worker_alive"]
        (tmp_path / "native-read-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    assert diagnostics["owned_excel_released"] and diagnostics["worker_released"]


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in live Excel desktop gate")
def test_live_excel_patch_conflicts_recovery_save_and_focus_binding(tmp_path):
    import pythoncom
    import win32com.client
    import win32process
    import psutil

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    before_pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
    application = document = other = reopened = sheet = None
    owned_process = None
    documents = []
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20, call_timeout=20)
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    diagnostics = {"live_excel_gate": False, "forced_fixture_cleanup": False}
    try:
        try:
            application = win32com.client.DispatchEx("Excel.Application")
            application.Visible = True
            pid = win32process.GetWindowThreadProcessId(int(application.Hwnd))[1]
            assert pid not in before_pids
            owned_process = psutil.Process(pid)
            diagnostics.update(pid=pid, created=owned_process.create_time())
            document = application.Workbooks.Add()
            documents.append(document)
        except pythoncom.com_error as error:
            pytest.skip("A usable live Excel session is unavailable (HRESULT " + str(error.hresult) + ")")
        sheet = document.Worksheets.Item(1)
        sheet.Name = "ORSIPhase4"

        def number_format(cell, *values):
            flags = pythoncom.DISPATCH_PROPERTYPUT if values else pythoncom.DISPATCH_PROPERTYGET
            return cell._oleobj_.Invoke(cell._oleobj_.GetIDsOfNames("NumberFormat"), 1033, flags, not values, *values)

        number_format(sheet.Range("A1"), "@")
        sheet.Range("A1").Value2 = "=seed"
        number_format(sheet.Range("A1"), "General")
        sheet.Range("A2").Formula2 = "=2+3"
        number_format(sheet.Range("A2"), "0.00")
        sheet.Range("A2").Font.Italic = True
        sheet.Range("B1").Value2 = "unrelated synthetic cell"
        other = application.Workbooks.Add()
        documents.append(other)
        other.Worksheets.Item(1).Range("A1").Value2 = 999
        bridge.connect()
        found = [d for d in bridge.list_documents() if d["application"] == "excel" and d["title"] == str(document.Name)]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        attached = execute(runtime, "attach", {"application": "excel", "document": found[0]["document"]}, "attach")
        assert attached.success
        session = attached.output["session"]
        (tmp_path / "test-application").mkdir()
        # Trusted test composition permits only synthetic output under this basetemp;
        # the production policy protecting ORSI itself is tested separately.
        for name in ("office.excel_edit", "office.revert", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "test-application")
        count = 0

        def read():
            nonlocal count
            count += 1
            value = execute(runtime, "read", {"session": session, "target": "ORSIPhase4!A1:A3"}, "read" + str(count))
            assert value.success
            return value.output

        initial = read()
        other.Activate()
        edited = execute(runtime, "excel_edit", {"session": session, "snapshot": initial["snapshot"], "changes": [
            {"sheet": "ORSIPhase4", "range": "A1", "values": [["=literal"]], "bold": True},
            {"sheet": "ORSIPhase4", "range": "A2", "number_format": "0.000", "italic": False},
            {"sheet": "ORSIPhase4", "range": "A3", "values": [[42]]}]}, "edit")
        assert edited.success and edited.output["affected_items"] == 3
        assert sheet.Range("A1").Value2 == "=literal" and not bool(sheet.Range("A1").HasFormula)
        assert bool(sheet.Range("A1").Font.Bold)
        assert number_format(sheet.Range("A2")) == "0.000" and not bool(sheet.Range("A2").Font.Italic)
        assert sheet.Range("B1").Value2 == "unrelated synthetic cell"
        assert other.Worksheets.Item(1).Range("A1").Value2 == 999
        after = read()
        sheet.Range("A3").Value2 = 99  # A later user change must survive recovery refusal.
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited.output["recovery"]}, "conflict")
        assert sheet.Range("A3").Value2 == 99
        sheet.Range("A3").Value2 = 42
        after = read()
        restored = execute(runtime, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited.output["recovery"]}, "restore")
        assert restored.success
        assert sheet.Range("A1").Value2 == "=seed" and not bool(sheet.Range("A1").HasFormula)
        assert not bool(sheet.Range("A1").Font.Bold)
        assert sheet.Range("A2").Formula2 == "=2+3" and sheet.Range("A2").Value2 == 5
        assert number_format(sheet.Range("A2")) == "0.00" and bool(sheet.Range("A2").Font.Italic)
        assert sheet.Range("A3").Value2 is None
        after = read()
        formula = execute(runtime, "excel_edit", {"session": session, "snapshot": after["snapshot"],
            "changes": [{"sheet": "ORSIPhase4", "range": "A3", "formulas": [["=SUM($A$2,0)"]]}]}, "formula")
        assert formula.success
        verified = read()
        assert verified["items"][2]["formulas"] == [["=SUM($A$2,0)"]] and verified["items"][2]["values"] == [[5.0]]
        destination = tmp_path / "synthetic.xlsx"
        saved = execute(runtime, "save", {"session": session, "path": str(destination)}, "save-as")
        assert saved.success and destination.is_file() and bool(document.Saved)
        sheet.Range("A3").Value2 = 7
        saved = execute(runtime, "save", {"session": session}, "save")
        assert saved.success and bool(document.Saved)
        runtime.shutdown()
        assert str(document.Name) == "synthetic.xlsx" and sheet.Range("B1").Value2 == "unrelated synthetic cell"
        document.Close(False)
        documents.remove(document)
        document = sheet = None
        reopened = application.Workbooks.Open(str(destination))
        documents.append(reopened)
        assert reopened.Worksheets.Item(1).Range("A3").Value2 == 7
        diagnostics["live_excel_gate"] = True
    finally:
        runtime.shutdown()
        if application is not None and owned_process is not None:
            try:
                collection = application.Workbooks
                foreign = any(not any(collection.Item(i)._oleobj_.QueryInterface(pythoncom.IID_IUnknown) ==
                    fixture._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for fixture in documents)
                    for i in range(1, int(collection.Count) + 1))
                if foreign:
                    # A user-opened workbook makes this application borrowed.
                    # Close only our fixtures and preserve the user's application.
                    for fixture in documents:
                        fixture.Close(False)
                    documents.clear()
                    owned_process = None
                    diagnostics["user_workbook_preserved"] = True
            except pythoncom.com_error:
                pass
        for item in documents:
            try:
                item.Saved = True
            except pythoncom.com_error:
                pass
        if owned_process is not None:
            try:
                application.Quit()
            except pythoncom.com_error:
                pass
        documents.clear()
        fixture = collection = item = application = document = other = reopened = sheet = None
        gc.collect()
        if owned_process is not None:
            try:
                owned_process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                # This exact Process object retains the verified creation identity.
                # Production code never terminates Office; this is fixture cleanup.
                owned_process.terminate()
                owned_process.wait(timeout=5)
                diagnostics["forced_fixture_cleanup"] = True
        diagnostics["bridge_released"] = not bridge.diagnostics["worker_alive"]
        (tmp_path / "native-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    assert diagnostics["bridge_released"]
