from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.status import ThinkingDots


class _Message(QFrame):
    def __init__(self, content: str, *, from_user: bool, error: bool = False):
        super().__init__()
        self.from_user = from_user
        self._content = content
        if from_user:
            self.setObjectName("userMessage")
        elif error:
            self.setObjectName("errorMessage")
        else:
            self.setObjectName("orsiMessage")

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14 if from_user else 0, 9, 14 if from_user else 0, 9)
        self.label = QLabel(content)
        self.label.setObjectName("messageText")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.label)

    def set_available_width(self, width: int) -> None:
        ratio = 0.72 if self.from_user else 0.80
        maximum = max(220, int(width * ratio))
        margins = self.layout().contentsMargins()
        horizontal_padding = margins.left() + margins.right()

        # QLabel's word-wrapped size hint often prefers a nearly square, very
        # narrow column. Size from the longest logical line instead, then wrap
        # only when that natural width reaches the conversation width limit.
        logical_lines = self._content.splitlines() or [self._content]
        natural_text_width = max(
            (self.label.fontMetrics().horizontalAdvance(line.expandtabs(4)) for line in logical_lines),
            default=0,
        )
        target = min(maximum, max(36, natural_text_width + horizontal_padding + 4))
        label_width = max(24, target - horizontal_padding)
        self.setFixedWidth(target)
        self.label.setFixedWidth(label_width)
        self.updateGeometry()


class ChatView(QScrollArea):
    """Chat-style conversation view without sender name tags."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("chatView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._follow_tail = True
        self._setting_scroll_position = False

        self._content = QWidget()
        self._content.setObjectName("chatContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(12, 18, 12, 18)
        self._layout.setSpacing(14)
        self._messages: list[_Message] = []

        self._thinking_row = QWidget()
        thinking_layout = QHBoxLayout(self._thinking_row)
        thinking_layout.setContentsMargins(4, 0, 0, 0)
        self.thinking_dots = ThinkingDots()
        thinking_layout.addWidget(self.thinking_dots)
        thinking_layout.addStretch(1)
        self._thinking_row.hide()
        self._layout.addWidget(self._thinking_row)
        self._layout.addStretch(1)
        self.setWidget(self._content)
        scroll_bar = self.verticalScrollBar()
        scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
        scroll_bar.actionTriggered.connect(self._on_user_scroll_action)
        scroll_bar.sliderMoved.connect(self._on_user_slider_moved)

    def add_message(self, sender: str, content: str, error: bool = False) -> None:
        from_user = sender.casefold() == "user"
        # Sending a message always follows the conversation tail. Incoming
        # replies preserve the reader's position if they intentionally
        # scrolled upward while O.R.S.I was working.
        if from_user:
            self._follow_tail = True
        message = _Message(content, from_user=from_user, error=error)
        message.set_available_width(self._message_area_width())

        row = QWidget()
        row.setObjectName("userMessageRow" if from_user else "orsiMessageRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        if from_user:
            row_layout.addStretch(1)
            row_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignLeft)
            row_layout.addStretch(1)

        # Keep the thinking indicator at the end of the conversation.
        self._layout.insertWidget(self._layout.indexOf(self._thinking_row), row)
        self._messages.append(message)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def set_thinking(self, thinking: bool) -> None:
        self._thinking_row.setVisible(thinking)
        if thinking:
            self.thinking_dots.start()
            if self._follow_tail:
                QTimer.singleShot(0, self._scroll_to_bottom)
        else:
            self.thinking_dots.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        width = self._message_area_width()
        for message in self._messages:
            message.set_available_width(width)

    def _message_area_width(self) -> int:
        return max(280, self.viewport().width() - 24)

    def _scroll_to_bottom(self) -> None:
        try:
            bar = self.verticalScrollBar()
        except RuntimeError:
            return
        self._setting_scroll_position = True
        try:
            bar.setValue(bar.maximum())
        finally:
            self._setting_scroll_position = False

    def _on_scroll_range_changed(self, minimum: int, maximum: int) -> None:
        del minimum, maximum
        # This fires after Qt has calculated the real content height, unlike
        # the original zero-delay timer which could see the previous maximum.
        if self._follow_tail:
            self._scroll_to_bottom()

    def _on_user_scroll_action(self, action: int) -> None:
        del action
        self._follow_tail = False
        QTimer.singleShot(0, self._refresh_follow_tail_from_position)

    def _on_user_slider_moved(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._follow_tail = bar.maximum() - value <= 12

    def _refresh_follow_tail_from_position(self) -> None:
        try:
            bar = self.verticalScrollBar()
        except RuntimeError:
            return
        self._follow_tail = bar.maximum() - bar.value() <= 12

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._follow_tail = False
        super().wheelEvent(event)
        QTimer.singleShot(0, self._refresh_follow_tail_from_position)
