"""Shared chat composer paint, controls and typography."""
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, QSize, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QStyle, QStyleOptionButton, QTextEdit, QWidget
from app.ui.inputs import ScrollSafeComboBox

ASSETS = Path(__file__).with_name("assets")
COMPOSER_WIDTH = 799
COMPOSER_HEIGHT = 54
MESSAGE_COMPOSER_HEIGHT = 110

REASONING_LABELS = {"none": "None", "low": "Low", "medium": "Medium", "high": "High", "xhigh": "Extra High", "max": "Max"}


def composer_selector(parent, name, width):
    selector = ComposerModelSelector(parent)
    selector.setObjectName("composerSelector")
    selector.setAccessibleName(name)
    selector.setFixedSize(width, 32)
    return selector


class ComposerModelSelector(ScrollSafeComboBox):
    """Keep the composer's model list above its trigger and within the screen."""

    def showPopup(self):  # noqa: N802
        super().showPopup()
        popup = self.view().window()
        popup.setObjectName("composerModelPopup")
        popup.setStyleSheet("QFrame#composerModelPopup { background: #292d36; border: 1px solid #4b505d; }")
        bounds = self.screen().availableGeometry()
        anchor = self.mapToGlobal(QPoint(0, 0))
        height = min(popup.height(), anchor.y() - bounds.top() - 6)
        if height <= 0:
            self.hidePopup()
            return
        width = min(bounds.width(), max(popup.width(), self.view().minimumWidth()))
        popup.resize(width, height)
        x = max(bounds.left(), min(anchor.x() + self.width() - width, bounds.right() - width + 1))
        popup.move(x, anchor.y() - height - 6)


def composer_microphone(parent):
    button = QPushButton(parent)
    button.setObjectName("composerMicrophone")
    button.setFixedSize(32, 32)
    button.setIcon(QIcon(str(ASSETS / "microphone.svg")))
    button.setIconSize(QSize(20, 20))
    button.setAccessibleName("Microphone (coming soon)")
    button.setToolTip("Microphone (coming soon)")
    button.setEnabled(False)
    return button


class MessageInput(QTextEdit):
    submit_requested = Signal()
    attachments_requested = Signal(object)

    def canInsertFromMimeData(self, source):  # noqa: N802
        return source.hasImage() or (source.hasUrls() and all(u.isLocalFile() for u in source.urls())) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):  # noqa: N802
        if source.hasImage() or (source.hasUrls() and all(u.isLocalFile() for u in source.urls())):
            self.attachments_requested.emit(source)
        else:
            super().insertFromMimeData(source)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ComposerFrame(QFrame):
    """Paint the same pill in chat and image inspection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1., 1., -1., -1.)
        radius = min(27., rect.height() / 2)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0., QColor("#2c3036"))
        fill.setColorAt(.45, QColor("#2a2e34"))
        fill.setColorAt(1., QColor("#282c32"))
        painter.setPen(QColor("#373c43"))
        painter.setBrush(fill)
        painter.drawPath(path)
        painter.setPen(QColor(255, 255, 255, 8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2., 2., -2., -2.), max(1., radius - 2), max(1., radius - 2))


class ComposerToolButton(QPushButton):
    """Animate the painted button, keeping its hit target and layout stable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 1.
        self._pulse = QVariantAnimation(self)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._pulse.valueChanged.connect(self._set_scale)
        self._pulse.finished.connect(lambda: self._set_scale(1. if not self.isDown() else .88))
        self.pressed.connect(self._press)
        self.released.connect(self._release)

    def _set_scale(self, value):
        self._scale = float(value)
        self.update()

    def _press(self):
        self._pulse.stop()
        self._pulse.setDuration(90)
        self._pulse.setStartValue(self._scale)
        self._pulse.setKeyValueAt(.3, self._scale)
        self._pulse.setEndValue(.88)
        self._pulse.start()

    def _release(self):
        self._pulse.stop()
        self._pulse.setDuration(190)
        self._pulse.setStartValue(self._scale)
        self._pulse.setKeyValueAt(.3, .88)
        self._pulse.setEndValue(1.)
        self._pulse.start()

    def paintEvent(self, event):  # noqa: N802
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.scale(self._scale, self._scale)
        painter.translate(-self.width() / 2, -self.height() / 2)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)


