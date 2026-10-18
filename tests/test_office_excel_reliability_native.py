"""Production-budget Excel qualification; only a disposable owned workbook."""
import gc
import json
import os
from time import monotonic
from uuid import uuid4

import pytest

from app.mcp.office_connection import OfficeConnection
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import execute


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in native Excel reliability gate")
@pytest.mark.parametrize("rows", [20, 100])
def test_dashboard_sized_patch_recovery_and_save_at_production_defaults(tmp_path, rows):
    import pythoncom
    import psutil
    import win32com.client
    import win32process

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
    application = document = sheet = owned = None
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud")
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    diagnostics = {"synthetic_only": True, "provider_requests": 0, "operations": [], "passed": False}
    count = 0
    try:
        application = win32com.client.DispatchEx("Excel.Application")
        pid = win32process.GetWindowThreadProcessId(int(application.Hwnd))[1]
        assert pid not in prior
        owned = psutil.Process(pid)
        diagnostics.update(owned_pid=pid, owned_created=owned.create_time(), cells=rows * 10)
        document = application.Workbooks.Add()
        sheet = document.Worksheets.Item(1)
        sheet.Name = "Dashboard"
        application.Visible = True
        title = str(document.Name)
        bridge.connect()
        found = [d for d in bridge.list_documents() if d["application"] == "excel" and d["title"] == title]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        attached = execute(runtime, "attach", {"application": "excel", "document": found[0]["document"]}, "attach")
        assert attached.success, attached.error
        session = attached.output["session"]
        (tmp_path / "protected-app").mkdir()
        for name in ("office.excel_edit", "office.revert", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "protected-app")

        def call(name, args):
            nonlocal count
            count += 1
            started = monotonic()
            result = execute(runtime, name, {"session": session, **args}, "gate-" + str(count))
            diagnostics["operations"].append({"tool": name, "duration_ms": round((monotonic() - started) * 1000),
                "success": result.success})
            assert result.success, result.error
            assert bridge.exposure.ready
            return result.output

        def read():
            target = "Dashboard!A1:J" + str(rows)
            page = call("read", {"target": target, "max_items": 1000, "max_chars": 8192})
            while page["cursor"]:
                page = call("read", {"target": target, "max_items": 1000, "max_chars": 8192, "cursor": page["cursor"]})
            return page["snapshot"]

        address = "A1:J" + str(rows)
        values = [[row * 10 + column + 1 for column in range(10)] for row in range(rows)]
        receipt = call("excel_edit", {"snapshot": read(), "changes": [{"sheet": "Dashboard", "range": address,
            "values": values, "number_format": "#,##0.00", "bold": True, "fill_color": "#DCE9E4"}]})
        assert receipt["affected_items"] == rows * 10
        assert sheet.Range(address).Value2 == tuple(tuple(row) for row in values)
        call("revert", {"snapshot": read(), "recovery": receipt["recovery"]})
        assert all(value is None for row in sheet.Range(address).Value2 for value in row)
        assert not bool(sheet.Range(address).Font.Bold)
        call("save", {"path": str(tmp_path / ("dashboard-" + uuid4().hex[:8] + ".xlsx"))})
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
        (tmp_path / "native-excel-reliability.json").write_text(json.dumps(diagnostics, indent=2))
    assert diagnostics["owned_excel_released"] and diagnostics["worker_released"]
