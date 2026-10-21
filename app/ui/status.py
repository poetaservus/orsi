from __future__ import annotations
from app.ui.localization import ui_extra, ui_text, QLabel, QWidget
from app.runtime.semantic_progress import ProgressPhase


import math

from PySide6.QtCore import QElapsedTimer, QRectF, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QPainter
from app.ui.theme_runtime import theme_color



def progress_sentence(phase):
    return {
        ProgressPhase.PREPARE: ui_extra("I'm preparing the task and its inputs."),
        ProgressPhase.WORK: ui_extra("I'm working through the requested task."),
        ProgressPhase.REVIEW: ui_extra("I'm checking the result before finishing."),
        ProgressPhase.FINALIZE: ui_extra("I'm saving the response and task history."),
    }[phase]


class ThinkingDots(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("thinkingDots")
        self.setFixedSize(37, 22)
        self.setAccessibleName(ui_text('O.R.S.I is thinking'))
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self.hide()

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._elapsed.start()
        self.show()
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self._elapsed.invalidate()
        self.hide()

    def _pulse(self, index: int, seconds: float) -> float:
        return (1 - math.cos(math.tau * (seconds / 1.4 - index * .16))) / 2

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        seconds = self._elapsed.nsecsElapsed() / 1_000_000_000 if self._elapsed.isValid() else 0
        for index, x in enumerate((0.0, 12.0, 24.0)):
            pulse = self._pulse(index, seconds)
            height = 5.0 + pulse * 9.0
            color = theme_color(self, "#c7cad2", "text_muted")
            color.setAlphaF(.35 + pulse * .65)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, (self.height() - height) / 2, 5, height), 2.5, 2.5)


class ConversationStatus(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("conversationStatus")

    @Slot(str)
    def set_activity(self, text: str) -> None:
        self.setText(text)
