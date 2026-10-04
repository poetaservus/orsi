from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit

from app.ui.main_window import MainWindow


class ApprovalService:
    def __init__(self):
        self.statuses = {"one": "pending", "two": "pending"}
        self.decisions = []

    def estimated_context_tokens(self):
        return 0

    def approval_status(self, approval_id):
        return self.statuses.get(approval_id)

    def resolve_approval(self, approval_id, approved):
        if self.approval_status(approval_id) == "pending":
            self.decisions.append((approval_id, approved))
            self.statuses[approval_id] = "approved" if approved else "denied"


def record(**changes):
    values = dict(approval_id="one", capability="filesystem.write_text",
                  resource="C:/workspace/example.txt", approval_preview="Exact file content\n")
    return SimpleNamespace(**(values | changes))


@pytest.fixture
def ui():
    app = QApplication.instance() or QApplication([])
    service = ApprovalService()
    window = MainWindow(service, "test")
    window.show()
    window.activateWindow()
    app.processEvents()
    yield app, window, service
    window.close()
    app.processEvents()


@pytest.mark.parametrize("key,approved", [(Qt.Key.Key_Return, True),
                                         (Qt.Key.Key_Enter, True), (Qt.Key.Key_Escape, False)])
def test_keyboard_review_is_inline_preserves_draft_and_resolves_once(ui, key, approved):
    app, window, service = ui
    window.input.setPlainText("Unsent draft")
    window._show_approval(record())
    app.processEvents()
    panel = window._approval_panel
    assert panel.parentWidget() is window.composer and not panel.isWindow()
    assert not window.findChildren(QDialog)
    assert window._composer_stack.currentWidget() is panel
    assert window.composer.height() == 280
    preview = panel.findChild(QPlainTextEdit, "approvalContent")
    assert preview.toPlainText() == "Exact file content\n" and preview.isReadOnly()
    preview.setFocus()
    app.processEvents()
    QTest.keyClick(preview, key)
    app.processEvents()
    assert service.decisions == [("one", approved)]
    assert window._approval_panel is None and window.composer.height() == 54
    assert window.input.toPlainText() == "Unsent draft"
    assert window.input.hasFocus()
    assert window.chat._messages == []


@pytest.mark.parametrize("changes", [dict(capability="unknown"), dict(resource=None),
                                     dict(approval_preview=None)])
def test_malformed_operation_is_denied_without_opening_review(ui, changes):
    _, window, service = ui
    window._show_approval(record(**changes))
    assert window._approval_panel is None
    assert service.decisions == [("one", False)]


def test_second_request_cannot_replace_the_operation_being_reviewed(ui):
    _, window, service = ui
    window._show_approval(record())
    original = window._approval_panel
    window._show_approval(record(approval_id="two", resource="C:/different.txt"))
    assert window._approval_panel is original
    assert service.decisions == [("two", False)]
    original.finish(True)
    original.finish(True)
    assert service.decisions == [("two", False), ("one", True)]


def test_allowlisted_launch_shows_executable_and_file_in_inline_review(ui):
    app, window, service = ui
    details = "Launch Blender\nExecutable: C:/Blender/blender.exe\nOpen file: C:/workspace/scene.blend"
    window._show_approval(record(capability="application.launch",
                                resource="C:/Blender/blender.exe", approval_preview=details))
    app.processEvents()
    panel = window._approval_panel
    assert panel.findChild(QPlainTextEdit, "approvalDetails").toPlainText() == details
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    app.processEvents()
    assert service.decisions == [("one", False)] and window._approval_panel is None


def test_cancellation_and_stale_approval_restore_the_composer(ui):
    app, window, service = ui
    window._show_approval(record())
    service.statuses["one"] = "cancelled"
    QTest.qWait(150)
    app.processEvents()
    assert window._approval_panel is None and not service.decisions
    window._show_approval(record())
    assert window._approval_panel is None


@pytest.mark.parametrize("full_local", [False, True])
def test_app_startup_uses_configured_access_without_warning(monkeypatch, tmp_path, full_local):
    import app.main as main
    import app.ui.main_window as ui_module
    import PySide6.QtWidgets as widgets

    config = SimpleNamespace(full_local_read_enabled=full_local)
    captured = {}
    monkeypatch.setattr(main.sys, "argv", ["orsi"])
    monkeypatch.setattr(main, "PATHS", SimpleNamespace(state=tmp_path, ensure_directories=lambda: None))
    monkeypatch.setattr(main, "configure_logging", lambda path: None)
    monkeypatch.setattr(main, "load_agent_feature_config", lambda: config)
    monkeypatch.setattr(widgets.QMessageBox, "question", lambda *args: pytest.fail("Startup warning"))
    monkeypatch.setattr(widgets, "QApplication", lambda args: SimpleNamespace(
        aboutToQuit=SimpleNamespace(connect=lambda callback: None), exec=lambda: 0))
    monkeypatch.setattr(ui_module, "MainWindow", lambda *args: SimpleNamespace(show=lambda: None))

    def build(**kwargs):
        captured.update(kwargs)
        return None, {"hostname": "test"}, None, None

    monkeypatch.setattr(main, "build_application", build)
    assert main.main() == 0
    assert captured == dict(agent_config_override=config, full_local_read_acknowledged=full_local)
