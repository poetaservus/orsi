"""A model-aware effort slider in a compact popup above the composer."""
from app.ui.localization import ui_text, QFrame, QLabel, QPushButton, QSlider

from app.ui.theme_runtime import apply_theme_style, theme_color
from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import QVBoxLayout

from app.ui.composer import ASSETS, COMPOSER_CONTROL_SIZE, REASONING_LABELS


class EffortSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(30)
        self.setTracking(False)
        self.setAccessibleName(ui_text('Reasoning effort'))

    def _index_at(self, x):
        fraction = max(0., min(1., (x - 15) / max(1, self.width() - 30)))
        return round(self.minimum() + fraction * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.setSliderDown(True)
        self.setSliderPosition(self._index_at(event.position().x()))
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if not self.isSliderDown():
            return super().mouseMoveEvent(event)
        self.setSliderPosition(self._index_at(event.position().x()))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.isSliderDown():
            return super().mouseReleaseEvent(event)
        self.setSliderPosition(self._index_at(event.position().x()))
        self.setValue(self.sliderPosition())
        self.setSliderDown(False)
        self.update()
        event.accept()

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QRectF(3, 4, self.width() - 6, 22)
        path = QPainterPath()
        path.addRoundedRect(track, 11, 11)
        painter.fillPath(path, theme_color(self, "#3b4046", "border"))
        steps = max(1, self.maximum() - self.minimum())
        position = 15 + (self.width() - 30) * (self.sliderPosition() - self.minimum()) / steps
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(QRectF(3, 4, position - 3, 22), theme_color(self, "#2475ef", "accent"))
        painter.restore()
        for index in range(self.minimum(), self.maximum() + 1):
            x = 15 + (self.width() - 30) * (index - self.minimum()) / steps
            painter.setBrush(theme_color(self, "#80adf8" if index <= self.sliderPosition() else "#777c83", "accent" if index <= self.sliderPosition() else "text_disabled"))
            painter.drawEllipse(QPoint(round(x), 15), 2, 2)
        painter.setBrush(theme_color(self, "#ffffff", "text"))
        painter.drawEllipse(QPoint(round(position), 15), 14, 14)
        if self.hasFocus():
            painter.setPen(theme_color(self, "#91baff", "focus"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(round(position), 15), 14, 14)


class EffortPopup(QFrame):
    dismissed = Signal()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(theme_color(self, "#35393f", "border"))
        painter.setBrush(theme_color(self, "#202328", "surface"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 16, 16)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):  # noqa: N802
        self.dismissed.emit()
        super().hideEvent(event)


class ReasoningSelector(QPushButton):
    effort_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("reasoningSelector")
        self.setAccessibleName(ui_text('Reasoning level'))
        self.setFixedHeight(COMPOSER_CONTROL_SIZE)
        self._efforts = ()
        self.current_effort = None
        self._chevron = QIcon(str(ASSETS / "chevron-up.svg"))
        self.popup = EffortPopup(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.popup.setObjectName("reasoningPopup")
        self.popup.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.popup.setFixedSize(256, 108)
        apply_theme_style(self.popup, POPUP_STYLE)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(2)
        self.level_label = QLabel(self.popup)
        self.level_label.setObjectName("reasoningLevel")
        self.model_label = QLabel(self.popup)
        self.model_label.setObjectName("reasoningModel")
        for label in (self.level_label, self.model_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
        layout.addSpacing(6)
        self.slider = EffortSlider(self.popup)
        layout.addWidget(self.slider)
        self.slider.sliderMoved.connect(self._preview)
        self.slider.valueChanged.connect(self._select)
        self.popup.dismissed.connect(self._restore)
        self.clicked.connect(self.showPopup)
        self.set_context((), None, "")

    def set_context(self, efforts, current, model):
        self._efforts = tuple(efforts)
        self.current_effort = current if current in self._efforts else None
        self.model_label.setText(model)
        self.model_label.setToolTip(model)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self._efforts) - 1))
        self.slider.setValue(self._efforts.index(current) if self.current_effort else 0)
        self.slider.blockSignals(False)
        self._preview(self.slider.value())
        label = ui_text(REASONING_LABELS.get(self.current_effort, "Reasoning"))
        self.setText(label)
        self.setFixedWidth(max(100, self.fontMetrics().horizontalAdvance(label) + 34))
        self.setAccessibleDescription(label)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        painter.drawPixmap(self.width() - 16, (self.height() - 6) // 2, self._chevron.pixmap(10, 6, mode))

    def _preview(self, index):
        effort = self._efforts[index] if 0 <= index < len(self._efforts) else None
        label = ui_text(REASONING_LABELS.get(effort, "Reasoning"))
        self.level_label.setText(label)
        self.slider.setAccessibleDescription(label)
        self.slider.update()

    def _select(self, index):
        if self.isEnabled() and 0 <= index < len(self._efforts):
            self.effort_selected.emit(self._efforts[index])

    def _restore(self):
        self.slider.blockSignals(True)
        self.slider.setSliderDown(False)
        self.slider.setValue(self._efforts.index(self.current_effort) if self.current_effort else 0)
        self.slider.setSliderPosition(self.slider.value())
        self.slider.blockSignals(False)
        self._preview(self.slider.value())

    def showPopup(self):  # noqa: N802
        if not self.isEnabled() or not self._efforts:
            return
        self._restore()
        anchor = self.mapToGlobal(QPoint(self.width(), 0))
        bounds = self.screen().availableGeometry()
        x = max(bounds.left(), min(anchor.x() - self.popup.width(), bounds.right() - self.popup.width() + 1))
        self.popup.move(x, max(bounds.top(), anchor.y() - self.popup.height() - 8))
        self.window().installEventFilter(self)
        self.popup.show()
        self.slider.setFocus(Qt.FocusReason.PopupFocusReason)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.window() and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Hide):
            self.popup.hide()
        return super().eventFilter(watched, event)

    def changeEvent(self, event):  # noqa: N802
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled() and hasattr(self, "popup"):
            self.popup.hide()
        super().changeEvent(event)

    def hideEvent(self, event):  # noqa: N802
        self.popup.hide()
        super().hideEvent(event)


POPUP_STYLE = """
QLabel { background: transparent; border: none; font-family: Saira; }
QLabel#reasoningLevel { color: #3688ff; font-size: 14px; font-weight: 600; }
QLabel#reasoningModel { color: #a3a8b0; font-size: 12px; }
QSlider { background: transparent; border: none; }
"""
