"""Essential native Word actions through actual UI, stdio, recovery and persistence."""
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


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in synthetic native Word actions")
def test_native_word_insert_style_table_ui_recovery_and_save_reopen(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    from PySide6.QtWidgets import QApplication, QPlainTextEdit
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.protocol import ModelCapabilityCall, ModelResponse
    from app.state.storage import JsonStore
    from app.ui.main_window import MainWindow
    from tests.test_office_approval_ui import wait_until

    pythoncom.CoInitializeEx(2)
    prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "winword.exe"}
    application = document = other = table = reopened = window = service = owned = None
    documents = []
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20, call_timeout=30)
    model = ScriptedModel([])
    model.mode, model.context_length = "cloud", 131_072
    runtime = runtime_for(bridge, tmp_path, model=model, policy=bridge.resource_policy)
    diagnostics = {"native_word_actions": False, "provider_requests": 0, "forced_fixture_cleanup": False}
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
            pytest.skip("A usable native Word session is unavailable (HRESULT " + str(error.hresult) + ")")
        document.Content.Text = "Anchor text\rMixed bold and plain\rUnrelated body\r"
        mixed = document.Paragraphs.Item(2).Range
        source_style = document.Styles.Add("ORSIWordActionsSource", 1)
        source_style.Font.Italic = True
        mixed.Style = source_style
        document.Range(int(mixed.Start) + 6, int(mixed.Start) + 10).Font.Bold = True
        mixed.ParagraphFormat.SpaceAfter = 14
        document.Sections.Item(1).Headers.Item(1).Range.Text = "Unrelated header"
        table = document.Tables.Add(document.Range(document.Content.End - 1, document.Content.End - 1), 2, 2)
        table.AllowAutoFit = False
        for row, col, value in [(1, 1, "One"), (1, 2, "Two"), (2, 1, "Three")]:
            table.Cell(row, col).Range.Text = value
        table.Cell(1, 1).Range.Font.Bold = True
        unchanged_cell = table.Cell(2, 1).Range
        document.Range(int(unchanged_cell.Start), int(unchanged_cell.Start) + 2).Font.Italic = True
        other = application.Documents.Add()
        documents.append(other)
        other.Content.Text = "Foreign focused document"
        bridge.connect()
        found = [d for d in bridge.list_documents() if d["application"] == "word" and d["title"] == str(document.Name)]
        assert len(found) == 1
        bridge.select_document(found[0]["document"])
        session = execute(runtime, "attach", {"application": "word", "document": found[0]["document"]}, "attach").output["session"]
        (tmp_path / "test-app").mkdir()
        for name in ("office.word_edit", "office.revert", "office.save"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "test-app")
        app = QApplication.instance() or QApplication([])
        service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"), agent_runtime=runtime,
            portable_root=ROOT, allowed_read_roots=(ROOT,))
        window = MainWindow(service, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
        serial = 0

        def read(target, **kwargs):
            nonlocal serial
            serial += 1
            result = execute(runtime, "read", {"session": session, "target": target, **kwargs}, "read" + str(serial))
            assert result.success, result.error
            return result.output

        def args(view, action, **payload):
            return {"session": session, "snapshot": view["snapshot"], "changes": [
                {"target": view["items"][0]["target"], "action": action, **payload}]}

        def approve(view, action, **payload):
            nonlocal serial
            serial += 1
            model.responses.extend([ModelResponse.calls((ModelCapabilityCall(provider_call_id="native-action-" + str(serial),
                capability="office.word_edit", arguments=args(view, action, **payload)),)), ModelResponse.text("Synthetic Word action settled.")])
            window.show()
            window.input.setPlainText("Perform the bounded synthetic Word action.")
            window.submit()
            wait_until(lambda: window._approval_panel is not None or window.thread is None, timeout=20)
            panel = window._approval_panel
            assert panel is not None
            assert "Word" in panel.findChild(QPlainTextEdit, "approvalDetails").toPlainText()
            from tests.test_inline_approvals import settle_composer
            settle_composer(window)
            window.activateWindow()
            preview = panel.findChild(QPlainTextEdit, "approvalDetails")
            preview.setFocus()
            app.processEvents()
            # The separate saved/unsaved ON/deny/OFF matrix exercises real Qt
            # key events for every action. Invoke the displayed review's own
            # decision handler here so this COM gate does not depend on the
            # offscreen platform's focus after repeated native Word calls.
            panel.finish(True)
            wait_until(lambda: window._approval_panel is None, timeout=3)
            wait_until(lambda: window.thread is None and window._approval_panel is None, timeout=30)
            result = service.store.turns()[-1].settled_calls[0].result
            assert result.success, result.error
            return result.output

        def revert(view, recovery):
            nonlocal serial
            serial += 1
            result = execute(runtime, "revert", {"session": session, "snapshot": view["snapshot"], "recovery": recovery}, "restore" + str(serial))
            assert result.success, result.error
            return result.output

        styles = json.loads(read("styles")["items"][0]["text"])
        assert {v["style"] for v in styles} == {"Normal", "Heading 1", "Heading 2", "Title", "Subtitle"}
        discovery = read("tables")
        assert json.loads(discovery["items"][0]["text"])["read_target"] == "table:1"
        original_table = str(table.Range.Text)
        initial = read("text:0:11")
        other.Activate()
        inserted = approve(initial, "insert_after", text=" after <&> \U0001f642")
        expected_text = "Anchor text after <&> \U0001f642"
        assert str(document.Paragraphs.Item(1).Range.Text) == expected_text + "\r"
        assert str(table.Range.Text) == original_table and str(application.ActiveDocument.Name) == str(other.Name)
        revert(read("text:0:" + str(units(expected_text))), inserted["recovery"])
        assert str(document.Paragraphs.Item(1).Range.Text) == "Anchor text\r"
        mixed = document.Paragraphs.Item(2).Range
        target = f"text:{int(mixed.Start)}:{int(mixed.End) - 1}"
        styled = approve(read(target), "apply_style", style="Heading 1")
        assert str(document.Paragraphs.Item(2).Range.Style.NameLocal) == str(document.Styles.Item(-2).NameLocal)
        assert str(document.Paragraphs.Item(2).Range.Text) == "Mixed bold and plain\r"
        assert document.Paragraphs.Item(2).Range.ParagraphFormat.SpaceAfter == 14
        revert(read(target), styled["recovery"])
        assert str(document.Paragraphs.Item(2).Range.Style.NameLocal) == "ORSIWordActionsSource"
        assert bool(document.Range(int(mixed.Start) + 6, int(mixed.Start) + 10).Font.Bold)
        # Qualify every discovered target style, including the native default
        # style transition, on the same mixed/directly formatted paragraph.
        for label, number in [("Heading 2", -3), ("Title", -63), ("Subtitle", -75), ("Normal", -1)]:
            style_view = read(target)
            changed_style = execute(runtime, "word_edit", args(style_view, "apply_style", style=label), "style-" + str(-number))
            assert changed_style.success, changed_style.error
            assert str(document.Paragraphs.Item(2).Range.Style.NameLocal) == str(document.Styles.Item(number).NameLocal)
            assert document.Paragraphs.Item(2).Range.ParagraphFormat.SpaceAfter == 14
            revert(read(target), changed_style.output["recovery"])
            assert str(document.Paragraphs.Item(2).Range.Style.NameLocal) == "ORSIWordActionsSource"
        first = view = read("table:1", max_chars=37)
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", args(first, "edit_table", cells=[["bad", "Two"], ["Three", ""]]), "incomplete-table")
        while view["cursor"]:
            view = read("table:1", cursor=view["cursor"], max_chars=37)
            assert view["snapshot"] == first["snapshot"]
        matrix = [["Longer <&> \U0001f642", "Two"], ["Three", "New empty-cell text"]]
        edited = approve(first, "edit_table", cells=matrix)
        assert edited["affected_items"] == 2
        assert str(table.Cell(1, 1).Range.Text) == matrix[0][0] + "\r\x07"
        assert bool(table.Cell(1, 1).Range.Font.Bold)
        assert table.Rows.Count == table.Columns.Count == 2 and not table.AllowAutoFit
        after = read("table:1")
        table.Cell(1, 2).Range.Text = "Later user cell"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]}, "later-table-change")
        table.Cell(1, 2).Range.Text = "Two"
        revert(read("table:1"), edited["recovery"])
        assert str(table.Range.Text) == original_table
        # A new table at the same position/text cannot inherit old range authority.
        document.Range(document.Content.End - 1, document.Content.End - 1).InsertBefore("\r")
        second = document.Tables.Add(document.Range(document.Content.End - 1, document.Content.End - 1), 2, 2)
        second.AllowAutoFit = False
        for row in range(1, 3):
            for col in range(1, 3):
                second.Cell(row, col).Range.Text = "Clone"
        assert int(document.Tables.Count) == 2
        stale = read("table:2")
        start = int(second.Range.Start)
        second.Cell(1, 1).Merge(second.Cell(1, 2))
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", args(stale, "edit_table", cells=[["bad", "Clone"], ["Clone", "Clone"]]), "merged-table-refusal")
        second.Delete()
        clone = document.Tables.Add(document.Range(start, start), 2, 2)
        clone.AllowAutoFit = False
        for row in range(1, 3):
            for col in range(1, 3):
                clone.Cell(row, col).Range.Text = "Clone"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.word_edit", args(stale, "edit_table", cells=[["retargeted", "Clone"], ["Clone", "Clone"]]), "table-identity-refusal")
        clone.Delete()
        destination = tmp_path / "word-actions.docx"
        assert execute(runtime, "save", {"session": session, "path": str(destination)}, "save-as").success
        persisted = approve(read("table:1"), "edit_table", cells=matrix)
        assert execute(runtime, "save", {"session": session}, "save").success
        runtime.shutdown()
        window.close()
        document.Close(False)
        documents.remove(document)
        document = table = mixed = second = clone = None
        reopened = application.Documents.Open(str(destination))
        documents.append(reopened)
        assert str(reopened.Tables.Item(1).Cell(1, 1).Range.Text) == matrix[0][0] + "\r\x07"
        assert str(reopened.Tables.Item(1).Cell(2, 2).Range.Text) == matrix[1][1] + "\r\x07"
        assert str(reopened.Sections.Item(1).Headers.Item(1).Range.Text) == "Unrelated header\r"
        assert str(reopened.Paragraphs.Item(3).Range.Text) == "Unrelated body\r"
        diagnostics["native_word_actions"] = True
    finally:
        if service is not None:
            service.cancel_current_task()
        if window is not None:
            wait_until(lambda: window.thread is None, timeout=30)
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
                owned = None
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
        fixture = collection = application = document = other = table = reopened = mixed = second = clone = source_style = unchanged_cell = None
        gc.collect()
        if owned is not None:
            try:
                owned.wait(10)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                owned.terminate()
                owned.wait(5)
                diagnostics["forced_fixture_cleanup"] = True
        diagnostics.update(bridge_released=not bridge.diagnostics["worker_alive"])
        diagnostics.update({key: value for key, value in bridge.diagnostics.items() if key.startswith("failure_")})
        (tmp_path / "native-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
        pythoncom.CoUninitialize()
    assert diagnostics["bridge_released"] and not diagnostics["forced_fixture_cleanup"]
