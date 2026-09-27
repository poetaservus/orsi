from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QPushButton


class CopyButton(QPushButton):
    """Shared icon and clipboard feedback for messages and code blocks."""

    feedback_finished = Signal()

    def __init__(self, description: str):
        super().__init__()
        assets = Path(__file__).with_name("assets")
        self._copy_icon = QIcon(str(assets / "copy.svg"))
        self._check_icon = QIcon(str(assets / "check.svg"))
        self._description = description
        self.copy_succeeded = False
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.setInterval(1400)
        self._feedback_timer.timeout.connect(self._finish_feedback)
        self._restore_icon()

    def copy_text(self, text: str) -> bool:
        self._feedback_timer.stop()
        self._restore_icon()
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            copied = clipboard.text() == text
        except RuntimeError:
            copied = False
        if not copied:
            self.setToolTip("Copy failed. Try again.")
            return False
        self.copy_succeeded = True
        self.setIcon(self._check_icon)
        self.setToolTip("Copied")
        self.setAccessibleName("Copied")
        self._feedback_timer.start()
        return True

    def _restore_icon(self) -> None:
        self.copy_succeeded = False
        self.setIcon(self._copy_icon)
        self.setToolTip(self._description)
        self.setAccessibleName(self._description)

    def _finish_feedback(self) -> None:
        self._restore_icon()
        self.feedback_finished.emit()
