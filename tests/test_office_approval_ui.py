"""Office mutations must reach the actual composer review before dispatch."""
import os
from pathlib import Path
import shutil
import sys
from time import monotonic, sleep

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityContext
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_discovery import OfficeDiscovery, OfficeInstallation
from app.mcp.stdio_transport import OwnedStdioTransport
from app.runtime.cancellation import CancellationToken
from app.security.host_access import HostAccessPolicy
from app.security.permissions import ApprovalStatus, prepare_capability_call
from app.settings.agent import AgentFeatureConfig
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from tests.test_agent_runtime import ScriptedModel
from tests.test_inline_approvals import ui, record
from tests.test_office_mcp_capabilities import authorize
from tests.test_office_mcp_connection import ROOT


@pytest.mark.parametrize("name", ["office.excel_edit", "office.word_edit", "office.word_compose", "office.revert", "office.save"])
@pytest.mark.parametrize("saved", [False, True])
def test_reviewed_office_actions_display_document_details_without_auto_denial(ui, name, saved):
    app, window, service = ui
    path = "C:/Users/fixture/Desktop/numbers.xlsx" if saved else None
    preview = "Synthetic workbook\nEdit 2 Excel cells: Sheet1!A1:A2"
    window._show_approval(record(capability=name, resource=path, approval_preview=preview))
    app.processEvents()
    panel = window._approval_panel
    assert panel is not None and service.decisions == []
    details = panel.findChild(QPlainTextEdit, "approvalDetails")
    assert details.isReadOnly() and details.toPlainText() == preview
    shown_path = panel.findChild(QPlainTextEdit, "approvalPath")
    assert (shown_path.toPlainText() if shown_path else None) == path
    panel.reject()
    assert service.decisions == [("one", False)]


@pytest.mark.parametrize("name", ["office.powerpoint_edit"])
def test_unimplemented_office_writes_are_still_denied(ui, name):
    _, window, service = ui
    window._show_approval(record(capability=name))
    assert window._approval_panel is None and service.decisions == [("one", False)]


def test_unsaved_office_review_requires_a_nonempty_operation_preview(ui):
    _, window, service = ui
    window._show_approval(record(capability="office.excel_edit", resource=None, approval_preview=""))
    assert window._approval_panel is None and service.decisions == [("one", False)]


def wait_until(condition, timeout=10):
    deadline = monotonic() + timeout
    while not condition():
        QApplication.processEvents()
        assert monotonic() < deadline, "The Office approval workflow did not settle."
        sleep(0.01)
    QApplication.processEvents()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP and actual Qt approval workflow")
