"""Attention events, local sound playback and UI preference persistence."""
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon


log = logging.getLogger(__name__)
SOUNDS = Path(__file__).with_name("assets") / "sounds"
EVENTS = {
    "response": ("O.R.S.I responded", "Your response is ready. Click to open O.R.S.I."),
    "approval": ("O.R.S.I needs approval", "Review the pending tool request in O.R.S.I."),
    "image": ("O.R.S.I finished your image", "Your generated image is ready. Click to open O.R.S.I."),
    "error": ("O.R.S.I needs attention", "The task could not finish. Open O.R.S.I for details."),
}


class NotificationManager(QObject):
    def __init__(self, window, store=None):
        super().__init__(window)
        self.window = window
        self.store = store
        self.enabled = True
        self.sound = "noti_1.ogg"
        self.backend = None
        self.player = None
        self.audio = None
        self.closed = False
        self._sound_preview = False
        window.installEventFilter(self)
        try:
            payload = store.load({}) if store is not None else {}
            values = payload.get("notifications", {}) if isinstance(payload, dict) else {}
            if isinstance(values, dict):
                self.enabled = values.get("enabled", True) is not False
                sound = values.get("sound", self.sound)
                if isinstance(sound, str):
                    self.sound = sound
        except Exception:
            log.warning("Notification preferences could not be loaded.")

    def configure(self, *, enabled=None, sound=None):
        if enabled is not None:
            self.enabled = bool(enabled)
            if not self.enabled and self.player is not None:
                self.player.stop()
        if sound is not None:
            self.sound = sound
            if self.player is not None:
                self.player.stop()
        if self.store is not None:
            try:
                payload = self.store.load({})
                if not isinstance(payload, dict):
                    raise ValueError("Invalid UI preferences")
                values = payload.get("notifications", {})
                values = dict(values) if isinstance(values, dict) else {}
                values.update(enabled=self.enabled, sound=self.sound)
                payload["notifications"] = values
                self.store.save(payload)
            except Exception:
                # Never overwrite unreadable preferences with a partial document.
                log.warning("Notification preferences could not be saved.")

    def sound_path(self):
        if not self.sound:
            return None
        path = SOUNDS / self.sound if self.sound in {"noti_1.ogg", "noti_2.ogg"} else Path(self.sound)
        return path if path.is_file() else SOUNDS / "noti_1.ogg"

    def play_sound(self, *, preview=True):
        if self.closed or QApplication.platformName() in {"offscreen", "minimal"}:
            return
        path = self.sound_path()
        if path is None:
            return
        try:
            if self.player is None:
                from app.ui.notification_audio import NotificationAudio
                self.player = NotificationAudio(self)
                self.player.errorOccurred.connect(lambda *_: log.warning("Notification sound playback failed."))
            self._sound_preview = preview
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
            self.player.play(allowed=lambda: not self.closed and (preview or self.enabled and self._needs_attention()))
        except Exception:
            log.warning("Notification sound playback is unavailable.")

    def _ensure_backend(self):
        if self.backend is not None or QApplication.platformName() in {"offscreen", "minimal"}:
            return
        if sys.platform == "win32":
            from app.ui.windows_notifications import WindowsNotifications
            self.backend = WindowsNotifications(self.window)
            self.backend.clicked.connect(self.open_window)
        elif QSystemTrayIcon.isSystemTrayAvailable():
            self.backend = QSystemTrayIcon(QIcon(str(SOUNDS.parent / "top_new_session.svg")), self)
            self.backend.setToolTip("O.R.S.I")
            self.backend.messageClicked.connect(self.open_window)
            self.backend.show()

    def notify(self, event):
        if self.closed or not self.enabled or getattr(self.window, "_closing", False):
            return
        if not self._needs_attention():
            return
        title, message = EVENTS[event]
        self.play_sound(preview=False)
        QApplication.alert(self.window)
        try:
            self._ensure_backend()
            if self.backend is not None:
                if sys.platform == "win32":
                    if not self.backend.show_message(title, message):
                        log.warning("Desktop notification could not be displayed.")
                else:
                    self.backend.showMessage(title, message)
        except Exception:
            log.warning("Desktop notifications are unavailable.")

    def _needs_attention(self):
        return self.window.isMinimized() or not self.window.isActiveWindow()

    def eventFilter(self, watched, event):  # noqa: N802
        if (watched is self.window and event.type() == QEvent.Type.WindowActivate
                and self.player is not None and not self._sound_preview):
            self.player.stop()
        return super().eventFilter(watched, event)

    def open_window(self):
        if self.closed or getattr(self.window, "_closing", False):
            return
        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        panel = getattr(self.window, "_approval_panel", None)
        (panel if panel is not None else self.window.input).setFocus()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        if self.player is not None:
            self.player.shutdown()
        if self.backend is not None:
            if sys.platform == "win32":
                self.backend.shutdown()
            else:
                self.backend.hide()
