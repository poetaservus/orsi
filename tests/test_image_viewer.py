import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from time import monotonic, sleep

import pytest
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from app.conversation.attachments import AttachmentStore
from app.ui.chat import ChatView
from app.ui.image_viewer import ImageViewer
from app.ui.composer import ComposerFrame, MessageInput


def picture(color, width=1800, height=1000):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


def wait_for(predicate):
    deadline = monotonic() + 10
    while not predicate():
        assert monotonic() < deadline, "Viewer did not settle"
        QApplication.processEvents()
        sleep(.01)
    QApplication.processEvents()


@pytest.fixture
def viewer(tmp_path, viewer_application):
    store = AttachmentStore(tmp_path / "attachments")
    refs = tuple(store.import_bytes(picture(color), name=f"{i}.png") for i, color in enumerate(("red", "blue")))
    values = []
    def make(**kwargs):
        window = ImageViewer(store, kwargs.pop('references', refs), **kwargs)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        values.append(window)
        window.show()
        wait_for(lambda: window.reference.id in window.loader._images)
        return window
    yield make, store, refs
    for window in values:
        window.close()
        wait_for(lambda: window.loader.pool.activeThreadCount() == 0)
        window.deleteLater()
    QApplication.processEvents()


@pytest.fixture(scope='session')
def viewer_application():
    # Keep one application alive while later UI tests process queued Qt events.
    return QApplication.instance() or QApplication([])


def test_viewer_decodes_large_saved_original_and_fills_available_screen(viewer):
    make, store, refs = viewer
    window = make(index=1)
    image = window.loader._images[refs[1].id]
    assert image.size().width() == 1800 and image.height() == 1000
    assert image.pixelColor(500, 500) == QColor("blue")
    assert window.canvas.width() > 500 and window.canvas.height() > 400
    assert window.counter.text() == "2 / 2" and window.name.text() == "1.png"
    screen = window.screen().availableGeometry()
    assert window.geometry() == screen
    content = store.root / refs[1].id / "content"
    renamed = content.with_name("released")
    content.rename(renamed)
    renamed.rename(content)


