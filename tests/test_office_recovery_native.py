"""Opt-in essential Office recovery gate against one disposable owned Excel instance."""
import gc
import json
import os
import posixpath
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from app.agent.contracts import AgentRunStatus
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.mcp.office_connection import OfficeConnection
from app.security.write_policy import HostWritePolicy
from tests.test_bounded_edit_recovery import RoomyScriptedModel
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_mcp_connection import ROOT


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in isolated native Excel recovery gate")
def test_changed_workbook_renews_identical_save_and_metadata_calls_then_completes(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
    application = document = sheet = owned = None
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud")
    model = RoomyScriptedModel([])
    model.mode = "cloud"
    runtime = runtime_for(bridge, tmp_path, model, policy=bridge.resource_policy)
    diagnostics = {"synthetic_only": True, "provider_requests": 0, "passed": False}
    workbook = tmp_path / ("office-recovery-" + uuid4().hex[:8] + ".xlsx")
    try:
        # DispatchEx creates our instance; never use GetActiveObject, close other
        # workbooks, or change application settings on an existing Excel process.
        application = win32com.client.DispatchEx("Excel.Application")
        pid = win32process.GetWindowThreadProcessId(int(application.Hwnd))[1]
        assert pid not in prior
        owned = psutil.Process(pid)
        diagnostics.update(owned_pid=pid, owned_created=owned.create_time())
        document = application.Workbooks.Add()
        sheet = document.Worksheets.Item(1)
        sheet.Name = "RecoveryGate"
        document.SaveAs(str(workbook), FileFormat=51)
        application.Visible = True

        bridge.connect()
        found = [d for d in bridge.list_documents()
                 if d["application"] == "excel" and d["title"] == str(document.Name)]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        protected = tmp_path / "protected-app"
        protected.mkdir()
        for name in ("office.excel_edit", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(protected)
        approvals = []

        def approve(record):
            approvals.append(record)
            runtime.resolve_approval(record.approval_id, True)

        runtime.set_approval_requester(approve)

        def output(messages, capability):
            values = [m["result"]["output"] for m in messages
                      if m.get("role") == "capability" and m.get("capability") == capability]
            assert values and isinstance(values[-1], dict)
            return values[-1]

        def session(messages):
            return output(messages, "office.attach")["session"]

        def read_args(messages):
            return {"session": session(messages), "target": "RecoveryGate!A1:B1"}

        plan = [("office.documents", lambda messages: {"application": "excel"}),
                ("office.attach", lambda messages: {"application": "excel", "document": found[0]["document"]}),
                ("office.read", read_args)]
        for revision in (1, 2, 3):
            def edit_args(messages, revision=revision):
                return {"session": session(messages), "snapshot": output(messages, "office.read")["snapshot"],
                        "changes": [{"sheet": "RecoveryGate", "range": "A1", "values": [[revision]]},
                                    {"sheet": "RecoveryGate", "range": "B1", "formulas": [["=A1*10"]]}]}
            plan.extend([("office.excel_edit", edit_args), ("office.read", read_args),
                         ("office.save", lambda messages: {"session": session(messages)}),
                         ("office.documents", lambda messages: {"application": "excel"})])

        for index, (capability, arguments) in enumerate(plan):
            model.responses.append(ModelResponse.text("placeholder"))

            def prepare(messages, definitions, index=index, capability=capability, arguments=arguments):
                model.responses[0] = ModelResponse.calls((ModelCapabilityCall(
                    provider_call_id=f"native-office-{index}", capability=capability,
                    arguments=arguments(messages)),))

            model.before_request[index] = prepare
        model.responses.append(ModelResponse.text("Updated the disposable workbook; three revisions were read back and saved."))
        store = ConversationStore(tmp_path / "conversation.json")
        objective = "Update and verify the selected disposable Excel workbook through three revisions."
        turn_id = store.begin_turn(objective)
        store.start_goal(turn_id)
        outcome = runtime.run([{"role": "user", "content": objective}], session_id=store.session_id,
                              turn_id=turn_id, portable_root=ROOT, allowed_read_roots=(ROOT,),
                              goal_request=objective,
                              settled_observer=lambda settled: store.record_settled(turn_id, settled))
        diagnostics.update(status=outcome.status.value, settled_calls=len(outcome.settled_calls),
                           blocked_capability=(outcome.blocked_attempt.capability if outcome.blocked_attempt else None))
        assert outcome.status == AgentRunStatus.COMPLETED, outcome.message
        assert outcome.completion_review is not None and outcome.completion_review.status == "ready"
        assert outcome.completion_review.ledger_version == 2
        assert all(item.result.success for item in outcome.settled_calls)
        saves = [item for item in outcome.settled_calls if item.call.capability == "office.save"]
        metadata = [item for item in outcome.settled_calls if item.call.capability == "office.documents"]
        edits = [item for item in outcome.settled_calls if item.call.capability == "office.excel_edit"]
        assert len(saves) == len(edits) == 3 and len(metadata) == 4
        assert len({json.dumps(item.call.arguments, sort_keys=True) for item in saves}) == 1
        assert len({json.dumps(item.call.arguments, sort_keys=True) for item in metadata}) == 1
        assert all(item.result.output["outcome"] == "applied" for item in edits)
        assert all(item.result.output["saved"] is True for item in saves)
        claims = {claim.call_id: claim.claim for claim in outcome.completion_review.evidence}
        assert [claims[item.result.call_id] for item in edits] == ["applied"] * 3
        assert [claims[item.result.call_id] for item in saves] == ["unverified", "unverified", "saved"]
        reads = [item.result.output for item in outcome.settled_calls if item.call.capability == "office.read"]
        assert len(reads) == 4 and all(read["cursor"] is None for read in reads)
        assert len({read["snapshot"] for read in reads}) == 4
        for revision, read in enumerate(reads[1:], 1):
            assert [item["values"][0][0] for item in read["items"]] == [revision, revision * 10]
            assert read["items"][1]["formulas"] == [["=A1*10"]]
        assert len(approvals) == 6
        assert sheet.Range("A1").Value2 == 3 and sheet.Range("B1").Value2 == 30
        assert sheet.Range("B1").Formula == "=A1*10" and bool(document.Saved)
        store.finish_turn(turn_id, outcome, outcome.assistant_text)
        restored = ConversationStore(tmp_path / "conversation.json").turns()[0]
        assert restored.outcome.status == AgentRunStatus.COMPLETED
        assert restored.outcome.completion_review.status == "ready"
        assert restored.outcome.completion_review.ledger_version == 2
        assert len(restored.settled_calls) == len(plan)
        # Check the saved artifact independently of the live COM objects, with
        # the standard library so qualification needs no extra workbook package.
        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        office_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        package_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
        with ZipFile(workbook) as saved:
            book = ElementTree.fromstring(saved.read("xl/workbook.xml"))
            sheets = book.find(f"{{{main}}}sheets")
            relationship = next(s.attrib[f"{{{office_rel}}}id"] for s in sheets if s.attrib["name"] == "RecoveryGate")
            relationships = ElementTree.fromstring(saved.read("xl/_rels/workbook.xml.rels"))
            target = next(r.attrib["Target"] for r in relationships.findall(f"{{{package_rel}}}Relationship")
                          if r.attrib["Id"] == relationship)
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            saved_sheet = ElementTree.fromstring(saved.read(path))
            cells = {cell.attrib["r"]: cell for cell in saved_sheet.findall(f".//{{{main}}}c")}
            assert float(cells["A1"].find(f"{{{main}}}v").text) == 3
            assert cells["B1"].find(f"{{{main}}}f").text == "A1*10"
            assert float(cells["B1"].find(f"{{{main}}}v").text) == 30
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
                # Only the exact process created above is eligible for cleanup.
                if owned.create_time() == diagnostics["owned_created"]:
                    owned.terminate()
                    owned.wait(timeout=10)
        diagnostics["worker_released"] = not bridge.diagnostics["worker_alive"]
        (tmp_path / "native-office-recovery.json").write_text(json.dumps(diagnostics, indent=2))
    assert diagnostics["owned_excel_released"] and diagnostics["worker_released"]
