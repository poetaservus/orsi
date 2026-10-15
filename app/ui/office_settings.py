"""Basic Office controls. All discovery/stdio/COM work stays off the UI thread."""
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from app.runtime.cancellation import CancellationSource
from app.ui.inputs import ScrollSafeComboBox
from app.ui.localization import QLabel, QWidget
from app.ui.settings_layout import SettingsButton


class OfficeWorker(QThread):
    completed = Signal(str, object)
    failed = Signal()

    def __init__(self, connection, action, document=None, parent=None):
        super().__init__(parent)
        self.connection, self.action, self.document = connection, action, document
        self.cancel = CancellationSource()

    def run(self):
        try:
            if self.action == "connect":
                self.connection.connect(self.cancel.token)
                result = self.connection.list_documents(cancellation=self.cancel.token)
            elif self.action == "refresh":
                result = self.connection.refresh(self.cancel.token)
            elif self.action == "disconnect":
                self.connection.disconnect()
                result = []
            else:
                result = self.connection.select_document(self.document, self.cancel.token)
            self.completed.emit(self.action, result)
        except Exception:
            self.failed.emit()


class OfficeControls(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window, self.worker = window, None
        self.connection = getattr(window.service, "office_connection", None)
        self._selected = False
        self._last_state = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 20)
        heading = QLabel("Office documents")
        heading.setObjectName("settingsGroupTitle")
        layout.addWidget(heading)
        hint = QLabel("Read open documents and edit Excel cells in Cloud mode. Saving is separate; Excel recovery stays available while connected.")
        hint.setWordWrap(True)
        hint.setObjectName("settingsDescription")
        layout.addWidget(hint)
        self.status = QLabel("Disconnected")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.documents = ScrollSafeComboBox()
        self.documents.setAccessibleName("Open Office document")
        self.documents.addItem("Choose a document", None)
        self.documents.currentIndexChanged.connect(self._choice_changed)
        layout.addWidget(self.documents)
        row = QHBoxLayout()
        self.connect_button = SettingsButton("Connect")
        self.disconnect_button = SettingsButton("Disconnect")
        self.refresh_button = SettingsButton("Refresh")
        self.select_button = SettingsButton("Use document")
        for button, action in ((self.connect_button, "connect"), (self.disconnect_button, "disconnect"),
                               (self.refresh_button, "refresh"), (self.select_button, "select")):
            row.addWidget(button)
            button.clicked.connect(lambda checked=False, action=action: self.start(action))
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.sync)
        self.timer.start()
        self.sync()

    def _choice_changed(self):
        # A dropdown choice alone grants no authority; Use document is explicit.
        self.sync()

    def sync(self):
        idle = self.worker is None and self.window.thread is None and not self.window._settings_busy
        cloud = getattr(self.window.inference, "mode", None) == "cloud"
        ready = self.connection is not None and self.connection.exposure.ready
        available = (idle and cloud and self.connection is not None
                     and not getattr(self.window, "_profile_locked", False) and not getattr(self.window, "_closing", False))
        self.connect_button.setEnabled(available and not ready)
        self.disconnect_button.setEnabled(idle and ready)
        self.refresh_button.setEnabled(available and ready)
        self.select_button.setEnabled(available and ready and self.documents.currentData() is not None)
        self.documents.setEnabled(available and ready)
        if self.worker is None and (cloud, ready) != self._last_state:
            self._last_state = (cloud, ready)
            if not cloud:
                self.status.setText("Office reads require Cloud mode.")
            elif not ready:
                self.status.setText("Disconnected")
                self._selected = False
                self.documents.clear()
                self.documents.addItem("Choose a document", None)
            else:
                self.status.setText("Document selected · Ready to read" if self._selected else "Connected · Choose a document")

    def start(self, action):
        if self.worker is not None or self.window.thread is not None or self.window._settings_busy:
            return
        self.window._settings_worker_busy(True)
        self.status.setText("Connecting…" if action == "connect" else "Working…")
        self.worker = OfficeWorker(self.connection, action, self.documents.currentData(), self)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(lambda: self.status.setText("Office is unavailable. Close any Office dialog and refresh."))
        self.worker.finished.connect(self._finished)
        self.sync()
        self.worker.start()

    def _completed(self, action, result):
        if getattr(self.window, "_closing", False):
            return
        if action == "select":
            self._selected = True
            self.status.setText("Document selected · Ready to read")
        else:
            self.documents.clear()
            self.documents.addItem("Choose a document", None)
            for document in result:
                label = document["application"].title() + " · " + document["title"]
                if not document["has_path"]:
                    label += " · Unsaved"
                self.documents.addItem(label, document["document"])
            self._selected = False
            self.status.setText("Connected · Choose a document" if result else
                                "Connected · No open documents" if action != "disconnect" else "Disconnected")

    def _finished(self):
        self.worker.deleteLater()
        self.worker = None
        if getattr(self.window, "_closing", False):
            self.window.close()
        else:
            self.window._settings_worker_busy(False)
            self.sync()

    def stop(self):
        if self.worker is not None:
            self.worker.cancel.cancel()

    def revoke(self):
        self.timer.stop()
        self.stop()
        self.clear()

    def clear(self):
        self.documents.clear()
        self.status.clear()
        self._selected = False
