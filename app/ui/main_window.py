from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.inference.engine import InferenceUnavailable
from app.ui.chat import ChatView
from app.ui.status import ConversationStatus


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
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(0)

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

        self.input = QLineEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Ask O.R.S.I")
        self.input.setMinimumHeight(42)

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
        self.input.returnPressed.connect(self.submit)
        if startup_error:
            self.chat.add_message("Agent", startup_error, True)

    def submit(self) -> None:
        message = self.input.text().strip()
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
        self.chat.set_thinking(busy)
        self.activity.set_activity("" if busy else self._ready_status())

    def cancel_current_task(self) -> None:
        cancel = getattr(self.service, "cancel_current_task", None)
        if callable(cancel):
            cancel()
            self.stop.setEnabled(False)
            self.activity.set_activity("Stopping...")

    def _ready_status(self) -> str:
        if self.inference is None:
            return "Ready · Chat only"
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
        self.activity.set_activity(self._ready_status())

    def _ensure_cloud_ready(self) -> bool:
        if self.inference is None:
            return False
        if not self._cloud_privacy_accepted:
            answer = QMessageBox.question(
                self,
                "Use cloud model?",
                "Cloud mode sends this conversation to "
                f"{self.inference.cloud_provider_name}. O.R.S.I is chat-only and cannot access or "
                "operate your computer.\n\nDo not use Cloud mode for confidential information.\n\nContinue?",
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

    def _sync_inference_selector(self) -> None:
        if self.inference is None:
            return
        index = self.model_selector.findData(self.inference.mode)
        if index >= 0 and index != self.model_selector.currentIndex():
            self.model_selector.blockSignals(True)
            self.model_selector.setCurrentIndex(index)
            self.model_selector.blockSignals(False)


_STYLE = """
QMainWindow#mainWindow, QWidget#root, QWidget#chatContent {
    background: #171717;
    color: #ececec;
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
QLabel#conversationStatus {
    color: #929292;
    background: transparent;
    min-height: 18px;
    padding: 0 18px;
    font-size: 11px;
}
QWidget#composer { background: #171717; }
QLineEdit#messageInput {
    color: #f1f1f1;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 14px;
    padding: 0 14px;
    selection-background-color: #10a37f;
}
QLineEdit#messageInput:focus { border-color: #666666; }
QLineEdit#messageInput:disabled { color: #888888; background: #202020; }
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
