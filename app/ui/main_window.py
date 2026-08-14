from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
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


class MainWindow(QMainWindow):
    def __init__(self, service, hostname: str, startup_error: str | None = None, inference=None):
        super().__init__()
        del hostname
        self.service = service
        self.inference = inference
        self.startup_error = startup_error
        self._cloud_privacy_accepted = False
        self.thread = None
        self.worker = None

        self.setObjectName("mainWindow")
        self.setWindowTitle("O.R.S.I")
        self.resize(760, 640)

        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(52)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(7, 11, 7, 11)
        sidebar_layout.setSpacing(5)

        self.new_session_button = QPushButton()
        self.new_session_button.setObjectName("sidebarButton")
        self.new_session_button.setFixedSize(38, 38)
        self.new_session_button.setIcon(QIcon(str(_ICON_DIRECTORY / "new_session.svg")))
        self.new_session_button.setIconSize(QSize(21, 21))
        self.new_session_button.setToolTip("New session — permanently clears this conversation")
        self.new_session_button.setAccessibleName("New session")
        self.new_session_button.setEnabled(service is not None)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("sidebarButton")
        self.settings_button.setFixedSize(38, 38)
        self.settings_button.setIcon(QIcon(str(_ICON_DIRECTORY / "settings.svg")))
        self.settings_button.setIconSize(QSize(20, 20))
        self.settings_button.setToolTip("Settings — coming later")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setEnabled(False)

        sidebar_layout.addWidget(self.new_session_button)
        sidebar_layout.addWidget(self.settings_button)
        sidebar_layout.addStretch(1)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("mainContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        context_header = QWidget()
        context_header.setObjectName("contextHeader")
        context_header_layout = QHBoxLayout(context_header)
        context_header_layout.setContentsMargins(12, 12, 16, 6)
        context_header_layout.setSpacing(0)
        context_header_layout.addStretch(1)
        self.context_window = ContextWindowBar(
            int(getattr(inference, "context_length", 0))
        )
        context_header_layout.addWidget(self.context_window)
        layout.addWidget(context_header)

        self.chat = ChatView()
        layout.addWidget(self.chat, 1)
        self.activity = ConversationStatus(
            self._ready_status() if not startup_error else "Model unavailable"
        )
        layout.addWidget(self.activity)

        composer = QWidget()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(14, 8, 14, 0)
        composer_layout.setSpacing(8)

        self.input = MessageInput()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Ask O.R.S.I")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(42)

        self.model_selector = QComboBox()
        self.model_selector.setObjectName("modelSelector")
        self.model_selector.setMinimumHeight(42)
        if inference is None:
            self.model_selector.addItem("Local", "local")
            self.model_selector.setEnabled(False)
        else:
            for mode in inference.available_modes:
                self.model_selector.addItem("Local" if mode == "local" else "Cloud · Free", mode)
            self._sync_inference_selector()
            self.model_selector.currentIndexChanged.connect(self._select_inference_mode)

        self.send = QPushButton("Send")
        self.send.setObjectName("sendButton")
        self.send.setMinimumHeight(42)
        self.stop = QPushButton("Stop")
        self.stop.setObjectName("stopButton")
        self.stop.setMinimumHeight(42)
        self.stop.setEnabled(False)

        composer_layout.addWidget(self.input, 1)
        composer_layout.addWidget(self.model_selector)
        composer_layout.addWidget(self.send)
        composer_layout.addWidget(self.stop)
        layout.addWidget(composer)

        self.setCentralWidget(root)
        self.setStyleSheet(_STYLE)
        self.send.clicked.connect(self.submit)
        self.stop.clicked.connect(self.cancel_current_task)
        self.new_session_button.clicked.connect(self.create_new_session)
        self.input.submit_requested.connect(self.submit)
        self._update_context_window()
        if startup_error:
            self.chat.add_message("Agent", startup_error, True)
        elif self._agent_error():
            self.chat.add_message("Agent", self._agent_error(), True)

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
            read_status = (
                "Full local read · Metadata only"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else "Portable-root read · Metadata only"
            )
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

    def _cloud_privacy_message(self) -> str:
        provider = self.inference.cloud_provider_name
        if self._agent_enabled():
            scope = (
                "across enabled local filesystem drives that the current Windows account can access"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else "inside O.R.S.I's portable root"
            )
            return (
                f"Cloud mode sends this conversation and any filesystem.stat metadata results "
                f"to {provider}. Agent mode can inspect metadata for one requested file or "
                f"directory {scope}, but cannot read file content or perform other "
                "computer actions.\n\nDo not use Cloud mode for confidential information.\n\nContinue?"
            )
        return (
            f"Cloud mode sends this conversation to {provider}. O.R.S.I is chat-only and cannot "
            "access or operate your computer.\n\nDo not use Cloud mode for confidential "
            "information.\n\nContinue?"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
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

    def _update_context_window(self) -> None:
        length = int(getattr(self.inference, "context_length", 0))
        self.context_window.set_context_length(length)
        estimate = getattr(self.service, "estimated_context_tokens", None)
        used = estimate() if callable(estimate) else 0
        self.context_window.set_used_tokens(used)


_STYLE = """
QMainWindow#mainWindow, QWidget#root, QWidget#mainContent, QWidget#chatContent,
QWidget#contextHeader, QWidget#sidebar {
    background: #171717;
    color: #ececec;
}
QWidget#sidebar {
    border-right: 1px solid #353535;
}
QPushButton#sidebarButton {
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 0;
}
QPushButton#sidebarButton:hover { background: #292929; }
QPushButton#sidebarButton:pressed { background: #222222; }
QPushButton#sidebarButton:disabled { background: transparent; }
QWidget#contextWindow { background: transparent; }
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
QScrollArea#chatView { background: #171717; border: none; }
QFrame#userMessage {
    background: #303030;
    border: 1px solid #3a3a3a;
    border-radius: 15px;
}
QFrame#orsiMessage, QFrame#errorMessage { background: transparent; border: none; }
QFrame#userMessage QLabel, QFrame#orsiMessage QLabel { color: #eeeeee; font-size: 14px; }
QFrame#errorMessage QLabel { color: #ff8d86; font-size: 14px; }
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
    padding: 0 18px;
    font-size: 11px;
}
QWidget#composer { background: #171717; }
QTextEdit#messageInput {
    color: #f1f1f1;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 14px;
    padding: 8px 12px;
    selection-background-color: #10a37f;
}
QTextEdit#messageInput:focus { border-color: #666666; }
QTextEdit#messageInput:disabled { color: #888888; background: #202020; }
QPushButton {
    color: #ededed;
    background: #303030;
    border: 1px solid #424242;
    border-radius: 12px;
    padding: 0 14px;
}
QPushButton:hover { background: #3b3b3b; }
QPushButton:pressed { background: #252525; }
QPushButton:disabled { color: #777777; background: #242424; border-color: #303030; }
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
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #444444; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
