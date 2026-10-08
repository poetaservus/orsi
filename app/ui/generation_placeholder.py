"""Cached drifting clouds and grain for an active image request."""
from math import cos, pi, sin
from random import Random

from PySide6.QtCore import QElapsedTimer, QEvent, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QWidget


class GenerationPlaceholder(QWidget):
    cycle_ms = 10_000
    _cached_visuals = None

    def __init__(self, parent=None, *, aspect_ratio=1.0):
        super().__init__(parent)
        self.setObjectName("imageGenerationPlaceholder")
        self.setAccessibleName("Generating image")
        self.aspect_ratio = aspect_ratio
        self.active = False
        self._occluded = False
        self.status = "Generating image…"
        self._status_key = self._status_path = None
        self._elapsed_ms = 0
        self._clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        if GenerationPlaceholder._cached_visuals is None:
            layers = tuple(self._layer(color) for color in
                           ("#142942", "#78372d", "#9a4032", "#091a30"))
            grain = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
            random = Random(71)
            for y in range(256):
                for x in range(256):
                    shade = 235 if random.random() > .5 else 0
                    grain.setPixelColor(x, y, QColor(shade, shade, shade, random.randrange(3, 14)))
            GenerationPlaceholder._cached_visuals = (layers, grain)
        self.layers, self.grain = GenerationPlaceholder._cached_visuals
        self.set_frame_width(280)

    @staticmethod
    def _layer(color):
        image = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        gradient = QRadialGradient(160, 160, 160)
        gradient.setColorAt(0, QColor(color))
        gradient.setColorAt(.22, QColor(color))
        transparent = QColor(color)
        transparent.setAlpha(0)
        gradient.setColorAt(1, transparent)
        painter.fillRect(image.rect(), gradient)
        painter.end()
        return image

    def set_frame_width(self, width):
        width = max(1, min(420, width))
        self.setFixedSize(width, max(1, round(width / self.aspect_ratio)))

    def start(self):
        self.active = True
        self.status = "Generating image…"
        self.setAccessibleName(self.status)
        self._resume()

    def stop(self, status=""):
        self._pause()
        self.active = False
        self.status = status
        self.setAccessibleName(status or "Image generation finished")
        self.update()

    def _pause(self):
        if self._clock.isValid():
            self._elapsed_ms += self._clock.elapsed()
            self._clock.invalidate()
        self.timer.stop()

    def _resume(self):
        if self.active and self.isVisible() and not self._occluded and not self.window().isMinimized():
            if not self._clock.isValid():
                self._clock.start()
            self.timer.start()

    def set_occluded(self, occluded):
        self._occluded = bool(occluded)
        self._pause() if self._occluded else self._resume()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.window().installEventFilter(self)
        self._resume()

    def hideEvent(self, event):  # noqa: N802
        self._pause()
        super().hideEvent(event)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.window() and event.type() == QEvent.Type.WindowStateChange:
            self._pause() if watched.isMinimized() else self._resume()
        return super().eventFilter(watched, event)

    def _tick(self):
        if self.visibleRegion().isEmpty():
            return  # Occluded/scrolled-out frames do no painting work.
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 13, 13)
        painter.setClipPath(clip)
        painter.fillRect(bounds, QColor("#101720"))
        elapsed = self._elapsed_ms + (self._clock.elapsed() if self._clock.isValid() else 0)
        phase = 2 * pi * elapsed / self.cycle_ms
        for index, layer in enumerate(self.layers):
            angle = phase * (1 + index * .17) + index * 1.7
            cx = self.width() * (.48 + .34 * sin(angle))
            cy = self.height() * (.45 + .30 * cos(angle * .83 + index))
            width = self.width() * (1.15 + .32 * sin(angle + 1))
            height = self.height() * (1.30 + .30 * cos(angle))
            painter.setOpacity(.72 + .14 * sin(angle * 1.3))
            painter.drawImage(QRectF(cx - width / 2, cy - height / 2, width, height), layer)
        painter.setOpacity(.75)
        painter.drawImage(bounds, self.grain)
        if self.status:
            painter.setOpacity(1)
            shade = QLinearGradient(0, self.height() * .65, 0, self.height())
            shade.setColorAt(0, QColor(8, 13, 20, 0))
            shade.setColorAt(1, QColor(8, 13, 20, 145))
            painter.fillRect(bounds, shade)
            self._draw_status(painter, bounds, elapsed, phase)

    def _draw_status(self, painter, bounds, elapsed, phase):
        font = painter.font()
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Medium)
        metrics = QFontMetricsF(font)
        baseline = bounds.bottom() - 24 - metrics.descent()
        left = bounds.left() + (40 if self.active else 24)
        key = (self.status, bounds.width(), bounds.height(), font.key(), self.active)
        if key != self._status_key:
            label = metrics.elidedText(self.status, Qt.TextElideMode.ElideRight,
                                      max(0, bounds.right() - 24 - left))
            self._status_path = QPainterPath()
            self._status_path.addText(QPointF(left, baseline), font, label)
            self._status_key = key
        ink = QColor("#b6b9c0")
        if self.active:
            # A soft reflection crosses only the glyphs, with a quiet gap between sweeps.
            text_width = self._status_path.boundingRect().width()
            center = left - 48 + (text_width + 96) * min(1., (elapsed % 3600) / 2800)
            reflection = QLinearGradient(center - 36, 0, center + 36, 0)
            reflection.setColorAt(0, ink)
            reflection.setColorAt(.5, QColor("#fff1e7"))
            reflection.setColorAt(1, ink)
            painter.fillPath(self._status_path, reflection)
            painter.setPen(Qt.PenStyle.NoPen)
            dot = QColor("#d08870")
            dot.setAlphaF(.65 + .25 * sin(phase * 2))
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(bounds.left() + 27, baseline - metrics.ascent() * .36), 3, 3)
        else:
            painter.fillPath(self._status_path, ink)
