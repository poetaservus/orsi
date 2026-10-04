"""Composer-only skill picker; selection is metadata for one outgoing message."""
import re
from html import escape

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)


_COMMAND = re.compile(r"(?:^|\s)(?P<command>/skill(?:[ \t]+(?P<query>[^\r\n]*))?)$")


class SkillPicker(QObject):
    """Keep the existing text editor and send behavior, with an optional chip.

    The list reads cached registry metadata only. Names are retained as exact
    identifiers and displayed as plain text; no source or body is rendered.
    """

    def __init__(self, editor, composer, registry, *, input_layout, send_button=None):
        super().__init__(editor)
        self.editor, self.composer, self.registry = editor, composer, registry
        self.send_button = send_button
        self.selected_name = None
        self._command_range = None
        self._updating = False
        self.chip = QPushButton(editor.parentWidget())
        self.chip.setObjectName("skillChip")
        self.chip.setFixedHeight(30)
        self.chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip.hide()
        self.chip.clicked.connect(self.clear_selection)
        input_layout.insertWidget(0, self.chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self.popup = QFrame(composer.parentWidget())
        self.popup.setObjectName("skillPicker")
        self.popup.setAccessibleName("Choose a skill for this message")
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = QWidget(self.popup)
        self.header.setObjectName("skillPickerHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 7, 10, 7)
        self.title = QLabel("Skills", self.header)
        self.title.setObjectName("skillPickerTitle")
        header_layout.addWidget(self.title)
        layout.addWidget(self.header)
        body = QWidget(self.popup)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 6, 8, 8)
        self.items = QListWidget(body)
        self.items.setObjectName("skillPickerList")
        self.items.setAccessibleName("Installed skills")
        self.items.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setWordWrap(False)
        self.items.itemClicked.connect(self._choose)
        body_layout.addWidget(self.items)
        self.empty = QLabel("No skills installed", body)
        self.empty.setObjectName("skillPickerEmpty")
        self.empty.setTextFormat(Qt.TextFormat.PlainText)
        self.empty.setWordWrap(True)
        body_layout.addWidget(self.empty)
        layout.addWidget(body)
        self.popup.hide()
        editor.installEventFilter(self)
        editor.textChanged.connect(self._refresh)
        editor.cursorPositionChanged.connect(self._refresh)

    def _refresh(self):
        if self._updating:
            return
        cursor = self.editor.textCursor()
        if not self.editor.isEnabled() or cursor.hasSelection():
            self.popup.hide()
            return
        prefix_cursor = QTextCursor(cursor)
        prefix_cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
        prefix = prefix_cursor.selectedText().replace("\u2029", "\n")
        match = _COMMAND.search(prefix)
        if match is None:
            self.popup.hide()
            self._command_range = None
            return
        start = len(prefix[:match.start("command")].encode("utf-16-le")) // 2
        self._command_range = (start, cursor.position())
        query = (match.group("query") or "").strip().casefold()
        catalog = self.registry.list() if self.registry is not None else ()
        skills = [skill for skill in catalog if query in skill.name.casefold()
                  or query in skill.description.casefold()]
        self.reposition()
        self.items.clear()
        for skill in skills:
            name = " ".join(skill.name.split())[:128]
            metrics = self.items.fontMetrics()
            name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, self.popup.width() - 50)
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, skill.name)
            item.setToolTip("<qt>" + escape(" ".join(skill.description.split())[:512]) + "</qt>")
            self.items.addItem(item)
        self.items.setVisible(bool(skills))
        self.empty.setVisible(not skills)
        self.empty.setText("No matching skills" if catalog else "No skills installed")
        if skills:
            self.items.setCurrentRow(0)
        row_height = max(32, self.items.sizeHintForRow(0))
        self.popup.setFixedHeight(self.header.sizeHint().height() + 14 + 2 * self.popup.frameWidth()
                                  + max(1, min(len(skills), 5)) * row_height)
        self.reposition()
        self.popup.show()
        self.popup.raise_()

    def reposition(self):
        width = min(600, max(240, self.composer.width() - 24))
        self.popup.setFixedWidth(width)
        self.popup.move(self.composer.x() + 12, max(8, self.composer.y() - self.popup.height() - 8))
        if self.popup.isVisible():
            self.popup.raise_()

    def _choose(self, item):
        if item is None or self._command_range is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._updating = True
        try:
            cursor = self.editor.textCursor()
            cursor.setPosition(self._command_range[0])
            cursor.setPosition(self._command_range[1], QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.editor.setTextCursor(cursor)
            self.selected_name = name
            label = self.chip.fontMetrics().elidedText("/" + " ".join(name.split()),
                                                     Qt.TextElideMode.ElideRight, 210)
            self.chip.setText(label.replace("&", "&&") + "  ×")
            self.chip.setToolTip("<qt>" + escape(name[:512]) + "<br/>Applies to this message. Click to remove.</qt>")
            self.chip.setAccessibleName("Remove skill " + " ".join(name.split())[:128])
            self.chip.show()
            self._command_range = None
            self.popup.hide()
            self.editor.setFocus()
        finally:
            self._updating = False

    def clear_selection(self):
        self.selected_name = None
        self.chip.hide()
        self.popup.hide()
        self._command_range = None
        self.editor.setFocus()

    def accept_current(self):
        """Consume Send while choosing, without submitting a slash command."""
        if not self.popup.isVisible():
            return False
        self._choose(self.items.currentItem())
        self.editor.setFocus()
        return True

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.EnabledChange:
            self.chip.setEnabled(self.editor.isEnabled())
            if not self.editor.isEnabled():
                self.popup.hide()
        elif event.type() == QEvent.Type.FocusOut:
            # A mouse press focuses Send before its clicked signal reaches
            # MainWindow.submit(). Keep the current choice alive for that click.
            if self.send_button is None or QApplication.focusWidget() is not self.send_button:
                self.popup.hide()
        elif event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if self.popup.isVisible():
                if key == Qt.Key.Key_Escape:
                    self.popup.hide()
                    return True
                if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    if self.items.count():
                        delta = 1 if key == Qt.Key.Key_Down else -1
                        self.items.setCurrentRow(max(0, min(self.items.count() - 1,
                                                          self.items.currentRow() + delta)))
                    return True
                if key == Qt.Key.Key_Tab or (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._choose(self.items.currentItem())
                    return True
            if key == Qt.Key.Key_Backspace and self.selected_name is not None:
                cursor = self.editor.textCursor()
                if cursor.position() == 0 and not cursor.hasSelection():
                    self.clear_selection()
                    return True
        return super().eventFilter(watched, event)
