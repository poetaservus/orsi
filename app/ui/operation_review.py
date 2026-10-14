"""Explicit human acknowledgement of retained uncertain outcomes."""
from app.ui.localization import ui_text, QCheckBox, QDialog, QLabel, QPlainTextEdit, QPushButton

from datetime import datetime

from app.ui.theme_runtime import apply_theme_style
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout)

from app.ui.motion import install_smooth_scroll


_LABELS = {
    "filesystem.write_text": "Write file", "filesystem.edit_text": "Edit text",
    "filesystem.mkdir": "Create folder", "filesystem.move": "Move file",
    "filesystem.copy": "Copy file", "filesystem.trash": "Send file to Recycle Bin",
    "shell.run": "Shell command", "application.launch": "Launch app",
    "project.verify": "Project build or tests", "project.inspect": "App inspection",
    "filesystem.read_text": "Read file", "filesystem.search": "Search file contents",
    "filesystem.list": "List folder", "filesystem.find": "Find file",
    "filesystem.stat": "Read file details", "conversation.read_turn": "Read earlier chat",
}


def _operation_time(timestamp):
    try:
        return f"{datetime.fromtimestamp(timestamp / 1000).astimezone():%Y-%m-%d %H:%M:%S %Z}"
    except (ValueError, OverflowError, OSError):
        return "Time unavailable"


class OperationReviewDialog(QDialog):
    def __init__(self, parent, service, snapshot):
        super().__init__(parent)
        self.setWindowTitle(ui_text('Review interrupted operations'))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(680, 540)
        self.setMinimumSize(620, 500)
        self._service = service
        self._call_ids = tuple(item.call_id for item in snapshot.operations)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        heading = QLabel(ui_text('Review interrupted operations'), self)
        heading.setStyleSheet("font-size: 20px; font-weight: 500;")
        layout.addWidget(heading)
        description = QLabel(
            ui_text('O.R.S.I stopped before confirming the outcome of these operations. Check the affected files or apps and the earlier chat before continuing with changes. Chat and read-only checks remain available.\n\nAcknowledging keeps these outcomes uncertain. It does not retry the operations or mark earlier tasks complete.'), self)
        description.setWordWrap(True)
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setAlignment(Qt.AlignmentFlag.AlignTop)
        description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(description)
        self.details = QPlainTextEdit(self)
        self.details.setObjectName("interruptedOperationDetails")
        self.details.setReadOnly(True)
        install_smooth_scroll(self.details)
        self.details.setPlainText("\n\n".join(
            f"{_LABELS.get(item.capability, item.capability)} · {_operation_time(item.updated_at_ms)}\n"
            f"Chat: {item.session_id} · Turn: {item.turn_id}\nOperation: {item.call_id}"
            for item in snapshot.operations) or "No recoverable operation records are available yet.")
        layout.addWidget(self.details, 1)
        self.confirm = QCheckBox(
            ui_text('I reviewed these operations and understand the outcomes are uncertain.'), self)
        self.confirm.setObjectName("confirmOperationReview")
        self.confirm.setEnabled(not snapshot.restart_required and bool(self._call_ids))
        layout.addWidget(self.confirm)
        self.notice = QLabel(self)
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        if snapshot.restart_required:
            self.notice.setText(ui_text('The last result could not be saved safely. Restart O.R.S.I, then reopen this review.'))
        else:
            self.notice.hide()
        layout.addWidget(self.notice)
        buttons = QHBoxLayout()
        buttons.addStretch()
        keep = QPushButton(ui_text('Keep paused'), self)
        keep.clicked.connect(self.reject)
        buttons.addWidget(keep)
        self.acknowledge = QPushButton(ui_text('Acknowledge reviewed operations'), self)
        self.acknowledge.setObjectName("acknowledgeOperationReview")
        self.acknowledge.setEnabled(False)
        self.acknowledge.setAutoDefault(False)
        self.confirm.toggled.connect(self.acknowledge.setEnabled)
        self.acknowledge.clicked.connect(self.accept)
        buttons.addWidget(self.acknowledge)
        layout.addLayout(buttons)
        apply_theme_style(self, """
            QDialog { background: #20232f; color: #eeeeef; }
            QLabel, QCheckBox { color: #eeeeef; }
            QPlainTextEdit { background: #151722; color: #eeeeef; border: 1px solid #494d60; border-radius: 6px; }
            QPushButton { background: #323747; color: #eeeeef; padding: 8px 12px; border: 1px solid #555b70; border-radius: 6px; }
            QPushButton:disabled { color: #8c90a0; border-color: #3c4150; }
        """)

    def accept(self):
        if not self.confirm.isEnabled() or not self.confirm.isChecked():
            return
        try:
            self._service.acknowledge_operation_review(self._call_ids)
        except Exception:
            # No raw storage/path errors or private call data in the UI.
            self.notice.setText(ui_text('The review could not be saved. Operations remain paused. Restart O.R.S.I and try again.'))
            self.notice.show()
            return
        super().accept()

    def done(self, result):
        self._call_ids = ()
        self._service = None
        self.details.clear()
        self.confirm.setChecked(False)
        self.notice.clear()
        super().done(result)
