"""Small settings dialog for the independent cloud image tool."""
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout
from app.settings.images import ImageGenerationSettings


class ImageSettingsDialog(QDialog):
    def __init__(self, settings_store, apply_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image generation")
        self.setMinimumWidth(370)
        self.store, self.apply_settings = settings_store, apply_settings
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.choices = {}
        for name, label, values in (
            ("model", "Image model", ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini")),
            ("size", "Size", ("1024x1024", "1536x1024", "1024x1536")),
            ("quality", "Quality", ("auto", "low", "medium", "high")),
            ("output_format", "Format", ("png", "jpeg", "webp")),
        ):
            selector = QComboBox()
            selector.setAccessibleName(label)
            selector.addItems(values)
            selector.setCurrentText(getattr(settings_store.current, name))
            selector.setMinimumHeight(32)
            form.addRow(label, selector)
            self.choices[name] = selector
        layout.addLayout(form)
        self.notice = QLabel("Availability depends on your cloud account. Images are saved at their original resolution.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        try:
            settings = ImageGenerationSettings(**{name: widget.currentText() for name, widget in self.choices.items()})
            self.apply_settings(settings)
        except Exception:
            self.notice.setText("Could not save image settings. Finish the current request and try again.")
            return
        self.accept()
