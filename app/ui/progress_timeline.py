"""A quiet chronological work log: public paragraphs and settled operations."""
from collections import deque

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout

from app.runtime.semantic_progress import NarrativeItem, OperationKind
from app.ui.localization import QLabel, QWidget, ui_extra
from app.ui.markdown import MarkdownLabel
from app.ui.theme_runtime import apply_theme_style


def operation_label(kind, success):
    if not success:
        return ui_extra("Tool attempt stopped")
    return {
        OperationKind.READ: ui_extra("Read files"),
        OperationKind.INSPECT: ui_extra("Inspected files"),
        OperationKind.EDIT: ui_extra("Updated files"),
        OperationKind.COMMAND: ui_extra("Ran commands"),
        OperationKind.CHECK: ui_extra("Ran checks"),
        OperationKind.OFFICE: ui_extra("Worked in Office"),
        OperationKind.TOOL: ui_extra("Used tools"),
    }[kind]


class _OperationRow(QWidget):
    def __init__(self, item):
        super().__init__()
        self.operations = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(8)
        icon = QLabel("›_")
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(True)
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.caption, 1)
        apply_theme_style(self, "QLabel { color: #858791; font-size: 12px; background: transparent; }")
        self.add(item)

    def add(self, item):
        key = (item.operation, item.success)
        if key not in self.operations:
            self.operations.append(key)
        self.refresh_text()

    def refresh_text(self):
        self.caption.setText(" · ".join(operation_label(kind, success).resolve() for kind, success in self.operations))

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange:
            self.refresh_text()


class ProgressTimeline(QWidget):
    """At most 40 visible entries per task; never part of model chat history."""
    def __init__(self):
        super().__init__()
        self.setObjectName("progressTimeline")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(18)
        self.entries = []
        self._last_note = None
        self._seen = set()
        self._event_order = deque()
        self._available_width = 600

    def append(self, item):
        if not isinstance(item, NarrativeItem) or not item.event_id or item.event_id in self._seen:
            return False
        if item.operation is None and (not item.text.strip() or item.text.strip()[:4000] == self._last_note):
            return False
        self._seen.add(item.event_id)
        self._event_order.append(item.event_id)
        if len(self._event_order) > 1024:
            self._seen.discard(self._event_order.popleft())
        if item.operation is not None:
            if not isinstance(item.operation, OperationKind):
                return False
            if self.entries and isinstance(self.entries[-1], _OperationRow):
                self.entries[-1].add(item)
                return True
            widget = _OperationRow(item)
        else:
            self._last_note = item.text.strip()[:4000]
            widget = MarkdownLabel(self._last_note)
            apply_theme_style(widget, "color: #dedee0; font-size: 14px; background: transparent; border: none;")
        self.entries.append(widget)
        self._layout.addWidget(widget)
        if len(self.entries) > 40:
            oldest = self.entries.pop(0)
            self._layout.removeWidget(oldest)
            oldest.deleteLater()
        self.set_available_width(self._available_width)
        return True

    def set_available_width(self, width):
        self._available_width = max(100, width)
        self.setFixedWidth(self._available_width)
        for widget in self.entries:
            if isinstance(widget, MarkdownLabel):
                widget.refresh_formatting()
                widget.setFixedWidth(self._available_width)
                widget.setFixedHeight(widget.heightForWidth(self._available_width) + 4)
        self.updateGeometry()
