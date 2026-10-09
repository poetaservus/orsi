"""Public bundled artwork covering the window while an unlocked profile loads."""
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEventLoop, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


_FADE_MS = 240
_PAINT_EVENTS = (QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                 | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers)


class ProfileLoadingWindow(QWidget):
    def __init__(self, previous):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("profileLoadingWindow")
        self.setWindowTitle("O.R.S.I")
        self.setAccessibleName("Opening personal profile")
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(previous.geometry())
        self._picture = QPixmap(str(Path(__file__).with_name("assets") / "orsi_start.png"))

    def present(self):
        self.setWindowOpacity(0.)
        self.show()
        self.raise_()
        # Deliver native exposure/paint before synchronous profile composition.
        QApplication.processEvents(_PAINT_EVENTS)
        self.repaint()
        self._fade_to(1.)

    def dismiss(self):
        try:
            if self.isVisible():
                self._fade_to(0.)
        finally:
            self.close()

    def _fade_to(self, opacity):
        # Profile composition blocks the UI thread. Finish fading in before it
        # starts, then fade out over the replacement view after it is ready.
        loop = QEventLoop()
        animation = QPropertyAnimation(self, b"windowOpacity")
        animation.setDuration(_FADE_MS)
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(opacity)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.finished.connect(loop.quit)
        application = QApplication.instance()
        application.aboutToQuit.connect(loop.quit)
        try:
            animation.start()
            # Keep painting/timers alive without admitting queued user input.
            loop.exec(_PAINT_EVENTS)
        finally:
            animation.stop()
            application.aboutToQuit.disconnect(loop.quit)
        self.setWindowOpacity(opacity)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080d15"))
        if not self._picture.isNull():
            scale = max(self.width() / self._picture.width(), self.height() / self._picture.height())
            width, height = self._picture.width() * scale, self._picture.height() * scale
            target = QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self._picture, QRectF(self._picture.rect()))
