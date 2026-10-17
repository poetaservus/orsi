"""Opt-in production Word bridge with test-owned documents and scripted responses."""
import gc
import json
import os
from uuid import uuid4

import pytest

from app.mcp.office_connection import OfficeConnection
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_capabilities import runtime_for, prepare
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import execute
from tests.test_bounded_edit_recovery import RoomyScriptedModel
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.agent.contracts import AgentRunStatus
from app.capabilities.contracts import CapabilityExecutionError


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in isolated native Word gate")
def test_native_revision_recovery_review_save_completion_and_closing_failure(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process

    pythoncom.CoInitializeEx(2)
    application = document = reopened = None
    owned = None
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20)
    class VisionScriptedModel(RoomyScriptedModel):
        def count_image_message_tokens(self, messages):
            from app.inference.local_images import image_accounting_messages
            image_accounting_messages(messages)
            return 2048
    model = VisionScriptedModel([], auto_review=False)
    model.mode = "cloud"
    model.supports_native_attachment_tools = True
    runtime = runtime_for(bridge, tmp_path, model=model, policy=bridge.resource_policy)
    counts = {"composes": 0, "model_requests": 0, "images": 0}
    destination = tmp_path / ("isolated-workflow-" + uuid4().hex + ".docx")
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = True
        application.DisplayAlerts = 0
        document = application.Documents.Add()
        owned = psutil.Process(win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1])
        document.SaveAs2(str(destination), 12)
        bridge.connect()
        selected = next(d for d in bridge.list_documents() if d["title"] == str(document.Name) and d["application"] == "word")
        bridge.select_document(selected["document"])
        attached = execute(runtime, "attach", {"application": "word", "document": selected["document"]}, "attach")
        assert attached.success, attached.error
        session = attached.output["session"]
        (tmp_path / "application").mkdir()
        for name in ("office.word_compose", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "application")
        runtime.set_approval_requester(lambda record: runtime.resolve_approval(record.approval_id, True))
        serial = 0

        def read(target):
            nonlocal serial
            cursor = None
            while True:
                serial += 1
                result = execute(runtime, "read", {"session": session, "target": target, "max_chars": 8192,
                    **({"cursor": cursor} if cursor else {})}, "read" + str(serial))
                assert result.success, result.error
                cursor = result.output["cursor"]
                if cursor is None:
                    return result.output

        def plan(snapshot, title):
            return {"session": session, "snapshot": snapshot, "blocks": [
                {"kind": "paragraph", "text": title, "style": "Title"},
                {"kind": "paragraph", "text": "Synthetic first page."},
                {"kind": "page_break"},
                {"kind": "paragraph", "text": "Synthetic second page."}]}

        wrong = read("layout")
        with pytest.raises(CapabilityExecutionError, match="authoring"):
            prepare(runtime, "office.word_compose", plan(wrong["snapshot"], "Draft"), "wrong-snapshot")
        fresh = read("authoring")
        first = execute(runtime, "word_compose", plan(fresh["snapshot"], "Draft"), "initial-compose")
        assert first.success, first.error
        counts["composes"] += 1
        rendered = read("render:1:2")
        pages = bridge.render_images(rendered)
        assert [number for number, _ in pages] == [1, 2]
        assert all(blob.startswith(b"\x89PNG") for _, blob in pages)
        defect = {"location": "page 1 title", "defect": "Title reads Draft", "requirement": "The requested title is Final"}
        review = execute(runtime, "word_review", {"session": session,
            "revision": rendered["word_workflow"]["revision"], "findings": [defect],
            "requirements_checked": ["Title Final and two legible pages"], "requirements_met": False}, "defect-review")
        assert review.success, review.error
        interim = execute(runtime, "save", {"session": session}, "preserved-draft")
        assert interim.success, interim.error
        fresh = read("authoring")
        corrected = execute(runtime, "word_compose", plan(fresh["snapshot"], "Final"), "correct-title")
        assert corrected.success, corrected.error
        counts["composes"] += 1
        evidence = corrected.output["word_workflow"]
        assert evidence["review"] is None and evidence["current_save"] is None
        assert evidence["image_pages"] == [] and evidence["save_receipts"][0]["operation"] == "preserved-draft"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_compose", plan(fresh["snapshot"], "Final"), "no-replay")

        def call(name, **arguments):
            return ModelResponse.calls((ModelCapabilityCall(provider_call_id=uuid4().hex,
                capability="office." + name, arguments={"session": session, **arguments}),))

        model.responses = [call("read", target="render:1:2"), ModelResponse.text("placeholder"),
                           call("save"), ModelResponse.text("Verified and saved the isolated document.")]
        def inspect(messages, definitions):
            rendered_output = [m["result"]["output"] for m in messages if m.get("role") == "capability"][-1]
            image_parts = [p for m in messages if isinstance(m.get("content"), list) for p in m["content"]
                           if isinstance(p, dict) and p.get("type") == "image_url"]
            assert len(image_parts) == 2
            counts["images"] = len(image_parts)
            model.responses[0] = call("word_review", revision=rendered_output["word_workflow"]["revision"],
                findings=[], requirements_checked=["Title Final", "Two legible pages"], requirements_met=True)
        model.before_request[1] = inspect
        result = runtime.run([{"role": "user", "content": "Verify and save the isolated synthetic two-page document with title Final."}],
            session_id="native-workflow", turn_id="finish", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert result.status == AgentRunStatus.COMPLETED, (result.message, result.assistant_text)
        assert [s.call.capability for s in result.settled_calls] == ["office.read", "office.word_review", "office.save"]
        assert result.settled_calls[-1].result.output["word_workflow"]["verified_saved"]
        # Closing-response failure must retain the successful save and review evidence.
        model.before_request.clear()
        model.responses = [call("save"), RuntimeError("synthetic closing response unavailable")]
        failed = runtime.run([{"role": "user", "content": "Save the current isolated document."}],
            session_id="native-workflow", turn_id="closing-failure", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert failed.status != AgentRunStatus.COMPLETED
        receipts = [s.result for s in failed.settled_calls if s.call.capability == "office.save"]
        assert len(receipts) == 1 and receipts[0].success and receipts[0].output["saved"]
        assert receipts[0].output["word_workflow"]["current_save"] is not None
        assert "Successful save receipt for this revision" in failed.partial_text
        counts["model_requests"] = len(model.requests)
        document.Close(0)
        document = None
        reopened = application.Documents.Open(str(destination), ReadOnly=True, AddToRecentFiles=False)
        assert str(reopened.Paragraphs.Item(1).Range.Text).strip() == "Final"
        assert int(reopened.Range(0, 0).Information(4)) == 2
        reopened.Close(0)
        reopened = None
    finally:
        runtime.shutdown()
        if reopened is not None:
            reopened.Close(0)
        if document is not None:
            document.Close(0)
        if application is not None and owned is not None and owned.is_running():
            application.Quit(0)
        reopened = document = application = None
        gc.collect()
        pythoncom.CoUninitialize()
    assert not bridge.diagnostics["worker_alive"] and bridge.diagnostics["temporary_released"]
    if owned is not None:
        owned.wait(timeout=15)
    assert counts["composes"] == 2 and counts["images"] == 2
    (tmp_path / "qualification.json").write_text(json.dumps({**counts, "live_model_requests": 0,
        "native_reopen_pages": 2, "bridge_released": True, "word_process_released": True}, indent=2))
