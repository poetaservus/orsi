import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QTimer, QUrl, Qt
from PySide6.QtGui import QImage, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

from app.conversation.attachment_processing import AttachmentProcessor
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.ui.attachments import AttachmentPreparationWorker
from app.ui.main_window import MainWindow


class Recorder(InferenceEngine):
    def __init__(self, mode, enabled):
        self.mode = mode
        self.supports_attachment_inputs = enabled
        self.requests = []

    def respond(self, messages):
        self.requests.append(messages)
        return "Reply"

    def respond_with_attachments(self, messages, *, attachment_store):
        self.requests.append(messages)
        return "Attachment reply"

    def count_attachment_message_tokens(self, messages):
        return 500


def wait_for(predicate, timeout=10):
    deadline = monotonic() + timeout
    while not predicate():
        assert monotonic() < deadline, "GUI worker did not settle"
        QApplication.processEvents()
        # QTest.qWait can hold the Python GIL while pumping Qt, starving the
        # Python preparation worker. The real QApplication loop releases it.
        sleep(0.01)
    QApplication.processEvents()


@pytest.fixture
def windows(tmp_path):
    app = QApplication.instance() or QApplication([])
    values = []
    def make(mode="local", enabled=False):
        root = tmp_path / str(len(values))
        engine = Recorder(mode, enabled)
        service = ConversationService(engine, ConversationStore(root / "chat.json"))
        inference = SimpleNamespace(mode=mode, available_modes=("local", "cloud"), context_length=8192,
            cloud_has_api_key=True, cloud_provider_name="Cloud", consume_notice=lambda: None,
            close=lambda: None)
        def set_mode(mode):
            inference.mode = engine.mode = mode
        inference.set_mode = set_mode
        window = MainWindow(service, "test", inference=inference)
        window.resize(1280, 800)
        window.show()
        QApplication.processEvents()
        values.append(window)
        return window
    yield make
    for window in values:
        window.close()
        wait_for(lambda: not window.attachment_tray.is_processing and window.thread is None)
        window.close()
    QApplication.processEvents()


def text_file(tmp_path, name="file.txt", content="file contents"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_plus_opens_single_file_picker_in_local_and_prepares_draft(windows, tmp_path, monkeypatch):
    window = windows()
    path = text_file(tmp_path)
    called = []
    def choose(*args):
        called.append(args[1])
        return str(path), ""
    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose)
    window.add_placeholder.click()
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert called and window.attachment_tray.ready and window.attachment_tray.count == 1
    ref = window.attachment_tray.references[0]
    assert AttachmentProcessor(window.service.store.attachment_store).load(ref).text == "file contents"
    assert window.composer.height() == 130 and not window.attachment_tray.isHidden()
    assert window.folder_placeholder.toolTip() == "Folder (placeholder)"


def test_cloud_picker_accepts_multiple_in_order_without_small_cap(windows, tmp_path, monkeypatch):
    window = windows("cloud")
    paths = [text_file(tmp_path, f"{i}.txt", str(i)) for i in range(12)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(p) for p in paths], ""))
    window.add_placeholder.click()
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert [ref.name for ref in window.attachment_tray.references] == [p.name for p in paths]
    assert window.attachment_tray.ready and window.attachment_tray.count == 12


def test_local_limit_is_atomic_across_picker_drop_and_paste(windows, tmp_path):
    window = windows()
    paths = [text_file(tmp_path, f"{i}.txt") for i in range(2)]
    window.attachment_tray.add_paths(paths)
    assert window.attachment_tray.count == 0 and "one file or image" in window.attachment_hint.toolTip()
    window.attachment_tray.add_paths(paths[:1])
    wait_for(lambda: not window.attachment_tray.is_processing)
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    mime = QMimeData()
    mime.setImageData(image)
    window.input.insertFromMimeData(mime)
    assert window.attachment_tray.count == 1
    assert window.attachment_tray.references[0].name == "0.txt"


