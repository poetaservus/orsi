"""Conformist's stationary, softly shimmering image-generation dot grid."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.generation_placeholder import GenerationPlaceholder
from app.ui.main_window import MainWindow
from app.ui.themes import ThemeError, export_folder, import_folder, validate_manifest


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def scene(qt):
    window = MainWindow(None, "SYNTHETIC")
    window.resize(1000, 800)
    placeholder = GenerationPlaceholder(window._content, aspect_ratio=2 / 3)
    placeholder.move(40, 60)
    window.show()
    placeholder.show()
    qt.processEvents()
    yield window, placeholder
    placeholder.stop()
    placeholder.close()
    window.close()
    qt.processEvents()


def still(widget, elapsed):
    widget._pause()
    widget.active = True  # Render the active placeholder without a status label.
    widget._elapsed_ms = elapsed
    return widget.grab().toImage()


def test_dots_shimmer_in_place_on_an_opaque_flat_neutral_background(scene):
    window, placeholder = scene
    window.theme_controller.select("conformist")
    first = still(placeholder, 0)
    pattern = placeholder._dot_pattern()
    next_frame = still(placeholder, 33)
    later = still(placeholder, 2500)
    assert first != later and placeholder._dot_pattern() is pattern
    assert first.size().width() == 280 and first.size().height() == 420
    # Halfway between dots, every grid cell retains the exact same flat fill.
    for point, _, _ in pattern:
        x, y = round(point.x()), round(point.y())
        one, two = first.pixelColor(x, y), next_frame.pixelColor(x, y)
        assert one.red() == one.green() == one.blue() and one.alpha() == 255
        assert abs(one.red() - two.red()) <= 3  # A 33 ms frame cannot flash.
        if x + 8 < first.width() - 4 and y + 8 < first.height() - 4:
            assert first.pixelColor(x + 8, y + 8) == QColor("#141414")
            assert later.pixelColor(x + 8, y + 8) == QColor("#141414")
    assert len({first.pixelColor(round(p.x()), round(p.y())).red() for p, _, _ in pattern}) > 10
    placeholder.set_frame_width(340)
    assert placeholder._dot_pattern() is not pattern
    assert placeholder._elapsed_ms == 2500 and placeholder.height() == 510


def test_switching_themes_restores_the_existing_cloud_visual_exactly(scene, qt):
    window, placeholder = scene
    before = still(placeholder, 2500)
    window.theme_controller.select("conformist")
    dots = still(placeholder, 2500)
    assert dots != before
    window.theme_controller.select("ocean")
    assert still(placeholder, 2500) == before
    window.theme_controller.select("original")
    assert still(placeholder, 2500) == before


def test_active_dots_keep_the_existing_pause_stop_and_theme_switch_lifecycle(scene, qt):
    window, placeholder = scene
    window.theme_controller.select("conformist")
    placeholder.start()
    QTest.qWait(30)
    assert placeholder.timer.isActive() and placeholder._clock.isValid()
    assert placeholder.timer.interval() == 33
    window.theme_controller.select("original")
    assert placeholder.timer.isActive() and placeholder.active
    window.theme_controller.select("conformist")
    placeholder.set_occluded(True)
    assert not placeholder.timer.isActive() and not placeholder._clock.isValid()
    elapsed = placeholder._elapsed_ms
    QTest.qWait(15)
    assert placeholder._elapsed_ms == elapsed
    placeholder.set_occluded(False)
    assert placeholder.timer.isActive()
    placeholder.hide()
    assert not placeholder.timer.isActive()
    placeholder.show()
    assert placeholder.timer.isActive()
    placeholder.stop("Image generation stopped")
    assert not placeholder.timer.isActive() and not placeholder.active
    assert placeholder.accessibleName() == "Image generation stopped"
    assert not placeholder.grab().isNull()


def test_exported_conformist_keeps_the_placeholder_style_under_a_new_id(scene, tmp_path):
    window, placeholder = scene
    package = window.theme_controller.repository.packages["conformist"]
    path = export_folder(package, tmp_path / "my-conformist")
    imported = import_folder(path)
    assert imported["manifest"]["image_placeholder"] == package["manifest"]["image_placeholder"]
    window.theme_controller.repository.add(imported)
    window.theme_controller.select("my-conformist")
    assert placeholder.placeholder_appearance()["style"] == "shimmer_dots"


@pytest.mark.parametrize("appearance", [
    {"style": "video"}, {"style": "shimmer_dots", "background": "red"},
    {"style": "shimmer_dots", "dot": "#fff"}, {"style": "shimmer_dots", "interval_ms": 1},
])
def test_placeholder_options_are_bounded_cosmetic_data(appearance):
    with pytest.raises(ThemeError):
        validate_manifest({"version": 1, "id": "custom", "name": "Custom", "image_placeholder": appearance})


def test_dot_placeholder_still_fades_into_the_actual_image(scene, qt, tmp_path):
    from app.conversation.attachments import AttachmentStore
    from app.ui.generated_image_frame import GeneratedImageFrame
    from app.ui.message_images import MessageImageLoader
    from tests.test_message_images import image_bytes, wait_for
    window, _ = scene
    window.theme_controller.select("conformist")
    store = AttachmentStore(tmp_path / "images")
    reference = store.import_bytes(image_bytes("#345678", 64, 96), name="synthetic.png")
    loader = MessageImageLoader(store)
    frame = GeneratedImageFrame(window._content, aspect_ratio=2 / 3)
    frame.move(400, 60)
    frame.show()
    frame.start()
    try:
        assert frame.placeholder_appearance()["style"] == "shimmer_dots"
        frame.show_result((reference,), loader)
        wait_for(lambda: frame.opacity == 1.0)
        assert not frame.active and not frame.timer.isActive()
        assert frame.transition.duration() == 650
        image = frame.grab().toImage()
        assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("#345678")
        opened = []
        frame.activated.connect(lambda: opened.append(True))
        QTest.keyClick(frame, Qt.Key.Key_Return)
        assert opened == [True]
    finally:
        frame.stop()
        loader.clear()
        wait_for(lambda: loader.pool.activeThreadCount() == 0)
        frame.close()
