"""Attention timing, silent native delivery, settings and resource ownership."""
import ctypes
import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QUrl, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.conversation.attachments import AttachmentStore
from app.inference.completion import CompletionMetadata, CompletionText
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow
from app.ui.notifications import EVENTS, SOUNDS, NotificationManager
from tests.test_inline_approvals import ApprovalService, record
from tests.test_message_images import image_bytes, wait_for


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_completion_and_streaming_attention_timing(app, monkeypatch):
    window = MainWindow(None, "test")
    notify = Mock()
    monkeypatch.setattr(window.notifications, "notify", notify)
    try:
        window._preview_active = True
        window._stream_preview("First")
        window._stream_preview("First second")
        notify.assert_not_called()
        window._worker_succeeded("Final response")
        notify.assert_called_once_with("response")
        notify.reset_mock()
        window._worker_failed("Task failed")
        notify.assert_called_once_with("error")
        notify.reset_mock()
        window._worker_succeeded(CompletionText("Stopped", CompletionMetadata(finish_reason="cancelled")))
        window._image_stopping = True
        window._worker_failed("Stopped")
        notify.assert_not_called()
        window._closing = True
        window._worker_succeeded("Late response")
        notify.assert_not_called()
    finally:
        window.close()


def test_image_completion_uses_single_image_notification(app, monkeypatch, tmp_path):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(image_bytes("blue", 100, 100), name="result.png")
    service = SimpleNamespace(store=SimpleNamespace(attachment_store=store))
    window = MainWindow(service, "test")
    notify = Mock()
    monkeypatch.setattr(window.notifications, "notify", notify)
    try:
        window.chat.start_image_generation(1)
        window._image_in_flight = True
        window._worker_succeeded(CompletionText("Image generated.", generated_images=(ref,)))
        notify.assert_called_once_with("image")
        assert window.chat._messages[-1].image_strip.references == (ref,)
    finally:
        window.chat.image_loader.clear()
        wait_for(lambda: window.chat.image_loader.pool.activeThreadCount() == 0)
        window.close()


def test_only_actionable_approval_notifies(app, monkeypatch):
    service = ApprovalService()
    window = MainWindow(service, "test")
    notify = Mock()
    monkeypatch.setattr(window.notifications, "notify", notify)
    try:
        window._show_approval(record())
        notify.assert_called_once_with("approval")
        window._show_approval(record(approval_id="two"))
        assert notify.call_count == 1
        window._approval_panel.reject()
        window._show_approval(record())  # Resolved request is not actionable.
        assert notify.call_count == 1
    finally:
        window.close()


def test_settings_preserve_other_preferences_and_restore(app, tmp_path):
    store = JsonStore(tmp_path / "ui.json")
    original = {"greeting_message": "Hello", "unrelated": {"keep": True}}
    store.save(original)
    window = MainWindow(None, "test", preferences_store=store)
    try:
        assert store.load() == original  # Startup does not migrate user state.
        assert window.notifications.sound == "noti_1.ogg"
        selector = window.notification_sound.selector
        selector.setCurrentIndex(selector.findData("noti_2.ogg"))
        window.notification_toggle.setChecked(False)
        window.greeting_input.setText("Welcome")
        window._finish_greeting_edit()
        saved = store.load()
        assert saved == original | {"greeting_message": "Welcome", "notifications": {
            "enabled": False, "sound": "noti_2.ogg"}}
    finally:
        window.close()
    restored = MainWindow(None, "test", preferences_store=store)
    try:
        assert restored.notifications.sound == "noti_2.ogg"
        assert not restored.notification_toggle.isChecked()
        assert restored.notification_sound.selector.currentData() == "noti_2.ogg"
    finally:
        restored.close()


