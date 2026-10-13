"""Native mixed question form rendered inside the existing composer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.conversation.questions import Question, QuestionBatch, format_answers
from app.ui.inputs import ScrollSafeComboBox
from app.ui.motion import install_smooth_scroll


def plain_label(text, parent):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class QuestionField(QWidget):
    changed = Signal()

    def __init__(self, question: Question, number: int, parent=None):
        super().__init__(parent)
        self.question = question
        self.setAccessibleName(question.title)
        self.buttons = []
        self.other_button = self.other_text = self.editor = self.combo = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 12)
        layout.setSpacing(8)
        title = plain_label(f"{number}. {question.title}", self)
        title.setObjectName("questionTitle")
        layout.addWidget(title)
        if question.kind == "multi" or not question.required:
            detail = "Select multiple" if question.kind == "multi" else ""
            if not question.required:
                detail += " (optional)" if detail else "Optional"
            hint = plain_label(detail, self)
            hint.setObjectName("questionHint")
            layout.addWidget(hint)
        self.group = QButtonGroup(self)
        self.group.setExclusive(question.kind != "multi")
        if question.kind == "text":
            self.editor = QPlainTextEdit(self)
            self.editor.setPlaceholderText("Type your answer here…")
            self.editor.setAccessibleName(question.title)
            self.editor.setFixedHeight(72)
            self.editor.textChanged.connect(self.changed)
            layout.addWidget(self.editor)
        elif question.kind == "dropdown" or question.kind == "single" and len(question.options) > 5:
            self.combo = ScrollSafeComboBox(self)
            self.combo.setAccessibleName(question.title)
            self.combo.addItem("Select an option…", None)
            for option in question.options:
                self.combo.addItem(option.label, option.id)
            if question.allow_other:
                self.combo.addItem("Something else…", "__other__")
            self.combo.currentIndexChanged.connect(self._changed)
            layout.addWidget(self.combo)
        else:
            button_type = QCheckBox if question.kind == "multi" else QRadioButton
            for option in question.options:
                button = button_type(option.label, self)
                # Qt button labels interpret ampersands as mnemonic markup.
                button.setText(option.label.replace("&", "&&"))
                button.setAccessibleName(option.label)
                button.setToolTip(option.label)
                self.buttons.append(button)
                self.group.addButton(button)
                button.toggled.connect(self._changed)
                layout.addWidget(button)
            if question.allow_other:
                self.other_button = button_type("Something else…", self)
                self.group.addButton(self.other_button)
                self.other_button.toggled.connect(self._changed)
                layout.addWidget(self.other_button)
        if question.allow_other:
            self.other_text = QLineEdit(self)
            self.other_text.setPlaceholderText("Your answer…")
            self.other_text.setAccessibleName(question.title + ": custom answer")
            self.other_text.setMaxLength(8000)
            self.other_text.hide()
            self.other_text.textChanged.connect(self.changed)
            layout.addWidget(self.other_text)

    def _changed(self, *_):
        if self.other_text is not None:
            self.other_text.setVisible(self._other_selected())
        self.changed.emit()

    def _other_selected(self):
        return (self.combo is not None and self.combo.currentData() == "__other__" or
                self.other_button is not None and self.other_button.isChecked())

    def values(self) -> tuple[str, ...]:
        if self.editor is not None:
            text = self.editor.toPlainText().strip()
            return (text,) if text else ()
        if self.combo is not None:
            index = self.combo.currentIndex() - 1
            values = [self.question.options[index].label] if 0 <= index < len(self.question.options) else []
        else:
            values = [option.label for option, button in zip(self.question.options, self.buttons) if button.isChecked()]
        if self._other_selected() and self.other_text.text().strip():
            values.append(self.other_text.text().strip())
        return tuple(values)

    def complete(self):
        return not (self._other_selected() and not self.other_text.text().strip()) and (
            not self.question.required or bool(self.values()))


class QuestionComposer(QFrame):
    send_requested = Signal()
    chat_requested = Signal()

    def __init__(self, batch: QuestionBatch, parent=None):
        super().__init__(parent)
        self.batch = batch
        self.setObjectName("questionComposer")
        self.setStyleSheet(QUESTION_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = plain_label("O.R.S.I. / Questions", self)
        title.setObjectName("questionsHeader")
        header.addWidget(title, 1)
        self.required_count = plain_label("", self)
        self.required_count.setObjectName("questionHint")
        header.addWidget(self.required_count)
        layout.addLayout(header)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(0)
        self.body = QWidget(self.scroll)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 6, 0)
        body_layout.setSpacing(0)
        self.fields = {}
        for number, question in enumerate(batch.questions, 1):
            separator = QFrame(self.body)
            separator.setObjectName("questionDivider")
            separator.setFixedHeight(1)
            body_layout.addWidget(separator)
            field = QuestionField(question, number, self.body)
            self.fields[question.id] = field
            field.changed.connect(self.refresh)
            body_layout.addWidget(field)
        extra = QuestionField(Question(id="additional", title="Additional information", kind="text", required=False),
                              len(batch.questions) + 1, self.body)
        self.additional = extra.editor
        extra.changed.connect(self.refresh)
        body_layout.addWidget(extra)
        body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        install_smooth_scroll(self.scroll)
        layout.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        self.chat_button = QPushButton("Answer in chat", self)
        self.chat_button.clicked.connect(self.chat_requested)
        footer.addWidget(self.chat_button)
        self.hint = plain_label("", self)
        self.hint.setObjectName("questionHint")
        footer.addWidget(self.hint, 1)
        self.send = QPushButton("Send  ↑", self)
        self.send.setObjectName("questionsSend")
        self.send.setAccessibleName("Send answers")
        self.send.clicked.connect(self._submit)
        footer.addWidget(self.send)
        layout.addLayout(footer)
        for keys, action in (("Ctrl+Return", self._submit), ("Ctrl+Enter", self._submit),
                             ("Escape", self.chat_requested.emit)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(action)
        first = next(iter(self.fields.values()))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(first.editor or first.combo or first.buttons[0])
        self.refresh()

    def desired_height(self, available):
        return min(max(180, available), max(240, self.body.sizeHint().height() + 102))

    def refresh(self):
        remaining = sum(field.question.required and not field.complete() for field in self.fields.values())
        try:
            self.answer_text()
            valid = all(field.complete() for field in self.fields.values())
        except ValueError:
            valid = False
        self.required_count.setText(f"{remaining} required" if remaining else "Ready" if valid else "Check answers")
        self.hint.setText("Complete required questions to continue" if remaining else
                          "Ready to send" if valid else "Check your answers")
        self.send.setEnabled(valid and self.isEnabled())

    def _submit(self):
        self.refresh()
        if self.send.isEnabled():
            self.send_requested.emit()

    def answer_text(self):
        if not all(field.complete() for field in self.fields.values()):
            raise ValueError("Complete required questions to continue.")
        return format_answers(self.batch, {id: field.values() for id, field in self.fields.items()},
                              self.additional.toPlainText())


QUESTION_STYLE = """
QFrame#questionComposer, QFrame#questionComposer QWidget { background: transparent; color: #ededee; font-size: 12px; }
QFrame#questionComposer QLabel { border: none; font-size: 12px; }
QLabel#questionsHeader, QLabel#questionTitle { font-weight: 600; }
QLabel#questionHint { color: #a4a7ad; font-size: 10px; }
QFrame#questionDivider { background: #242628; border: none; }
QFrame#questionComposer QRadioButton, QFrame#questionComposer QCheckBox { spacing: 9px; min-height: 22px; }
QFrame#questionComposer QRadioButton::indicator, QFrame#questionComposer QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid #62656b; background: #090a0b;
}
QFrame#questionComposer QRadioButton::indicator { border-radius: 8px; }
QFrame#questionComposer QRadioButton::indicator:checked { background: #eeeeef; border: 3px solid #85888c; border-radius: 10px; }
QFrame#questionComposer QCheckBox::indicator { border-radius: 3px; }
QFrame#questionComposer QCheckBox::indicator:checked { background: #eeeeef; border-color: #eeeeef; }
QFrame#questionComposer QPlainTextEdit, QFrame#questionComposer QLineEdit, QFrame#questionComposer QComboBox {
    background: #090a0b; color: #ededee; border: 1px solid #393c41; border-radius: 7px; padding: 8px;
}
QFrame#questionComposer QComboBox { border-radius: 18px; min-height: 20px; }
QFrame#questionComposer QComboBox::drop-down { border: none; width: 28px; margin-right: 6px; }
QFrame#questionComposer QComboBox QAbstractItemView { background: #17191c; selection-background-color: #3b3e44; }
QFrame#questionComposer QScrollBar:vertical { background: transparent; width: 5px; margin: 0; }
QFrame#questionComposer QScrollBar::handle:vertical { background: #41444a; border-radius: 2px; min-height: 24px; }
QFrame#questionComposer QScrollBar::add-line:vertical, QFrame#questionComposer QScrollBar::sub-line:vertical { height: 0; }
QFrame#questionComposer QScrollBar::add-page:vertical, QFrame#questionComposer QScrollBar::sub-page:vertical { background: transparent; }
QFrame#questionComposer QPushButton { background: transparent; border: none; padding: 7px 10px; border-radius: 14px; }
QFrame#questionComposer QPushButton:hover { background: #303237; }
QFrame#questionComposer QPushButton#questionsSend { background: #303237; min-width: 55px; }
QFrame#questionComposer QPushButton:disabled { color: #777a80; }
QFrame#questionComposer QRadioButton:focus, QFrame#questionComposer QCheckBox:focus,
QFrame#questionComposer QPushButton:focus, QFrame#questionComposer QComboBox:focus,
QFrame#questionComposer QLineEdit:focus, QFrame#questionComposer QPlainTextEdit:focus { border: 1px solid #b6bac3; }
"""
