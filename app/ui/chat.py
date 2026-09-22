from __future__ import annotations

import re

from PySide6.QtCore import QElapsedTimer, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.status import ThinkingDots


_FENCED_CODE = re.compile(
    r"^[ \t]*```([^\r\n`]*)[ \t]*\r?\n(.*?)^[ \t]*```[ \t]*(?:\r?\n|$)",
    re.MULTILINE | re.DOTALL,
)

_CONVERSATION_WIDTH = 1120


def _elapsed_label(prefix: str, seconds: float) -> str:
    return f"{prefix} for {max(0.0, seconds):.1f}s"


def _split_fenced_code(content: str) -> list[tuple[str, str, str]]:
    parts: list[tuple[str, str, str]] = []
    position = 0
    for match in _FENCED_CODE.finditer(content):
        before = content[position:match.start()].rstrip("\r\n")
        if before:
            parts.append(("text", "", before))
        language = match.group(1).strip() or "Code"
        code = match.group(2).rstrip("\r\n")
        parts.append(("code", language, code))
        position = match.end()
    after = content[position:].lstrip("\r\n")
    if after:
        parts.append(("text", "", after))
    return parts or [("text", "", content)]


class _CodeBlock(QFrame):
    def __init__(self, language: str, code: str):
        super().__init__()
        self.code = code
        self.setObjectName("codeBlock")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("codeHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)
        header_layout.setSpacing(8)

        self.language = QLabel(language)
        self.language.setObjectName("codeLanguage")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("copyCodeButton")
        self.copy_button.setToolTip("Copy code")
        self.copy_button.setAccessibleName("Copy code")
        self.copy_button.setFixedHeight(24)

        header_layout.addWidget(self.language)
        header_layout.addStretch(1)
        header_layout.addWidget(self.copy_button)
        layout.addWidget(header)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("codeEditor")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlainText(code)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.editor.setFont(fixed_font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        line_count = max(2, min(14, code.count("\n") + 1))
        editor_height = self.editor.fontMetrics().lineSpacing() * line_count + 18
        self.editor.setFixedHeight(max(60, min(300, editor_height)))
        layout.addWidget(self.editor)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._restore_copy_label)
        self.copy_button.clicked.connect(self.copy_code)

    def copy_code(self) -> None:
        QApplication.clipboard().setText(self.code)
        self.copy_button.setText("Copied")
        self._copy_timer.start(1400)

    def _restore_copy_label(self) -> None:
        self.copy_button.setText("Copy")


class _Message(QFrame):
    def __init__(self, content: str, *, from_user: bool, error: bool = False):
        super().__init__()
        self.from_user = from_user
        self._content = content
        if from_user:
            self.setObjectName("userMessage")
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAutoFillBackground(False)
        elif error:
            self.setObjectName("errorMessage")
        else:
            self.setObjectName("orsiMessage")

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        horizontal_margin = 24 if from_user else 0
        vertical_margin = 12 if from_user and "\n" in content else (9 if from_user else 0)
        layout.setContentsMargins(
            horizontal_margin,
            vertical_margin,
            horizontal_margin,
            vertical_margin,
        )
        layout.setSpacing(8)
        self._text_labels: list[QLabel] = []
        self._code_blocks: list[_CodeBlock] = []
        self.label = None

        parts = (
            [("text", "", content)]
            if from_user or error
            else _split_fenced_code(content)
        )
        for kind, language, value in parts:
            if kind == "code":
                block = _CodeBlock(language, value)
                self._code_blocks.append(block)
                layout.addWidget(block)
            else:
                label = QLabel(value)
                label.setObjectName("messageText")
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                label.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                self._text_labels.append(label)
                if self.label is None:
                    self.label = label
                layout.addWidget(label)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self.from_user:
            super().paintEvent(event)
            return
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#373943"))
        radius = min(22, max(1, self.height() // 2))
        painter.drawRoundedRect(self.rect(), radius, radius)

    def set_available_width(self, width: int) -> None:
        if self.from_user:
            ratio = 0.72 if "\n" in self._content else 0.48
        else:
            ratio = 0.80
        maximum = max(220, int(width * ratio))
        margins = self.layout().contentsMargins()
        horizontal_padding = margins.left() + margins.right()

        # QLabel's word-wrapped size hint often prefers a nearly square, very
        # narrow column. Size from the longest logical line instead, then wrap
        # only when that natural width reaches the conversation width limit.
        natural_text_width = max(
            (
                label.fontMetrics().horizontalAdvance(line.expandtabs(4))
                for label in self._text_labels
                for line in (label.text().splitlines() or [label.text()])
            ),
            default=0,
        )
        natural_code_width = max(
            (
                block.editor.fontMetrics().horizontalAdvance(line.expandtabs(4)) + 28
                for block in self._code_blocks
                for line in (block.code.splitlines() or [block.code])
            ),
            default=0,
        )
        natural_width = max(natural_text_width, natural_code_width)
        minimum = min(360, maximum) if self._code_blocks else 36
        target = min(maximum, max(minimum, natural_width + horizontal_padding + 4))
        if self.from_user and "\n" in self._content:
            target = maximum
        content_width = max(24, target - horizontal_padding)
        self.setFixedWidth(target)
        for label in self._text_labels:
            label.setFixedWidth(content_width)
            bounds = label.fontMetrics().boundingRect(
                QRect(0, 0, content_width, 100_000),
                int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs),
                label.text(),
            )
            height_padding = max(2, label.fontMetrics().descent())
            label.setFixedHeight(
                max(label.fontMetrics().lineSpacing(), bounds.height()) + height_padding
            )
        for block in self._code_blocks:
            block.setFixedWidth(content_width)
        self.updateGeometry()


class _MessageBand(QWidget):
    """One message plus its quiet, hover-revealed actions."""

    def __init__(
        self,
        message: _Message,
        *,
        from_user: bool,
        duration_seconds: float | None,
    ):
        super().__init__()
        self.message = message
        self.setObjectName("conversationBand")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.meta_row = QWidget()
        self.meta_row.setObjectName("messageMetaRow")
        self.meta_row.setFixedHeight(25)
        meta_layout = QHBoxLayout(self.meta_row)
        meta_layout.setContentsMargins(2, 0, 2, 0)
        meta_layout.setSpacing(8)

        self.timing_label = QLabel()
        self.timing_label.setObjectName("responseTiming")
        if not from_user and duration_seconds is not None:
            self.timing_label.setText(_elapsed_label("Worked", duration_seconds))
            meta_layout.addWidget(self.timing_label)
        else:
            self.timing_label.hide()
        meta_layout.addStretch(1)

        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("copyMessageButton")
        self.copy_button.setToolTip("Copy message")
        self.copy_button.setAccessibleName("Copy message")
        self.copy_button.setFixedSize(52, 23)
        self.copy_button.hide()
        if from_user:
            meta_layout.addWidget(self.copy_button)
        if from_user or duration_seconds is not None:
            layout.addWidget(self.meta_row)
        else:
            self.meta_row.hide()

        body = QWidget()
        body.setObjectName("messageBodyRow")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        if from_user:
            body_layout.addStretch(1)
            body_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignRight)
        else:
            body_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignLeft)
            body_layout.addStretch(1)
        layout.addWidget(body)

        self.action_row = QWidget()
        self.action_row.setObjectName("messageActionRow")
        self.action_row.setFixedHeight(25)
        action_layout = QHBoxLayout(self.action_row)
        action_layout.setContentsMargins(2, 0, 2, 0)
        action_layout.setSpacing(8)
        if from_user:
            self.action_row.hide()
        else:
            action_layout.addWidget(self.copy_button)
            action_layout.addStretch(1)
            layout.addWidget(self.action_row)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._restore_copy_label)
        self.copy_button.clicked.connect(self.copy_message)

    def set_available_width(self, width: int) -> None:
        self.setFixedWidth(width)
        self.message.set_available_width(width)

    def copy_message(self) -> None:
        QApplication.clipboard().setText(self.message._content)
        self.copy_button.setText("Copied")
        self.copy_button.show()
        self._copy_timer.start(1400)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.copy_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        QTimer.singleShot(0, self._hide_copy_button_if_idle)

    def _hide_copy_button_if_idle(self) -> None:
        if not self.underMouse() and not self.copy_button.underMouse():
            self.copy_button.hide()

    def _restore_copy_label(self) -> None:
        self.copy_button.setText("Copy")
        if not self.underMouse() and not self.copy_button.underMouse():
            self.copy_button.hide()


