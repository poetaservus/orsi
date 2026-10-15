"""Opt-in native Word qualification; test-owned synthetic documents only."""
import gc
import json
import os

import pytest

from app.capabilities.contracts import CapabilityExecutionError
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_word_native import units
from app.security.write_policy import HostWritePolicy
from tests.test_office_mcp_capabilities import runtime_for, prepare, authorize
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import execute
from tests.test_agent_runtime import ScriptedModel


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in live Word desktop gate")
def test_native_word_stdio_preservation_conflicts_restore_save_reopen_and_release(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "winword.exe"}
    application = document = other = table = reopened = None
    owned = None
    documents = []
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20, call_timeout=30)
    model = ScriptedModel([])
    model.mode, model.context_length = "cloud", 131_072
    runtime = runtime_for(bridge, tmp_path, model=model, policy=bridge.resource_policy)
    service = window = None
    diagnostics = {"native_word_gate": False, "forced_fixture_cleanup": False, "provider_requests": 0}
    try:
        try:
            application = win32com.client.DispatchEx("Word.Application")
            application.Visible = True
            document = application.Documents.Add()
            documents.append(document)
            pid = win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1]
            assert pid not in prior
            owned = psutil.Process(pid)
            diagnostics.update(pid=pid, created=owned.create_time())
        except pythoncom.com_error as error:
            pytest.skip("A usable Word session is unavailable (HRESULT " + str(error.hresult) + ")")
        initial = "First \U0001f642 text"
        document.Content.Text = initial + "\rMixed bold and plain\rDuplicate\rDuplicate\r"
        document.Range(0, units(initial)).Font.Name = "Calibri"
        document.Range(0, units(initial)).Font.Size = 12
        document.Range(0, units(initial)).Font.NameBi = "Segoe UI Emoji"
        custom_style = document.Styles.Add("ORSIPhase5Synthetic", 1)
        custom_style.Font.Italic = True
        document.Paragraphs.Item(1).Range.Style = custom_style
        document.Range(0, units(initial)).Font.Name = "Calibri"
        document.Range(0, units(initial)).Font.Size = 12
        document.Range(0, units(initial)).Font.NameBi = "Segoe UI Emoji"
        document.Paragraphs.Item(1).Range.ParagraphFormat.SpaceAfter = 14
        document.Sections.Item(1).Headers.Item(1).Range.Text = "Unrelated synthetic header"
        mixed = document.Paragraphs.Item(2).Range
        mixed_start = int(mixed.Start)
        document.Range(mixed_start + 6, mixed_start + 10).Font.Bold = True
        table = document.Tables.Add(document.Range(int(document.Content.End) - 1, int(document.Content.End) - 1), 2, 2)
        table.Cell(1, 1).Range.Text = "unrelated table"
        table.Cell(2, 2).Range.Text = "preserved"
        table_text = str(table.Range.Text)
        other = application.Documents.Add()
        documents.append(other)
        other.Content.Text = "unrelated focused document"
        bridge.connect()
        found = [d for d in bridge.list_documents() if d["application"] == "word" and d["title"] == str(document.Name)]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        attached = execute(runtime, "attach", {"application": "word", "document": found[0]["document"]}, "attach")
        assert attached.success
        session = attached.output["session"]
        (tmp_path / "test-application").mkdir()
        for name in ("office.word_edit", "office.revert", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "test-application")
        serial = 0

        def read(target, **kwargs):
            nonlocal serial
            serial += 1
            result = execute(runtime, "read", {"session": session, "target": target, **kwargs}, "read" + str(serial))
            assert result.success, result.error
            return result.output

        def patch(page, text):
            return {"session": session, "snapshot": page["snapshot"], "changes": [
                {"target": page["items"][0]["target"], "action": "replace_text", "text": text}]}

        first_target = "text:0:" + str(units(initial))
        first = page = read(first_target, max_chars=2)
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(first, "replacement"), "incomplete")
        text = first["items"][0]["text"]
        while page["cursor"]:
            page = read(first_target, cursor=page["cursor"], max_chars=2)
            assert page["snapshot"] == first["snapshot"] and page["items"][0]["target"] == first["items"][0]["target"]
            text += "".join(item["text"] for item in page["items"])
        assert text == initial
        other.Activate()
        new_text = "Replacement \U0001f642 <&> longer"
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QPlainTextEdit
        from app.conversation.orchestrator import ConversationService
        from app.conversation.store import ConversationStore
        from app.inference.protocol import ModelCapabilityCall, ModelResponse
        from app.state.storage import JsonStore
        from app.ui.main_window import MainWindow
        from tests.test_office_approval_ui import wait_until
        app = QApplication.instance() or QApplication([])
        model.responses.extend([ModelResponse.calls((ModelCapabilityCall(provider_call_id="native-word-edit",
            capability="office.word_edit", arguments=patch(first, new_text)),)), ModelResponse.text("Synthetic Word replacement settled.")])
        service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"),
            agent_runtime=runtime, portable_root=ROOT, allowed_read_roots=(ROOT,))
        window = MainWindow(service, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
        window.show()
        window.input.setPlainText("Replace the selected synthetic Word text.")
        window.submit()
        wait_until(lambda: window._approval_panel is not None or window.thread is None)
        panel = window._approval_panel
        assert panel is not None
        assert "Word body text:" in panel.findChild(QPlainTextEdit, "approvalDetails").toPlainText()
        assert panel.grab().save(str(tmp_path / "native-word-approval.png"))
        QTest.keyClick(panel, Qt.Key.Key_Return)
        wait_until(lambda: window.thread is None and window._approval_panel is None)
        settled = service.store.turns()[-1].settled_calls
        assert len(settled) == 1
        edited = settled[0].result
        window.hide()
        assert edited.success, edited.error
        assert str(document.Range(0, units(new_text)).Text) == new_text
        assert document.Range(0, units(new_text)).Font.Name == "Calibri"
        assert document.Range(0, units(new_text)).Font.Size == 12
        assert document.Paragraphs.Item(1).Range.ParagraphFormat.SpaceAfter == 14
        assert str(document.Paragraphs.Item(1).Range.Style.NameLocal) == "ORSIPhase5Synthetic"
        assert bool(document.Range(0, units(new_text)).Font.Italic)
        assert str(table.Range.Text) == table_text
        assert str(other.Content.Text).startswith("unrelated focused document")
        assert str(application.ActiveDocument.Name) == str(other.Name)
        document.Activate()
        document.Sections.Item(1).Headers.Item(1).Range.Select()
        header_read = execute(runtime, "read", {"session": session, "target": "selection"}, "header-refusal")
        assert not header_read.success and bridge.exposure.ready
        other.Activate()
        after = read("text:0:" + str(units(new_text)))
        restored = execute(runtime, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited.output["recovery"]}, "restore")
        assert restored.success, restored.error
        assert str(document.Range(0, units(initial)).Text) == initial
        assert str(table.Range.Text) == table_text
        # Mixed target refuses; a uniform subrange preserves surrounding runs.
        mixed = document.Paragraphs.Item(2).Range
        mixed_start, mixed_end = int(mixed.Start), int(mixed.End) - 1
        mixed_page = read(f"text:{mixed_start}:{mixed_end}")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(mixed_page, "flattened"), "mixed-refusal")
        sub = read(f"text:{mixed_start + 6}:{mixed_start + 10}")
        mixed_edit = execute(runtime, "word_edit", patch(sub, "strong"), "mixed-subrange")
        assert mixed_edit.success, mixed_edit.error
        assert str(document.Paragraphs.Item(2).Range.Text) == "Mixed strong and plain\r"
        assert bool(document.Range(mixed_start + 6, mixed_start + 12).Font.Bold)
        assert not bool(document.Range(mixed_start, mixed_start + 5).Font.Bold)
        # Both end markers and table text are visible but never writable.
        for target in (f"text:0:{int(document.Paragraphs.Item(1).Range.End)}",
                       f"text:{int(table.Cell(1, 1).Range.Start)}:{int(table.Cell(1, 1).Range.End) - 2}"):
            unsupported = read(target)
            with pytest.raises(CapabilityExecutionError):
                prepare(runtime, "office.word_edit", patch(unsupported, "bad"), "unsupported" + str(serial))
        # An insertion before a duplicate cannot silently retarget the anchor.
        duplicate = document.Paragraphs.Item(4).Range
        duplicate_page = read(f"text:{int(duplicate.Start)}:{int(duplicate.End) - 1}")
        document.Range(0, 0).InsertBefore("prefix ")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(duplicate_page, "retargeted"), "moved-anchor")
        document.Range(0, 7).Delete()
        # Unsupported document states reject before native mutation dispatch.
        fresh = read(first_target)
        document.TrackRevisions = True
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(fresh, "tracked"), "tracked-refusal")
        document.TrackRevisions = False
        bookmark = document.Bookmarks.Add("ORSIPhase5Bookmark", document.Range(0, 1))
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(fresh, "bookmark"), "bookmark-refusal")
        bookmark.Delete()
        field = document.Fields.Add(document.Range(int(document.Content.End) - 1, int(document.Content.End) - 1), 33)
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(fresh, "field"), "field-refusal")
        field.Delete()
        document.Protect(3, True, "")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(fresh, "protected"), "protection-refusal")
        document.Unprotect("")
        header_shape = document.Sections.Item(1).Headers.Item(1).Shapes.AddShape(1, 0, 0, 10, 10)
        readonly = read(first_target)
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", patch(readonly, "drawing"), "drawing-refusal")
        header_shape.Delete()
        # Native formatting changes after approval cannot reach dispatch.
        fresh = read(first_target)
        prepared = prepare(runtime, "office.word_edit", patch(fresh, "stale-format"), "format-conflict")
        authorization = authorize(runtime, prepared)
        document.Range(0, 1).Font.Bold = True
        refused = runtime.executor.execute(prepared, authorization)
        assert not refused.success and bridge.exposure.ready
        document.Range(0, 1).Font.Bold = False
        fresh = read(first_target)
        second = execute(runtime, "word_edit", patch(fresh, "Final text"), "final-edit")
        assert second.success, second.error
        after = read("text:0:10")
        document.Range(0, 5).Text = "Later"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.revert", {"session": session, "snapshot": after["snapshot"], "recovery": second.output["recovery"]}, "later-change")
        assert str(document.Range(0, 10).Text) == "Later text"
        destination = tmp_path / "synthetic.docx"
        occupied = tmp_path / "occupied.docx"
        occupied.write_bytes(b"Synthetic destination must survive")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.save", {"session": session, "path": str(occupied), "overwrite": True}, "existing-destination")
        assert occupied.read_bytes() == b"Synthetic destination must survive"
        saved = execute(runtime, "save", {"session": session, "path": str(destination)}, "save-as")
        assert saved.success and destination.is_file() and bool(document.Saved), saved.error
        # New path remains bound through the host policy and a follow-up edit.
        # Keep the deliberately later-edited first paragraph intact. Read a
        # separate uniform paragraph rather than flattening those manual runs.
        follow_paragraph = document.Paragraphs.Item(3).Range
        after_save = read(f"text:{int(follow_paragraph.Start)}:{int(follow_paragraph.End) - 1}")
        follow = execute(runtime, "word_edit", patch(after_save, "Saved again"), "followup-edit")
        assert follow.success, follow.error
        saved = execute(runtime, "save", {"session": session}, "save")
        assert saved.success and bool(document.Saved)
        runtime.shutdown()
        assert str(document.Name) == "synthetic.docx"
        document.Close(False)
        documents.remove(document)
        document = table = mixed = duplicate = None
        reopened = application.Documents.Open(str(destination))
        documents.append(reopened)
        assert str(reopened.Paragraphs.Item(1).Range.Text) == "Later text\r"
        assert str(reopened.Paragraphs.Item(3).Range.Text) == "Saved again\r"
        assert str(reopened.Tables.Item(1).Range.Text) == table_text
        assert str(reopened.Paragraphs.Item(2).Range.Text) == "Mixed strong and plain\r"
        assert str(reopened.Paragraphs.Item(1).Range.Style.NameLocal) == "ORSIPhase5Synthetic"
        assert str(reopened.Sections.Item(1).Headers.Item(1).Range.Text) == "Unrelated synthetic header\r"
        diagnostics["native_word_gate"] = True
    finally:
        if service is not None:
            service.cancel_current_task()
        if window is not None:
            wait_until(lambda: window.thread is None)
            window.close()
        runtime.shutdown()
        if service is not None:
            service.shutdown()
        if application is not None and owned is not None:
            try:
                collection = application.Documents
                foreign = any(not any(collection.Item(i)._oleobj_.QueryInterface(pythoncom.IID_IUnknown) ==
                    fixture._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for fixture in documents)
                    for i in range(1, int(collection.Count) + 1))
                if foreign:
                    owned = None
                    diagnostics["user_document_preserved"] = True
            except pythoncom.com_error:
                owned = None  # Unproven ownership never permits application cleanup.
        for fixture in documents:
            try:
                fixture.Close(False)
            except pythoncom.com_error:
                pass
        if owned is not None:
            try:
                application.Quit(False)
            except pythoncom.com_error:
                pass
        documents.clear()
        fixture = collection = application = document = other = table = reopened = mixed = duplicate = custom_style = bookmark = field = follow_paragraph = header_shape = None
        gc.collect()
        if owned is not None:
            try:
                owned.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                # Only the exact freshly created fixture PID/creation identity.
                owned.terminate()
                owned.wait(timeout=5)
                diagnostics["forced_fixture_cleanup"] = True
        diagnostics["bridge_released"] = not bridge.diagnostics["worker_alive"]
        diagnostics.update({key: value for key, value in bridge.diagnostics.items() if key.startswith("failure_")})
        (tmp_path / "native-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
        pythoncom.CoUninitialize()
    assert diagnostics["bridge_released"] and not diagnostics["forced_fixture_cleanup"]
