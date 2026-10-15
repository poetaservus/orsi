"""Opt-in dashboard qualification on test-owned Excel workbooks; zero provider calls."""
import gc
import json
import os

import pytest

from app.mcp.office_connection import OfficeConnection
from app.mcp.office_com import WindowsOffice
from app.mcp.office_live import LiveOffice
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_excel import mutate
from tests.test_office_mcp_live import execute, tool


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in synthetic native Excel dashboard gate")
@pytest.mark.parametrize("transport", ["direct", "stdio"])
def test_native_dashboard_objects_filters_persistence_and_owned_recovery(tmp_path, transport):
    import pythoncom
    import win32com.client
    import win32process
    import psutil

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    before_pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
    application = document = source = dashboard = calculation = pivot = slicer = cache = chart = shape = None
    live = bridge = runtime = None
    owned_process = None
    diagnostics = {"transport": transport, "synthetic_only": True, "provider_requests": 0,
                   "real_workbooks_changed": False, "passed": False}
    count = 0
    try:
        application = win32com.client.DispatchEx("Excel.Application")
        pid = win32process.GetWindowThreadProcessId(int(application.Hwnd))[1]
        assert pid not in before_pids
        owned_process = psutil.Process(pid)
        document = application.Workbooks.Add()
        source = document.Worksheets.Item(1)
        source.Name = "SyntheticSource"
        source.Range("A1:B4").Value2 = (("Region", "Revenue"), ("North", 10), ("South", 20), ("North", 30))
        source.ListObjects.Add(1, source.Range("A1:B4"), pythoncom.Missing, 1).Name = "SyntheticOrders"
        dashboard = document.Worksheets.Add()
        dashboard.Name = "Dashboard"
        calculation = document.Worksheets.Add()
        calculation.Name = "Calculations"
        original_fill = dashboard.Range("A1").Interior
        original_fill.ThemeColor = 5
        original_fill.TintAndShade = 0.4
        original_theme = (int(original_fill.ThemeColor), float(original_fill.TintAndShade))
        original_fill = None

        diagnostics.update(owned_pid=pid, owned_created=owned_process.create_time())
        (tmp_path / "native-dashboard-diagnostics.json").write_text(json.dumps(diagnostics))
        if transport == "direct":
            class OwnedOffice(WindowsOffice):
                # The direct gate owns one exact workbook; discovery/stdio are
                # independently covered by the second gate.
                def __init__(self):
                    from threading import get_ident
                    import win32com.client.dynamic
                    # Borrow the test caller's initialized STA. The caller owns
                    # its lifetime and its other native Excel references.
                    self.com, self.dynamic = pythoncom, win32com.client.dynamic
                    self.thread = get_ident()
                def close(self):
                    self.check_thread()
                def documents(self, enabled):
                    return [("excel", document)]
                def verify_excel_object(self, spec, state):
                    self.test_verification_state = state
                    return super().verify_excel_object(spec, state)
                def capture_excel(self, descriptor, **kwargs):
                    state = super().capture_excel(descriptor, **kwargs)
                    self.test_last_capture = (descriptor[2:], state)
                    return state
            live = LiveOffice(OwnedOffice)
            live.control("configure", {"applications": ["excel"]})
            document_id = next(key for key, (_, obj) in live.documents.items() if str(obj.Name) == str(document.Name))
            binding = live.binding(document=document_id)
            authority = {"document": document_id, "identity": binding["identity"]}
            attached = live.call(tool("attach"), tool("attach").arguments(application="excel", document=document_id), authority)
            session = attached["session"]
        else:
            bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20, call_timeout=30)
            runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
            bridge.connect()
            found = [d for d in bridge.list_documents() if d["application"] == "excel" and d["title"] == str(document.Name)]
            assert len(found) == 1
            bridge.select_document(found[0]["document"])
            attached = execute(runtime, "attach", {"application": "excel", "document": found[0]["document"]}, "attach")
            assert attached.success
            session = attached.output["session"]
            (tmp_path / "test-application").mkdir()
            for name in ("office.excel_edit", "office.revert", "office.save"):
                runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "test-application")

        def invoke(name, args):
            nonlocal count
            count += 1
            diagnostics["last_stage"] = name + "-" + str(count)
            if transport == "direct":
                if name in ("read",):
                    return live.call(tool(name), tool(name).arguments.model_validate(args), authority)
                try:
                    return mutate(live, authority, name, args, "native-" + str(count))
                except Exception as error:
                    context = error.__context__
                    extra = {}
                    if name == "revert":
                        coordinates, current_cell = live.backend.test_last_capture
                        for descriptor, original_cell, applied_cell in live.excel.recoveries[args["recovery"]][2]:
                            if descriptor[2:] == coordinates:
                                expected_cell = {**applied_cell, "value": None, "formula": ""}
                                extra["cell"] = {k: [v, current_cell.get(k)] for k, v in expected_cell.items() if v != current_cell.get(k)}
                        for record in live.excel.recoveries[args["recovery"]][4]:
                            try:
                                current = live.backend.capture_excel_object(document, record["spec"], record["object"], record["auxiliary"])
                                extra[record["spec"].name] = {"matches": live.backend.excel_object_matches(document, record["spec"], record["object"], record["auxiliary"]),
                                    "differences": {k: [v, current.get(k)] for k, v in record["state"].items() if v != current.get(k)}}
                            except Exception as inspect_error:
                                extra[record["spec"].name] = {"inspection_error": type(inspect_error).__name__}
                    raise AssertionError("Synthetic native failure: " + repr(context or error)
                        + " " + json.dumps(extra or getattr(live.backend, "test_verification_state", {}))) from error
            result = execute(runtime, name, args, "native-" + str(count))
            assert result.success, result.error
            return result.output

        def read(target):
            page = invoke("read", {"session": session, "target": target, "max_chars": 8192, "max_items": 1000})
            while page["cursor"]:
                page = invoke("read", {"session": session, "target": target, "cursor": page["cursor"], "max_chars": 8192, "max_items": 1000})
            return page["snapshot"]

        def edit(objects=None, changes=None, destination="Dashboard!A1"):
            snapshot = read(destination)
            return invoke("excel_edit", {"session": session, "snapshot": snapshot,
                                         "objects": objects or [], "changes": changes or []})

        fill_receipt = edit(changes=[{"sheet": "Dashboard", "range": "A1", "fill_color": "#267F78"}])
        assert int(dashboard.Range("A1").Interior.Color) == 0x787F26
        invoke("revert", {"session": session, "snapshot": read("Dashboard!A1"), "recovery": fill_receipt["recovery"]})
        assert int(dashboard.Range("A1").Interior.ThemeColor) == original_theme[0]
        assert abs(float(dashboard.Range("A1").Interior.TintAndShade) - original_theme[1]) < 1e-5
        diagnostics["fill_and_theme_recovery"] = True

        source_snapshot = read("SyntheticSource!A1:B4")
        pivot_receipt = edit(objects=[{"kind": "pivot", "sheet": "Calculations", "name": "RevenueByRegion",
            "destination": "A1:B14", "source": {"snapshot": source_snapshot, "sheet": "SyntheticSource", "range": "A1:B4"},
            "rows": ["Region"], "value_field": "Revenue", "aggregate": "sum"}], destination="Calculations!A1:B14")
        pivot = calculation.PivotTables("RevenueByRegion")
        assert float(pivot.GetPivotData("Revenue").Value2) == 60
        output_range = str(pivot.TableRange2.Address)
        diagnostics["native_pivot_verified"] = True

        # GETPIVOTDATA links the KPI to the slicer's filter context.
        edit(changes=[{"sheet": "Dashboard", "range": "B3", "formulas": [['=GETPIVOTDATA("Revenue",Calculations!$A$1)']], "number_format": "#,##0.00"}], destination="Dashboard!B3")
        linked_snapshot = read("Dashboard!B3")
        shape_receipt = edit(objects=[{"kind": "shape", "sheet": "Dashboard", "name": "RevenueCard",
            "geometry": {"left": 15, "top": 20, "width": 240, "height": 90}, "shape_type": "rounded_rectangle",
            "link": {"snapshot": linked_snapshot, "sheet": "Dashboard", "range": "B3"}, "fill_color": "#DCE9F1",
            "line_color": "#267F78", "font_color": "#172B4D", "font_size": 24, "bold": True}])
        shape = dashboard.Shapes.Item("RevenueCard")
        assert "60" in str(shape.TextFrame2.TextRange.Text)
        diagnostics["native_linked_shape_verified"] = True
        label_receipt = edit(objects=[{"kind": "shape", "sheet": "Dashboard", "name": "RevenueLabel",
            "geometry": {"left": 15, "top": 1, "width": 240, "height": 18}, "shape_type": "rectangle",
            "text": "Revenue", "fill_color": "none", "line_color": "none", "font_size": 11, "bold": True}])
        assert str(dashboard.Shapes.Item("RevenueLabel").TextFrame2.TextRange.Text) == "Revenue"
        diagnostics["native_static_text_shape_verified"] = True

        chart_source = read("Calculations!" + output_range)
        chart_receipt = edit(objects=[{"kind": "chart", "sheet": "Dashboard", "name": "RevenueChart",
            "geometry": {"left": 15, "top": 140, "width": 420, "height": 260}, "chart_type": "bar",
            "source": {"snapshot": chart_source, "sheet": "Calculations", "range": output_range},
            "title": "Revenue by region", "legend": False, "colors": ["#267F78"]}])
        chart = dashboard.ChartObjects("RevenueChart")
        assert int(chart.Chart.ChartType) == 57
        assert int(chart.Chart.SeriesCollection().Count) >= 1
        diagnostics["native_chart_verified"] = True

        slicer_source = read("Calculations!" + output_range)
        slicer_receipt = edit(objects=[{"kind": "slicer", "sheet": "Dashboard", "name": "RegionFilter",
            "geometry": {"left": 460, "top": 20, "width": 180, "height": 200},
            "source": {"snapshot": slicer_source, "sheet": "Calculations", "range": output_range},
            "field": "Region", "caption": "Region", "style": "light"}])
        cache = document.SlicerCaches.Item("RegionFilter")
        slicer = cache.Slicers.Item("RegionFilter")
        # A remaining connected slicer is a dependency, even when Excel hands
        # the bridge a different COM wrapper for the same PivotTable.
        from app.mcp.office_excel import OfficeConflict
        from app.capabilities.contracts import CapabilityExecutionError
        from tests.test_office_mcp_capabilities import prepare
        blocked_args = {"session": session, "snapshot": read("Calculations!A1:B14"), "recovery": pivot_receipt["recovery"]}
        with pytest.raises((OfficeConflict, CapabilityExecutionError), match="dependent slicer"):
            if transport == "direct":
                mutate(live, authority, "revert", blocked_args, "dependency-check")
            else:
                prepare(runtime, "office.revert", blocked_args, "dependency-check")
        assert int(calculation.PivotTables().Count) == 1 and int(document.SlicerCaches.Count) == 1
        diagnostics["dependent_slicer_preserved"] = True

        inventory = invoke("read", {"session": session, "target": "Dashboard!objects", "max_chars": 8192, "max_items": 1000})
        assert inventory["cursor"] is None
        metadata = [json.loads(item["text"]) for item in inventory["items"]]
        assert {item["kind"] for item in metadata} == {"chart", "shape", "slicer"}
        inventory = invoke("read", {"session": session, "target": "Calculations!objects", "max_chars": 8192, "max_items": 1000})
        assert json.loads(inventory["items"][0]["text"])["range"] == output_range
        diagnostics["native_object_discovery_verified"] = True
        cache.SlicerItems.Item("South").Selected = False
        application.Calculate()
        assert float(pivot.GetPivotData("Revenue").Value2) == 40
        assert float(dashboard.Range("B3").Value2) == 40
        assert "40" in str(shape.TextFrame2.TextRange.Text)
        diagnostics["slicer_filters_pivot_and_linked_kpi"] = True
        cache.ClearManualFilter()
        application.Calculate()
        assert float(dashboard.Range("B3").Value2) == 60

        destination = tmp_path / "native-dashboard.xlsx"
        invoke("save", {"session": session, "path": str(destination)})
        assert destination.is_file() and bool(document.Saved)
        diagnostics["native_saved"] = True
        if transport == "direct":
            authority["identity"] = live.binding(session=session)["identity"]

        # Restore creations in dependency order. A fresh complete reserved-cell
        # read is necessary for PivotTable restoration.
        for receipt, area in ((slicer_receipt, "Dashboard!A1"), (chart_receipt, "Dashboard!A1"),
                              (label_receipt, "Dashboard!A1"), (shape_receipt, "Dashboard!A1"), (pivot_receipt, "Calculations!A1:B14")):
            invoke("revert", {"session": session, "snapshot": read(area), "recovery": receipt["recovery"]})
        assert int(dashboard.ChartObjects().Count) == 0 and int(dashboard.Shapes.Count) == 0
        assert int(calculation.PivotTables().Count) == 0
        assert calculation.Range("A1").Value2 is None
        assert source.Range("B4").Value2 == 30
        diagnostics["owned_object_recovery_verified"] = True

        if runtime is not None:
            runtime.shutdown()
            runtime = None
        if live is not None:
            live.close()
            live = None
        document.Close(False)
        document = None
        document = application.Workbooks.Open(str(destination))
        dashboard = document.Worksheets.Item("Dashboard")
        calculation = document.Worksheets.Item("Calculations")
        assert int(dashboard.ChartObjects().Count) == 1
        assert int(dashboard.Shapes.Count) >= 4
        assert int(calculation.PivotTables().Count) == 1 and int(document.SlicerCaches.Count) == 1
        diagnostics["native_reopened_features_preserved"] = True
        diagnostics["passed"] = True
    finally:
        if runtime is not None:
            runtime.shutdown()
        if live is not None:
            live.close()
            live = None
        if document is not None:
            try:
                document.Close(False)
            except (pythoncom.com_error, AttributeError):
                diagnostics["fixture_close_failed"] = True
        try:
            if application is not None and int(application.Workbooks.Count) == 0:
                application.Quit()
            else:
                owned_process = None
        except (pythoncom.com_error, AttributeError):
            diagnostics["fixture_quit_failed"] = True
        source = dashboard = calculation = pivot = slicer = cache = chart = shape = document = application = None
        gc.collect()
        if owned_process is not None:
            try:
                owned_process.wait(timeout=10)
                diagnostics["owned_excel_released"] = True
            except psutil.NoSuchProcess:
                diagnostics["owned_excel_released"] = True
            except psutil.TimeoutExpired:
                owned_process.terminate()
                owned_process.wait(timeout=5)
                diagnostics["forced_fixture_cleanup"] = True
        if bridge is not None:
            diagnostics["bridge_released"] = not bridge.diagnostics["worker_alive"]
        pythoncom.CoUninitialize()
        (tmp_path / "native-dashboard-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    assert diagnostics["passed"]
