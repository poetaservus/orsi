"""Wheel input, streaming position, picker cancellation and image-only cards."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from app.ui.motion import install_smooth_scroll
from tests.test_attachment_composer import windows, wait_for, text_file


def wheel(area, y=-120, *, pixel=0, modifiers=Qt.KeyboardModifier.NoModifier):
    event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, pixel), QPoint(0, y),
                        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(area.viewport(), event)


def test_wheel_accumulation_and_trackpad_interrupt_preserve_exact_position(windows):
    window = windows()
    area = QScrollArea(window)
    area.resize(300, 150)
    content = QWidget()
    content.resize(280, 2000)
    area.setWidget(content)
    area.show()
    QApplication.processEvents()
    scrolling = install_smooth_scroll(area)
    bar = area.verticalScrollBar()
    bar.setSingleStep(20)
    bar.setValue(200)
    wheel(area)
    wheel(area)
    destination = 200 + 40 * QApplication.wheelScrollLines()
    wait_for(lambda: bar.value() == destination)
    wheel(area)
    QApplication.processEvents()
    before = bar.value()
    wheel(area, pixel=-17)
    assert bar.value() == before + 17
    assert all(a.state() == a.State.Stopped for a in scrolling._animations.values())
    area.close()


def test_scrolling_up_during_streaming_is_not_overridden_by_queued_tail_follow(windows):
    window = windows()
    chat = window.chat
    for index in range(18):
        chat.add_message("Agent", f"Message {index}\n" + "Long synthetic paragraph. " * 30)
    QApplication.processEvents()
    bar = chat.verticalScrollBar()
    wait_for(lambda: bar.maximum() > 0 and bar.value() == bar.maximum())
    chat.set_thinking(True)  # Queues a tail-follow callback before the user scrolls.
    start = bar.value()
    wheel(chat, 120)
    chat.set_stream_preview("New streamed text " * 20)
    wait_for(lambda: all(a.state() == a.State.Stopped for a in chat.smooth_scroll._animations.values()))
    assert bar.value() < start and not chat._follow_tail
    settled = bar.value()
    chat.set_stream_preview("More streamed text " * 40)
    QApplication.processEvents()
    assert bar.value() == settled
    chat.set_thinking(False)


def test_picker_cancel_and_repeated_open_leave_existing_draft_untouched(windows, tmp_path):
    window = windows()
    path = text_file(tmp_path)
    window.attachment_tray.add_paths([str(path)])
    wait_for(lambda: not window.attachment_tray.is_processing)
    original = window.attachment_tray.references
    window.input.setPlainText("Keep this draft")
    window._pick_attachments()
    first = window._attachment_picker
    window._pick_attachments()
    assert window._attachment_picker is first
    first.reject()
    assert window._attachment_picker is None
    assert window.attachment_tray.references == original
    assert window.input.toPlainText() == "Keep this draft" and window.thread is None


def test_closing_main_window_dismisses_attachment_picker(windows):
    window = windows()
    window._pick_attachments()
    dialog = window._attachment_picker
    window.close()
    assert window._attachment_picker is None and not dialog.isVisible()


def test_attached_and_pasted_images_hide_labels_but_keep_documents_and_removal(windows, tmp_path):
    from PySide6.QtCore import QMimeData
    window = windows("cloud")
    image = QImage(160, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    path = tmp_path / "photograph.png"
    assert image.save(str(path))
    window.attachment_tray.add_paths([str(path), str(text_file(tmp_path))])
    mime = QMimeData()
    mime.setImageData(image)
    window.attachment_tray.add_mime(mime)
    wait_for(lambda: not window.attachment_tray.is_processing)
    entries = list(window.attachment_tray._entries.values())
    for entry in (entries[0], entries[2]):
        assert entry["name"].isHidden() and entry["status"].isHidden()
        assert entry["card"].width() == 56 and not entry["preview"].pixmap().isNull()
        assert entry["card"].accessibleName() == entry["job"].name
    assert not entries[1]["name"].isHidden() and not entries[1]["status"].isHidden()
    entries[0]["remove"].click()
    assert window.attachment_tray.count == 2