def test_overlay_blurs_only_chat_and_uses_shared_centered_composer(viewer):
    make, store, refs = viewer
    parent = QWidget()
    parent.resize(1000, 800)
    layout = QVBoxLayout(parent)
    label = QLabel('Chat behind the image')
    label.setStyleSheet('background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ffffff,stop:0.499 #ffffff,stop:0.5 #ff0000,stop:1 #ff0000); color: white; font-size: 60px')
    layout.addWidget(label)
    parent.show()
    QApplication.processEvents()
    window = make(parent=parent)
    assert not window._backdrop.isNull()
    assert window._backdrop.width() <= 1280 and window._backdrop.height() <= 900
    blurred = window._backdrop.toImage()
    edge = blurred.pixelColor(blurred.width() // 2 + 5, blurred.height() // 2 + 100)
    assert 0 < edge.green() < 255
    assert parent.graphicsEffect() is None
    assert isinstance(window.composer, ComposerFrame) and isinstance(window.prompt, MessageInput)
    assert window.composer.height() == 54 and window.composer.width() <= 799
    assert abs(window.composer.geometry().center().x() - window.rect().center().x()) <= 1
    assert window.composer.y() > window.canvas.geometry().bottom()
    assert window.prompt.height() == 41 and window.send.size().width() == 34
    assert window.prompt.placeholderText() == 'Ask O.R.S.I.'
    frame = window.grab().toImage()
    # Chat is dimmed; the foreground image stays saturated and sharp.
    assert frame.pixelColor(5, frame.height() // 2).red() < 90
    center = window.canvas.mapTo(window, window.canvas.rect().center())
    assert frame.pixelColor(center) == QColor('red')
    window.close()
    assert window._backdrop.isNull()
    window.setParent(None)
    parent.close()


def test_portrait_original_keeps_detail_above_previous_decoder_height(viewer):
    make, store, refs = viewer
    ref = store.import_bytes(picture('green', 2800, 3900), name='portrait.png')
    window = make(references=(ref,))
    image = window.loader._images[ref.id]
    assert image.width() == 2800 and image.height() == 3900
    target = window.canvas.target_rect(image)
    assert target.height() >= window.canvas.height() - 10
    assert abs(target.width() / target.height() - 2800 / 3900) < .002


def test_navigation_preserves_prompt_and_keyboard_edits_text(viewer):
    make, store, refs = viewer
    window = make(cloud=True)
    window.prompt.setPlainText("Compare the colors")
    QTest.keyClick(window, Qt.Key.Key_Right)
    wait_for(lambda: refs[1].id in window.loader._images)
    assert window.reference == refs[1]
    window.prompt.setFocus()
    QTest.keyClick(window.prompt, Qt.Key.Key_Left)
    assert window.reference == refs[1]
    window.previous.click()
    assert window.reference == refs[0] and window.prompt.toPlainText() == "Compare the colors"


def test_reply_selects_current_image_or_explicit_all_in_cloud(viewer):
    make, store, refs = viewer
    window = make(index=1, cloud=True)
    emitted = []
    window.reply_requested.connect(lambda refs, prompt: emitted.append((refs, prompt)))
    window.prompt.setPlainText("Look more closely")
    window.send.click()
    assert emitted[-1] == ((refs[1],), "Look more closely")
    window.include_all.setChecked(True)
    QTest.keyClick(window.prompt, Qt.Key.Key_Return)
    assert emitted[-1] == (refs, "Look more closely")
    before = len(emitted)
    QTest.keyClick(window.prompt, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert len(emitted) == before and "\n" in window.prompt.toPlainText()


def test_local_and_busy_gate_keep_viewer_prompt(viewer):
    make, store, refs = viewer
    window = make()
    assert not window.include_all.isEnabled()
    emitted = []
    window.reply_requested.connect(lambda *args: emitted.append(args))
    window.prompt.setPlainText("Read this")
    window.set_reply_available(False)
    QTest.keyClick(window.prompt, Qt.Key.Key_Return)
    assert not emitted and window.prompt.toPlainText() == "Read this"
    window.set_reply_available(True)
    assert window.send.isEnabled()
    window.set_preparing()
    assert not window.send.isEnabled() and not window.prompt.isEnabled()


def test_missing_snapshot_opens_safe_fallback_and_disables_resend(viewer):
    make, store, refs = viewer
    (store.root / refs[0].id / "content").unlink()
    window = make()
    window.prompt.setPlainText("Read it")
    assert window.loader._images[refs[0].id].isNull() and not window.send.isEnabled()
    window.next.click()
    wait_for(lambda: refs[1].id in window.loader._images)
    assert window.send.isEnabled()


@pytest.mark.parametrize("sender,received", [("User", False), ("Agent", True)])
def test_user_and_future_output_thumbnails_emit_same_viewer_selection(viewer, sender, received):
    make, store, refs = viewer
    chat = ChatView(attachment_store=store)
    chat.resize(1280, 800)
    chat.show()
    emitted = []
    chat.image_activated.connect(lambda refs, index: emitted.append((refs, index)))
    message = chat.add_message(sender, "Pictures", **({"images": refs} if received else {"attachments": refs})).message
    QApplication.processEvents()
    preview = message.image_strip.previews[1]
    QTest.mouseClick(preview, Qt.MouseButton.LeftButton)
    assert emitted[-1] == (refs, 1)
    QTest.keyClick(preview, Qt.Key.Key_Space)
    assert emitted[-1] == (refs, 1)
    chat.image_loader.clear()
    wait_for(lambda: chat.image_loader.pool.activeThreadCount() == 0)
    chat.close()
    chat.deleteLater()
    QApplication.processEvents()


def test_escape_closes_and_clears_high_resolution_cache(viewer):
    make, store, refs = viewer
    window = make()
    window.prompt.setFocus()
    QTest.keyClick(window.prompt, Qt.Key.Key_Escape)
    assert not window.isVisible() and not window.loader._images