def test_custom_sound_cancel_preview_and_missing_file_fallback(app, tmp_path, monkeypatch):
    window = MainWindow(None, "test", preferences_store=JsonStore(tmp_path / "ui.json"))
    control = window.notification_sound
    try:
        control.selector.setCurrentIndex(control.selector.count() - 1)
        assert control.dialog is not None
        control.dialog.reject()
        assert window.notifications.sound == "noti_1.ogg"
        custom = tmp_path / "custom sound.ogg"
        custom.write_bytes((SOUNDS / "noti_2.ogg").read_bytes())
        control._file_selected(str(custom))
        assert window.notifications.sound_path() == custom
        assert control.selector.currentData() == str(custom.resolve())
        assert control.preview.isEnabled()
        custom.unlink()
        assert window.notifications.sound_path() == SOUNDS / "noti_1.ogg"
        control.selector.setCurrentIndex(control.selector.findData(""))
        assert window.notifications.sound_path() is None
        assert not control.preview.isEnabled()
    finally:
        window.close()


def test_unreadable_preferences_are_never_overwritten(app, tmp_path):
    store = JsonStore(tmp_path / "ui.json")
    store.path.write_text("invalid document", encoding="utf-8")
    parent = MainWindow(None, "test")
    try:
        manager = NotificationManager(parent, store)
        manager.configure(sound="noti_2.ogg")
        assert store.path.read_text(encoding="utf-8") == "invalid document"
    finally:
        parent.close()


def test_playback_uses_selected_ogg_and_silent_stops_playback(app, monkeypatch):
    window = MainWindow(None, "test")
    manager = window.notifications
    manager.player = Mock()
    monkeypatch.setattr(QApplication, "platformName", lambda: "windows")
    try:
        manager.play_sound()
        manager.player.setSource.assert_called_once_with(QUrl.fromLocalFile(str((SOUNDS / "noti_1.ogg").resolve())))
        manager.player.play.assert_called_once()
        manager.configure(sound="noti_2.ogg")
        manager.play_sound()
        assert manager.player.setSource.call_args.args[0].toLocalFile().endswith("noti_2.ogg")
        manager.configure(sound="")
        manager.play_sound()
        assert manager.player.play.call_count == 2
        before = manager.player.stop.call_count
        manager.configure(enabled=False)
        assert manager.player.stop.call_count == before + 1
    finally:
        window.close()


def test_foreground_quiet_background_popup_disabled_and_shutdown(app, monkeypatch):
    window = MainWindow(None, "test")
    manager = window.notifications
    manager.backend = Mock()
    play = Mock()
    monkeypatch.setattr(manager, "play_sound", play)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    try:
        manager.notify("response")
        play.assert_not_called()
        manager.backend.show_message.assert_not_called()
        monkeypatch.setattr(window, "isActiveWindow", lambda: False)
        manager.notify("approval")
        manager.backend.show_message.assert_called_once_with(*EVENTS["approval"])
        manager.enabled = False
        manager.notify("image")
        assert play.call_count == 1
        manager.enabled = True
        manager.player = Mock()
        manager.shutdown()
        manager.player.shutdown.assert_called_once()
        manager.backend.shutdown.assert_called_once()
        manager.notify("response")
        assert play.call_count == 1
    finally:
        # Shutdown is idempotent for the actual backend/player.
        window.close()


@pytest.mark.parametrize("event", EVENTS)
def test_all_automatic_events_are_quiet_in_foreground(app, monkeypatch, event):
    window = MainWindow(None, "test")
    manager = window.notifications
    manager.backend = Mock()
    play = Mock()
    monkeypatch.setattr(manager, "play_sound", play)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    try:
        manager.notify(event)
        play.assert_not_called()
        manager.backend.show_message.assert_not_called()
        monkeypatch.setattr(window, "isMinimized", lambda: True)
        manager.notify(event)
        play.assert_called_once_with(preview=False)
        manager.backend.show_message.assert_called_once_with(*EVENTS[event])
    finally:
        window.close()


def test_returning_to_orsi_cancels_alert_audio_but_preserves_explicit_preview(app):
    window = MainWindow(None, "test")
    window.notifications.player = Mock()
    try:
        app.sendEvent(window, QEvent(QEvent.Type.WindowActivate))
        window.notifications.player.stop.assert_called_once()
        window.notifications._sound_preview = True
        app.sendEvent(window, QEvent(QEvent.Type.WindowActivate))
        assert window.notifications.player.stop.call_count == 1
    finally:
        window.close()


