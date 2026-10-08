"""Reusable image preferences, independent of chat model profiles."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from app.settings.images import ImageGenerationSettings


class ImageSettingsPage(QWidget):
    saved = Signal()

    def __init__(self, settings_store=None, apply_settings=None, parent=None):
        super().__init__(parent)
        self.setObjectName("imageSettingsPage")
        self.store, self.apply_settings = settings_store, apply_settings
        self._available = settings_store is not None and callable(apply_settings)
        self._busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.choices = {}
        for name, label, values in (
            ("model", "Image model", ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini")),
            ("size", "Image size", ("1024x1024", "1536x1024", "1024x1536")),
            ("quality", "Quality", ("auto", "low", "medium", "high")),
            ("output_format", "File format", ("png", "jpeg", "webp")),
        ):
            selector = QComboBox()
            selector.setAccessibleName(label)
            selector.addItems(values)
            selector.setMinimumHeight(40)
            selector.setMinimumWidth(240)
            form.addRow(label, selector)
            self.choices[name] = selector
        layout.addLayout(form)
        self.notice = QLabel("Availability depends on your cloud account. Images are saved at their original resolution.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        actions = QHBoxLayout()
        self.save_button = QPushButton("Save image settings")
        self.reset_button = QPushButton("Reset changes")
        actions.addWidget(self.save_button)
        actions.addWidget(self.reset_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.save_button.clicked.connect(self._save)
        self.reset_button.clicked.connect(self.reload)
        self.reload()
        self.set_context(settings_store, apply_settings, available=self._available)

    def reload(self):
        settings = self.store.current if self.store is not None else ImageGenerationSettings()
        for name, selector in self.choices.items():
            selector.setCurrentText(getattr(settings, name))

    def set_context(self, store, apply_settings, *, available, busy=False):
        changed = store is not self.store
        self.store, self.apply_settings = store, apply_settings
        self._available = bool(available and store is not None and callable(apply_settings))
        self._busy = busy
        if changed:
            self.reload()
        for widget in (*self.choices.values(), self.save_button, self.reset_button):
            widget.setEnabled(self._available and not busy)

    def _save(self):
        if not self._available or self._busy:
            return
        try:
            settings = ImageGenerationSettings(**{name: widget.currentText() for name, widget in self.choices.items()})
            self.apply_settings(settings)
        except Exception:
            self.notice.setText("Could not save image settings. Finish the current request and try again.")
            return
        self.notice.setText("Image generation settings saved.")
        self.saved.emit()


class ImageSettingsDialog(QDialog):
    """Compatibility shell; the main settings panel embeds ImageSettingsPage."""

    def __init__(self, settings_store, apply_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image generation")
        self.setMinimumWidth(370)
        self.store, self.apply_settings = settings_store, apply_settings
        layout = QVBoxLayout(self)
        self.page = ImageSettingsPage(settings_store, apply_settings, self)
        self.choices, self.notice = self.page.choices, self.page.notice
        self.page.save_button.hide()
        self.page.reset_button.hide()
        self.page.saved.connect(self.accept)
        layout.addWidget(self.page)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self.page._save()
