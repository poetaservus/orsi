from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.host_access import HostReadScope
from app.inference.engine import InferenceUnavailable
from app.ui.chat import ChatView
from app.ui.context_window import ContextWindowBar
from app.ui.status import ConversationStatus


_ICON_DIRECTORY = Path(__file__).with_name("assets")
_TOP_BAR_HEIGHT = 68
_TOP_BUTTON_SIZE = 42
_TOP_ICON_SIZE = 30
_COMPOSER_WIDTH = 1040
_COMPOSER_HEIGHT = 74
_COMPOSER_BOTTOM_MARGIN = 44
_MIDDLE_PANEL_WIDTH = 1120
_BACKGROUND_TOP_CROP = 68


class MessageInput(QTextEdit):
    submit_requested = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        is_return = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class Worker(QObject):
    finished = Signal(str)
    failed = Signal(str)
    activity = Signal(str)

    def __init__(self, service, message: str):
        super().__init__()
        self.service = service
        self.message = message

    def run(self) -> None:
        try:
            response = self.service.run(self.message, self.activity.emit)
            if response is None or not str(response).strip():
                raise RuntimeError("O.R.S.I finished processing, but returned an empty response.")
            self.finished.emit(str(response))
        except Exception as exc:
            self.failed.emit(str(exc))


