from __future__ import annotations
from app.ui.localization import ui_text, QLabel, QWidget, QProgressBar


from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout

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

        self.title = QLabel(ui_text('Context Window'))
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
        self.size.setText(ui_text('{value_0}', value_0=format(length,',')))
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
            ui_text('{value_0} // {value_1} // Context Window: {value_2}{value_3}%', value_0=_APP_STATUS_VERSION, value_1=ui_text(self._runtime_mode), value_2=estimate, value_3=percent)
        )
        if self._budget is None:
            tooltip = (
                ui_text('Estimated conversation use: {value_0} of {value_1} tokens', value_0=f'{self._used_tokens:,}', value_1=f'{self.bar.maximum():,}')
            )
        else:
            budget = self._budget
            usage = (ui_text('Latest reported request use: {value_0}', value_0=f'{self._reported_tokens:,}') if self._reported_tokens is not None
                     else ui_text('Estimated next input: {value_0}', value_0=f'{budget.request_input_tokens:,}'))
            tooltip = (
                ui_text(
                    '{value_0} of {value_1} tokens\nNext request safety budget: {value_2}\n'
                    'System: {value_3} · Conversation: {value_4} · Tool history: {value_5}\n'
                    'Capability schemas: {value_6} · Output reserve: {value_7} · Safety buffer: {value_8}\n'
                    'Remaining after reserves: {value_9}',
                    value_0=usage, value_1=f'{budget.model_context_limit:,}',
                    value_2=f'{budget.total_estimated_request_tokens:,}',
                    value_3=f'{budget.system_message_tokens:,}', value_4=f'{budget.conversation_tokens:,}',
                    value_5=f'{budget.structured_tool_history_tokens:,}', value_6=f'{budget.capability_schema_reserve:,}',
                    value_7=f'{budget.requested_output_reserve:,}', value_8=f'{budget.safety_buffer:,}',
                    value_9=f'{budget.remaining_tokens:,}')
            )
        self.setToolTip(tooltip)
        self.bar.setToolTip(tooltip)