def test_clipboard_image_is_encoded_in_worker_and_has_thumbnail(windows):
    window = windows()
    image = QImage(160, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#778899"))
    QApplication.clipboard().setImage(image)
    window.input.paste()
    wait_for(lambda: not window.attachment_tray.is_processing)
    ref = window.attachment_tray.references[0]
    assert ref.name == "Clipboard image.png" and ref.kind == "image"
    entry = next(iter(window.attachment_tray._entries.values()))
    assert not entry["preview"].pixmap().isNull()
    assert entry["prepared"].processed.width == 160
    assert window.input.toPlainText() == ""


def test_local_file_urls_are_attached_and_remote_links_remain_text(windows, tmp_path):
    window = windows()
    path = text_file(tmp_path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    window.input.insertFromMimeData(mime)
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert window.attachment_tray.references[0].name == path.name and window.input.toPlainText() == ""
    remote = QMimeData()
    remote.setText("https://example.com/image.png")
    remote.setUrls([QUrl("https://example.com/image.png")])
    window.input.insertFromMimeData(remote)
    assert window.attachment_tray.count == 1
    assert "https://example.com/image.png" in window.input.toPlainText()


def test_remove_restores_compact_composer_and_allows_next_file(windows, tmp_path):
    window = windows()
    path = text_file(tmp_path)
    window.attachment_tray.add_paths([path])
    wait_for(lambda: not window.attachment_tray.is_processing)
    entry = next(iter(window.attachment_tray._entries.values()))
    entry["remove"].click()
    assert window.attachment_tray.count == 0 and window.composer.height() == 54
    window.attachment_tray.add_paths([path])
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert window.attachment_tray.count == 1


def test_gate_preserves_text_and_attachments_without_inference_or_key_prompt(windows, tmp_path, monkeypatch):
    window = windows("cloud")
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(lambda: not window.attachment_tray.is_processing)
    window.input.setPlainText("Read this carefully")
    monkeypatch.setattr(window, "_ensure_cloud_ready", lambda: pytest.fail("Unexpected credential prompt"))
    window.submit()
    assert window.input.toPlainText() == "Read this carefully" and window.attachment_tray.count == 1
    assert not window.service.inference.requests and window.service.store.messages() == []
    assert window.thread is None and "not enabled" in window.attachment_hint.toolTip()


def test_attachment_only_dispatch_uses_verified_references_when_adapter_ready(windows, tmp_path):
    window = windows(enabled=True)
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(lambda: not window.attachment_tray.is_processing)
    reference = window.attachment_tray.references[0]
    window.submit()
    wait_for(lambda: window.thread is None)
    assert window.service.store.visible_messages()[0].content == ""
    assert window.service.store.visible_messages()[0].attachments == (reference,)
    assert window.attachment_tray.count == 0
    labels = window.chat._messages[0].findChildren(QLabel, "messageAttachment")
    assert labels[0].text() == "File · file.txt"
    assert window.chat._messages[1]._content == "Attachment reply"


def test_local_document_adapter_sends_prepared_text_and_retains_reference(windows, tmp_path):
    window = windows()
    window.service.inference.supports_local_document_inputs = True
    window.attachment_tray.add_paths([text_file(tmp_path, content="Local document evidence")])
    wait_for(lambda: not window.attachment_tray.is_processing)
    reference = window.attachment_tray.references[0]
    window.input.setPlainText("Explain this document")
    window.submit()
    wait_for(lambda: window.thread is None)
    assert window.attachment_tray.count == 0
    request = window.service.inference.requests[0]
    assert "Local document evidence" in request[-1]["content"]
    assert "attachments" not in request[-1]
    assert window.service.store.visible_messages()[0].attachments == (reference,)
    assert window.chat._messages[-1]._content == "Reply"


def test_local_image_gate_keeps_draft_and_reports_vision_requirement(windows, tmp_path):
    window = windows()
    window.service.inference.supports_local_document_inputs = True
    image = QImage(30, 30, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    mime = QMimeData()
    mime.setImageData(image)
    window.attachment_tray.add_mime(mime)
    wait_for(lambda: not window.attachment_tray.is_processing)
    window.input.setPlainText("Read image")
    window.submit()
    assert window.thread is None and not window.service.inference.requests
    assert window.attachment_tray.count == 1 and window.input.toPlainText() == "Read image"
    assert "vision model" in window.attachment_hint.toolTip()


def test_failed_file_can_be_removed_and_does_not_reach_model(windows, tmp_path):
    window = windows()
    path = tmp_path / "bad.exe"
    path.write_bytes(b"MZ binary")
    window.attachment_tray.add_paths([path])
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert not window.attachment_tray.ready and "Unsupported file type" in window.attachment_hint.toolTip()
    window.submit()
    assert window.thread is None and not window.service.inference.requests
    window.attachment_tray.remove(next(iter(window.attachment_tray._entries)))
    assert window.attachment_tray.ready and window.attachment_tray.count == 0


def test_mode_switch_keeps_cloud_draft_and_requires_local_limit(windows, tmp_path):
    window = windows("cloud")
    window.attachment_tray.add_paths([text_file(tmp_path, "1.txt"), text_file(tmp_path, "2.txt")])
    wait_for(lambda: not window.attachment_tray.is_processing)
    window.model_selector.setCurrentIndex(window.model_selector.findData("local"))
    assert window.attachment_tray.count == 2 and not window.attachment_tray.ready
    assert "Remove the extra attachments" in window.attachment_hint.toolTip()
    window.attachment_tray.remove(next(iter(window.attachment_tray._entries)))
    assert window.attachment_tray.ready


def test_background_preparation_keeps_gui_responsive_and_remove_cancels(windows, tmp_path, monkeypatch):
    window = windows()
    entered = Event()
    original = AttachmentProcessor.prepare
    def delayed(self, ref, *, cancellation=None):
        entered.set()
        assert cancellation.wait(5), "Draft removal did not cancel preparation"
        cancellation.raise_if_cancelled()
        return original(self, ref, cancellation=cancellation)
    monkeypatch.setattr(AttachmentProcessor, "prepare", delayed)
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(entered.is_set)
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    window.input.setPlainText("Still typing")
    wait_for(lambda: bool(ticks))
    window.attachment_tray.remove(next(iter(window.attachment_tray._entries)))
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert window.input.toPlainText() == "Still typing" and not window.service.inference.requests


def test_close_cancels_preparation_and_waits_for_thread_to_release(windows, tmp_path, monkeypatch):
    window = windows()
    entered = Event()
    def delayed(self, ref, *, cancellation=None):
        entered.set()
        assert cancellation.wait(5)
        cancellation.raise_if_cancelled()
    monkeypatch.setattr(AttachmentProcessor, "prepare", delayed)
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(entered.is_set)
    window.close()
    wait_for(lambda: not window.attachment_tray.is_processing and not window.isVisible())
    assert not window.service.inference.requests


def test_new_session_clears_prepared_draft(windows, tmp_path):
    window = windows()
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(lambda: not window.attachment_tray.is_processing)
    window.create_new_session()
    assert window.attachment_tray.count == 0 and window.composer.height() == 54


def test_plain_text_paste_and_enter_keep_existing_behavior(windows):
    window = windows()
    QApplication.clipboard().setText("Plain text")
    window.input.paste()
    QTest.keyClick(window.input, Qt.Key.Key_Return)
    wait_for(lambda: window.thread is None)
    assert window.service.store.messages()[0] == {"role": "user", "content": "Plain text"}
    assert window.attachment_tray.count == 0


def test_window_drop_accepts_local_file_mime(windows, tmp_path):
    window = windows()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(text_file(tmp_path)))])
    enter = QDragEnterEvent(QPoint(300, 400), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(300, 400), Qt.DropAction.CopyAction, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    assert drop.isAccepted()
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert window.attachment_tray.references[0].name == "file.txt"


def test_attachment_gate_preserves_manual_skill_selection(windows, tmp_path):
    window = windows()
    window.attachment_tray.add_paths([text_file(tmp_path)])
    wait_for(lambda: not window.attachment_tray.is_processing)
    window.skill_picker.selected_name = "user-selected-skill"
    window.input.setPlainText("Keep this draft")
    window.submit()
    assert window.skill_picker.selected_name == "user-selected-skill"
    assert window.input.toPlainText() == "Keep this draft"
    assert window.service.active_skill is None and not window.service.inference.requests


def test_cloud_additions_while_processing_preserve_order(windows, tmp_path, monkeypatch):
    window = windows("cloud")
    entered, release = Event(), Event()
    original = AttachmentProcessor.prepare
    def delayed(self, ref, *, cancellation=None):
        if ref.name == "first.txt":
            entered.set()
            assert release.wait(5)
        return original(self, ref, cancellation=cancellation)
    monkeypatch.setattr(AttachmentProcessor, "prepare", delayed)
    first, second = text_file(tmp_path, "first.txt"), text_file(tmp_path, "second.txt")
    window.attachment_tray.add_paths([first])
    wait_for(entered.is_set)
    window.attachment_tray.add_paths([second])
    assert not window.attachment_tray.ready and window.attachment_tray.count == 2
    release.set()
    wait_for(lambda: not window.attachment_tray.is_processing)
    assert [ref.name for ref in window.attachment_tray.references] == ["first.txt", "second.txt"]