class ComposerFrame(QFrame):
    """Paint a clean v2 composer pill without baked-in image artifacts."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = rect.height() / 2
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#41444d"))
        fill.setColorAt(0.45, QColor("#383b45"))
        fill.setColorAt(1.0, QColor("#303340"))
        painter.setPen(QColor(105, 109, 124, 190))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QColor(255, 255, 255, 26))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
        painter.drawRoundedRect(inner, max(1.0, radius - 2.0), max(1.0, radius - 2.0))


class ComposerActionButton(QPushButton):
    """Icon button whose hover circle stays aligned with the upward-nudged icon."""

    def __init__(self, icon_path: Path, icon_size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._action_icon = QIcon(str(icon_path))
        self._action_icon_size = QSize(icon_size, icon_size)
        self._circle_size = 42
        self.setFixedSize(self._circle_size, 46)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().mousePressEvent(event)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().mouseReleaseEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        circle = QRectF(0.0, 0.0, float(self._circle_size), float(self._circle_size))
        if self.isDown():
            painter.setBrush(QColor("#2c2e35"))
        elif self.underMouse() and self.isEnabled():
            painter.setBrush(QColor("#454852"))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle)

        pixmap = self._action_icon.pixmap(self._action_icon_size)
        x = (self._circle_size - self._action_icon_size.width()) / 2
        y = (self._circle_size - self._action_icon_size.height()) / 2
        if not self.isEnabled():
            painter.setOpacity(0.45)
        painter.drawPixmap(QRectF(x, y, self._action_icon_size.width(), self._action_icon_size.height()), pixmap, QRectF(pixmap.rect()))


class ChatSurface(QWidget):
    """Paint the quiet gradient and centered conversation panel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mainContent")
        self._background = QPixmap(str(_ICON_DIRECTORY / "o.r.s.i_gui_bck.png"))

    def middle_panel_rect(self) -> QRect:
        width = min(_MIDDLE_PANEL_WIDTH, max(0, self.width()))
        x = max(0, (self.width() - width) // 2)
        return QRect(x, 0, width, self.height())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        if self._background.isNull():
            gradient = QLinearGradient(0, 0, max(1, self.width()), 0)
            gradient.setColorAt(0.0, QColor("#131517"))
            gradient.setColorAt(0.55, QColor("#111315"))
            gradient.setColorAt(1.0, QColor("#101214"))
            painter.fillRect(self.rect(), gradient)
        else:
            source_y = min(_BACKGROUND_TOP_CROP, max(0, self._background.height() - 1))
            source = QRect(
                0,
                source_y,
                self._background.width(),
                max(1, self._background.height() - source_y),
            )
            painter.drawPixmap(self.rect(), self._background, source)


class MainWindow(QMainWindow):
    approval_requested = Signal(object)

    def __init__(self, service, hostname: str, startup_error: str | None = None, inference=None):
        super().__init__()
        del hostname
        self.service = service
        self.inference = inference
        self.startup_error = startup_error
        self._cloud_privacy_accepted = False
        self.thread = None
        self.worker = None
        self._approval_dialog = None
        self.approval_requested.connect(self._show_approval, Qt.ConnectionType.QueuedConnection)
        bind_approval = getattr(service, "set_approval_requester", None)
        if callable(bind_approval):
            bind_approval(self.approval_requested.emit)

        self.setObjectName("mainWindow")
        self.setWindowTitle("O.R.S.I")
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        topbar = QWidget()
        self.topbar = topbar
        topbar.setObjectName("topBar")
        topbar.setFixedHeight(_TOP_BAR_HEIGHT)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(21, 0, 22, 0)
        topbar_layout.setSpacing(17)

        self.new_session_button = QPushButton()
        self.new_session_button.setObjectName("topBarButton")
        self.new_session_button.setFixedSize(_TOP_BUTTON_SIZE, _TOP_BUTTON_SIZE)
        self.new_session_button.setIcon(QIcon(str(_ICON_DIRECTORY / "new_message_icon_cropped.png")))
        self.new_session_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.new_session_button.setToolTip("New session — permanently clears this conversation")
        self.new_session_button.setAccessibleName("New session")
        self.new_session_button.setEnabled(service is not None)

        first_separator = QFrame()
        first_separator.setObjectName("topBarSeparator")
        first_separator.setFixedSize(1, 28)

        self.history_button = QPushButton()
        self.history_button.setObjectName("topBarButton")
        self.history_button.setFixedSize(_TOP_BUTTON_SIZE, _TOP_BUTTON_SIZE)
        self.history_button.setIcon(QIcon(str(_ICON_DIRECTORY / "history.svg")))
        self.history_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.history_button.setToolTip("History")
        self.history_button.setAccessibleName("History")

        second_separator = QFrame()
        second_separator.setObjectName("topBarSeparator")
        second_separator.setFixedSize(1, 28)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("topBarButton")
        self.settings_button.setFixedSize(_TOP_BUTTON_SIZE, _TOP_BUTTON_SIZE)
        self.settings_button.setIcon(QIcon(str(_ICON_DIRECTORY / "settings_icon_cropped.png")))
        self.settings_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")

        topbar_layout.addWidget(self.new_session_button, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(first_separator, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(self.history_button, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(second_separator, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addStretch(1)
        self.context_window = ContextWindowBar(
            int(getattr(inference, "context_length", 0)),
            topbar,
        )
        topbar_layout.addWidget(self.context_window, 0, Qt.AlignmentFlag.AlignVCenter)
        root_layout.addWidget(topbar)

        content = ChatSurface()
        self._content = content
        content.installEventFilter(self)
        content_layout = QVBoxLayout(content)
        self._content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        self.chat = ChatView()
        content_layout.addWidget(self.chat, 1)

        self.settings_panel = QFrame(root)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setFixedSize(314, 168)
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setSpacing(10)

        settings_title = QLabel("Settings")
        settings_title.setObjectName("settingsTitle")
        settings_layout.addWidget(settings_title)

        model_label = QLabel("Model")
        model_label.setObjectName("settingsLabel")
        settings_layout.addWidget(model_label)

        self.model_selector = QComboBox()
        self.model_selector.setObjectName("modelSelector")
        self.model_selector.setFixedHeight(38)
        if inference is None:
            self.model_selector.addItem("Local", "local")
            self.model_selector.setEnabled(False)
        else:
            for mode in inference.available_modes:
                self.model_selector.addItem("Local" if mode == "local" else "Cloud · Free", mode)
            self._sync_inference_selector()
            self.model_selector.currentIndexChanged.connect(self._select_inference_mode)
        settings_layout.addWidget(self.model_selector)

        self.activity = ConversationStatus(
            self._ready_status() if not startup_error else "Model unavailable"
        )
        settings_layout.addWidget(self.activity)
        self.settings_panel.hide()

        self.composer = ComposerFrame(content)
        self.composer.setObjectName("composer")
        self.composer.setFixedHeight(_COMPOSER_HEIGHT)
        composer_layout = QHBoxLayout(self.composer)
        composer_layout.setContentsMargins(30, 8, 28, 8)
        composer_layout.setSpacing(8)

        self.input = MessageInput()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Ask O.R.S.I.")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(58)

        self.send = ComposerActionButton(_ICON_DIRECTORY / "input_button_cropped.png", 38)
        self.send.setObjectName("sendButton")
        self.send.setToolTip("Send")
        self.send.setAccessibleName("Send")

        self.stop = ComposerActionButton(_ICON_DIRECTORY / "stop.svg", 18)
        self.stop.setObjectName("stopButton")
        self.stop.setToolTip("Stop")
        self.stop.setAccessibleName("Stop")
        self.stop.setEnabled(False)
        self.stop.hide()

        composer_layout.addWidget(self.input, 1)
        composer_layout.addWidget(self.send)
        composer_layout.addWidget(self.stop)

        self.setCentralWidget(root)
        self.setStyleSheet(_STYLE)
        self.send.clicked.connect(self.submit)
        self.stop.clicked.connect(self.cancel_current_task)
        self.new_session_button.clicked.connect(self.create_new_session)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.input.submit_requested.connect(self.submit)
        self._update_context_window()
        self._position_overlays()
        if startup_error:
            self.chat.add_message("Agent", startup_error, True)
        elif self._agent_error():
            self.chat.add_message("Agent", self._agent_error(), True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._position_overlays()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if watched is getattr(self, "_content", None) and event.type() == QEvent.Type.Resize:
            self._position_overlays()
        return super().eventFilter(watched, event)

    def _position_overlays(self) -> None:
        if not hasattr(self, "composer"):
            return
        content = self.composer.parentWidget()
        width = min(_COMPOSER_WIDTH, max(320, content.width() - 32))
        x = max(16, (content.width() - width) // 2)
        y = max(16, content.height() - _COMPOSER_BOTTOM_MARGIN - _COMPOSER_HEIGHT)
        self.composer.setGeometry(x, y, width, _COMPOSER_HEIGHT)
        self.composer.raise_()
        self.settings_panel.move(162, _TOP_BAR_HEIGHT + 12)
        if self.settings_panel.isVisible():
            self.settings_panel.raise_()

    @Slot()
    def _toggle_settings(self) -> None:
        visible = not self.settings_panel.isVisible()
        self.settings_panel.setVisible(visible)
        if visible:
            self.settings_panel.raise_()

    def submit(self) -> None:
        message = self.input.toPlainText().strip()
        if not message or self.thread is not None:
            return
        if self.startup_error:
            self.chat.add_message("Agent", self.startup_error, True)
            return
        if self.inference is not None and self.inference.mode == "cloud" and not self._ensure_cloud_ready():
            return

        self.input.clear()
        self.chat.add_message("User", message)
        self._set_busy(True)
        self.thread = QThread()
        self.worker = Worker(self.service, message)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._worker_succeeded)
        self.worker.failed.connect(self._worker_failed)
        self.worker.activity.connect(self.activity.set_activity)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot(object)
    def _show_approval(self, record) -> None:
        if self._approval_dialog is not None:
            self.service.resolve_approval(record.approval_id, False)
            return
        if record.capability == "filesystem.mkdir":
            self._show_folder_approval(record)
            return
        if record.capability == "filesystem.write_text":
            self._show_text_write_approval(record)
            return
        if record.capability == "filesystem.copy":
            self._show_copy_approval(record)
            return
        if record.capability == "filesystem.move":
            self._show_move_approval(record)
            return
        if record.capability == "filesystem.trash":
            self._show_trash_approval(record)
            return
        self.service.resolve_approval(record.approval_id, False)

    def _show_folder_approval(self, record) -> None:
        if record.capability != "filesystem.mkdir" or not record.resource:
            self.service.resolve_approval(record.approval_id, False)
            return
        if self.service.approval_status(record.approval_id) != "pending":
            return
        dialog = QDialog(self)
        dialog.setObjectName("folderApproval")
        dialog.setWindowTitle("Create folder?")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(560, 240)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Create one empty folder at:", dialog))
        path = QPlainTextEdit(dialog)
        path.setObjectName("approvalPath")
        path.setPlainText(record.resource)
        path.setReadOnly(True)
        layout.addWidget(path)
        notice = QLabel("Existing entries will not be replaced. Approval is for this folder only.", dialog)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
        create = buttons.addButton("Create folder", QDialogButtonBox.ButtonRole.AcceptRole)
        create.setObjectName("approveFolder")
        create.setAutoDefault(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)

        def refresh():
            try:
                pending = self.service.approval_status(record.approval_id) == "pending"
            except (LookupError, ValueError):
                pending = False
            if not pending:
                dialog.reject()

        def finish(code):
            timer.stop()
            self.service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
            self._approval_dialog = None
            dialog.deleteLater()

        timer.timeout.connect(refresh)
        dialog.finished.connect(finish)
        self._approval_dialog = dialog
        self.activity.set_activity("Waiting for folder approval...")
        timer.start(100)
        dialog.open()
        cancel.setFocus()

    def _show_copy_approval(self, record) -> None:
        preview = getattr(record, "approval_preview", None)
        if record.capability != "filesystem.copy" or not record.resource or not isinstance(preview, str):
            self.service.resolve_approval(record.approval_id, False)
            return
        if self.service.approval_status(record.approval_id) != "pending":
            return
        dialog = QDialog(self)
        dialog.setObjectName("copyApproval")
        dialog.setWindowTitle("Copy file?")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(640, 340)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Copy file with these exact details:", dialog))
        details = QPlainTextEdit(dialog)
        details.setObjectName("approvalDetails")
        details.setPlainText(preview)
        details.setReadOnly(True)
        layout.addWidget(details, 1)
        notice = QLabel("Approval is for this source, destination, and collision policy only.", dialog)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
        copy = buttons.addButton("Copy file", QDialogButtonBox.ButtonRole.AcceptRole)
        copy.setObjectName("approveCopy")
        copy.setAutoDefault(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)

        def refresh():
            try:
                pending = self.service.approval_status(record.approval_id) == "pending"
            except (LookupError, ValueError):
                pending = False
            if not pending:
                dialog.reject()

        def finish(code):
            timer.stop()
            self.service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
            self._approval_dialog = None
            dialog.deleteLater()

        timer.timeout.connect(refresh)
        dialog.finished.connect(finish)
        self._approval_dialog = dialog
        self.activity.set_activity("Waiting for copy approval...")
        timer.start(100)
        dialog.open()
        cancel.setFocus()

    def _show_move_approval(self, record) -> None:
        preview = getattr(record, "approval_preview", None)
        if record.capability != "filesystem.move" or not record.resource or not isinstance(preview, str):
            self.service.resolve_approval(record.approval_id, False)
            return
        if self.service.approval_status(record.approval_id) != "pending":
            return
        dialog = QDialog(self)
        dialog.setObjectName("moveApproval")
        dialog.setWindowTitle("Move file?")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(640, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Move file with these exact details:", dialog))
        details = QPlainTextEdit(dialog)
        details.setObjectName("approvalDetails")
        details.setPlainText(preview)
        details.setReadOnly(True)
        layout.addWidget(details, 1)
        notice = QLabel("Approval is for this source, destination, and collision policy only. The source is removed after verification.", dialog)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
        move = buttons.addButton("Move file", QDialogButtonBox.ButtonRole.AcceptRole)
        move.setObjectName("approveMove")
        move.setAutoDefault(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)

        def refresh():
            try:
                pending = self.service.approval_status(record.approval_id) == "pending"
            except (LookupError, ValueError):
                pending = False
            if not pending:
                dialog.reject()

        def finish(code):
            timer.stop()
            self.service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
            self._approval_dialog = None
            dialog.deleteLater()

        timer.timeout.connect(refresh)
        dialog.finished.connect(finish)
        self._approval_dialog = dialog
        self.activity.set_activity("Waiting for move approval...")
        timer.start(100)
        dialog.open()
        cancel.setFocus()

    def _show_trash_approval(self, record) -> None:
        preview = getattr(record, "approval_preview", None)
        if record.capability != "filesystem.trash" or not record.resource or not isinstance(preview, str):
            self.service.resolve_approval(record.approval_id, False)
            return
        if self.service.approval_status(record.approval_id) != "pending":
            return
        dialog = QDialog(self)
        dialog.setObjectName("trashApproval")
        dialog.setWindowTitle("Send file to Recycle Bin?")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(640, 320)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Send this file to the Windows Recycle Bin:", dialog))
        details = QPlainTextEdit(dialog)
        details.setObjectName("approvalDetails")
        details.setPlainText(preview)
        details.setReadOnly(True)
        layout.addWidget(details, 1)
        notice = QLabel("Approval is for this exact file only. Directories and permanent deletion are not part of this checkpoint.", dialog)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
        trash = buttons.addButton("Send to Recycle Bin", QDialogButtonBox.ButtonRole.AcceptRole)
        trash.setObjectName("approveTrash")
        trash.setAutoDefault(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)

        def refresh():
            try:
                pending = self.service.approval_status(record.approval_id) == "pending"
            except (LookupError, ValueError):
                pending = False
            if not pending:
                dialog.reject()

        def finish(code):
            timer.stop()
            self.service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
            self._approval_dialog = None
            dialog.deleteLater()

        timer.timeout.connect(refresh)
        dialog.finished.connect(finish)
        self._approval_dialog = dialog
        self.activity.set_activity("Waiting for trash approval...")
        timer.start(100)
        dialog.open()
        cancel.setFocus()

    def _show_text_write_approval(self, record) -> None:
        preview = getattr(record, "approval_preview", None)
        if record.capability != "filesystem.write_text" or not record.resource or not isinstance(preview, str):
            self.service.resolve_approval(record.approval_id, False)
            return
        if self.service.approval_status(record.approval_id) != "pending":
            return
        dialog = QDialog(self)
        dialog.setObjectName("writeApproval")
        dialog.setWindowTitle("Write text file?")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Write text to:", dialog))
        path = QPlainTextEdit(dialog)
        path.setObjectName("approvalPath")
        path.setPlainText(record.resource)
        path.setReadOnly(True)
        path.setMaximumHeight(92)
        layout.addWidget(path)
        layout.addWidget(QLabel("New file content:", dialog))
        content = QPlainTextEdit(dialog)
        content.setObjectName("approvalContent")
        content.setPlainText(preview)
        content.setReadOnly(True)
        layout.addWidget(content, 1)
        notice = QLabel("This creates the file or replaces the entire existing file. Approval is for this path and content only.", dialog)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
        write = buttons.addButton("Write file", QDialogButtonBox.ButtonRole.AcceptRole)
        write.setObjectName("approveTextWrite")
        write.setAutoDefault(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)

        def refresh():
            try:
                pending = self.service.approval_status(record.approval_id) == "pending"
            except (LookupError, ValueError):
                pending = False
            if not pending:
                dialog.reject()

        def finish(code):
            timer.stop()
            self.service.resolve_approval(record.approval_id, code == QDialog.DialogCode.Accepted)
            self._approval_dialog = None
            dialog.deleteLater()

        timer.timeout.connect(refresh)
        dialog.finished.connect(finish)
        self._approval_dialog = dialog
        self.activity.set_activity("Waiting for file approval...")
        timer.start(100)
        dialog.open()
        cancel.setFocus()

    @Slot(str)
    def _worker_succeeded(self, text: str) -> None:
        self._done(text, False)

    @Slot(str)
    def _worker_failed(self, text: str) -> None:
        self._done(text, True)

    def _done(self, text: str, error: bool) -> None:
        if self.inference is not None:
            notice = self.inference.consume_notice()
            if notice:
                text = f"{text}\n\n{notice}"
            self._sync_inference_selector()
        self._update_context_window()
        self._set_busy(False)
        self.chat.add_message("Agent", text, error)

    @Slot()
    def _thread_finished(self) -> None:
        self.thread.deleteLater()
        self.thread = None
        self.worker = None

    def _set_busy(self, busy: bool) -> None:
        self.send.setEnabled(not busy)
        self.stop.setEnabled(busy and self.service is not None)
        self.send.setVisible(not busy)
        self.stop.setVisible(busy)
        self.input.setEnabled(not busy)
        self.model_selector.setEnabled(not busy and self.inference is not None)
        self.new_session_button.setEnabled(not busy and self.service is not None)
        self.chat.set_thinking(busy)
        self.activity.set_activity("" if busy else self._ready_status())

    def cancel_current_task(self) -> None:
        cancel = getattr(self.service, "cancel_current_task", None)
        if callable(cancel):
            cancel()
            self.stop.setEnabled(False)
            self.activity.set_activity("Stopping...")

    def create_new_session(self) -> None:
        if self.thread is not None:
            return
        reset = getattr(self.service, "new_session", None)
        if not callable(reset):
            return
        try:
            reset()
        except Exception as exc:
            self.chat.add_message("Agent", str(exc), True)
            return
        self.chat.clear_messages()
        self.input.clear()
        self._update_context_window()
        self.activity.set_activity(self._ready_status())
        self.input.setFocus()

    def _ready_status(self) -> str:
        if self._agent_error() and not self._agent_enabled():
            return "Agent unavailable · Chat only"
        if self.inference is None:
            return "Ready · Chat only"
        if self._agent_enabled():
            listing_enabled = self._filesystem_list_enabled()
            find_enabled = self._filesystem_find_enabled()
            text_read_enabled = self._filesystem_read_text_enabled()
            search_enabled = self._filesystem_search_enabled()
            parts = ["Metadata"]
            if find_enabled:
                parts.append("find")
            if listing_enabled:
                parts.append("listing")
            if text_read_enabled:
                parts.append("text")
            if search_enabled:
                parts.append("search")
            read_capabilities = "Metadata only" if parts == ["Metadata"] else " + ".join(parts)
            read_status = (
                f"Full local read · {read_capabilities}"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else f"Portable-root read · {read_capabilities}"
            )
            if "filesystem.mkdir" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Folder approval"
            if "filesystem.write_text" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Text-write approval"
            if "filesystem.copy" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Copy approval"
            if "filesystem.move" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Move approval"
            if "filesystem.trash" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Trash approval"
            if self.inference.mode == "cloud":
                return (
                    f"Cloud key needed · Agent · {read_status}"
                    if not self.inference.cloud_has_api_key
                    else f"Ready · Cloud · Agent · {read_status}"
                )
            return f"Ready · Local · Agent · {read_status}"
        if self.inference.mode == "cloud":
            return (
                "Cloud key needed · Chat only"
                if not self.inference.cloud_has_api_key
                else "Ready · Cloud · Chat only"
            )
        return "Ready · Local · Chat only"

    @Slot(int)
    def _select_inference_mode(self, index: int) -> None:
        if self.inference is None or index < 0:
            return
        requested = self.model_selector.itemData(index)
        previous = self.inference.mode
        if requested == "cloud" and not self._ensure_cloud_ready():
            self._sync_inference_selector()
            return
        try:
            self.inference.set_mode(requested)
        except InferenceUnavailable as exc:
            self.chat.add_message("Agent", str(exc), True)
            self.inference.set_mode(previous)
        self._sync_inference_selector()
        self._update_context_window()
        self.activity.set_activity(self._ready_status())

    def _ensure_cloud_ready(self) -> bool:
        if self.inference is None:
            return False
        if not self._cloud_privacy_accepted:
            answer = QMessageBox.question(
                self,
                "Use cloud model?",
                self._cloud_privacy_message(),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            self._cloud_privacy_accepted = True
        if not self.inference.cloud_has_api_key:
            key, accepted = QInputDialog.getText(
                self,
                f"{self.inference.cloud_provider_name} API key",
                "Enter the API key for this session. It will not be saved to the USB drive:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted or not key.strip():
                return False
            self.inference.set_cloud_api_key(key)
        return True

    def _agent_enabled(self) -> bool:
        return bool(getattr(self.service, "agent_enabled", False))

    def _agent_error(self) -> str | None:
        value = getattr(self.service, "agent_error", None)
        return str(value) if value else None

    def _host_read_scope(self) -> HostReadScope | None:
        value = getattr(self.service, "host_read_scope", None)
        try:
            return HostReadScope(value) if value is not None else None
        except ValueError:
            return None

    def _filesystem_list_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.list" in values

    def _filesystem_find_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.find" in values

    def _filesystem_read_text_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.read_text" in values

    def _filesystem_search_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.search" in values

    def _cloud_privacy_message(self) -> str:
        provider = self.inference.cloud_provider_name
        if self._agent_enabled():
            scope = (
                "across enabled local filesystem drives that the current Windows account can access"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else "inside O.R.S.I's portable root"
            )
            find_enabled = self._filesystem_find_enabled()
            listing_enabled = self._filesystem_list_enabled()
            text_read_enabled = self._filesystem_read_text_enabled()
            search_enabled = self._filesystem_search_enabled()
            result_parts = ["filesystem.stat metadata"]
            access_parts = ["inspect metadata"]
            if find_enabled:
                result_parts.append("filesystem.find matching file and folder names")
                access_parts.append("resolve exact file or folder names inside one requested folder")
            if listing_enabled:
                result_parts.append("filesystem.list directory names and types")
                access_parts.append("list one requested directory")
            if text_read_enabled:
                result_parts.append("filesystem.read_text file content")
                access_parts.append("read bounded text from one specifically requested file")
            if search_enabled:
                result_parts.append("filesystem.search matching snippets")
                access_parts.append("search bounded text snippets inside one requested directory")
            if len(result_parts) == 1:
                results = f"{result_parts[0]} results"
            elif len(result_parts) == 2:
                results = " and ".join(result_parts)
            else:
                results = ", ".join(result_parts[:-1]) + f", and {result_parts[-1]}"
            if len(access_parts) == 1:
                access = f"{access_parts[0]} for one requested file or directory"
            elif len(access_parts) == 2:
                access = " or ".join(access_parts)
            else:
                access = ", ".join(access_parts[:-1]) + f", or {access_parts[-1]}"
            if text_read_enabled or search_enabled:
                boundary = "but cannot write or perform other computer actions"
                confidentiality = (
                    "File content, snippets, and directory or file names may be confidential"
                    if search_enabled
                    else "File content and directory or file names may be confidential"
                )
            else:
                boundary = "but cannot read file content, search, or perform other computer actions"
                confidentiality = "Directory and file names may be confidential"
            mkdir_enabled = "filesystem.mkdir" in getattr(self.service, "agent_capabilities", ())
            text_write_enabled = "filesystem.write_text" in getattr(self.service, "agent_capabilities", ())
            copy_enabled = "filesystem.copy" in getattr(self.service, "agent_capabilities", ())
            move_enabled = "filesystem.move" in getattr(self.service, "agent_capabilities", ())
            trash_enabled = "filesystem.trash" in getattr(self.service, "agent_capabilities", ())
            write_actions = []
            approved_results = []
            if mkdir_enabled:
                write_actions.append("create one empty folder")
                approved_results.append("approved folder paths")
            if text_write_enabled:
                write_actions.append("create or replace one text file")
                approved_results.append("text-write paths and content")
            if copy_enabled:
                write_actions.append("copy one regular file")
                approved_results.append("copy paths")
            if move_enabled:
                write_actions.append("move one regular file")
                approved_results.append("move paths")
            if trash_enabled:
                write_actions.append("send one regular file to the Recycle Bin")
                approved_results.append("trash paths")
            if write_actions:
                if len(write_actions) == 1:
                    actions = write_actions[0]
                else:
                    actions = ", ".join(write_actions[:-1]) + f", or {write_actions[-1]}"
                delete_boundary = (
                    "it cannot permanently delete entries or trash directories"
                    if trash_enabled
                    else "it cannot trash entries or delete anything except the source of an approved move"
                    if move_enabled
                    else "it cannot move, trash, or delete entries"
                )
                boundary = (
                    f"and can {actions} only after separate approval of exact paths and, when "
                    f"relevant, exact content or collision policy; {delete_boundary}"
                )
                if len(approved_results) == 1:
                    results += f" plus {approved_results[0]}"
                else:
                    results += " plus " + ", ".join(approved_results[:-1]) + f", and {approved_results[-1]}"
            return (
                f"Cloud mode sends this conversation and any {results} to {provider}. Agent mode "
                f"can {access} {scope}, {boundary}.\n\n{confidentiality}. Do not use Cloud mode "
                "for confidential information.\n\nContinue?"
            )
        return (
            f"Cloud mode sends this conversation to {provider}. O.R.S.I is chat-only and cannot "
            "access or operate your computer.\n\nDo not use Cloud mode for confidential "
            "information.\n\nContinue?"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._approval_dialog is not None:
            self._approval_dialog.reject()
        shutdown = getattr(self.service, "shutdown", None)
        if callable(shutdown):
            shutdown()
        super().closeEvent(event)

    def _sync_inference_selector(self) -> None:
        if self.inference is None:
            return
        index = self.model_selector.findData(self.inference.mode)
        if index >= 0 and index != self.model_selector.currentIndex():
            self.model_selector.blockSignals(True)
            self.model_selector.setCurrentIndex(index)
            self.model_selector.blockSignals(False)

    def _runtime_mode_label(self) -> str:
        if self.inference is None:
            return "Local"
        return "Cloud" if self.inference.mode == "cloud" else "Local"

    def _update_context_window(self) -> None:
        length = int(getattr(self.inference, "context_length", 0))
        self.context_window.set_runtime_mode(self._runtime_mode_label())
        self.context_window.set_context_length(length)
        estimate = getattr(self.service, "estimated_context_tokens", None)
        used = estimate() if callable(estimate) else 0
        self.context_window.set_used_tokens(used)


_STYLE = """
QDialog#folderApproval, QDialog#writeApproval, QDialog#copyApproval, QDialog#moveApproval, QDialog#trashApproval {
    background: #202224;
    color: #ededed;
}
QDialog#folderApproval QLabel, QDialog#writeApproval QLabel, QDialog#copyApproval QLabel, QDialog#moveApproval QLabel, QDialog#trashApproval QLabel {
    color: #dedede;
    font-family: Arial;
    font-size: 14px;
}
QPlainTextEdit#approvalPath, QPlainTextEdit#approvalContent, QPlainTextEdit#approvalDetails {
    background: #151719;
    color: #f2f2f2;
    border: 1px solid #55595c;
    padding: 8px;
    font-family: Consolas;
    font-size: 14px;
    selection-background-color: #355e7e;
}
QDialog#folderApproval QPushButton, QDialog#writeApproval QPushButton, QDialog#copyApproval QPushButton, QDialog#moveApproval QPushButton, QDialog#trashApproval QPushButton {
    background: #34383b;
    color: #f1f1f1;
    border: 1px solid #64696d;
    border-radius: 4px;
    padding: 7px 15px;
    font-family: Arial;
    font-size: 14px;
}
QDialog#folderApproval QPushButton:focus, QDialog#writeApproval QPushButton:focus, QDialog#copyApproval QPushButton:focus, QDialog#moveApproval QPushButton:focus, QDialog#trashApproval QPushButton:focus { border: 2px solid #91bfe0; }
QDialog#folderApproval QPushButton:hover, QDialog#writeApproval QPushButton:hover, QDialog#copyApproval QPushButton:hover, QDialog#moveApproval QPushButton:hover, QDialog#trashApproval QPushButton:hover { background: #42484d; }
QMainWindow#mainWindow, QWidget#root {
    background: #050506;
    color: #d7d7d9;
    font-family: Arial;
}
QWidget#mainContent, QWidget#chatContent { background: transparent; }
QWidget#topBar {
    background: #050506;
    border-bottom: 1px solid #101217;
}
QPushButton#topBarButton {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 0;
}
QPushButton#topBarButton:hover { background: #15161a; }
QPushButton#topBarButton:pressed { background: #202128; }
QPushButton#topBarButton:disabled { background: transparent; }
QFrame#topBarSeparator {
    background: #15161a;
    border: none;
}
QFrame#settingsPanel {
    background: #252627;
    border: 1px solid #3a3b3c;
    border-radius: 15px;
}
QLabel#settingsTitle {
    color: #e1e1e1;
    background: transparent;
    border: none;
    font-size: 16px;
    font-weight: 600;
}
QLabel#settingsLabel {
    color: #a8a8a8;
    background: transparent;
    border: none;
    font-size: 12px;
}
QWidget#contextWindow { background: transparent; }
QLabel#contextStatusLine {
    color: #d6d4d4;
    background: transparent;
    border: none;
    font-family: Arial;
    font-size: 17px;
}
QLabel#contextWindowTitle, QLabel#contextWindowSize {
    color: #a8a8a8;
    background: transparent;
    font-size: 11px;
}
QLabel#contextWindowSize { color: #dedede; }
QProgressBar#contextWindowBar {
    background: #303030;
    border: none;
    border-radius: 2px;
}
QProgressBar#contextWindowBar::chunk {
    background: #d4d4d4;
    border-radius: 2px;
}
QScrollArea#chatView { background: transparent; border: none; }
QScrollArea#chatView QWidget#qt_scrollarea_viewport { background: transparent; }
QFrame#userMessage {
    background: transparent;
    border: none;
    border-radius: 27px;
}
QFrame#orsiMessage, QFrame#errorMessage { background: transparent; border: none; }
QFrame#userMessage QLabel, QFrame#orsiMessage QLabel {
    color: #e3e3e4;
    font-family: Arial;
    font-size: 22px;
    font-weight: 400;
}
QFrame#userMessage QLabel { font-size: 21px; }
QFrame#errorMessage QLabel { color: #ff8d86; font-size: 16px; }
QFrame#codeBlock {
    background: #202020;
    border: 1px solid #3b3b3b;
    border-radius: 9px;
}
QWidget#codeHeader {
    background: #292929;
    border: none;
    border-bottom: 1px solid #3b3b3b;
}
QLabel#codeLanguage {
    color: #a9a9a9;
    background: transparent;
    border: none;
    font-size: 11px;
}
QPushButton#copyCodeButton {
    color: #d8d8d8;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0 7px;
    font-size: 11px;
}
QPushButton#copyCodeButton:hover { background: #383838; }
QPushButton#copyCodeButton:pressed { background: #222222; }
QPlainTextEdit#codeEditor {
    color: #e8e8e8;
    background: #202020;
    border: none;
    padding: 9px;
    selection-color: #ffffff;
    selection-background-color: #505050;
}
QLabel#conversationStatus {
    color: #929292;
    background: transparent;
    min-height: 18px;
    padding: 0;
    font-size: 11px;
}
QFrame#composer {
    background: transparent;
    border: none;
    border-radius: 36px;
}
QTextEdit#messageInput {
    color: #dedee0;
    background: transparent;
    border: none;
    padding: 11px 0 4px 4px;
    font-family: Arial;
    font-size: 24px;
    selection-background-color: #666666;
}
QTextEdit#messageInput:focus { border: none; }
QTextEdit#messageInput:disabled { color: #777777; background: transparent; }
QPushButton#sendButton, QPushButton#stopButton {
    background: transparent;
    border: none;
    border-radius: 21px;
    padding: 0;
}
QPushButton#sendButton:hover, QPushButton#stopButton:hover { background: #454852; }
QPushButton#sendButton:pressed, QPushButton#stopButton:pressed { background: #2c2e35; }
QPushButton#sendButton:disabled, QPushButton#stopButton:disabled { background: transparent; }
QComboBox#modelSelector {
    color: #ededed;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 12px;
    padding: 0 12px;
    min-width: 92px;
}
QComboBox#modelSelector:hover, QComboBox#modelSelector:focus { border-color: #666666; }
QComboBox#modelSelector::drop-down { border: none; width: 20px; }
QComboBox#modelSelector QAbstractItemView {
    color: #ededed;
    background: #262626;
    border: 1px solid #424242;
    selection-background-color: #3b3b3b;
}
QScrollBar:vertical { background: transparent; width: 14px; margin: 0; }
QScrollBar::handle:vertical {
    background: #3f4149;
    border-radius: 6px;
    min-height: 72px;
    margin: 0 6px 0 0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
