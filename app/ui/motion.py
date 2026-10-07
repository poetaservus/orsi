"""Small presentation animations that leave layout and input ownership intact."""
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QApplication, QAbstractItemView, QFileDialog, QPlainTextEdit


class OpeningFade(QObject):
    """Fade a Qt-owned window without changing its final geometry or focus."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.animation = QPropertyAnimation(window, b"windowOpacity", self)
        self.animation.setDuration(180)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        window.setWindowOpacity(0.)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.Show:
            self.animation.stop()
            self.window.setWindowOpacity(0.)
            self.animation.start()
        elif event.type() == QEvent.Type.Hide:
            self.animation.stop()
            self.window.setWindowOpacity(1.)
        return False


class AttachmentFileDialog(QFileDialog):
    def __init__(self, parent, *, cloud, name_filter):
        super().__init__(parent)
        # Native OS dialogs do not expose Qt's window animation properties.
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setWindowTitle("Attach images or files" if cloud else "Attach an image or file")
        self.setNameFilter(name_filter)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setFileMode(QFileDialog.FileMode.ExistingFiles if cloud else QFileDialog.FileMode.ExistingFile)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("""
            QFileDialog { background: #242832; color: #dedee0; }
            QLabel { color: #dedee0; }
            QTreeView, QListView, QLineEdit, QComboBox {
                background: #191d25; color: #dedee0; border: 1px solid #444b59;
                selection-background-color: #48566d; selection-color: white;
            }
            QHeaderView { background: #303642; }
            QHeaderView::section { background: #303642; color: #dedee0; border: none; padding: 5px; }
            QPushButton { background: #363d4b; color: #dedee0; border: 1px solid #505867;
                          border-radius: 6px; padding: 5px 14px; }
            QPushButton:hover { background: #454e60; }
            QPushButton:disabled { color: #818795; }
            QToolButton { background: transparent; color: #dedee0; border: none; padding: 4px; }
            QScrollBar:vertical { background: #242832; width: 12px; }
            QScrollBar:horizontal { background: #242832; height: 12px; }
            QScrollBar::handle { background: #626c7e; border-radius: 4px; min-width: 24px; min-height: 24px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        """)
        self.opening = OpeningFade(self)
        for view in self.findChildren(QAbstractItemView):
            install_smooth_scroll(view)


class SmoothScroll(QObject):
    """Ease wheel detents; keep pixel/trackpad motion and manual dragging direct."""

    started = Signal()
    finished = Signal()

    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self._animations = {}
        self._targets = {}
        if isinstance(area, QAbstractItemView):
            area.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            area.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        for bar in (area.verticalScrollBar(), area.horizontalScrollBar()):
            animation = QPropertyAnimation(bar, b"value", self)
            animation.setDuration(150)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(self.finished)
            self._animations[bar] = animation
            bar.sliderPressed.connect(self.stop)
            bar.actionTriggered.connect(self.stop)
            bar.rangeChanged.connect(lambda low, high, current=bar: self._range_changed(current, low, high))
        area.viewport().installEventFilter(self)

    def stop(self, *_):
        for animation in self._animations.values():
            animation.stop()
        self._targets.clear()

    def _range_changed(self, bar, low, high):
        if bar in self._targets:
            target = max(low, min(high, self._targets[bar]))
            self._targets[bar] = target
            self._animations[bar].setEndValue(round(target))

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.Hide:
            self.stop()
        elif event.type() == QEvent.Type.Wheel:
            return self.wheel(event)
        return False

    def wheel(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.stop()
            return False  # Preserve editor zoom and other native shortcuts.
        pixel, angle = event.pixelDelta(), event.angleDelta()
        if not pixel.isNull() and isinstance(self.area, QPlainTextEdit):
            self.stop()
            return False  # Its vertical range uses lines; Qt owns pixel accumulation.
        horizontal = (bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                      or abs(angle.x()) > abs(angle.y()) or abs(pixel.x()) > abs(pixel.y()))
        bar = self.area.horizontalScrollBar() if horizontal else self.area.verticalScrollBar()
        if not horizontal and bar.maximum() <= bar.minimum() and self.area.horizontalScrollBar().maximum() > 0:
            bar = self.area.horizontalScrollBar()
        if bar.maximum() <= bar.minimum():
            return False  # Let nested views propagate scrolling to the chat.
        delta = (pixel.x() if horizontal and pixel.x() else pixel.y()) if not pixel.isNull() else (
            angle.x() if horizontal and angle.x() else angle.y())
        if not delta:
            return False
        animation = self._animations[bar]
        running = animation.state() == QPropertyAnimation.State.Running
        saved = self._targets.get(bar, bar.value())
        current = saved if pixel.isNull() and (running or round(saved) == bar.value()) else bar.value()
        distance = delta if not pixel.isNull() else delta / 120 * bar.singleStep() * QApplication.wheelScrollLines()
        target = max(bar.minimum(), min(bar.maximum(), current - distance))
        if target == bar.value() and not running:
            return False
        self.started.emit()
        animation.stop()
        self._targets[bar] = target
        if not pixel.isNull():
            bar.setValue(round(target))
            self.finished.emit()
        else:
            animation.setStartValue(bar.value())
            animation.setEndValue(round(target))
            animation.start()
        event.accept()
        return True


def install_smooth_scroll(area):
    existing = getattr(area, "smooth_scroll", None)
    if existing is None:
        existing = area.smooth_scroll = SmoothScroll(area)
    return existing
