import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from time import monotonic, sleep

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.conversation.attachments import AttachmentStore
from app.ui.chat import ChatView


def image_bytes(color, width=320, height=200, format="PNG"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, format)
    return bytes(buffer.data())


def wait_for(predicate):
    deadline = monotonic() + 10
    while not predicate():
        assert monotonic() < deadline, "Image preview did not settle"
        QApplication.processEvents()
        sleep(.01)
    QApplication.processEvents()


@pytest.fixture
def chat(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = AttachmentStore(tmp_path / "attachments")
    view = ChatView(attachment_store=store)
    view.resize(1280, 800)
    view.show()
    yield view, store
    view.image_loader.clear()
    wait_for(lambda: view.image_loader.pool.activeThreadCount() == 0)
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def test_single_image_uses_snapshot_and_keeps_text_below_preview(chat, tmp_path):
    view, store = chat
    source = tmp_path / "photo.png"
    source.write_bytes(image_bytes("#ff4422"))
    ref = store.import_file(source)
    source.unlink()
    message = view.add_message("User", "check this picture", attachments=(ref,)).message
    wait_for(lambda: ref.id in view.image_loader._images)
    image = view.image_loader._images[ref.id]
    assert not image.isNull() and image.pixelColor(10, 10) == QColor("#ff4422")
    strip = message.image_strip
    assert strip.previews[0].height() == 180
    assert message.label.y() >= strip.y() + strip.height()
    assert message.width() >= 280 + 32
    assert [label.text() for label in message._text_labels] == ["check this picture"]
    # The decoder releases its verified snapshot handle after loading.
    snapshot = store.root / ref.id / "content"
    moved = snapshot.with_name("handle-check")
    snapshot.rename(moved)
    moved.rename(snapshot)


def test_multiple_images_line_up_in_order_and_files_remain_labels(chat):
    view, store = chat
    refs = [store.import_bytes(image_bytes(color), name=f"{i}.png")
            for i, color in enumerate(("red", "green", "blue"))]
    document = store.import_bytes(b"some notes", name="notes.txt")
    message = view.add_message("User", "compare these", attachments=(refs[0], document, *refs[1:])).message
    wait_for(lambda: all(ref.id in view.image_loader._images for ref in refs))
    previews = message.image_strip.previews
    assert [preview.reference for preview in previews] == refs
    assert len({preview.y() for preview in previews}) == 1
    assert all(a.x() + a.width() < b.x() for a, b in zip(previews, previews[1:]))
    assert all(preview.width() == 112 for preview in previews)
    assert [label.text() for label in message._text_labels] == ["File · notes.txt", "compare these"]
    assert previews[1].accessibleName() == "Attached image: 1.png"


@pytest.mark.parametrize("suffix,format", [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"), ("gif", "GIF")])
def test_supported_formats_decode_from_verified_handle_and_keep_portrait_shape(chat, suffix, format):
    import base64
    view, store = chat
    data = (base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==") if suffix == "gif"
            else image_bytes("#334455", 100, 400, format))
    ref = store.import_bytes(data, name="photo." + suffix)
    view.add_message("User", "inspect", attachments=(ref,))
    wait_for(lambda: ref.id in view.image_loader._images)
    image = view.image_loader._images[ref.id]
    assert not image.isNull() and image.width() <= 560 and image.height() <= 360
    if suffix != "gif":
        assert image.height() == image.width() * 4


def test_long_cloud_row_loads_only_visible_images_and_scrolls_to_last(chat):
    view, store = chat
    refs = [store.import_bytes(image_bytes("red"), name=f"{i}.png") for i in range(45)]
    message = view.add_message("User", "", attachments=refs).message
    strip = message.image_strip
    wait_for(lambda: bool(view.image_loader._images) and not view.image_loader._jobs)
    assert 0 < len(view.image_loader._images) < 10
    assert refs[-1].id not in view.image_loader._images
    assert strip.horizontalScrollBar().maximum() > 0
    view.resize(400, 600)
    QApplication.processEvents()
    assert strip.width() <= message.width() - 32
    strip.horizontalScrollBar().setValue(strip.horizontalScrollBar().maximum())
    wait_for(lambda: refs[-1].id in view.image_loader._images)
    assert not view.image_loader._images[refs[-1].id].isNull()
    for index, ref in enumerate(refs):
        strip.horizontalScrollBar().setValue(min(index * 120, strip.horizontalScrollBar().maximum()))
        wait_for(lambda: ref.id in view.image_loader._images)
    assert len(view.image_loader._images) <= 32


@pytest.mark.parametrize("failure", ["missing", "changed", "unreadable"])
def test_unavailable_preview_preserves_bubble_and_filename(chat, failure):
    view, store = chat
    ref = store.import_bytes(b"not an image" if failure == "unreadable" else image_bytes("blue"), name="photo.png")
    snapshot = store.root / ref.id / "content"
    if failure == "missing":
        snapshot.unlink()
    elif failure == "changed":
        snapshot.write_bytes(image_bytes("red"))
    message = view.add_message("User", "my request", attachments=(ref,)).message
    wait_for(lambda: ref.id in view.image_loader._images)
    assert view.image_loader._images[ref.id].isNull()
    assert message.label.text() == "my request"
    assert "photo.png" in message.image_strip.previews[0].toolTip()


def test_clear_ignores_old_job_completion_without_losing_new_preview(chat, monkeypatch):
    from threading import Event
    view, store = chat
    ref = store.import_bytes(image_bytes("blue"), name="photo.png")
    original = store.open
    entered, release = Event(), Event()
    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "open", delayed)
    view.add_message("User", "first", attachments=(ref,))
    wait_for(entered.is_set)
    view.clear_messages()
    view.add_message("User", "reopened", attachments=(ref,))
    release.set()
    wait_for(lambda: ref.id in view.image_loader._images)
    assert not view.image_loader._images[ref.id].isNull()
    assert len(view._messages) == 1 and view._messages[0].label.text() == "reopened"


def test_standalone_chat_without_storage_preserves_attachment_label():
    app = QApplication.instance() or QApplication([])
    from app.inference.attachments import AttachmentReference
    ref = AttachmentReference(id="att-" + "a" * 32, name="photo.png", kind="image", media_type="image/png",
                              size_bytes=1, sha256="a" * 64)
    view = ChatView()
    message = view.add_message("User", "hello", attachments=(ref,)).message
    assert message.image_strip is None
    assert message._text_labels[0].text() == "Image · photo.png"
    view.close()
