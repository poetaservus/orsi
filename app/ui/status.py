from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QTimer, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QWidget


class ThinkingDots(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("thinkingDots")
        self.setFixedSize(54, 30)
        self.setAccessibleName("O.R.S.I is thinking")
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._advance)
        self.hide()

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._phase = 0.0
        self.show()
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.28) % (math.tau * 2)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#b8b8b8"))
        painter.setBrush(QColor("#b8b8b8"))
        radius = 3.1
        baseline = self.height() / 2 + 2
        for index, x in enumerate((13.0, 27.0, 41.0)):
            wave = max(0.0, math.sin(self._phase - index * 0.85))
            y = baseline - wave * 7.0
            painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))


class ConversationStatus(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("conversationStatus")

    @Slot(str)
    def set_activity(self, text: str) -> None:
        self.setText(text)
