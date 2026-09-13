from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


_APP_STATUS_VERSION = "O.R.S.I. v0.4.0-dev"


class ContextWindowBar(QWidget):
    """Compact context-capacity indicator for the conversation header."""

    def __init__(self, context_length: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contextWindow")
        self.setFixedWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._runtime_mode = "Local"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status = QLabel()
        self.status.setObjectName("contextStatusLine")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status)

        labels = QHBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(10)

        self.title = QLabel("Context Window")
        self.title.setObjectName("contextWindowTitle")
        self.size = QLabel()
        self.size.setObjectName("contextWindowSize")

        labels.addWidget(self.title)
        labels.addStretch(1)
        labels.addWidget(self.size)
        layout.addLayout(labels)

        self.bar = QProgressBar()
        self.bar.setObjectName("contextWindowBar")
        self.bar.setFixedHeight(4)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        self.title.hide()
        self.size.hide()
        self.bar.hide()

        self.set_context_length(context_length)

    def set_runtime_mode(self, mode: str) -> None:
        self._runtime_mode = mode or "Local"
        self._update_tooltip()

    def set_context_length(self, context_length: int) -> None:
        length = max(0, int(context_length))
        previous = self.bar.value()
        self.bar.setRange(0, max(1, length))
        self.bar.setValue(min(previous, length))
        self.size.setText(f"{length:,}")
        self._update_tooltip()

    def set_used_tokens(self, used_tokens: int) -> None:
        self.bar.setValue(max(0, min(int(used_tokens), self.bar.maximum())))
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        percent = round((self.bar.value() / max(1, self.bar.maximum())) * 100)
        percent = max(0, min(100, percent))
        self.status.setText(
            f"{_APP_STATUS_VERSION} // {self._runtime_mode} // Context Window: {percent}%"
        )
        tooltip = (
            f"Estimated conversation use: {self.bar.value():,} of "
            f"{self.bar.maximum():,} tokens"
        )
        self.setToolTip(tooltip)
        self.bar.setToolTip(tooltip)