@pytest.mark.parametrize("size", [(1280, 800), (760, 600)])
def test_notification_settings_visible_and_clickable_after_open_and_reopen(app, tmp_path, size):
    store = JsonStore(tmp_path / "ui.json")
    window = MainWindow(None, "test", preferences_store=store)
    try:
        window.resize(*size)
        window.show()
        for _ in range(2):
            window.settings_button.click()
            app.processEvents()
            scroll = window.settings_panel.pages.currentWidget()
            for control in (window.notification_toggle, window.notification_sound):
                scroll.ensureWidgetVisible(control)
                app.processEvents()
                visible = control.rect().translated(control.mapTo(scroll.viewport(), QPoint()))
                assert control.isVisible() and control.isEnabled()
                assert scroll.viewport().rect().contains(visible)
                assert control.width() >= scroll.viewport().width() - 16
            selector = window.notification_sound.selector
            preview = window.notification_sound.preview
            assert selector.isVisible() and preview.isVisible()
            assert window.notification_sound.rect().contains(selector.geometry())
            assert window.notification_sound.rect().contains(preview.geometry())
            selector.setCurrentIndex(selector.findData("noti_2.ogg"))
            assert store.load()["notifications"]["sound"] == "noti_2.ogg"
            scroll.ensureWidgetVisible(window.notification_toggle)
            app.processEvents()
            before = window.notification_toggle.isChecked()
            QTest.mouseClick(window.notification_toggle, Qt.MouseButton.LeftButton,
                             pos=QPoint(10, window.notification_toggle.height() // 2))
            assert window.notification_toggle.isChecked() != before
            assert store.load()["notifications"]["enabled"] != before
            window.settings_panel.hide()
    finally:
        window.close()


def test_click_restores_window_and_focuses_approval(app):
    service = ApprovalService()
    window = MainWindow(service, "test")
    try:
        window.show()
        window._show_approval(record())
        window.showMinimized()
        window.notifications.open_window()
        app.processEvents()
        assert not window.isMinimized()
        assert window._approval_panel.hasFocus()
    finally:
        window.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows notification ABI")
def test_native_delivery_suppresses_system_chime_click_and_cleanup(app, monkeypatch):
    from ctypes import wintypes
    from app.ui.windows_notifications import NotifyIconData, WindowsNotifications
    calls = []
    def send(operation, pointer):
        data = NotifyIconData.from_buffer_copy(ctypes.string_at(pointer, ctypes.sizeof(NotifyIconData)))
        calls.append((operation, data))
        return True
    shell = SimpleNamespace(Shell_NotifyIconW=Mock(side_effect=send))
    user = SimpleNamespace(LoadIconW=Mock(return_value=123), RegisterWindowMessageW=Mock(return_value=999))
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kw: shell if name == "shell32" else user)
    window = MainWindow(None, "test")
    backend = WindowsNotifications(window)
    try:
        assert ctypes.sizeof(NotifyIconData) == (976 if ctypes.sizeof(ctypes.c_void_p) == 8 else 956)
        assert backend.show_message(*EVENTS["approval"])
        assert [operation for operation, _ in calls] == [0, 4, 1]
        data = calls[-1][1]
        assert data.dwInfoFlags & 0x10  # NIIF_NOSOUND
        assert data.dwInfoFlags & 0x80
        assert data.szInfoTitle == EVENTS["approval"][0]
        clicks = Mock()
        backend.clicked.connect(clicks)
        message = wintypes.MSG()
        message.message = backend.callback_message
        message.lParam = 0x405
        assert backend.nativeEvent(b"windows_generic_MSG", ctypes.addressof(message)) == (True, 0)
        clicks.assert_called_once()
        message.message = backend.taskbar_created
        backend.nativeEvent(b"windows_generic_MSG", ctypes.addressof(message))
        assert [operation for operation, _ in calls][-2:] == [0, 4]
        backend.shutdown()
        assert calls[-1][0] == 2
        count = len(calls)
        backend.shutdown()
        assert not backend.show_message(*EVENTS["response"])
        assert len(calls) == count
    finally:
        backend.shutdown()
        window.close()
