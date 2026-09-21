from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class ApprovalDialogSpec:
    capability: str
    object_name: str
    title: str
    heading: str
    approve_text: str
    approve_object_name: str
    notice: str
    activity: str
    size: tuple[int, int]
    content_kind: str


_SPECS = {
    "filesystem.mkdir": ApprovalDialogSpec(
        capability="filesystem.mkdir",
        object_name="folderApproval",
        title="Create folder?",
        heading="Create one empty folder at:",
        approve_text="Create folder",
        approve_object_name="approveFolder",
        notice="Existing entries will not be replaced. Approval is for this folder only.",
        activity="Waiting for folder approval...",
        size=(560, 240),
        content_kind="path",
    ),
    "filesystem.copy": ApprovalDialogSpec(
        capability="filesystem.copy",
        object_name="copyApproval",
        title="Copy file?",
        heading="Copy file with these exact details:",
        approve_text="Copy file",
        approve_object_name="approveCopy",
        notice="Approval is for this source, destination, and collision policy only.",
        activity="Waiting for copy approval...",
        size=(640, 340),
        content_kind="details",
    ),
    "filesystem.move": ApprovalDialogSpec(
        capability="filesystem.move",
        object_name="moveApproval",
        title="Move file?",
        heading="Move file with these exact details:",
        approve_text="Move file",
        approve_object_name="approveMove",
        notice=(
            "Approval is for this source, destination, and collision policy only. "
            "The source is removed after verification."
        ),
        activity="Waiting for move approval...",
        size=(640, 360),
        content_kind="details",
    ),
    "filesystem.trash": ApprovalDialogSpec(
        capability="filesystem.trash",
        object_name="trashApproval",
        title="Send file to Recycle Bin?",
        heading="Send this file to the Windows Recycle Bin:",
        approve_text="Send to Recycle Bin",
        approve_object_name="approveTrash",
        notice=(
            "Approval is for this exact file only. Directories and permanent deletion are not "
            "part of this checkpoint."
        ),
        activity="Waiting for trash approval...",
        size=(640, 320),
        content_kind="details",
    ),
    "filesystem.write_text": ApprovalDialogSpec(
        capability="filesystem.write_text",
        object_name="writeApproval",
        title="Write text file?",
        heading="Write text to:",
        approve_text="Write file",
        approve_object_name="approveTextWrite",
        notice=(
            "This creates the file or replaces the entire existing file. Approval is for this "
            "path and content only."
        ),
        activity="Waiting for file approval...",
        size=(640, 420),
        content_kind="path_and_content",
    ),
}


def open_approval_dialog(
    parent: QWidget,
    service,
    record,
    on_finished: Callable[[], None],
) -> tuple[QDialog, str] | None:
    """Validate and display the approval surface for one supported write capability."""
    spec = _SPECS.get(getattr(record, "capability", None))
    if spec is None or not getattr(record, "resource", None):
        service.resolve_approval(record.approval_id, False)
        return None
    preview = getattr(record, "approval_preview", None)
    if spec.content_kind != "path" and not isinstance(preview, str):
        service.resolve_approval(record.approval_id, False)
        return None
    if service.approval_status(record.approval_id) != "pending":
        return None

    dialog = QDialog(parent)
    dialog.setObjectName(spec.object_name)
    dialog.setWindowTitle(spec.title)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.resize(*spec.size)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(spec.heading, dialog))
    _add_content(layout, dialog, record.resource, preview, spec.content_kind)
    notice = QLabel(spec.notice, dialog)
    notice.setWordWrap(True)
    layout.addWidget(notice)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
    approve = buttons.addButton(spec.approve_text, QDialogButtonBox.ButtonRole.AcceptRole)
    approve.setObjectName(spec.approve_object_name)
    approve.setAutoDefault(False)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    cancel.setDefault(True)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    timer = QTimer(dialog)

    def refresh() -> None:
        try:
            pending = service.approval_status(record.approval_id) == "pending"
        except (LookupError, ValueError):
            pending = False
        if not pending:
            dialog.reject()

    def finish(code: int) -> None:
        timer.stop()
        service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
        on_finished()
        dialog.deleteLater()

    timer.timeout.connect(refresh)
    dialog.finished.connect(finish)
    timer.start(100)
    dialog.open()
    cancel.setFocus()
    return dialog, spec.activity


def _add_content(
    layout: QVBoxLayout,
    dialog: QDialog,
    resource: str,
    preview: str | None,
    content_kind: str,
) -> None:
    if content_kind in {"path", "path_and_content"}:
        path = QPlainTextEdit(dialog)
        path.setObjectName("approvalPath")
        path.setPlainText(resource)
        path.setReadOnly(True)
        if content_kind == "path_and_content":
            path.setMaximumHeight(92)
        layout.addWidget(path)
    if content_kind == "path_and_content":
        layout.addWidget(QLabel("New file content:", dialog))
        content = QPlainTextEdit(dialog)
        content.setObjectName("approvalContent")
        content.setPlainText(preview or "")
        content.setReadOnly(True)
        layout.addWidget(content, 1)
    elif content_kind == "details":
        details = QPlainTextEdit(dialog)
        details.setObjectName("approvalDetails")
        details.setPlainText(preview or "")
        details.setReadOnly(True)
        layout.addWidget(details, 1)
