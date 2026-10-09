"""Notification sound selector embedded in General settings."""
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QPushButton, QWidget
from app.ui.inputs import ScrollSafeComboBox


class NotificationSwitch(QCheckBox):
    """Keyboard-accessible switch with the settings panel's neutral styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._position = 0.0
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(140)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._slide.valueChanged.connect(self._move_thumb)
        self.toggled.connect(self._animate)

    def _move_thumb(self, value):
        self._position = float(value)
        self.update()

    def _animate(self, checked):
        self._slide.stop()
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self._move_thumb(target)
            return
        self._slide.setStartValue(self._position)
        self._slide.setEndValue(target)
        self._slide.start()

    def hitButton(self, position):  # noqa: N802
        return self.rect().contains(position)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#343b48"))
        painter.drawRoundedRect(QRectF(0, 3, 44, 18), 9, 9)
        painter.setBrush(QColor("#e4e5eb" if self.isEnabled() else "#a7adb7"))
        painter.drawRoundedRect(QRectF(3 + 24 * self._position, 5, 14, 14), 5, 5)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#9baec6"), 1))
            painter.drawRoundedRect(QRectF(0.5, 1, 43, 22), 10, 10)


class NotificationSoundControl(QWidget):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setObjectName("notificationSoundControl")
        self.manager = manager
        self.dialog = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.selector = ScrollSafeComboBox()
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
        self.selector.setFixedHeight(36)
        self.selector.currentIndexChanged.connect(self._selected)
        self.preview = QPushButton()
        self.preview.setObjectName("notificationPreview")
        self.preview.setIcon(QIcon(str(Path(__file__).with_name("assets") / "notification_play.svg")))
        self.preview.setIconSize(QSize(16, 16))
        self.preview.setAccessibleName("Preview notification sound")
        self.preview.setToolTip("Preview notification sound")
        self.preview.setFixedSize(36, 36)
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
