"""A cancellable deployment dialog; profile ownership remains with the local app."""
from app.ui.localization import ui_text, QCheckBox, QDialog, QLineEdit, QPushButton, QRadioButton, QFileDialog

from pathlib import Path

from app.ui.theme_runtime import apply_theme_style
from PySide6.QtCore import QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QProgressBar, QVBoxLayout)

from app.portable.deployment import DeploymentError, deploy_node
from app.portable.identity import DEPLOYMENT_DISABLED, is_deployed_node, node_name
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.ui.personal_profile import _STYLE, label
from app.vault.profiles import public_error


class DeploymentWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, manager, destination, *, include_profile, include_models, parent=None):
        super().__init__(parent)
        self.manager, self.destination = manager, destination
        self.include_profile, self.include_models = include_profile, include_models
        self.cancellation = CancellationSource()
        self._last_progress = None

    def cancel(self):
        self.cancellation.cancel()

    def drain(self):
        if not self.wait(30000):
            raise RuntimeError("Portable deployment is still stopping.")

    def report_progress(self, value, text):
        if (value, text) != self._last_progress:
            self._last_progress = value, text
            self.progress.emit(value, text)

    @Slot()
    def run(self):
        try:
            result = deploy_node(self.manager, self.destination, include_profile=self.include_profile,
                include_models=self.include_models, token=self.cancellation.token, progress=self.report_progress)
            self.succeeded.emit(result)
        except TaskCancelled:
            self.failed.emit("Deployment cancelled. No node was published.")
        except DeploymentError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(public_error(error))


