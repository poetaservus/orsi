from __future__ import annotations

import re

from PySide6.QtCore import QRect, QTimer, Qt
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
        horizontal_margin = 30 if from_user else 0
        vertical_margin = 18 if from_user and "\n" in content else (14 if from_user else 0)
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
        painter.setBrush(QColor("#3c3e49"))
        radius = min(27, max(1, self.height() // 2))
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
            label.setFixedHeight(max(label.fontMetrics().lineSpacing(), bounds.height()))
        for block in self._code_blocks:
            block.setFixedWidth(content_width)
        self.updateGeometry()


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
        self._message_bands: list[QWidget] = []

        self._thinking_row = QWidget()
        self._thinking_layout = QHBoxLayout(self._thinking_row)
        self._thinking_layout.setContentsMargins(4, 0, 0, 0)
        self.thinking_dots = ThinkingDots()
        self._thinking_layout.addWidget(self.thinking_dots)
        self._thinking_layout.addStretch(1)
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
        band_width = self._message_area_width()

        row = QWidget()
        row.setObjectName("userMessageRow" if from_user else "orsiMessageRow")
        row_layout = QHBoxLayout(row)
        left_margin, right_margin = self._column_margins()
        row_layout.setContentsMargins(left_margin, 0, right_margin, 0)
        row_layout.setSpacing(0)

        band = QWidget()
        band.setObjectName("conversationBand")
        band.setFixedWidth(band_width)
        band.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        band_layout = QHBoxLayout(band)
        band_layout.setContentsMargins(0, 0, 0, 0)
        band_layout.setSpacing(0)
        if from_user:
            band_layout.addStretch(1)
            band_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignRight)
        else:
            band_layout.addWidget(message, 0, Qt.AlignmentFlag.AlignLeft)
            band_layout.addStretch(1)
        row_layout.addStretch(1)
        row_layout.addWidget(band)
        row_layout.addStretch(1)

        # Keep the thinking indicator at the end of the conversation.
        self._layout.insertWidget(self._layout.indexOf(self._thinking_row), row)
        message.ensurePolished()
        for label in message._text_labels:
            label.ensurePolished()
        message.set_available_width(band_width)
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
        left_margin, right_margin = self._column_margins()
        width = self._message_area_width()
        for message, band, row in zip(
            self._messages,
            self._message_bands,
            self._message_rows,
        ):
            row.layout().setContentsMargins(left_margin, 0, right_margin, 0)
            band.setFixedWidth(width)
            message.set_available_width(width)
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
