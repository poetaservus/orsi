from __future__ import annotations
from app.ui.localization import ui_extra, ui_text, QFrame, QLabel, QPlainTextEdit, QScrollArea, QWidget, QPushButton


import re
from html import escape

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout)

from app.ui.status import ThinkingDots, progress_sentence
from app.ui.progress_timeline import ProgressTimeline
from app.runtime.semantic_progress import ProgressPhase
from app.ui.code_highlighting import CodeHighlighter
from app.ui.copy_button import CopyButton
from app.ui.markdown import MarkdownLabel
from app.ui.message_images import MessageImageLoader, MessageImageStrip
from app.ui.motion import install_smooth_scroll
from app.inference.completion import CompletionMetadata
from app.inference.attachments import attachment_references
from app.ui.theme_runtime import apply_theme_style, apply_theme_tree, theme_color


_FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})([^\r\n]*)(?:\r?\n|$)", re.MULTILINE)

_CONVERSATION_WIDTH = 1120


def _elapsed_label(prefix: str, seconds: float) -> str:
    hours, remainder = divmod(int(max(0.0, seconds)), 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    duration = ui_extra("{seconds}s", seconds=remaining_seconds)
    if hours:
        duration = ui_extra("{hours} h {minutes} m {seconds}s", hours=hours, minutes=minutes, seconds=remaining_seconds)
    elif minutes:
        duration = ui_extra("{minutes} m {seconds}s", minutes=minutes, seconds=remaining_seconds)
    if prefix == "Working":
        return ui_extra("Working for {duration}", duration=duration)
    if prefix == "Worked":
        return ui_extra("Worked for {duration}", duration=duration)
    if prefix == "Stopped":
        return ui_extra("Stopped for {duration}", duration=duration)
    return f"{prefix} for {duration}"


def _split_fenced_code(content: str) -> list[tuple[str, str, str]]:
    parts: list[tuple[str, str, str]] = []
    position = 0
    while match := _FENCE_OPEN.search(content, position):
        before = content[position:match.start()].rstrip("\r\n")
        if before:
            parts.append(("text", "", before))
        fence = match.group(1)
        language = match.group(2).strip() or "Code"
        closing = re.compile(r"^[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence))
                             + r",}[ \t]*(?:\r?\n|$)", re.MULTILINE).search(content, match.end())
        if closing is None:
            parts.append(("incomplete_code", language, content[match.end():]))
            position = len(content)
            break
        parts.append(("code", language, content[match.end():closing.start()].rstrip("\r\n")))
        position = closing.end()
    after = content[position:].lstrip("\r\n")
    if after:
        parts.append(("text", "", after))
    return parts or [("text", "", content)]


class _CodeBlock(QFrame):
    def __init__(self, language: str, code: str, *, incomplete: bool = False):
        super().__init__()
        self.code = code
        self.incomplete = incomplete
        self.setObjectName("codeBlock")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("codeHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 7, 10, 7)
        header_layout.setSpacing(8)

        self.language = QLabel(ui_text('{value_0} · Incomplete', value_0=language) if incomplete else language)
        self.language.setObjectName("codeLanguage")
        self.copy_button = CopyButton("Copy code")
        self.copy_button.setObjectName("copyCodeButton")
        self.copy_button.setFixedSize(28, 28)

        header_layout.addWidget(self.language)
        header_layout.addStretch(1)
        header_layout.addWidget(self.copy_button)
        layout.addWidget(header)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("codeEditor")
        self.editor.setReadOnly(True)
        install_smooth_scroll(self.editor)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlainText(code)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSizeF(10.5)
        self.editor.setFont(fixed_font)
        self.highlighter = CodeHighlighter(self.editor.document(), language)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        line_count = max(2, min(14, code.count("\n") + 1))
        metrics = self.editor.fontMetrics()
        editor_height = max(metrics.height(), metrics.lineSpacing()) * line_count + 36
        self.editor.setFixedHeight(max(76, min(320, editor_height)))
        layout.addWidget(self.editor)

        self.copy_button.clicked.connect(self.copy_code)

    def copy_code(self) -> None:
        self.copy_button.copy_text(self.code)


class _Message(QFrame):
    def __init__(self, content: str, *, from_user: bool, error: bool = False, attachments=(), images=(), image_loader=None, generation_frame=None):
        super().__init__()
        self.from_user = from_user
        self._content = content
        self.attachments = attachment_references(attachments) if from_user else ()
        self.completion = getattr(content, "completion", CompletionMetadata())
        self.completion_history = getattr(content, "completion_history", ())
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
        horizontal_margin = 16 if from_user else 0
        vertical_margin = 10 if from_user else 0
        layout.setContentsMargins(
            horizontal_margin,
            vertical_margin,
            horizontal_margin,
            vertical_margin,
        )
        layout.setSpacing(8)
        self._text_labels: list[QLabel | MarkdownLabel] = []
        self._code_blocks: list[_CodeBlock] = []
        self.label = None
        images = (tuple(ref for ref in self.attachments if ref.kind == "image")
                  if from_user else attachment_references(images))
        if any(ref.kind != "image" for ref in images):
            raise ValueError("Displayed output images must be saved image references.")
        self.image_strip = generation_frame or (MessageImageStrip(images, image_loader, preserve_aspect=not from_user)
                                                if images and image_loader else None)
        self.result_thumbnails = None
        if self.image_strip is not None:
            layout.addWidget(self.image_strip)
        if generation_frame is not None and len(images) > 1:
            self.result_thumbnails = MessageImageStrip(images, image_loader)
            layout.addWidget(self.result_thumbnails)
        for reference in self.attachments:
            if reference.kind == "image" and self.image_strip is not None:
                continue
            attachment = QLabel(("Image · " if reference.kind == "image" else "File · ") + reference.name)
            attachment.setObjectName("messageAttachment")
            attachment.setTextFormat(Qt.TextFormat.PlainText)
            attachment.setWordWrap(True)
            apply_theme_style(attachment, "color: #b1b8c8; font-size: 12px; padding: 3px 0;")
            attachment.setToolTip(ui_text('{value_0} · {value_1} bytes', value_0=reference.name, value_1=format(reference.size_bytes,',')))
            self._text_labels.append(attachment)
            layout.addWidget(attachment)

        parts = (
            [("text", "", content)]
            if from_user or (error and not self.completion.incomplete)
            else _split_fenced_code(content)
        )
        self.completion_label = None
        if not from_user and (self.completion.incomplete or any(kind == "incomplete_code" for kind, _, _ in parts)):
            indication = (ui_text("Task stopped locally before completion.")
                          if self.completion.finish_reason == "agent_recovery_stop" else
                          ui_text("Incomplete — output limit reached. Partial response.")
                          if self.completion.finish_reason == "length" else
                          ui_text("Incomplete response.") if self.completion.incomplete else
                          ui_text("Incomplete code block — closing fence missing."))
            if getattr(content, "status_message", None):
                indication = ui_text("{indication}\n{detail}", indication=indication, detail=content.status_message)
            elif self.completion.failure_message and self.completion.failure_message not in content:
                indication = ui_text("{indication}\n{detail}", indication=indication, detail=self.completion.failure_message)
            self.completion_label = QLabel(indication)
            self.completion_label.setObjectName("incompleteResponse")
            self.completion_label.setWordWrap(True)
            self.completion_label.setTextFormat(Qt.TextFormat.PlainText)
            self.completion_label.setToolTip(
                ui_text('Finish reason: {value_0}\nFailure reason: {value_1}\nInput tokens: {value_2}\nOutput tokens: {value_3}\nTotal tokens: {value_4}', value_0=self.completion.finish_reason or 'not supplied', value_1=self.completion.failure_reason or 'not supplied', value_2=self.completion.usage.input_tokens, value_3=self.completion.usage.output_tokens, value_4=self.completion.usage.total_tokens))
            layout.addWidget(self.completion_label)
        for kind, language, value in parts:
            if kind in {"code", "incomplete_code"}:
                block = _CodeBlock(language, value, incomplete=kind == "incomplete_code")
                self._code_blocks.append(block)
                layout.addWidget(block)
            else:
                formatted = not from_user and (not error or self.completion.incomplete)
                label = MarkdownLabel(value) if formatted else QLabel(value)
                label.setObjectName("messageText")
                if not formatted:
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
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        glass = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        glass.setColorAt(0, theme_color(self, QColor(46, 58, 85, 210), "user_bubble_top"))
        glass.setColorAt(1, theme_color(self, QColor(38, 42, 60, 212), "user_bubble_bottom"))
        painter.setPen(QPen(theme_color(self, QColor(170, 190, 232, 55), "user_bubble_border"), 1))
        painter.setBrush(glass)
        radius = min(12, max(1, self.height() / 2))
        painter.drawRoundedRect(bounds, radius, radius)

    def set_available_width(self, width: int, *, minimum_width: int = 0) -> None:
        if self.from_user:
            ratio = 0.72 if "\n" in self._content else 0.48
        else:
            ratio = 0.80
        maximum = max(220, int(width * ratio))
        margins = self.layout().contentsMargins()
        horizontal_padding = margins.left() + margins.right()
        labels = self._text_labels + (
            [self.completion_label] if self.completion_label is not None else []
        )
        for label in labels:
            if isinstance(label, MarkdownLabel):
                label.refresh_formatting()

        # QLabel's word-wrapped size hint often prefers a nearly square, very
        # narrow column. Size from the longest logical line instead, then wrap
        # only when that natural width reaches the conversation width limit.
        natural_text_width = max(
            (
                label.fontMetrics().horizontalAdvance(line.expandtabs(4))
                + (2 * label.document.documentMargin() if isinstance(label, MarkdownLabel) else 0)
                for label in labels
                for line in ((label.plain_text() if isinstance(label, MarkdownLabel) else label.text()).splitlines()
                             or [""])
            ),
            default=0,
        )
        natural_code_width = max(
            (
                block.editor.fontMetrics().horizontalAdvance(line.expandtabs(4)) + 44
                for block in self._code_blocks
                for line in (block.code.splitlines() or [block.code])
            ),
            default=0,
        )
        image_width = self.image_strip.natural_width if self.image_strip is not None else 0
        natural_width = max(natural_text_width, natural_code_width, image_width)
        minimum = min(360, maximum) if self._code_blocks else max(36, horizontal_padding + 24)
        minimum = min(maximum, max(minimum, minimum_width))
        target = min(maximum, max(minimum, natural_width + horizontal_padding + 4))
        if self.from_user:
            # Wrap at the normal width cap, then fit the bubble to the widest
            # rendered line. Word wrapping often leaves unused space before the
            # next word; that space should not inflate the bubble's right edge.
            wrap_width = max(24, target - horizontal_padding)
            wrapped_width = max(
                label.fontMetrics().boundingRect(
                    QRect(0, 0, wrap_width, 100_000),
                    int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs),
                    label.text(),
                ).width()
                for label in self._text_labels
            )
            target = min(target, max(minimum, max(wrapped_width, image_width) + horizontal_padding + 4))
        content_width = max(24, target - horizontal_padding)
        self.setFixedWidth(target)
        if self.image_strip is not None:
            self.image_strip.set_available_width(content_width)
        if self.result_thumbnails is not None:
            self.result_thumbnails.set_available_width(content_width)
        for label in labels:
            label.setFixedWidth(content_width)
            if isinstance(label, MarkdownLabel):
                # Rich text includes paragraph margins, list indents and heading sizes.
                label.setFixedHeight(max(label.fontMetrics().lineSpacing(),
                                         label.heightForWidth(content_width))
                                     + max(2, label.fontMetrics().descent()))
                continue
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
        skill_name: str | None = None,
    ):
        super().__init__()
        self.message = message
        self.from_user = from_user
        self.skill_name = skill_name if from_user else None
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
        self.skill_label = QLabel(self.meta_row)
        self.skill_label.setObjectName("userSkill")
        self.skill_label.setTextFormat(Qt.TextFormat.PlainText)
        self.skill_label.setAccessibleName(ui_text('Skill used for this message'))
        if from_user:
            meta_layout.addWidget(self.skill_label)
        self.skill_label.setVisible(bool(self.skill_name))
        self.timing_label.setObjectName("responseTiming")
        if not from_user and duration_seconds is not None:
            self.timing_label.setText(_elapsed_label(
                "Stopped" if message.completion.incomplete else "Worked", duration_seconds))
            meta_layout.addWidget(self.timing_label)
        else:
            self.timing_label.hide()
        meta_layout.addStretch(1)

        self.copy_button = CopyButton("Copy message")
        self.copy_button.setObjectName("copyMessageButton")
        self.copy_button.setFixedSize(28, 23)
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

        self.copy_button.feedback_finished.connect(self._hide_copy_button_if_idle)
        self.copy_button.clicked.connect(self.copy_message)

    def set_available_width(self, width: int) -> None:
        self.setFixedWidth(width)
        self.skill_label.ensurePolished()
        caption = "/" + " ".join(self.skill_name.split()) if self.skill_name else ""
        caption_width = min(210, self.skill_label.fontMetrics().horizontalAdvance(caption))
        minimum = caption_width + 40 if caption else 0
        self.message.set_available_width(width, minimum_width=minimum)
        if self.from_user:
            self.meta_row.layout().setContentsMargins(width - self.message.width() + 2, 0, 2, 0)
        available = max(1, self.message.width() - 40)
        self.skill_label.setMaximumWidth(available)
        self.skill_label.setText(self.skill_label.fontMetrics().elidedText(caption, Qt.TextElideMode.ElideRight, available))
        self.skill_label.setToolTip("<qt>" + escape(caption) + "</qt>" if caption else "")

    def set_skill_name(self, name: str) -> None:
        if not self.from_user:
            return
        self.skill_name = name
        self.skill_label.show()
        self.set_available_width(self.width())

    def copy_message(self) -> None:
        if self.copy_button.copy_text(self.message._content):
            self.copy_button.show()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.copy_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        QTimer.singleShot(0, self._hide_copy_button_if_idle)

    def _hide_copy_button_if_idle(self) -> None:
        if (not self.copy_button.copy_succeeded
                and not self.underMouse() and not self.copy_button.underMouse()):
            self.copy_button.hide()


