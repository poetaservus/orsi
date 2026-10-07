"""A generation frame which becomes a clickable source-backed image."""
from PySide6.QtCore import QEasingCurve, QRectF, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from app.ui.generation_placeholder import GenerationPlaceholder


class GeneratedImageFrame(GenerationPlaceholder):
    activated = Signal()
    image_activated = Signal(object, int)

    def __init__(self, parent=None, *, aspect_ratio=1.0):
        super().__init__(parent, aspect_ratio=aspect_ratio)
        self.reference = self.loader = None
        self.opacity = 0.0
        self.transition = None
        self.references = ()
        self.natural_width = 280
        self.activated.connect(lambda: self.image_activated.emit(self.references, 0))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_available_width(self, width):
        self.set_frame_width(min(280, width))

    def show_result(self, references, loader):
        self.stop("")
        self.references = tuple(references)
        reference = self.references[0]
        self.reference, self.loader = reference, loader
        self.setAccessibleName("Generated image: " + reference.name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        loader.loaded.connect(self._loaded)
        image = loader.image(reference)
        if image is not None:
            self._loaded(reference.id)
        self.update()

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        if self.transition is not None and self.transition.state() == QVariantAnimation.State.Running:
            self.transition.pause()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self.transition is not None and self.transition.state() == QVariantAnimation.State.Paused:
            self.transition.resume()

    def _loaded(self, key):
        if self.reference is None or key != self.reference.id or self.transition is not None:
            return
        image = self.loader.image(self.reference)
        if image is None or image.isNull():
            self.stop("Preview unavailable")
            return
        self.transition = QVariantAnimation(self)
        self.transition.setDuration(650)
        self.transition.setStartValue(0.0)
        self.transition.setEndValue(1.0)
        self.transition.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.transition.valueChanged.connect(self._fade)
        self.transition.start()
        if not self.isVisible():
            self.transition.pause()

    def _fade(self, value):
        self.opacity = value
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self.reference is not None and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if self.reference is not None and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self.reference is None:
            return
        image = self.loader.image(self.reference)
        if image is None or image.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 13, 13)
        painter.setClipPath(clip)
        painter.setOpacity(self.opacity)
        painter.fillRect(bounds, QColor("#11131b"))
        size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                        size.width(), size.height())
        painter.drawImage(target, image)
