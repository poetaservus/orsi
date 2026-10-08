"""Vector button feedback and dragging for the settings UI."""
from math import sin, pi

from PySide6.QtCore import QEasingCurve, QLineF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton, QStylePainter, QWidget


class SettingsIconButton(QPushButton):
    pulse_finished = Signal()

    def __init__(self, parent=None, *, svg=None, duration=320):
        super().__init__(parent)
        self.renderer = QSvgRenderer(str(svg), self) if svg is not None else None
        self.scale = 1.0
        self.angle = 0.0
        self._start_angle = 0.0
        self._turn = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self.pulse_finished)

    def pulse(self, turn=0.0):
        self.animation.stop()
        self._start_angle = self.angle
        self._turn = turn
        self.animation.start()

    def _frame(self, progress):
        self.scale = 1.0 - 0.18 * sin(pi * progress)
        self.angle = self._start_angle + self._turn * progress
        self.update()

    def reset(self):
        self.animation.stop()
        self.scale = 1.0
        self.angle %= 360.0
        self.update()

    def hideEvent(self, event):  # noqa: N802
        self.reset()
        super().hideEvent(event)

    def paintEvent(self, event):  # noqa: N802
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.icon = QIcon()
        option.text = ""
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        painter.setRenderHint(QStylePainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        size = self.scale * (0.94 if self.isDown() else 1.0)
        painter.scale(size, size)
        painter.rotate(self.angle)
        if self.renderer is not None:
            side = self.iconSize().width()
            self.renderer.render(painter, QRectF(-side / 2, -side / 2, side, side))
        else:
            painter.setPen(QPen(QColor("#eeeeef" if self.underMouse() else "#cbd0da"),
                                1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QLineF(-5, -5, 5, 5))
            painter.drawLine(QLineF(5, -5, -5, 5))


class SettingsDragStrip(QWidget):
    """A dedicated top-edge hit area, separate from the title and close control."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.panel.mapToGlobal(self.panel.rect().topLeft())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            parent = self.panel.parentWidget()
            position = parent.mapFromGlobal(event.globalPosition().toPoint() - self._drag_offset)
            self.panel.move(self.panel.bounded_position(position))
            self.panel.user_positioned = True
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
