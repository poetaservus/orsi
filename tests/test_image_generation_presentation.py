import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from app.conversation.attachments import AttachmentStore
from app.ui.chat import ChatView
from app.ui.generated_image_frame import GeneratedImageFrame
from app.ui.image_viewer import ImageViewer
from tests.test_message_images import image_bytes, wait_for


@pytest.fixture(scope="session")
def presentation_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_frame_transfers_to_result_and_fades_into_original_aspect(presentation_app, tmp_path):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(image_bytes("#6272ac", 1024, 1536), name="portrait.png")
    view = ChatView(attachment_store=store)
    view.resize(900, 800)
    view.show()
    try:
        view.set_thinking(True)
        view.start_image_generation(2 / 3)
        frame = view.generation_frame
        assert (frame.width(), frame.height()) == (280, 420)
        view.set_thinking(False)
        moved = view.take_generation_frame((ref,))
        assert moved is frame and not frame.active and not frame.timer.isActive()
        message = view.add_message("Agent", "Image generated.", images=(ref,), generation_frame=moved).message
        assert message.image_strip is frame
        wait_for(lambda: frame.opacity == 1.0)
        assert frame.height() == round(frame.width() * 1.5)
        activated = []
        view.image_activated.connect(lambda refs, index: activated.append((refs, index)))
        frame.activated.emit()
        assert activated == [((ref,), 0)]
    finally:
        view.image_loader.clear()
        wait_for(lambda: view.image_loader.pool.activeThreadCount() == 0)
        view.close()


def test_multiple_results_open_in_order_and_save_original_bytes(presentation_app, tmp_path, monkeypatch):
    store = AttachmentStore(tmp_path / "attachments")
    raw = [image_bytes(color, 1536, 1024) for color in ("red", "green", "blue")]
    refs = tuple(store.import_bytes(data, name=f"generated-{i}.png") for i, data in enumerate(raw))
    view = ChatView(attachment_store=store)
    view.resize(900, 700)
    view.show()
    parent = view
    viewer = None
    try:
        view.set_thinking(True)
        view.start_image_generation(3 / 2)
        view.set_thinking(False)
        frame = view.take_generation_frame(refs)
        message = view.add_message("Agent", "Images generated.", images=refs, generation_frame=frame).message
        assert message.result_thumbnails.references == refs
        wait_for(lambda: frame.opacity == 1.0)
        viewer = ImageViewer(store, refs, 1, cloud=True, parent=parent)
        viewer.show()
        destination = tmp_path / "saved.png"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
        viewer._save_image()
        assert destination.read_bytes() == raw[1]
        viewer.navigate(1)
        assert viewer.reference == refs[2]
    finally:
        if viewer is not None:
            viewer.reject()
        view.image_loader.clear()
        wait_for(lambda: view.image_loader.pool.activeThreadCount() == 0)
        view.close()
