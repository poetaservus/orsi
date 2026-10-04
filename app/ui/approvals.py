from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QVBoxLayout, QWidget


@dataclass(frozen=True, slots=True)
class ApprovalSpec:
    title: str
    content_kind: str


_SPECS = {
    "filesystem.edit_text": ApprovalSpec("Apply text edit?", "path_and_content"),
    "filesystem.mkdir": ApprovalSpec("Create folder?", "path"),
    "filesystem.copy": ApprovalSpec("Copy file?", "details"),
    "filesystem.move": ApprovalSpec("Move file?", "details"),
    "filesystem.trash": ApprovalSpec("Send to Recycle Bin?", "details"),
    "filesystem.write_text": ApprovalSpec("Write file?", "path_and_content"),
    "application.launch": ApprovalSpec("Launch application?", "details"),
}


class InlineApproval(QFrame):
    """Review one exact operation in the composer, without a modal window."""

    def __init__(self, parent: QWidget, service, record, spec: ApprovalSpec,
                 on_finished: Callable[[], None]):
        super().__init__(parent)
        self.setObjectName("inlineApproval")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._service = service
        self._record = record
        self._on_finished = on_finished
        self._finished = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 12, 22, 12)
        layout.setSpacing(6)
        title = QLabel(spec.title, self)
        title.setObjectName("approvalTitle")
        layout.addWidget(title)
        if spec.content_kind in {"path", "path_and_content"}:
            path = self._add_preview(layout, "approvalPath", record.resource)
            path.setMaximumHeight(54)
        if spec.content_kind == "path_and_content":
            label = "Exact diff" if record.capability == "filesystem.edit_text" else "File content"
            layout.addWidget(QLabel(label, self))
            self._add_preview(layout, "approvalContent", record.approval_preview)
        elif spec.content_kind == "details":
            self._add_preview(layout, "approvalDetails", record.approval_preview)
        hint = QLabel("Enter to approve · Esc to abort", self)
        hint.setObjectName("approvalHint")
        layout.addWidget(hint)

        self._shortcuts = []
        for key, approved in ((Qt.Key.Key_Return, True), (Qt.Key.Key_Enter, True),
                              (Qt.Key.Key_Escape, False)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda value=approved: self.finish(value))
            self._shortcuts.append(shortcut)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(100)

    def _add_preview(self, layout, name, text):
        preview = QPlainTextEdit(self)
        preview.setObjectName(name)
        preview.setReadOnly(True)
        preview.setPlainText(text)
        layout.addWidget(preview, 1)
        return preview

    def _refresh(self) -> None:
        try:
            pending = self._service.approval_status(self._record.approval_id) == "pending"
        except (LookupError, ValueError):
            pending = False
        if not pending:
            self.finish(False)

    def finish(self, approved: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
        try:
            # The service rechecks expiry and binds this decision to the exact call.
            self._service.resolve_approval(self._record.approval_id, approved)
        finally:
            self._on_finished()
            self.deleteLater()

    def reject(self) -> None:
        self.finish(False)


def create_inline_approval(parent: QWidget, service, record,
                           on_finished: Callable[[], None]) -> InlineApproval | None:
    spec = _SPECS.get(getattr(record, "capability", None))
    if spec is None or not getattr(record, "resource", None):
        service.resolve_approval(record.approval_id, False)
        return None
    if spec.content_kind != "path" and not isinstance(getattr(record, "approval_preview", None), str):
        service.resolve_approval(record.approval_id, False)
        return None
    if service.approval_status(record.approval_id) != "pending":
        return None
    return InlineApproval(parent, service, record, spec, on_finished)