def composer_tools(parent):
    tools = QWidget(parent)
    tools.setObjectName("composerTools")
    layout = QHBoxLayout(tools)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    buttons = []
    for name, asset, description in (
        ("composerAddPlaceholder", "plus.svg", "Attach images or files"),
        ("composerFolderPlaceholder", "folder.svg", "Folder (placeholder)"),
    ):
        button = ComposerToolButton(tools) if asset == "plus.svg" else QPushButton(tools)
        button.setObjectName(name)
        button.setFixedSize(32, 32)
        button.setIcon(QIcon(str(ASSETS / asset)))
        button.setIconSize(QSize(28, 28))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(description)
        button.setAccessibleName(description)
        button.setAutoDefault(False)
        layout.addWidget(button)
        buttons.append(button)
    return tools, *buttons


def configure_input(input):
    input.setObjectName("messageInput")
    input.setPlaceholderText("Ask O.R.S.I.")
    input.setAcceptRichText(False)
    input.setFixedHeight(41)
    input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    palette = input.palette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#a2a8ba"))
    input.setPalette(palette)


def configure_send(button):
    button.setObjectName("sendButton")
    button.setFixedSize(34, 34)
    button.setIcon(QIcon(str(ASSETS / "input_button_cropped.png")))
    button.setIconSize(QSize(27, 27))
    button.setToolTip("Send")
    button.setAccessibleName("Send")
    button.setAutoDefault(False)


COMPOSER_STYLE = """
QFrame#composer { background: transparent; border: none; border-radius: 27px; }
QWidget#composerTools { background: transparent; border: none; }
QPushButton#composerMicrophone { background: transparent; border: none; padding: 0; }
QPushButton#reasoningSelector {
    background: transparent; color: #dedee0; border: none; border-radius: 14px;
    padding: 3px 22px 3px 8px; font-family: Saira; font-size: 13px;
}
QPushButton#reasoningSelector:hover, QPushButton#reasoningSelector:focus { background: rgba(255, 255, 255, 14); }
QPushButton#reasoningSelector:disabled { color: #777d8b; }
QComboBox#composerSelector {
    background: transparent; color: #dedee0; border: none; border-radius: 8px;
    padding: 3px 8px; font-family: Saira; font-size: 13px;
}
QComboBox#composerSelector:hover { background: rgba(255, 255, 255, 14); }
QComboBox#composerSelector:disabled { color: #777d8b; }
QComboBox#composerSelector::drop-down { border: none; width: 18px; }
QComboBox#composerSelector QAbstractItemView {
    background: #292d36; color: #dedee0; border: 1px solid #4b505d;
    selection-background-color: #414753; outline: none; padding: 4px;
}
QPushButton#composerAddPlaceholder, QPushButton#composerFolderPlaceholder {
    background: transparent; border: none; border-radius: 16px; padding: 0;
}
QPushButton#composerAddPlaceholder:hover, QPushButton#composerFolderPlaceholder:hover { background: rgba(255, 255, 255, 14); }
QPushButton#composerAddPlaceholder:pressed, QPushButton#composerFolderPlaceholder:pressed { background: rgba(255, 255, 255, 8); }
QTextEdit#messageInput {
    color: #dedee0; background: transparent; border: none; padding: 4px 0 3px 4px;
    font-family: Saira; font-size: 17px; font-weight: 400; selection-background-color: #666666;
}
QTextEdit#messageInput:focus { border: none; }
QTextEdit#messageInput:disabled { color: #777777; background: transparent; }
QPushButton#sendButton, QPushButton#stopButton {
    background: transparent; border: none; border-radius: 17px; padding: 0;
}
QPushButton#sendButton:hover, QPushButton#stopButton:hover { background: #454852; }
QPushButton#sendButton:pressed, QPushButton#stopButton:pressed { background: #2c2e35; }
QPushButton#sendButton:disabled, QPushButton#stopButton:disabled { background: transparent; }
"""
COMPOSER_STYLE += f'''QComboBox#composerSelector::down-arrow {{
    image: url("{(ASSETS / 'chevron-down.svg').as_posix()}"); width: 10px; height: 6px;
}}'''
