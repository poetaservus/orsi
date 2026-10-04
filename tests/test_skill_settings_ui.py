"""Settings-only import with actual worker/installer handoff and isolated storage."""
import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from app.ui.main_window import MainWindow
from app.ui.skill_settings import SkillSettingsDialog
from app.runtime.skills import import_source
from tests.test_skill_activation import make_service, skill_payload
from tests.test_skill_import_source import DATA, RAW


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows safe installer")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_worker(dialog):
    for _ in range(400):
        QApplication.processEvents()
        if dialog.thread is None:
            return
        QTest.qWait(10)
    pytest.fail("Skill Settings worker did not finish")


@pytest.fixture
def ui(tmp_path, app):
    service, model = make_service(tmp_path)
    window = MainWindow(service, "TEST")
    window.show()
    dialog = SkillSettingsDialog(service, window)
    dialog.catalog_changed.connect(window._skills_changed)
    dialog.show()
    app.processEvents()
    yield window, dialog, service, model
    wait_worker(dialog)
    dialog.close()
    window.close()


def test_settings_is_the_only_management_entry_and_busy_state_preserves_draft(ui):
    window, dialog, service, model = ui
    assert window.skills_button.parentWidget() is window.settings_panel
    assert not window.composer.findChildren(QPushButton, "manageSkillsButton")
    window.input.setPlainText("Keep draft")
    window._set_busy(True)
    assert not window.skills_button.isEnabled()
    window._set_busy(False)
    assert window.skills_button.isEnabled() and window.input.toPlainText() == "Keep draft"
    opened = []
    def close_modal():
        manager = QApplication.activeModalWidget()
        opened.append(isinstance(manager, SkillSettingsDialog))
        manager.close_button.click()
    QTimer.singleShot(0, close_modal)
    window.skills_button.click()
    assert opened == [True]
    assert not model.requests


def test_enter_previews_local_file_then_install_refreshes_picker_without_restart(ui, tmp_path):
    window, dialog, service, model = ui
    source = tmp_path / "any-name.md"
    source.write_bytes(DATA)
    dialog.source.setText(str(source))
    dialog.source.setFocus()
    QTest.keyClick(dialog.source, Qt.Key.Key_Return)
    wait_worker(dialog)
    assert dialog.prepared.definition.name == "imported"
    assert service.skill_registry.get("imported") is None and dialog.install_button.isEnabled()
    assert not model.requests
    dialog.install_button.click()
    wait_worker(dialog)
    assert dialog.installed.count() == 3 and service.skill_registry.get("imported") is not None
    dialog.close_button.click()
    window.input.setFocus()
    QTest.keyClicks(window.input, "/skill imported")
    QApplication.processEvents()
    assert window.skill_picker.items.count() == 1
    QTest.keyClick(window.input, Qt.Key.Key_Return)
    QTest.keyClicks(window.input, "Prompt")
    QTest.keyClick(window.input, Qt.Key.Key_Return)
    for _ in range(200):
        QApplication.processEvents()
        if window.thread is None:
            break
        QTest.qWait(10)
    assert window.thread is None and skill_payload(model.requests[-1][0])["name"] == "imported"


def test_github_link_previews_and_changed_input_invalidates_install(ui, monkeypatch):
    _, dialog, service, model = ui
    downloaded = []
    monkeypatch.setattr(import_source, "_download", lambda url, limit: downloaded.append(url) or DATA)
    dialog.source.setText("https://github.com/owner/repo/blob/main/skills/imported/SKILL.md?plain=1")
    dialog.preview_button.click()
    wait_worker(dialog)
    assert downloaded == [RAW] and dialog.preview_name.text() == "imported"
    assert dialog.preview_name.textFormat() == Qt.TextFormat.PlainText
    dialog.source.setText("different source")
    assert dialog.prepared is None and not dialog.install_button.isEnabled()
    assert service.skill_registry.get("imported") is None and not model.requests


def test_drop_one_markdown_file_into_settings_source(ui, tmp_path):
    _, dialog, _, _ = ui
    source = tmp_path / "SKILL.md"
    source.write_bytes(DATA)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    event = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dialog.source.dropEvent(event)
    assert Path(dialog.source.text()) == source and event.isAccepted()
    dialog.preview_button.click()
    wait_worker(dialog)
    assert dialog.prepared.definition.name == "imported"


def test_remove_confirmation_keeps_other_skills_and_clears_matching_draft_chip(ui, monkeypatch):
    window, dialog, service, model = ui
    window.input.setPlainText("/skill oth")
    window.input.moveCursor(window.input.textCursor().MoveOperation.End)
    window.skill_picker._choose(window.skill_picker.items.item(0))
    assert window.skill_picker.selected_name == "other"
    dialog.installed.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    dialog.remove_button.click()
    assert service.skill_registry.get("other") is not None
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    dialog.remove_button.click()
    wait_worker(dialog)
    assert service.skill_registry.get("other") is None
    assert service.skill_registry.get("style") is not None and window.skill_picker.selected_name is None
    assert not model.requests


def test_busy_preview_cannot_close_or_install_and_failure_recovers(ui, monkeypatch):
    _, dialog, service, model = ui
    release = Event()
    def slow(url, limit):
        assert release.wait(5)
        raise SkillImportError("Synthetic connection failure")
    from app.runtime.skills.import_source import SkillImportError
    monkeypatch.setattr(import_source, "_download", slow)
    dialog.source.setText(RAW)
    dialog.preview_button.click()
    try:
        assert dialog.thread is not None and not dialog.close_button.isEnabled()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        dialog.close()
        assert dialog.isVisible() and not dialog.install_button.isEnabled()
    finally:
        release.set()
        wait_worker(dialog)
    assert dialog.thread is None and "Synthetic connection failure" in dialog.status.text()
    assert dialog.source.isEnabled() and dialog.close_button.isEnabled()
    assert service.skill_registry.get("imported") is None and not model.requests


def test_conflicting_install_releases_thread_without_replacing_existing_skill(ui, tmp_path):
    _, dialog, service, model = ui
    source = tmp_path / "SKILL.md"
    source.write_bytes(DATA.replace(b"name: imported", b"name: style"))
    original = service.skill_registry.get("style")
    dialog.source.setText(str(source))
    dialog.preview_button.click()
    wait_worker(dialog)
    dialog.install_button.click()
    wait_worker(dialog)
    assert "different content" in dialog.status.text()
    assert dialog.close_button.isEnabled() and service.skill_registry.get("style") == original
    assert not model.requests
