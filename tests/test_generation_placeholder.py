import pytest
from PySide6.QtWidgets import QApplication
from app.ui.generation_placeholder import GenerationPlaceholder


@pytest.fixture(scope="session")
def image_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_placeholder_pauses_hidden_and_stops_on_terminal_state(image_app):
    widget = GenerationPlaceholder()
    try:
        widget.show()
        widget.start()
        image_app.processEvents()
        assert widget.timer.isActive()
        widget.hide()
        assert not widget.timer.isActive() and not widget._clock.isValid()
        widget.show()
        assert widget.timer.isActive()
        widget.set_occluded(True)
        assert not widget.timer.isActive()
        widget.set_occluded(False)
        assert widget.timer.isActive()
        widget.stop("Image generation stopped")
        widget.hide()
        widget.show()
        assert not widget.timer.isActive() and not widget.active
        assert widget.accessibleName() == "Image generation stopped"
    finally:
        widget.stop()
        widget.close()


def test_placeholder_aspect_ratio_and_cached_motion(image_app):
    first = GenerationPlaceholder(aspect_ratio=2 / 3)
    second = GenerationPlaceholder(aspect_ratio=3 / 2)
    try:
        assert (first.width(), first.height()) == (280, 420)
        assert (second.width(), second.height()) == (280, 187)
        assert 10_000 <= first.cycle_ms <= 16_000
        assert first.layers is second.layers and first.grain is second.grain
        first.show()
        image_app.processEvents()
        before = first.grab().toImage()
        first._elapsed_ms = 7000
        after = first.grab().toImage()
        assert before != after
    finally:
        first.close()
        second.close()
