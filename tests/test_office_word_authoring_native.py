"""Opt-in native report authoring, exact authority, recovery, pixels and persistence."""
import gc
import json
import os
from pathlib import Path
from uuid import uuid4
from time import monotonic
from zipfile import ZipFile

import pytest

from app.capabilities.contracts import CapabilityExecutionError
from app.mcp.office_connection import OfficeConnection
from app.security.permissions import ApprovalStatus
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_capabilities import runtime_for, prepare, authorize
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import execute
from tests.test_office_word_authoring import report_plan
from tests.test_office_word_compose_validation import redundant_breaks


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in synthetic native report gate")
def test_blank_three_page_report_authority_restore_render_and_save(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    from app.agent.office_images import word_image_message
    from app.inference.protocol import ModelCapabilityCall
    from types import SimpleNamespace
    from app.mcp.office_word_document import capture_document, same_document
    from app.mcp.office_com import WindowsOffice
    from PIL import Image
    from io import BytesIO

    pythoncom.CoInitializeEx(2)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "winword.exe"}
    application = document = other = reopened = backend = None
    owned = None
    documents = []
    bridge = OfficeConnection(ROOT, backend=lambda:"cloud", startup_timeout=20)
    runtime = runtime_for(bridge,tmp_path,policy=bridge.resource_policy)
    diagnostics = {"native_report_gate":False,"provider_requests":0,"forced_fixture_cleanup":False}
    try:
        try:
            application=win32com.client.DispatchEx("Word.Application")
            application.Visible=True
            application.DisplayAlerts=0
            document=application.Documents.Add()
            documents.append(document)
            pid=win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1]
            assert pid not in prior
            owned=psutil.Process(pid)
            diagnostics.update(pid=pid,created=owned.create_time())
            # A unique on-disk fixture name prevents selecting a user's unrelated
            # unsaved "Document1" from another Word process.
            fixture_source=tmp_path/("word-authoring-fixture-"+uuid4().hex+".docx")
            document.SaveAs2(str(fixture_source),12)
        except pythoncom.com_error as error:
            pytest.skip("Native Word unavailable (HRESULT "+str(error.hresult)+")")
        backend=WindowsOffice()
        initial=capture_document(backend,document)
        other=application.Documents.Add()
        documents.append(other)
        other.Content.Text="Foreign focused fixture"
        bridge.connect()
        selected=next(d for d in bridge.list_documents() if d["application"]=="word" and d["title"]==str(document.Name))
        bridge.select_document(selected["document"])
        session=execute(runtime,"attach",{"application":"word","document":selected["document"]},"attach").output["session"]
        (tmp_path/"application").mkdir()
        for name in ("office.word_compose","office.word_edit","office.revert","office.save"):
            runtime.registry.resolve(name).write_policy=HostWritePolicy(tmp_path/"application")
        counter=0
        def read_authoring(max_chars=8192):
            nonlocal counter
            counter+=1
            value=execute(runtime,"read",{"session":session,"target":"authoring","max_chars":max_chars},
                          "authoring-"+str(counter)).output
            assert value is not None
            return value
        def complete(value):
            nonlocal counter
            while value["cursor"]:
                counter+=1
                next_page=execute(runtime,"read",{"session":session,"target":"authoring","cursor":value["cursor"],
                    "max_chars":8192},"cursor-"+str(counter)).output
                assert next_page["snapshot"]==value["snapshot"]
                value=next_page
            return value

        partial=read_authoring(30)
        assert partial["cursor"]
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime,"office.word_compose",report_plan(session,partial["snapshot"]),"partial-refusal")
        first=complete(partial)
        args=redundant_breaks(report_plan(session,first["snapshot"]))
        prepared=prepare(runtime,"office.word_compose",args,"denied-compose")
        assert "Replace ALL" in prepared.request.approval_preview
        assert prepared.validated_arguments().model_dump(mode="json")==runtime.registry.resolve(
            "office.word_compose").validate_arguments(report_plan(session,first["snapshot"])).model_dump(mode="json")
        assert sum(block["kind"]=="page_break" for block in json.loads(
            prepared.request.arguments_json)["blocks"])==2
        auth=authorize(runtime,prepared,ApprovalStatus.DENIED)
        rejected=runtime.executor.executor.execute(prepared,auth)
        assert not rejected.success
        assert same_document(initial,capture_document(backend,document))

        # A complete stale snapshot cannot authorize a report replacement.
        document.Content.Text="User's intervening fixture change"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime,"office.word_compose",args,"stale-refusal")
        document.Content.Text=""
        current=complete(read_authoring())
        args=redundant_breaks(report_plan(session,current["snapshot"]))
        diagnostics["submitted_page_breaks"]=sum(block["kind"]=="page_break" for block in args["blocks"])
        assert bridge.call_timeout == 10 and bridge.tool_timeout(runtime.registry.resolve("office.word_compose").contract) == 60
        assert runtime.registry.resolve("office.word_compose").timeout_seconds == 90
        compose_started=monotonic()
        edited=execute(runtime,"word_compose",args,"compose")
        diagnostics["compose_elapsed_seconds"]=round(monotonic()-compose_started,3)
        assert edited.success, edited.error
        assert str(other.Content.Text)=="Foreign focused fixture\r"
        assert int(document.Shapes.Count)==int(document.InlineShapes.Count)==0
        assert int(document.Tables.Count)==1
        assert str(document.Paragraphs.Item(1).Style.NameLocal)==str(document.Styles.Item(-63).NameLocal)
        layout=execute(runtime,"read",{"session":session,"target":"layout"},"layout").output
        info=json.loads(layout["items"][0]["text"])
        assert info["page_count"]==3 and info["tables_outside_body_or_irregular"]==[]
        assert str(document.Sections.Item(1).Footers.Item(1).Range.Fields.Item(2).Result.Text)=="3"
        rendered=execute(runtime,"read",{"session":session,"target":"render:1:3"},"render")
        assert rendered.success,rendered.error
        assert str(application.ActiveDocument.Name)==str(other.Name)
        pages=bridge.render_images(rendered.output)
        assert [page for page,_ in pages]==[1,2,3]
        assert all(json.loads(item["text"])["header_present"] is True for item in rendered.output["items"])
        for number,pixels in pages:
            with Image.open(BytesIO(pixels)) as image:
                assert image.format=="PNG" and image.width>1000 and image.height>1500
            (tmp_path/f"page-{number}.png").write_bytes(pixels)
        message=word_image_message(runtime.registry.resolve("office.read"),
            ModelCapabilityCall(provider_call_id="render",capability="office.read",
                arguments={"session":session,"target":"render:1:3"}),rendered,
            SimpleNamespace(supports_native_attachment_tools=True))
        assert sum(item["type"]=="image_url" for item in message["content"])==3
        from tests.test_bounded_edit_recovery import RoomyScriptedModel, call
        from app.inference.protocol import ModelResponse
        from app.inference.local_images import image_accounting_messages
        class VisionModel(RoomyScriptedModel):
            def count_image_message_tokens(self,messages):
                image_accounting_messages(messages)
                return 2048
        model=VisionModel([call(1,"office.read",session=session,target="render:1:3"),
            ModelResponse.text("The three synthetic Word pages were received for review.")])
        model.mode="cloud"
        model.supports_native_attachment_tools=True
        runtime.model=model
        runtime.registry.model=model
        outcome=runtime.run([{"role":"user","content":"Render and inspect all three pages of this synthetic report."}],
            session_id="native-render",turn_id="native-render",portable_root=ROOT,allowed_read_roots=(ROOT,))
        from app.agent.contracts import AgentRunStatus
        assert outcome.status==AgentRunStatus.COMPLETED
        assert sum(part.get("type")=="image_url" for message in model.requests[-1]
            if isinstance(message.get("content"),list) for part in message["content"])==3

        # A later user edit prevents owned restoration; undo is never used.
        document.Paragraphs.Item(1).Range.InsertBefore("Foreign change ")
        changed=complete(read_authoring())
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime,"office.revert",{"session":session,"snapshot":changed["snapshot"],
                    "recovery":edited.output["recovery"]},"revert-foreign-refusal")
        # Restore the fixture by another explicitly approved composition, then
        # exercise recovery to a nonempty report with running PAGE fields.
        second=execute(runtime,"word_compose",report_plan(session,changed["snapshot"]),"compose-second")
        assert second.success,second.error
        source=complete(read_authoring())
        small=report_plan(session,source["snapshot"])
        small["blocks"]=[{"kind":"paragraph","text":"A shorter owned report","style":"Title"}]
        shortened=execute(runtime,"word_compose",small,"compose-short")
        assert shortened.success,shortened.error
        current=complete(read_authoring())
        restored=execute(runtime,"revert",{"session":session,"snapshot":current["snapshot"],
            "recovery":shortened.output["recovery"]},"restore-report")
        assert restored.success,restored.error
        assert int(document.Range(0,0).Information(4))==3

        destination=tmp_path/"warehouse_performance_report.docx"
        saved=execute(runtime,"save",{"session":session,"path":str(destination)},"save-as")
        assert saved.success,saved.error
        with ZipFile(destination) as archive:
            body=archive.read("word/document.xml")
            assert b"txbxContent" not in body and b"<w:tbl>" in body and b"Warehouse Operations" in body
            assert any(name.startswith("word/footer") for name in archive.namelist())
        document.Close(False)
        documents.remove(document)
        document=None
        reopened=application.Documents.Open(str(destination))
        documents.append(reopened)
        assert int(reopened.Range(0,0).Information(4))==3
        assert int(reopened.Tables.Count)==1 and int(reopened.Shapes.Count)==0
        diagnostics["native_report_gate"]=True
    finally:
        runtime.shutdown()
        for fixture in documents:
            fixture.Close(False)
        documents.clear()
        fixture=document=other=reopened=None
        gc.collect()
        if application is not None and owned is not None:
            application.Quit(False)
        application=None
        gc.collect()
        if backend is not None:
            backend.close()
        backend=None
        if owned is not None:
            owned.wait(10)
        diagnostics["bridge_released"]=not bridge.diagnostics["worker_alive"]
        diagnostics["temporary_released"]=bridge.diagnostics["temporary_released"]
        (tmp_path/"native-diagnostics.json").write_text(json.dumps(diagnostics,indent=2),encoding="utf-8")
        pythoncom.CoUninitialize()
    assert diagnostics["bridge_released"] and diagnostics["temporary_released"] and not diagnostics["forced_fixture_cleanup"]
