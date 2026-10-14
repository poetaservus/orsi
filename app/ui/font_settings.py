"""English-only Appearance control for the independent font override."""
from PySide6.QtCore import Qt

from app.settings.font import FONT_CHOICES
from app.ui.inputs import ScrollSafeComboBox
from app.ui.profile_layout import FeedbackLabel


class FontControls:
    def __init__(self, panel, window, layout):
        self.controller = window.theme_controller
        self.selector = ScrollSafeComboBox(panel)
        self.selector.setAccessibleName("Font")
        self.selector.setAccessibleDescription(
            "Override the theme's font. Choose Theme default to use the theme's original font.")
        self.selector.use_description_as_tooltip()
        for identity, name in FONT_CHOICES:
            self.selector.addItem(name, identity)
        window.font_selector = self.selector
        panel._row(layout, "Font", "Choose the interface font", self.selector)
        self.status = FeedbackLabel()
        self.status.setObjectName("settingsDescription")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Font status")
        layout.addWidget(self.status)
        self.refresh()
        self.selector.currentIndexChanged.connect(self.select)
        self.controller.changed.connect(self.refresh)

    def refresh(self):
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.selector.findData(self.controller.font_identity))
        self.selector.blockSignals(False)
        self.selector.setEnabled(not self.controller.font_settings.load_error
                                 and not self.controller.font_settings.closed)
        self.status.setText(self.controller.font_notice)
        self.status.setVisible(bool(self.controller.font_notice))

    def select(self, index):
        identity = self.selector.itemData(index)
        if identity is None:
            return
        try:
            self.controller.select_font(identity)
        except Exception as error:
            self.controller.font_notice = (str(error) if isinstance(error, ValueError) else
                "Could not save the font selection. Your settings were preserved.")
        self.refresh()
