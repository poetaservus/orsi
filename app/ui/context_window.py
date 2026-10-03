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

from app.conversation.context import ContextBudget


_APP_STATUS_VERSION = "O.R.S.I. v0.4.0-dev"


class ContextWindowBar(QWidget):
    """Compact context-capacity indicator for the conversation header."""

    def __init__(self, context_length: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contextWindow")
        self.setFixedWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._runtime_mode = "Local"
        self._used_tokens = 0
        self._budget: ContextBudget | None = None
        self._reported_tokens: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status = QLabel()
        self.status.setObjectName("contextStatusLine")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.bar.setRange(0, max(1, length))
        self.bar.setValue(min(self._used_tokens, length))
        self.size.setText(f"{length:,}")
        self._update_tooltip()

    def set_used_tokens(self, used_tokens: int) -> None:
        self._budget = None
        self._reported_tokens = None
        self._used_tokens = max(0, int(used_tokens))
        self.bar.setValue(min(self._used_tokens, self.bar.maximum()))
        self._update_tooltip()

    def set_budget(self, budget: ContextBudget, *, reported_tokens: int | None = None) -> None:
        if not isinstance(budget, ContextBudget):
            raise TypeError("The context meter requires a ContextBudget.")
        self._budget = budget
        if reported_tokens is not None and (type(reported_tokens) is not int or reported_tokens < 0):
            raise ValueError("Reported context use must be a non-negative integer.")
        self._reported_tokens = reported_tokens
        self._used_tokens = budget.request_input_tokens if reported_tokens is None else reported_tokens
        self.set_context_length(budget.model_context_limit)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        percent = round((self._used_tokens / max(1, self.bar.maximum())) * 100)
        percent = max(0, min(100, percent))
        estimate = "~" if self._reported_tokens is None and self._used_tokens else ""
        self.status.setText(
            f"{_APP_STATUS_VERSION} // {self._runtime_mode} // Context Window: {estimate}{percent}%"
        )
        if self._budget is None:
            tooltip = (
                f"Estimated conversation use: {self._used_tokens:,} of "
                f"{self.bar.maximum():,} tokens"
            )
        else:
            budget = self._budget
            usage = (f"Latest reported request use: {self._reported_tokens:,}" if self._reported_tokens is not None
                     else f"Estimated next input: {budget.request_input_tokens:,}")
            tooltip = (
                f"{usage} of "
                f"{budget.model_context_limit:,} tokens\n"
                f"Next request safety budget: {budget.total_estimated_request_tokens:,}\n"
                f"System: {budget.system_message_tokens:,} · Conversation: "
                f"{budget.conversation_tokens:,} · Tool history: "
                f"{budget.structured_tool_history_tokens:,}\n"
                f"Capability schemas: {budget.capability_schema_reserve:,} · Output reserve: "
                f"{budget.requested_output_reserve:,} · Safety buffer: "
                f"{budget.safety_buffer:,}\nRemaining after reserves: {budget.remaining_tokens:,}"
            )
        self.setToolTip(tooltip)
        self.bar.setToolTip(tooltip)
