"""Public bundled artwork covering the window while an unlocked profile loads."""
from pathlib import Path
from math import cos, pi
import os
import subprocess
import sys
from threading import Event, Thread

from PySide6.QtCore import QEasingCurve, QEventLoop, QObject, QPropertyAnimation, QRect, QRectF, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


_FADE_IN_MS = 240
_FADE_OUT_MS = 560
_PAINT_EVENTS = (QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                 | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers)


class ProfileLoadingWindow(QWidget):
    def __init__(self, previous=None, *, geometry=None):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("profileLoadingWindow")
        self.setWindowTitle("O.R.S.I")
        self.setAccessibleName("Opening personal profile")
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(previous.geometry() if previous is not None else geometry)
        assets = Path(__file__).with_name("assets")
        self._picture = QPixmap(str(assets / "orsi_start.png"))
        self._logo = QPixmap(str(assets / "bsw_o.png"))
        self._breath = 0.0
        self.pulse = QVariantAnimation(self)
        self.pulse.setStartValue(0.0)
        self.pulse.setEndValue(1.0)
        self.pulse.setDuration(3200)
        self.pulse.setLoopCount(-1)
        self.pulse.valueChanged.connect(self._pulse_frame)

    def _pulse_frame(self, progress):
        self._breath = (1.0 - cos(2.0 * pi * progress)) / 2.0
        self.update()

    def present(self):
        self.setWindowOpacity(0.)
        self.show()
        self.raise_()
        self.pulse.start()
        # Deliver native exposure/paint before synchronous profile composition.
        QApplication.processEvents(_PAINT_EVENTS)
        self.repaint()
        self._fade_to(1.)

    def dismiss(self, reveal=None):
        try:
            if self.isVisible():
                if reveal is not None and reveal.isVisible():
                    # Native show/exposure is asynchronous. Paint the replacement
                    # before reducing the cover's opacity, revealing chat directly.
                    reveal.raise_()
                    reveal.activateWindow()
                    QApplication.processEvents(_PAINT_EVENTS)
                    reveal.repaint()
                    QApplication.processEvents(_PAINT_EVENTS)
                self._fade_to(0.)
        finally:
            self.pulse.stop()
            self.close()

    def _fade_to(self, opacity):
        # Profile composition blocks the UI thread. Finish fading in before it
        # starts, then fade out over the replacement view after it is ready.
        loop = QEventLoop()
        animation = QPropertyAnimation(self, b"windowOpacity")
        animation.setDuration(_FADE_IN_MS if opacity else _FADE_OUT_MS)
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
        if not self._logo.isNull():
            side = min(64.0, self.width() * .24, self.height() * .36)
            scale = side / max(self._logo.width(), self._logo.height()) * (.94 + .06 * self._breath)
            width, height = self._logo.width() * scale, self._logo.height() * scale
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.setOpacity(.70 + .30 * self._breath)
            painter.drawPixmap(QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height),
                               self._logo, QRectF(self._logo.rect()))


class ProfileLoadingCover(QObject):
    """Keep the public artwork animating while profile composition blocks Qt."""
    def __init__(self, previous):
        super().__init__(QApplication.instance())
        self.geometry = previous.geometry()
        self.process = None
        self.fallback = None
        QApplication.instance().aboutToQuit.connect(self.abort)

    def present(self):
        arguments = [str(value) for value in (self.geometry.x(), self.geometry.y(),
                                              self.geometry.width(), self.geometry.height())]
        compiled = getattr(sys, "frozen", False) or "__compiled__" in globals()
        command = [sys.executable, *([] if compiled else ["-m", "app.main"]), "--profile-loading", *arguments]
        ready = Event()
        acknowledged = []
        try:
            self.process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            process = self.process
            def read_ready():
                try:
                    acknowledged.append(process.stdout.readline().strip() == "ready")
                except (OSError, ValueError):
                    acknowledged.append(False)
                finally:
                    ready.set()
            Thread(target=read_ready, daemon=True).start()
            if not ready.wait(8) or not acknowledged or not acknowledged[0] or self.process.poll() is not None:
                raise RuntimeError("Loading cover unavailable")
        except (OSError, RuntimeError):
            self.abort()
            # A failed presentation helper must never prevent profile access.
            self.fallback = ProfileLoadingWindow(geometry=self.geometry)
            self.fallback.present()

    def dismiss(self, reveal=None):
        try:
            if self.fallback is not None:
                self.fallback.dismiss(reveal)
                self.fallback.deleteLater()
                self.fallback = None
            elif self.process is not None:
                if reveal is not None and reveal.isVisible():
                    reveal.raise_()
                    reveal.activateWindow()
                    QApplication.processEvents(_PAINT_EVENTS)
                    reveal.repaint()
                    QApplication.processEvents(_PAINT_EVENTS)
                try:
                    self.process.stdin.write("fade\n")
                    self.process.stdin.flush()
                    self.process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            self.abort()

    def abort(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            process.stdin.close()
            process.stdout.close()
        if self.fallback is not None:
            self.fallback.pulse.stop()
            self.fallback.close()


def run_loading_helper(arguments):
    """Private presentation entrypoint: only public assets and window geometry."""
    if len(arguments) != 4:
        return 2
    try:
        geometry = QRect(*(int(value) for value in arguments))
    except ValueError:
        return 2
    if not 1 <= geometry.width() <= 32768 or not 1 <= geometry.height() <= 32768:
        return 2
    application = QApplication([sys.argv[0]])
    loading = ProfileLoadingWindow(geometry=geometry)
    class Commands(QObject):
        received = Signal(str)
    commands = Commands()
    finished = False
    def receive(command):
        nonlocal finished
        if finished:
            return
        finished = True
        if command == "fade":
            loading.dismiss()
        else:
            loading.pulse.stop()
            loading.close()
        application.quit()
    commands.received.connect(receive)
    def listen():
        line = sys.stdin.readline()
        commands.received.emit(line.strip() if line else "abort")
    Thread(target=listen, daemon=True).start()
    loading.present()
    if finished:
        return 0
    print("ready", flush=True)
    return application.exec()
