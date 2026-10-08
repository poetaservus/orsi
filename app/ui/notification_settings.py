"""Notification sound selector embedded in General settings."""
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QPushButton, QWidget


class NotificationSoundControl(QWidget):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.dialog = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.selector = QComboBox()
        self.selector.setAccessibleName("Notification sound")
        self.selector.addItem("noti_1 (Default)", "noti_1.ogg")
        self.selector.addItem("noti_2", "noti_2.ogg")
        self.selector.addItem("Silent", "")
        if self.selector.findData(manager.sound) < 0:
            self.selector.addItem(Path(manager.sound).name, manager.sound)
        self.selector.addItem("Choose audio file…", None)
        self.selector.setCurrentIndex(self.selector.findData(manager.sound))
        self.selector.setMinimumWidth(0)
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMinimumContentsLength(1)
        self.selector.currentIndexChanged.connect(self._selected)
        self.preview = QPushButton("▶")
        self.preview.setAccessibleName("Preview notification sound")
        self.preview.setToolTip("Preview notification sound")
        self.preview.setFixedSize(32, 32)
        self.preview.setEnabled(bool(manager.sound))
        self.preview.clicked.connect(manager.play_sound)
        layout.addWidget(self.selector, 1)
        layout.addWidget(self.preview)

    def _select_saved(self):
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.selector.findData(self.manager.sound))
        self.selector.blockSignals(False)

    def _selected(self):
        sound = self.selector.currentData()
        if sound is not None:
            self.manager.configure(sound=sound)
            self.preview.setEnabled(bool(sound))
            return
        self._select_saved()
        if self.dialog is not None:
            self.dialog.raise_()
            return
        dialog = QFileDialog(self, "Choose notification sound")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Audio files (*.ogg *.wav *.mp3 *.flac *.m4a)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.fileSelected.connect(self._file_selected)
        dialog.finished.connect(self._dialog_finished)
        self.dialog = dialog
        dialog.open()

    def _file_selected(self, filename):
        path = Path(filename)
        if not path.is_file():
            return
        sound = str(path.resolve())
        self.manager.configure(sound=sound)
        self.selector.blockSignals(True)
        index = self.selector.findData(sound)
        if index < 0:
            index = self.selector.count() - 1
            self.selector.insertItem(index, path.name, sound)
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self.selector.setToolTip(sound)
        self.preview.setEnabled(True)

    def _dialog_finished(self):
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.deleteLater()

    def shutdown(self):
        if self.dialog is not None:
            self.dialog.reject()
