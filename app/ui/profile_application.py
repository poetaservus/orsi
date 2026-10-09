"""Own windows and profile lifetimes; selected locked profiles never compose personal consumers."""
import logging
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QTimer

from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.ui.personal_profile import PersonalProfilePage, restore_dialog
from app.vault.profiles import ProfileManager, public_error


class ProfileApplication(QObject):
    def __init__(self, application, application_root, builder, *, manager=None, initial_session=None,
                 legacy_logging=None, window_factory=None):
        super().__init__(application)
        self.application, self.builder = application, builder
        self.manager = manager or ProfileManager(application_root)
        self.legacy_logging = legacy_logging
        self.window_factory = window_factory or MainWindow
        self._composition = (None, None)
        self.window = None
        self._retired = []
        self._transitioning = False
        self._legacy_pending = None
        self.last_activity = monotonic()
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(5000)
        self.idle_timer.timeout.connect(self.check_idle)
        application.installEventFilter(self)
        application.aboutToQuit.connect(self.shutdown)
        if initial_session is not None:
            from app.vault.profiles import ProfileLocator
            backend = initial_session._vault
            self.manager.session = initial_session
            self.manager.locator = ProfileLocator(backend.root, "local", initial_session.encrypted,
                                                  backend._header["profile_id"])
            self.manager.known_roots.add(backend.root)

    def start(self):
        if self.manager.locator is not None and not self.manager.encrypted and not self.manager.active:
            try:
                self.manager.unlock()
            except Exception as error:
                self.render(public_error(error))
                return
        self.render()

    def _flush_preferences(self):
        window = self.window
        if window is not None and window._greeting_save_timer.isActive():
            window._greeting_save_timer.stop()
            window._save_greeting_message()

    def _release_legacy(self):
        window = self._legacy_pending or self.window
        if window is None or not getattr(window, "_owns_legacy", False):
            return
        # Before any new selection, stop legacy work too; it cannot complete into
        # a newly selected profile. Keep undrained Qt workers alive for a retry.
        self._legacy_pending = window
        window._stop_profile_view()
        shutdown = getattr(window.service, "shutdown", None)
        if callable(shutdown):
            shutdown()
        window._drain_profile_view()
        close = getattr(window.inference, "close", None)
        if callable(close):
            close()
        credentials = getattr(window.inference, "credential_provider", None)
        if credentials is not None and getattr(credentials.session, "ephemeral", False):
            credentials.session.lock()
        window._clear_profile_view()
        window._owns_legacy = False
        self._legacy_pending = None

    def transition(self, action, *, renew=False):
        if self._transitioning:
            return
        self._transitioning = True
        self.idle_timer.stop()
        message = ""
        try:
            self._flush_preferences()
            self._release_legacy()
            if renew:
                self.manager.renew()
            action()
            if renew:
                message = "Import completed and verified. Originals remain outside the vault; review them before choosing cleanup."
        except Exception as error:
            message = public_error(error)
        finally:
            self._transitioning = False
        self.render(message, show_profile=True)

    def render(self, message="", *, show_profile=False):
        old = self.window
        if old is not None:
            old.hide()
            self._retired.append(old)
        selected = self.manager.locator is not None or self.manager.bootstrap_error or self._legacy_pending is not None
        if self.manager.active:
            session = self.manager.session
            try:
                service, host, error, inference = self.builder(profile_session=session)
                preferences = JsonStore(session.storage_path("state/ui_preferences_v1.json"))
            except Exception as build_error:
                message = public_error(build_error)
                self.manager.lock()
                service, host, error, inference, preferences = None, {"hostname": ""}, None, None, None
        elif selected:
            service, host, error, inference, preferences = None, {"hostname": ""}, None, None, None
            # Locked errors are transient fixed messages, with no legacy file logger.
            root = logging.getLogger()
            for handler in tuple(root.handlers):
                root.removeHandler(handler)
                handler.close()
            root.addHandler(logging.NullHandler())
        else:
            if self.legacy_logging is not None:
                self.legacy_logging()
            service, host, error, inference = self.builder(session_credentials=True)
            preferences = JsonStore(self.manager.application_root / "state/ui_preferences_v1.json")
        self._composition = (service, inference)
        self.window = self.window_factory(service, host["hostname"], error, inference, preferences)
        self.window._owns_legacy = not selected
        if self.manager.active:
            self.window.bind_profile(self.manager.session)
        self.window._profile_manager = self.manager
        page = PersonalProfilePage(self.manager, self.window, message=message)
        self.window.personal_profile_page = page
        page.transition_requested.connect(self.transition)
        page.reload_requested.connect(lambda action: self.transition(action, renew=True))
        self.window.settings_panel.add_personal_page(page)
        self.window.skill_settings_page.set_vault_guidance(self.manager.active and self.manager.encrypted,
            self.manager.guidance() if self.manager.active else False)
        if hasattr(page, "guidance"):
            page.guidance.toggled.connect(lambda enabled: self.window.skill_settings_page.set_vault_guidance(True, enabled))
        if selected and not self.manager.active:
            self.window.composer.setEnabled(False)
            for index, button in enumerate(self.window.settings_panel.navigation[:-1]):
                button.setEnabled(False)
                self.window.settings_panel.pages.widget(index).setEnabled(False)
        # Restore must remain available when password/recovery unlock fails.
        if not self.manager.active:
            page._buttons((("Restore encrypted backup…", lambda: restore_dialog(page, self.manager, page.transition_requested.emit)),))
        self.window.show()
        if selected and not self.manager.active or show_profile:
            self.window.settings_panel.show_section("Personal profile")
            self.window.settings_panel.show()
            self.window.settings_panel.raise_()
            if hasattr(page, "password"):
                page.password.setFocus()
        self.last_activity = monotonic()
        self.idle_timer.start()
        self._collect_retired()

    def _collect_retired(self):
        keep = []
        for window in self._retired:
            threads = (window.thread, window.attachment_tray.thread, window.skill_settings_page.thread)
            session = getattr(window, "_profile_session", None)
            pending = session is not None and session is self.manager.session and bool(session._resources)
            if pending or window is self._legacy_pending or any(thread is not None and thread.isRunning() for thread in threads):
                keep.append(window)
            else:
                window.deleteLater()
        self._retired = keep

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() in {QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                            QEvent.Type.Wheel, QEvent.Type.TouchBegin}:
            self.last_activity = monotonic()
        return False

    def check_idle(self, *, now=None):
        self._collect_retired()
        if not self.manager.active or self._transitioning:
            return
        try:
            minutes = self.manager.settings().load({}).get("idle_lock_minutes", 0)
            if type(minutes) is int and minutes > 0 and (monotonic() if now is None else now) - self.last_activity >= minutes * 60:
                self.transition(self.manager.lock)
        except Exception:
            self.transition(self.manager.lock)

    def shutdown(self):
        self.idle_timer.stop()
        self._flush_preferences()
        try:
            if self.manager.session is not None:
                self.manager.lock()
            else:
                shutdown = getattr(self._composition[0], "shutdown", None)
                if callable(shutdown):
                    shutdown()
        except Exception:
            logging.getLogger(__name__).warning("Personal profile cleanup needs a retry.")
        finally:
            close = getattr(self._composition[1], "close", None)
            if callable(close):
                close()
            credentials = getattr(self._composition[1], "credential_provider", None)
            if credentials is not None and getattr(credentials.session, "ephemeral", False):
                credentials.session.lock()