@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("action", ["approve", "deny", "off"])
@pytest.mark.parametrize("kind", ["excel", "word", "word_insert", "word_style", "word_table"])
def test_window_conversation_mcp_edit_obeys_actual_review_and_exact_authority(tmp_path, saved, action, kind):
    variant = kind
    kind = kind.split("_", 1)[0]
    app = QApplication.instance() or QApplication([])
    portable = tmp_path / "application"
    (portable / "config").mkdir(parents=True)
    shutil.copyfile(ROOT / "config/office_mcp_v1.json", portable / "config/office_mcp_v1.json")
    model = ScriptedModel([])
    model.mode, model.context_length = "cloud", 131_072
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    bridge = OfficeConnection(portable, backend=lambda: model.mode,
        discovery=OfficeDiscovery(lambda: (OfficeInstallation(kind, "fixture", None),)),
        _transport_factory=lambda: OwnedStdioTransport(
            [sys.executable, "-m", "tests.fixtures.office_" + kind + "_server"], root=ROOT))
    runtime = build_agent_runtime(model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True, full_local_read_enabled=True,
                                  conversation_context_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy,
        office_connection=bridge, office_resource_policy=bridge.resource_policy)
    service = window = None

    def invoke(name, arguments, call_id):
        context = CapabilityContext(call_id=call_id, session_id="fixture", turn_id="setup",
            portable_root=portable, allowed_read_roots=policy.permission_roots(),
            host_access_policy=policy, cancellation=CancellationToken())
        prepared = prepare_capability_call(runtime.registry.resolve(name), arguments, context)
        runtime.executor.journal.record_prepared(prepared)
        result = runtime.executor.execute(prepared, authorize(runtime, prepared))
        assert result.success
        return result.output

    try:
        bridge.connect()
        target = tmp_path / ("numbers.xlsx" if kind == "excel" else "synthetic.docx")
        if saved:
            target.write_bytes(b"Synthetic workbook file; live edits are not saves.")
            bridge.control("fixture-document", {"path": str(target)})
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = invoke("office.attach", {"application": kind, "document": document["document"]}, "attach")["session"]
        read_target = "Sheet1!A1:A2" if kind == "excel" else "table:1" if variant == "word_table" else "document"
        page = invoke("office.read", {"session": session, "target": read_target}, "read")
        snapshot = page["snapshot"]
        changes = ([{"sheet": "Sheet1", "range": "A1:A2", "values": [[9], [10]]}] if kind == "excel" else
                   [{"target": page["items"][0]["target"], "action": "replace_text", "text": "replacement"}])
        if variant.startswith("word_"):
            from tests.test_office_word_actions import PAYLOADS
            word_action = {"word_insert": "insert_after", "word_style": "apply_style", "word_table": "edit_table"}[variant]
            changes = [{"target": page["items"][0]["target"], "action": word_action, **PAYLOADS[word_action]}]
        model.responses.extend([ModelResponse.calls((ModelCapabilityCall(provider_call_id="edit-cells",
            capability="office." + kind + "_edit", arguments={"session": session, "snapshot": snapshot,
                "changes": changes}),)),
            ModelResponse.text("The synthetic edit is settled.")])
        service = ConversationService(model, ConversationStore(portable / "chat.json"),
            agent_runtime=runtime, portable_root=portable, host_access_policy=policy,
            allowed_read_roots=policy.permission_roots())
        window = MainWindow(service, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
        reviews = []
        window.approval_requested.connect(reviews.append)
        window.show()
        window.activateWindow()
        app.processEvents()
        if action == "off":
            window.tool_approval_toggle.setChecked(False)
        window.input.setPlainText("Update the two selected Excel cells.")
        window.submit()
        if action != "off":
            wait_until(lambda: window._approval_panel is not None or window.thread is None)
            panel = window._approval_panel
            assert panel is not None, "The edit was rejected without presenting its approval."
            details = panel.findChild(QPlainTextEdit, "approvalDetails")
            assert document["title"] in details.toPlainText()
            assert ("Sheet1!A1:A2" if kind == "excel" else "Word body text:" if variant == "word" else
                    "Word body text" if variant == "word_insert" else "Word paragraph style" if variant == "word_style" else "Word table") in details.toPlainText()
            assert bridge.diagnostics["tool_calls"] == 2
            shown_path = panel.findChild(QPlainTextEdit, "approvalPath")
            assert (shown_path.toPlainText() if shown_path else None) == (str(target) if saved else None)
            if saved and action == "approve":
                assert panel.grab().save(str(tmp_path / "office-approval-panel.png"))
            panel.setFocus()
            app.processEvents()
            QTest.keyClick(panel, Qt.Key.Key_Return if action == "approve" else Qt.Key.Key_Escape)
        wait_until(lambda: window.thread is None and window._approval_panel is None)
        assert len(reviews) == int(action != "off")
        records = runtime.approval_manager.records
        assert len(records) == 1 and records[0].status == (
            ApprovalStatus.DENIED if action == "deny" else ApprovalStatus.CONSUMED)
        settled = service.store.turns()[-1].settled_calls
        assert len(settled) == 1 and settled[0].result.success == (action != "deny")
        assert bridge.diagnostics["tool_calls"] == (2 if action == "deny" else 3)
        after = invoke("office.read", {"session": session, "target": read_target}, "after")
        if kind == "excel":
            assert [item["values"][0][0] for item in after["items"]] == ([None, None] if action == "deny" else [9, 10])
        elif variant == "word":
            assert after["items"][0]["text"] == ("alpha\U0001f642 beta" if action == "deny" else "replacement")
        elif variant == "word_insert":
            assert after["items"][0]["text"] == "alpha\U0001f642 beta" + ("" if action == "deny" else " after \U0001f642")
        elif variant == "word_table":
            import json
            cells = json.loads(after["items"][0]["text"])["cells"]
            assert cells[0][0] == ("One" if action == "deny" else "Longer <&>")
        if saved:
            assert target.read_bytes() == b"Synthetic workbook file; live edits are not saves."
    finally:
        if service is not None:
            service.cancel_current_task()
        if window is not None:
            wait_until(lambda: window.thread is None)
            window.close()
        if service is not None:
            service.shutdown()
        else:
            runtime.shutdown()
        app.processEvents()
    assert not bridge.diagnostics["worker_alive"]
