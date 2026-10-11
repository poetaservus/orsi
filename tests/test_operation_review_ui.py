import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.execution.audit import CallLifecycleState
from app.ui.main_window import MainWindow
from tests.test_agent_runtime import build_runtime
from tests.test_operation_review import service_for, uncertain


@pytest.fixture
def ui(tmp_path):
    app = QApplication.instance() or QApplication([])
    runtime, model, capability, journal, _ = build_runtime(tmp_path, [])
    uncertain(journal, tmp_path)
    service = service_for(runtime, model, tmp_path)
    window = MainWindow(service, "test")
    window.show()
    app.processEvents()
    yield app, window, service, journal
    window.close()
    service.shutdown()
    app.processEvents()


def open_review(app, window):
    QTest.mouseClick(window.operation_review_button, Qt.MouseButton.LeftButton)
    app.processEvents()
    return window._operation_review_dialog


def test_visible_review_requires_explicit_confirmation_and_preserves_chat_draft(ui):
    app, window, service, journal = ui
    assert window.operation_review_banner.isVisible()
    assert window.input.isEnabled() and window.send.isEnabled()
    window.input.setPlainText("Unsent draft")
    dialog = open_review(app, window)
    assert dialog.isVisible() and dialog.details.isReadOnly()
    assert "test.journal" in dialog.details.toPlainText()
    assert "private" not in dialog.details.toPlainText()
    assert not dialog.acknowledge.isEnabled()
    dialog.accept()
    assert dialog.isVisible() and journal.review_required
    dialog.confirm.setChecked(True)
    QTest.mouseClick(dialog.acknowledge, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert window._operation_review_dialog is None
    assert not window.operation_review_banner.isVisible()
    assert window.input.toPlainText() == "Unsent draft"
    assert journal.get("interrupted-call").state == CallLifecycleState.INTERRUPTED_UNKNOWN_OUTCOME
    assert not journal.review_required
    assert window.chat._messages == []


def test_escape_and_new_chat_do_not_acknowledge_uncertain_operations(ui):
    app, window, service, journal = ui
    dialog = open_review(app, window)
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    app.processEvents()
    assert window._operation_review_dialog is None
    assert window.operation_review_banner.isVisible() and journal.review_required
    window.create_new_session()
    app.processEvents()
    assert window.operation_review_banner.isVisible() and journal.review_required


def test_failed_acknowledgement_keeps_review_open_and_durable_state_unchanged(ui, monkeypatch):
    import app.execution.audit as audit
    app, window, service, journal = ui
    before = journal.path.read_bytes()
    dialog = open_review(app, window)
    def fail(*args):
        raise OSError("private storage path")
    monkeypatch.setattr(audit, "_atomic_replace", fail)
    dialog.confirm.setChecked(True)
    QTest.mouseClick(dialog.acknowledge, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert dialog.isVisible() and journal.review_required
    assert "could not be saved" in dialog.notice.text()
    assert "private" not in dialog.notice.text()
    assert journal.path.read_bytes() == before


def test_persistence_failure_explains_restart_and_cannot_be_acknowledged(ui):
    app, window, service, journal = ui
    service.agent_runtime.executor._persistence_failed = True
    window._refresh_operation_review()
    assert "Restart O.R.S.I" in window.operation_review_label.text()
    dialog = open_review(app, window)
    assert not dialog.confirm.isEnabled() and not dialog.acknowledge.isEnabled()
    dialog.accept()
    assert dialog.isVisible() and journal.review_required


def test_review_controls_pause_during_work_and_return_afterwards(ui):
    app, window, service, journal = ui
    window._set_busy(True)
    assert not window.operation_review_button.isEnabled()
    window._set_busy(False)
    assert window.operation_review_button.isEnabled()
    window._settings_worker_busy(True)
    assert not window.operation_review_button.isEnabled()
    window._settings_worker_busy(False)
    assert window.operation_review_button.isEnabled()


def test_closing_window_closes_review_without_acknowledging(ui):
    app, window, service, journal = ui
    dialog = open_review(app, window)
    cleared = []
    dialog.finished.connect(lambda _: cleared.append(dialog.details.toPlainText()))
    window.close()
    app.processEvents()
    assert window._operation_review_dialog is None and cleared == [""]
    assert journal.review_required


def test_transcript_scroll_and_composer_remain_usable_with_review_banner(ui):
    app, window, service, journal = ui
    window.resize(960, 700)
    for _ in range(16):
        window.chat.add_message("Agent", "Synthetic earlier reply. " * 20)
    window._intro_active = False
    window._position_overlays()
    app.processEvents()
    scrollbar = window.chat.verticalScrollBar()
    for _ in range(100):
        if scrollbar.maximum() > 0:
            break
        QTest.qWait(10)
    assert scrollbar.maximum() > 0
    scrollbar.setValue(0)
    scrollbar.setFocus()
    QTest.keyClick(scrollbar, Qt.Key.Key_PageDown)
    app.processEvents()
    assert scrollbar.value() > 0
    assert window.composer.geometry().bottom() == window._content.height() - 43
    assert window.send.isEnabled() and window.operation_review_button.isEnabled()
