"""Public bundled artwork covering the window while an unlocked profile loads."""
from pathlib import Path

from PySide6.QtCore import QEventLoop, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


class ProfileLoadingWindow(QWidget):
    def __init__(self, previous):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setObjectName("profileLoadingWindow")
        self.setWindowTitle("O.R.S.I")
        self.setAccessibleName("Opening personal profile")
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(previous.geometry())
        self._picture = QPixmap(str(Path(__file__).with_name("assets") / "orsi_start.png"))

    def present(self):
        self.show()
        self.raise_()
        # Deliver native exposure/paint before synchronous profile composition.
        # Do not admit another password click or an activation socket callback.
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                                   | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers)
        self.repaint()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080d15"))
        if not self._picture.isNull():
            scale = max(self.width() / self._picture.width(), self.height() / self._picture.height())
            width, height = self._picture.width() * scale, self._picture.height() * scale
            target = QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self._picture, QRectF(self._picture.rect()))
