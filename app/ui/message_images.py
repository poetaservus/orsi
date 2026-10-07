"""Lazy, bounded previews of immutable chat attachments."""
from __future__ import annotations

from collections import OrderedDict
from html import escape

from PySide6.QtCore import QFile, QIODevice, QObject, QRectF, QRunnable, QSize, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QWidget

from app.conversation.attachment_processing import MAX_IMAGE_PIXELS
from app.runtime.cancellation import CancellationSource


class _PreviewSignals(QObject):
    finished = Signal(object, object)


class _PreviewJob(QRunnable):
    def __init__(self, store, reference, size):
        super().__init__()
        self.store, self.reference = store, reference
        self.size = size
        self.cancellation = CancellationSource()
        self.signals = _PreviewSignals()

    def run(self):
        image = QImage()
        token = self.cancellation.token
        try:
            with self.store.open(self.reference, cancellation=token) as stream:
                # Decode the verified, pinned handle, never a filename supplied
                # by the user or a second path lookup after verification.
                source = QFile()
                if source.open(stream.fileno(), QIODevice.OpenModeFlag.ReadOnly,
                               QFile.FileHandleFlag.DontCloseHandle):
                    try:
                        source.seek(0)
                        reader = QImageReader(source)
                        reader.setAutoTransform(True)
                        reader.setDecideFormatFromContent(True)
                        size = reader.size()
                        if (size.width() > 0 and size.height() > 0
                                and size.width() * size.height() <= MAX_IMAGE_PIXELS):
                            if size.width() > self.size.width() or size.height() > self.size.height():
                                reader.setScaledSize(size.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio))
                            image = reader.read()
                            token.raise_if_cancelled()
                            # Some codecs ignore the decoder's scaled size.
                            if not image.isNull() and (image.width() > self.size.width() or image.height() > self.size.height()):
                                image = image.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation)
                    finally:
                        source.close()
        except Exception:
            # A missing or changed snapshot must not prevent opening history.
            image = QImage()
        self.signals.finished.emit(self, image)


class MessageImageLoader(QObject):
    loaded = Signal(str)

    def __init__(self, store, parent=None, *, size=QSize(560, 360), max_cached=32):
        super().__init__(parent)
        self.store = store
        self.size, self.max_cached = size, max_cached
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._jobs = {}
        self._images = OrderedDict()

    def image(self, reference):
        key = reference.id
        if key in self._images:
            self._images.move_to_end(key)
            return self._images[key]
        if key not in self._jobs:
            job = _PreviewJob(self.store, reference, self.size)
            self._jobs[key] = job
            job.signals.finished.connect(self._finished)
            self.pool.start(job)
        return None

    @Slot(object, object)
    def _finished(self, job, image):
        key = job.reference.id
        if self._jobs.get(key) is not job:
            return
        del self._jobs[key]
        self._images[key] = image
        while len(self._images) > self.max_cached:
            self._images.popitem(last=False)
        self.loaded.emit(key)

    def clear(self):
        for job in self._jobs.values():
            job.cancellation.cancel()
        self.pool.clear()
        self._jobs.clear()
        self._images.clear()


class _ImagePreview(QWidget):
    activated = Signal()

    def __init__(self, reference, loader, size):
        super().__init__()
        self.reference, self.loader = reference, loader
        self.setObjectName("messageImagePreview")
        self.setAutoFillBackground(False)
        self.setFixedSize(size)
        self.setAccessibleName("Attached image: " + reference.name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("<qt>" + escape(f"{reference.name} · {reference.size_bytes:,} bytes") + "</qt>")
        loader.loaded.connect(self._loaded)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    @Slot(str)
    def _loaded(self, key):
        if key == self.reference.id:
            self.update()

    def paintEvent(self, event):  # noqa: N802
        # Qt paints only exposed thumbnails, so large cloud rows and old chats
        # do not eagerly decode every source. The shared cache caps image RAM.
        image = self.loader.image(self.reference)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 9, 9)
        painter.fillPath(clip, QColor(19, 23, 32, 130))
        painter.setClipPath(clip)
        if image is not None and not image.isNull():
            size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                            size.width(), size.height())
            painter.drawImage(target, image)
        else:
            painter.setPen(QColor("#b1b8c8"))
            font = painter.font()
            font.setPixelSize(11)
            painter.setFont(font)
            name = painter.fontMetrics().elidedText(self.reference.name, Qt.TextElideMode.ElideMiddle,
                                                   max(1, self.width() - 16))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter,
                             ("Loading image…" if image is None else "Preview unavailable") + "\n" + name)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(170, 190, 232, 40), 1))
        painter.drawPath(clip)


class MessageImageStrip(QScrollArea):
    image_activated = Signal(object, int)

    def __init__(self, references, loader, *, preserve_aspect=False):
        super().__init__()
        self.setObjectName("messageImages")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea#messageImages { background: transparent; border: none; }"
                           "QScrollArea#messageImages QWidget { background: transparent; }"
                           "QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }"
                           "QScrollBar::handle:horizontal { background: #667082; border-radius: 3px; min-width: 24px; }"
                           "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
                           "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }")
        self.viewport().setAutoFillBackground(False)
        self.content = QWidget()
        self.content.setAutoFillBackground(False)
        layout = QHBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.single = len(references) == 1
        self.aspect_ratio = 1.0 if preserve_aspect else 280 / 180
        self.preserve_aspect = preserve_aspect and self.single
        size = QSize(280, 280 if self.preserve_aspect else 180) if self.single else QSize(112, 96)
        self.references = tuple(references)
        self.previews = [_ImagePreview(ref, loader, size) for ref in self.references]
        for index, preview in enumerate(self.previews):
            preview.activated.connect(lambda index=index: self.image_activated.emit(self.references, index))
            layout.addWidget(preview)
        self.natural_width = min(480, size.width() * len(references) + 8 * (len(references) - 1))
        self.content.setFixedSize(size.width() * len(references) + 8 * (len(references) - 1), size.height())
        self.setWidget(self.content)
        if self.preserve_aspect:
            loader.loaded.connect(lambda key: self._aspect_loaded(key, loader))

    def _aspect_loaded(self, key, loader):
        if key != self.references[0].id:
            return
        image = loader._images.get(key)
        if image is not None and not image.isNull():
            self.aspect_ratio = image.width() / image.height()
            self.set_available_width(self.width())
            self.updateGeometry()

    def set_available_width(self, width):
        self.setFixedWidth(width)
        if self.single:
            width = min(280, width)
            height = max(1, round(width / self.aspect_ratio))
            self.previews[0].setFixedSize(width, height)
            self.content.setFixedSize(width, height)
        self.setFixedHeight(self.content.height() + (12 if self.content.width() > width else 0))