class ChatView(QScrollArea):
    """Chat-style conversation view without sender name tags."""

    image_activated = Signal(object, int)

    def __init__(self, parent: QWidget | None = None, *, attachment_store=None):
        super().__init__(parent)
        self.image_loader = MessageImageLoader(attachment_store, self) if attachment_store is not None else None
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
        self.generation_frame = None

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
        self._narrative_rows = []
        self._active_timeline = None
        self._standalone_activity_rows = []

        self._response_elapsed = QElapsedTimer()
        self._response_timer = QTimer(self)
        self._response_timer.setInterval(100)
        self._response_timer.timeout.connect(self._update_working_label)
        self.semantic_progress_enabled = False
        self._create_activity_row()
        self._layout.addStretch(1)
        self.setWidget(self._content)
        scroll_bar = self.verticalScrollBar()
        scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
        scroll_bar.actionTriggered.connect(self._on_user_scroll_action)
        scroll_bar.sliderMoved.connect(self._on_user_slider_moved)
        scroll_bar.valueChanged.connect(self._sync_generation_visibility)
        scrolling = install_smooth_scroll(self)
        scrolling.started.connect(self._begin_smooth_scroll)
        scrolling.finished.connect(self._refresh_follow_tail_from_position)

    def _create_activity_row(self):
        """One compact task header, retained with its answer after completion."""
        self._activity_attached = False
        self._active_timeline = None
        self._activity_row = QWidget()
        self._activity_row.setObjectName("taskProgressGroup")
        self._activity_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._activity_layout = QVBoxLayout(self._activity_row)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        self._activity_layout.setSpacing(4)
        self._thinking_row = QWidget()
        self._thinking_layout = QVBoxLayout(self._thinking_row)
        self._thinking_layout.setContentsMargins(4, 0, 0, 0)
        self._thinking_layout.setSpacing(6)
        self.working_label = QLabel(ui_text('Working for 0s'))
        self.working_label.setObjectName("responseTiming")
        self.activity_label = QLabel()
        self.activity_label.setObjectName("workingActivity")
        self.activity_label.setTextFormat(Qt.TextFormat.PlainText)
        self.activity_label.setWordWrap(True)
        self.activity_label.setAccessibleName(ui_text('Current activity'))
        self.thinking_dots = ThinkingDots()
        self.stream_preview = QLabel()
        self.stream_preview.setObjectName("streamPreview")
        self.stream_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.stream_preview.setWordWrap(True)
        self.stream_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stream_preview.hide()
        self._thinking_layout.addWidget(
            self.working_label,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self._thinking_layout.addWidget(self.activity_label)
        self._thinking_layout.addWidget(
            self.thinking_dots,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self._thinking_row.hide()
        self._thinking_layout.addWidget(self.stream_preview)
        self._technical_row = QWidget()
        self._technical_layout = QVBoxLayout(self._technical_row)
        self._technical_layout.setContentsMargins(4, 0, 0, 0)
        self.technical_toggle = QPushButton(ui_extra("Technical details"))
        self.technical_toggle.setCheckable(True)
        self.technical_toggle.setFlat(True)
        apply_theme_style(self.technical_toggle, """
            QPushButton { background: transparent; color: #b1b8c8; border: 1px solid transparent;
                border-radius: 4px; padding: 4px 0; font-size: 11px; text-align: left; outline: none; }
            QPushButton:hover, QPushButton:checked { color: #eeeeef; }
        """)
        self.technical_details = QPlainTextEdit()
        self.technical_details.setReadOnly(True)
        self.technical_details.setMaximumBlockCount(100)
        self.technical_details.setMaximumHeight(120)
        self.technical_details.setAccessibleName(ui_extra("Technical details"))
        apply_theme_style(self.technical_details, """
            QPlainTextEdit { background: #151722; color: #c7cad2; border: 1px solid #494d60;
                border-radius: 6px; padding: 6px; font-size: 11px; }
        """)
        self.technical_details.hide()
        self.technical_toggle.toggled.connect(self.technical_details.setVisible)
        self._technical_layout.addWidget(self.technical_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self._technical_layout.addWidget(self.technical_details)
        self._technical_row.hide()
        self._activity_layout.addWidget(self._technical_row)
        self._activity_layout.addWidget(self._thinking_row)
        self._activity_row.hide()
        self._layout.insertWidget(max(0, self._layout.count() - 1), self._activity_row)
        self._update_activity_margins()

    def _update_activity_margins(self):
        left_margin, right_margin = self._column_margins()
        width = self._message_area_width()
        column_width = self.viewport().width() - left_margin - right_margin
        left = max(4, left_margin + (column_width - width) // 2)
        right = max(0, self.viewport().width() - left - width)
        inset_left, inset_right = (4, 0) if self._activity_attached else (left + 4, right)
        self._thinking_layout.setContentsMargins(inset_left, 0, inset_right, 0)
        self._technical_layout.setContentsMargins(inset_left, 0, inset_right, 0)

    def _message_insert_index(self):
        index = self._layout.indexOf(self._activity_row)
        return index if index >= 0 else self._layout.count() - 1

    def _has_task_activity(self):
        return bool(self.technical_details.toPlainText() or
                    self._active_timeline is not None and self._active_timeline.entries)

    def set_composer_clearance(self, height: int) -> None:
        margins = self._layout.contentsMargins()
        self._layout.setContentsMargins(margins.left(), margins.top(), margins.right(), max(170, height))

    def add_message(
        self,
        sender: str,
        content: str,
        error: bool = False,
        *,
        duration_seconds: float | None = None,
        skill_name: str | None = None,
        attachments=(),
        images=(),
        generation_frame=None,
    ) -> _MessageBand:
        from_user = sender.casefold() == "user"
        # Sending a message always follows the conversation tail. Incoming
        # replies preserve the reader's position if they intentionally
        # scrolled upward while O.R.S.I was working.
        if from_user:
            self._follow_tail = True
            # A question can finish a turn without adding an answer bubble.
            # Leave its progress before the next user message as well.
            if (not self._activity_attached and not self._response_elapsed.isValid()
                    and self._has_task_activity()):
                self._standalone_activity_rows.append(self._activity_row)
                self._create_activity_row()
        message = _Message(content, from_user=from_user, error=error, attachments=attachments, images=images,
                           image_loader=self.image_loader, generation_frame=generation_frame)
        if message.image_strip is not None:
            message.image_strip.image_activated.connect(self.image_activated)
        if message.result_thumbnails is not None:
            message.result_thumbnails.image_activated.connect(self.image_activated)
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
            skill_name=skill_name,
        )
        row_layout.addStretch(1)
        row_layout.addWidget(band)
        row_layout.addStretch(1)

        if (not from_user and duration_seconds is not None and self.semantic_progress_enabled
                and not self._activity_attached and self._has_task_activity()):
            self._layout.removeWidget(self._activity_row)
            band.layout().insertWidget(0, self._activity_row)
            self._activity_attached = True
            self._update_activity_margins()
        self._layout.insertWidget(self._message_insert_index(), row)
        apply_theme_tree(row)
        message.ensurePolished()
        for label in message._text_labels:
            label.ensurePolished()
        if message.completion_label is not None:
            message.completion_label.ensurePolished()
        band.set_available_width(band_width)
        self._messages.append(message)
        self._message_rows.append(row)
        self._message_bands.append(band)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)
        return band

    def refresh_theme(self):
        """Reflow existing text after a family change without moving the reader."""
        scroll = self.verticalScrollBar()
        value, follow = scroll.value(), self._follow_tail
        for _, timeline in self._narrative_rows:
            timeline.set_available_width(self._message_area_width())
        if not self._message_bands:
            return
        for band in self._message_bands:
            band.set_available_width(self._message_area_width())
        self._layout.activate()
        self._follow_tail = follow
        def restore():
            if follow:
                self._scroll_to_bottom()
            else:
                scroll.setValue(min(value, scroll.maximum()))
        restore()
        QTimer.singleShot(0, restore)

    def set_message_skill(self, band: _MessageBand, name: str) -> None:
        if band not in self._message_bands:
            return
        band.set_skill_name(name)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def remove_message(self, band):
        """Remove an unsaved submitted bubble when its draft is restored."""
        if band not in self._message_bands:
            return
        index = self._message_bands.index(band)
        row = self._message_rows.pop(index)
        self._message_bands.pop(index)
        self._messages.pop(index)
        self._layout.removeWidget(row)
        row.deleteLater()

    def clear_messages(self) -> None:
        self.smooth_scroll.stop()
        self.set_thinking(False)
        self._clear_technical_details()
        for row, _ in self._narrative_rows:
            row.parentWidget().layout().removeWidget(row)
            row.deleteLater()
        self._narrative_rows.clear()
        self._active_timeline = None
        for row in self._standalone_activity_rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._standalone_activity_rows.clear()
        if self.generation_frame is not None:
            self.generation_frame.stop()
            self.generation_frame.deleteLater()
            self.generation_frame = None
        if self.image_loader is not None:
            self.image_loader.clear()
        for row in self._message_rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._message_rows.clear()
        self._message_bands.clear()
        self._messages.clear()
        if self._activity_attached:
            self._create_activity_row()
        self._activity_row.hide()
        self._follow_tail = True
        QTimer.singleShot(0, self._scroll_to_bottom)

    def start_image_generation(self, aspect_ratio=1.0):
        if self.image_loader is None or self.generation_frame is not None:
            return
        from app.ui.generated_image_frame import GeneratedImageFrame
        self.generation_frame = GeneratedImageFrame(aspect_ratio=aspect_ratio)
        self._thinking_layout.insertWidget(self._thinking_layout.count() - 1, self.generation_frame,
                                           alignment=Qt.AlignmentFlag.AlignLeft)
        self.generation_frame.start()
        self.activity_label.hide()
        self.thinking_dots.stop()
        self.thinking_dots.hide()
        QTimer.singleShot(0, self._sync_generation_visibility)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _sync_generation_visibility(self, *_):
        frame = self.generation_frame
        if frame is not None:
            bounds = frame.rect().translated(frame.mapTo(self.viewport(), QPoint(0, 0)))
            frame.set_occluded(not bounds.intersects(self.viewport().rect()))

    def take_generation_frame(self, images=(), *, status=""):
        frame, self.generation_frame = self.generation_frame, None
        if frame is None:
            return None
        self._thinking_layout.removeWidget(frame)
        frame.setParent(None)
        frame.set_occluded(False)
        if images:
            frame.show_result(images, self.image_loader)
        else:
            frame.stop(status or "Image generation stopped")
        return frame

    def set_thinking(self, thinking: bool) -> float | None:
        if thinking and self._activity_attached:
            self._create_activity_row()
        self.stream_preview.clear()
        self.stream_preview.hide()
        self._thinking_row.setVisible(thinking)
        if thinking:
            self._activity_row.show()
            self._active_timeline = None
            self.activity_label.show()
            self.thinking_dots.show()
            self.activity_label.setText(progress_sentence(ProgressPhase.PREPARE)
                if self.semantic_progress_enabled else ui_text('Preparing your request…'))
            self._clear_technical_details()
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
        self.activity_label.clear()
        self._activity_row.setVisible(self._has_task_activity())
        return elapsed

    def set_activity(self, text: str) -> None:
        if not self._response_elapsed.isValid():
            return
        self.activity_label.setText(text)
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def record_activity(self, text):
        if self.semantic_progress_enabled and self._response_elapsed.isValid():
            self.technical_details.appendPlainText(text[:512])
            self._technical_row.show()

    def append_narrative(self, item):
        if not self.semantic_progress_enabled or not self._response_elapsed.isValid():
            return
        if item.operation is None and not item.text.strip():
            return
        if self._active_timeline is None:
            row = QWidget()
            layout = QHBoxLayout(row)
            left, right = self._column_margins()
            layout.setContentsMargins(left, 0, right, 0)
            layout.setSpacing(0)
            timeline = ProgressTimeline()
            layout.addStretch()
            layout.addWidget(timeline)
            layout.addStretch()
            self._activity_layout.insertWidget(self._activity_layout.indexOf(self._technical_row), row)
            self._narrative_rows.append((row, timeline))
            self._active_timeline = timeline
            if len(self._narrative_rows) > 20:
                oldest, _ = self._narrative_rows.pop(0)
                oldest.parentWidget().layout().removeWidget(oldest)
                oldest.deleteLater()
        if self._active_timeline.append(item):
            self._active_timeline.set_available_width(self._message_area_width())
            self.activity_label.hide()
            if item.operation is None:
                self.stream_preview.clear()
                self.stream_preview.hide()
            if self._follow_tail:
                QTimer.singleShot(0, self._scroll_to_bottom)

    def _clear_technical_details(self):
        self.technical_toggle.setChecked(False)
        self.technical_details.clear()
        self._technical_row.hide()

    def set_stream_preview(self, text: str) -> None:
        # Empty provider events start a new stream, not a new user turn. Keep
        # the proposed answer through review/continued work until replacement.
        if not self._response_elapsed.isValid() or not text:
            return
        self.stream_preview.setText(text)
        if text and not self.semantic_progress_enabled:
            self.set_activity(ui_text('Writing reply…'))
        self.stream_preview.setVisible(bool(text))
        if self._follow_tail:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _update_working_label(self) -> None:
        elapsed = (
            self._response_elapsed.elapsed() / 1000.0
            if self._response_elapsed.isValid()
            else 0.0
        )
        self.working_label.setText(_elapsed_label("Working", elapsed))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.set_thinking(False)
        super().closeEvent(event)

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
        self._update_activity_margins()
        for row, timeline in self._narrative_rows:
            row.layout().setContentsMargins(left_margin, 0, right_margin, 0)
            timeline.set_available_width(width)

    def _message_area_width(self) -> int:
        left_margin, right_margin = self._column_margins()
        available = self.viewport().width() - left_margin - right_margin - 32
        return min(_CONVERSATION_WIDTH, max(280, available))

    def _column_margins(self) -> tuple[int, int]:
        return 0, 0

    def _scroll_to_bottom(self) -> None:
        if not self._follow_tail:
            return
        try:
            bar = self.verticalScrollBar()
        except RuntimeError:
            return
        self._setting_scroll_position = True
        try:
            self.smooth_scroll.stop()
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

    def _begin_smooth_scroll(self):
        self._follow_tail = False

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
        if self.smooth_scroll.wheel(event):
            return
        self._follow_tail = False
        super().wheelEvent(event)
        QTimer.singleShot(0, self._refresh_follow_tail_from_position)