class PortableDeploymentDialog(QDialog):
    def __init__(self, manager, window, parent=None):
        super().__init__(parent or window)
        self.setObjectName("personalProfileDialog")
        apply_theme_style(self, _STYLE + """
            QDialog#personalProfileDialog {
                background: qlineargradient(x1:0, y1:1, x2:1, y2:0, stop:0 #090c15, stop:1 #1d2637);
            }
            QProgressBar { background: #162235; border: 1px solid #3d3d3d; border-radius: 6px; color: #dce5f0; }
            QProgressBar::chunk { background: #3b5675; border-radius: 5px; }
            QPushButton#deployPrimary { background: #3b5675; border-color: #686868; color: #f4f6fb; }
            QPushButton#deployPrimary:hover { background: #46658a; }
            QPushButton#deployPrimary:disabled { background: #243247; color: #8899ad; }
        """)
        self.setWindowTitle(ui_text('Deploy portable node'))
        self.setMinimumWidth(520)
        self.resize(640, 650)
        self.manager, self.window = manager, window
        self.worker = None
        self.result = None
        self._unregister = lambda: None
        self._close_when_finished = False
        QApplication.instance().aboutToQuit.connect(self._shutdown)
        body = QVBoxLayout(self)
        body.setContentsMargins(26, 24, 26, 24)
        body.setSpacing(12)
        heading = label(ui_text('Deploy portable node'))
        heading.setObjectName("profileHeading")
        body.addWidget(heading)
        body.addWidget(label(ui_text('Create a complete O.R.S.I folder on a connected SSD, USB drive or this computer.')))
        self.current = QRadioButton(ui_text('Include my current profile'))
        self.current.setAccessibleName(ui_text('Include current profile'))
        self.current.setEnabled(manager.active)
        self.fresh = QRadioButton(ui_text('Fresh node'))
        self.fresh.setAccessibleName(ui_text('Fresh node'))
        self.current.setChecked(manager.active)
        self.fresh.setChecked(not manager.active)
        body.addWidget(self.current)
        self.profile_description = label(ui_text('Includes your profile, skills, imported files, conversations, preferences and saved backups. Encrypted profiles keep the same password, recovery key and saved connections. Session-only connections stay here.'))
        body.addWidget(self.profile_description)
        body.addWidget(self.fresh)
        body.addWidget(label(ui_text('Starts with profile creation and contains no personal data or saved connections.')))
        self.models = QCheckBox(ui_text('Include installed local models'))
        self.models.setAccessibleName(ui_text('Include installed local models'))
        body.addWidget(self.models)
        body.addWidget(label(ui_text("Leave off for a smaller cloud-only node. Including local models copies this app's installed models and local runtime.")))
        body.addWidget(label(ui_text('External drives are named automatically: O.R.S.I Portable Node Nr. 001, 002, … FAT/exFAT drives use shorter names such as ORSI 001.')))
        body.addWidget(label(ui_text('Destination · choose a new node folder')))
        location_row = QHBoxLayout()
        self.location = QLineEdit()
        self.location.setAccessibleName(ui_text('Portable node destination'))
        self.location.setPlaceholderText(ui_text('Choose where to create the node'))
        self.location.setFixedHeight(38)
        location_row.addWidget(self.location, 1)
        self.choose = QPushButton(ui_text('Choose folder…'))
        self.choose.setFixedHeight(38)
        self.choose.clicked.connect(self._choose)
        location_row.addWidget(self.choose)
        body.addLayout(location_row)
        self.progress = QProgressBar()
        self.progress.setAccessibleName(ui_text('Portable deployment progress'))
        self.progress.setRange(0, 100)
        self.progress.hide()
        body.addWidget(self.progress)
        self.status = label("")
        self.status.setAccessibleName(ui_text('Portable deployment status'))
        body.addWidget(self.status)
        body.addStretch()
        actions = QHBoxLayout()
        self.open_folder = QPushButton(ui_text('Open node folder'))
        self.open_folder.setFixedHeight(38)
        self.open_folder.hide()
        self.open_folder.clicked.connect(self._open_folder)
        actions.addWidget(self.open_folder)
        actions.addStretch()
        self.start_button = QPushButton(ui_text('Deploy node'))
        self.start_button.setObjectName("deployPrimary")
        self.start_button.setFixedHeight(38)
        self.start_button.clicked.connect(self._start)
        actions.addWidget(self.start_button)
        self.close_button = QPushButton(ui_text('Close'))
        self.close_button.setFixedHeight(38)
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.close_button)
        body.addLayout(actions)
        if is_deployed_node(manager.application_root):
            self.start_button.setEnabled(False)
            self.status.setText(DEPLOYMENT_DISABLED)

    def _choose(self):
        parent = QFileDialog.getExistingDirectory(self, ui_text('Choose a drive or parent folder for the new node'))
        if parent:
            self.location.setText(str(Path(parent) / "ORSI-node"))

    def _busy(self):
        return self.worker is not None and self.worker.isRunning()

    def _start(self):
        if is_deployed_node(self.manager.application_root):
            self.status.setText(DEPLOYMENT_DISABLED)
            return
        if self._busy() or self.result is not None:
            return
        if not self.location.text().strip():
            self.status.setText(ui_text('Choose a destination for the new node.'))
            return
        threads = (self.window.thread, self.window.attachment_tray.thread, self.window.skill_settings_page.thread)
        if any(thread is not None and thread.isRunning() for thread in threads):
            self.status.setText(ui_text('Wait for the current chat, file or skill operation to finish, then deploy.'))
            return
        if self.current.isChecked() and not self.manager.active:
            self.status.setText(ui_text('Unlock or open your profile before including it in a node.'))
            return
        if self.window._greeting_save_timer.isActive():
            self.window._greeting_save_timer.stop()
            self.window._save_greeting_message()
        self.status.setText(ui_text('Preparing node…'))
        self.progress.setValue(0)
        self.progress.show()
        self.worker = DeploymentWorker(self.manager, Path(self.location.text().strip()),
            include_profile=self.current.isChecked(), include_models=self.models.isChecked(), parent=self)
        if self.manager.active:
            self._unregister = self.manager.session.register(stop=self.worker.cancel, drain=self.worker.drain)
        self.worker.progress.connect(self._progress)
        self.worker.failed.connect(self.status.setText)
        self.worker.succeeded.connect(self._succeeded)
        self.worker.finished.connect(self._finished)
        for widget in (self.current, self.fresh, self.models, self.location, self.choose, self.start_button):
            widget.setEnabled(False)
        self.close_button.setText(ui_text('Cancel deployment'))
        self.worker.start()

    @Slot(int, str)
    def _progress(self, value, text):
        self.progress.setValue(value)
        self.status.setText(text)

    @Slot(object)
    def _succeeded(self, result):
        self.result = result
        message = node_name(result.node_number) + " is ready. Run ORSI.cmd in the new folder."
        if result.drive_message:
            message += "\n" + result.drive_message
        if not result.copy_registered:
            message += "\nIts location could not be added to profile copy tracking; keep track of this copy separately."
        self.status.setText(message)
        self.open_folder.show()

    @Slot()
    def _finished(self):
        self._unregister()
        self._unregister = lambda: None
        self.worker.deleteLater()
        self.worker = None
        self.close_button.setText(ui_text('Close'))
        self.close_button.setEnabled(True)
        if self.result is None:
            for widget in (self.fresh, self.models, self.location, self.choose, self.start_button):
                widget.setEnabled(True)
            self.current.setEnabled(self.manager.active)
        if self._close_when_finished:
            super().reject()

    def _open_folder(self):
        if self.result is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.destination)))

    @Slot()
    def _shutdown(self):
        # Fresh deployment is also available without an active profile session.
        if self.worker is not None:
            self.worker.cancel()
            self.worker.drain()

    def reject(self):
        if self._busy():
            self._close_when_finished = True
            self.worker.cancel()
            self.status.setText(ui_text('Cancelling deployment…'))
            self.close_button.setEnabled(False)
        else:
            super().reject()

    def closeEvent(self, event):  # noqa: N802
        if self._busy():
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
