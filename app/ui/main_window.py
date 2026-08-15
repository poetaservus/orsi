from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
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
_SIDEBAR_WIDTH = 98
_CONVERSATION_WIDTH = 968
_COMPOSER_HEIGHT = 94
_COMPOSER_BOTTOM_MARGIN = 36
_COMPOSER_RIGHT_COMPENSATION = 60


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
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(26, 29, 26, 20)
        sidebar_layout.setSpacing(20)

        self.new_session_button = QPushButton()
        self.new_session_button.setObjectName("sidebarButton")
        self.new_session_button.setFixedSize(46, 46)
        self.new_session_button.setIcon(QIcon(str(_ICON_DIRECTORY / "new_session.svg")))
        self.new_session_button.setIconSize(QSize(32, 32))
        self.new_session_button.setToolTip("New session — permanently clears this conversation")
        self.new_session_button.setAccessibleName("New session")
        self.new_session_button.setEnabled(service is not None)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("sidebarButton")
        self.settings_button.setFixedSize(46, 46)
        self.settings_button.setIcon(QIcon(str(_ICON_DIRECTORY / "settings.svg")))
        self.settings_button.setIconSize(QSize(32, 32))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")

        sidebar_layout.addWidget(self.new_session_button)
        sidebar_layout.addWidget(self.settings_button)
        sidebar_layout.addStretch(1)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("mainContent")
        self._content = content
        content.installEventFilter(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        self.chat = ChatView()
        content_layout.addWidget(self.chat, 1)

        self.settings_panel = QFrame(root)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setFixedSize(314, 218)
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

        self.context_window = ContextWindowBar(
            int(getattr(inference, "context_length", 0))
        )
        settings_layout.addWidget(self.context_window)

        self.activity = ConversationStatus(
            self._ready_status() if not startup_error else "Model unavailable"
        )
        settings_layout.addWidget(self.activity)
        self.settings_panel.hide()

        self.composer = QFrame(content)
        self.composer.setObjectName("composer")
        self.composer.setFixedHeight(_COMPOSER_HEIGHT)
        composer_layout = QHBoxLayout(self.composer)
        composer_layout.setContentsMargins(26, 10, 16, 10)
        composer_layout.setSpacing(8)

        self.input = MessageInput()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Ask O.R.S.I")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(74)

        self.send = QPushButton()
        self.send.setObjectName("sendButton")
        self.send.setFixedSize(56, 56)
        self.send.setIcon(QIcon(str(_ICON_DIRECTORY / "send.svg")))
        self.send.setIconSize(QSize(34, 34))
        self.send.setToolTip("Send")
        self.send.setAccessibleName("Send")

        self.stop = QPushButton()
        self.stop.setObjectName("stopButton")
        self.stop.setFixedSize(56, 56)
        self.stop.setIcon(QIcon(str(_ICON_DIRECTORY / "stop.svg")))
        self.stop.setIconSize(QSize(22, 22))
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
        available_width = max(0, content.width() - _COMPOSER_RIGHT_COMPENSATION)
        width = min(_CONVERSATION_WIDTH, max(320, available_width - 32))
        x = max(16, (available_width - width) // 2)
        y = max(16, content.height() - _COMPOSER_BOTTOM_MARGIN - _COMPOSER_HEIGHT)
        self.composer.setGeometry(x, y, width, _COMPOSER_HEIGHT)
        self.composer.raise_()
        self.settings_panel.move(_SIDEBAR_WIDTH + 14, 99)
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
            read_capabilities = (
                "Metadata + listing"
                if self._filesystem_list_enabled()
                else "Metadata only"
            )
            read_status = (
                f"Full local read · {read_capabilities}"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else f"Portable-root read · {read_capabilities}"
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

    def _filesystem_list_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.list" in values

    def _cloud_privacy_message(self) -> str:
        provider = self.inference.cloud_provider_name
        if self._agent_enabled():
            scope = (
                "across enabled local filesystem drives that the current Windows account can access"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else "inside O.R.S.I's portable root"
            )
            if self._filesystem_list_enabled():
                results = (
                    "filesystem.stat metadata and filesystem.list directory names and types"
                )
                access = "inspect metadata or list one requested directory"
            else:
                results = "filesystem.stat metadata results"
                access = "inspect metadata for one requested file or directory"
            return (
                f"Cloud mode sends this conversation and any {results} to {provider}. Agent mode "
                f"can {access} {scope}, but cannot read file content or perform other computer "
                "actions.\n\nDirectory and file names may be confidential. Do not use Cloud mode "
                "for confidential information.\n\nContinue?"
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
QMainWindow#mainWindow, QWidget#root, QWidget#mainContent, QWidget#chatContent {
    background: #121416;
    color: #ababab;
    font-family: Arial;
}
QWidget#sidebar {
    background: #101010;
    border-right: 1px solid #272727;
}
QPushButton#sidebarButton {
    background: transparent;
    border: none;
    border-radius: 12px;
    padding: 0;
}
QPushButton#sidebarButton:hover { background: #222222; }
QPushButton#sidebarButton:pressed { background: #2a2a2a; }
QPushButton#sidebarButton:disabled { background: transparent; }
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
QScrollArea#chatView { background: #121416; border: none; }
QFrame#userMessage {
    background: #28292a;
    border: none;
    border-radius: 26px;
}
QFrame#orsiMessage, QFrame#errorMessage { background: transparent; border: none; }
QFrame#userMessage QLabel, QFrame#orsiMessage QLabel {
    color: #adadad;
    font-family: Arial;
    font-size: 23px;
    font-weight: 400;
}
QFrame#userMessage QLabel { font-size: 22px; }
QFrame#errorMessage QLabel { color: #ff8d86; font-size: 18px; }
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
    background: #3a3a3b;
    border: none;
    border-radius: 19px;
}
QTextEdit#messageInput {
    color: #b2b2b2;
    background: transparent;
    border: none;
    padding: 14px 0 8px 8px;
    font-family: Arial;
    font-size: 25px;
    selection-background-color: #666666;
}
QTextEdit#messageInput:focus { border: none; }
QTextEdit#messageInput:disabled { color: #777777; background: transparent; }
QPushButton#sendButton, QPushButton#stopButton {
    background: #292a2b;
    border: none;
    border-radius: 28px;
    padding: 0;
}
QPushButton#sendButton:hover, QPushButton#stopButton:hover { background: #333435; }
QPushButton#sendButton:pressed, QPushButton#stopButton:pressed { background: #222324; }
QPushButton#sendButton:disabled, QPushButton#stopButton:disabled { background: #292a2b; }
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
QScrollBar:vertical { background: transparent; width: 22px; margin: 0; }
QScrollBar::handle:vertical {
    background: #444444;
    border-radius: 6px;
    min-height: 72px;
    margin: 0 10px 0 0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
