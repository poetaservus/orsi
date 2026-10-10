"""Typed settings controls that leave mouse-wheel gestures to the page."""
from PySide6.QtWidgets import QComboBox, QSpinBox


class ScrollSafeComboBox(QComboBox):
    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


class CompactNumberInput(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        # Qt 6.12 clips styled NoButtons editors at x=0 when the hidden
        # step buttons retain right alignment. Keep them outside the text width.
        self.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { subcontrol-position: top left; }"
        )
        self.setFixedSize(72, 36)

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()