class ChatView(QScrollArea):
    """Chat-style conversation view without sender name tags."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("chatView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.viewport().setAutoFillBackground(False)
        self._follow_tail = True
        self._setting_scroll_position = False

        self._content = QWidget()
        self._content.setObjectName("chatContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._content.setAutoFillBackground(False)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 55, 0, 170)
        self._layout.setSpacing(40)
        self._messages: list[_Message] = []
        self._message_rows: list[QWidget] = []
        self._message_bands: list[_MessageBand] = []

        self._thinking_row = QWidget()
        self._thinking_layout = QVBoxLayout(self._thinking_row)
        self._thinking_layout.setContentsMargins(4, 0, 0, 0)
        self._thinking_layout.setSpacing(1)
        self.working_label = QLabel("Working for 0.0s")
        self.working_label.setObjectName("responseTiming")
        self.thinking_dots = ThinkingDots()
        self._thinking_layout.addWidget(
            self.working_label,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self._thinking_layout.addWidget(
            self.thinking_dots,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self._thinking_row.hide()
        self._response_elapsed = QElapsedTimer()
        self._response_timer = QTimer(self)
        self._response_timer.setInterval(100)
        self._response_timer.timeout.connect(self._update_working_label)
        self._layout.addWidget(self._thinking_row)
        self._layout.addStretch(1)
        self.setWidget(self._content)
        scroll_bar = self.verticalScrollBar()
        scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
        scroll_bar.actionTriggered.connect(self._on_user_scroll_action)
        scroll_bar.sliderMoved.connect(self._on_user_slider_moved)

    def add_message(
        self,
        sender: str,
        content: str,
        error: bool = False,
        *,
        duration_seconds: float | None = None,
    ) -> None:
        from_user = sender.casefold() == "user"
        # Sending a message always follows the conversation tail. Incoming
        # replies preserve the reader's position if they intentionally
        # scrolled upward while O.R.S.I was working.
        if from_user:
            self._follow_tail = True
        message = _Message(content, from_user=from_user, error=error)
        band_width = self._message_area_width()

        row = QWidget()
        row.setObjectName("userMessageRow" if from_user else "orsiMessageRow")
        row_layout = QHBoxLayout(row)
        left_margin, right_margin = self._column_margins()
        row_layout.setContentsMargins(left_margin, 0, right_margin, 0)
        row_layout.setSpacing(0)

        band = _MessageBand(
            message,
            from_user=from_user,
            duration_seconds=duration_seconds,
        )
        row_layout.addStretch(1)
        row_layout.addWidget(band)
        row_layout.addStretch(1)

        # Keep the thinking indicator at the end of the conversation.
        self._layout.insertWidget(self._layout.indexOf(self._thinking_row), row)
        message.ensurePolished()
        for label in message._text_labels:
            label.ensurePolished()
        band.set_available_width(band_width)
        self._messages.append(message)
        self._message_rows.append(row)
        self._message_bands.append(band)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_messages(self) -> None:
        self.set_thinking(False)
        for row in self._message_rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._message_rows.clear()
        self._message_bands.clear()
        self._messages.clear()
        self._follow_tail = True
        QTimer.singleShot(0, self._scroll_to_bottom)

    def set_thinking(self, thinking: bool) -> float | None:
        self._thinking_row.setVisible(thinking)
        if thinking:
            self._response_elapsed.start()
            self._update_working_label()
            self._response_timer.start()
            self.thinking_dots.start()
            if self._follow_tail:
                QTimer.singleShot(0, self._scroll_to_bottom)
            return None
        elapsed = (
            self._response_elapsed.elapsed() / 1000.0
            if self._response_elapsed.isValid()
            else None
        )
        self._response_timer.stop()
        self._response_elapsed.invalidate()
        self.thinking_dots.stop()
        return elapsed

    def _update_working_label(self) -> None:
        elapsed = (
            self._response_elapsed.elapsed() / 1000.0
            if self._response_elapsed.isValid()
            else 0.0
        )
        self.working_label.setText(_elapsed_label("Working", elapsed))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        left_margin, right_margin = self._column_margins()
        width = self._message_area_width()
        for message, band, row in zip(
            self._messages,
            self._message_bands,
            self._message_rows,
        ):
            row.layout().setContentsMargins(left_margin, 0, right_margin, 0)
            band.set_available_width(width)
        column_width = self.viewport().width() - left_margin - right_margin
        left = max(4, left_margin + (column_width - width) // 2)
        right = max(0, self.viewport().width() - left - width)
        self._thinking_layout.setContentsMargins(left + 4, 0, right, 0)

    def _message_area_width(self) -> int:
        left_margin, right_margin = self._column_margins()
        available = self.viewport().width() - left_margin - right_margin - 32
        return min(_CONVERSATION_WIDTH, max(280, available))

    def _column_margins(self) -> tuple[int, int]:
        return 0, 0

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
