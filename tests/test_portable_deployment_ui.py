"""Native deployment controls, pending preference flush and profile-lock cancellation."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

import app.ui.portable_deployment as ui
from app.portable.deployment import PROFILE_FOLDER
from app.state.storage import JsonStore
from app.ui.profile_application import ProfileApplication
from app.vault.profiles import ProfileManager
from tests.test_portable_deployment import source
from tests.test_profile_onboarding import close_controller
from tests.test_vault_controls import PASSWORD, build_synthetic, qt


@pytest.fixture
def controller(qt, source):
    manager = ProfileManager(source)
    manager.create(source / "profiles/original", password=PASSWORD)
    owner = ProfileApplication(qt, source, build_synthetic, manager=manager)
    owner.start()
    yield owner
    close_controller(qt, owner)


def wait_until(qt, condition):
    for _ in range(300):
        qt.processEvents()
        if condition():
            return
        QTest.qWait(10)
    pytest.fail("Deployment did not finish within the bounded wait")


def test_open_dialog_and_deploy_current_profile_flushes_pending_preferences(qt, controller):
    window = controller.window
    window.greeting_input.setText("Synthetic pending deployment greeting")
    assert window._greeting_save_timer.isActive()
    target = controller.manager.application_root.parent / "node from controls"
    before_session, before_locator = controller.manager.session, controller.manager.locator
    observations = []
    def handle_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ui.PortableDeploymentDialog)
        QTimer.singleShot(5000, dialog.reject)
        assert dialog.current.isChecked() and not dialog.fresh.isChecked() and not dialog.models.isChecked()
        dialog.location.setText(str(target))
        QTest.mouseClick(dialog.start_button, Qt.MouseButton.LeftButton)
        def finish():
            if dialog.worker is not None:
                QTimer.singleShot(10, finish)
                return
            observations.append((dialog.result, dialog.status.text(), dialog.open_folder.isVisible(), dialog.progress.value()))
            dialog.accept()
        QTimer.singleShot(10, finish)
    page = window.personal_profile_page
    button = next(control for control in page.findChildren(QPushButton) if control.text() == "Deploy portable node…")
    window.settings_panel.show_section("Personal profile")
    window.settings_panel.show()
    qt.processEvents()
    QTimer.singleShot(0, handle_dialog)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert observations and observations[0][0] is not None, observations
    assert observations[0][2:] == (True, 100)
    assert controller.manager.session is before_session and controller.manager.locator == before_locator
    copied = ProfileManager(target)
    copied.unlock(PASSWORD)
    try:
        assert JsonStore(copied.session.storage_path("state/ui_preferences_v1.json")).load()["greeting_message"] == "Synthetic pending deployment greeting"
        assert copied.locator.root == target / PROFILE_FOLDER
    finally:
        copied.lock()


def test_fresh_choice_does_not_export_profile(qt, controller):
    dialog = ui.PortableDeploymentDialog(controller.manager, controller.window)
    target = controller.manager.application_root.parent / "fresh from controls"
    try:
        dialog.show()
        QTest.mouseClick(dialog.fresh, Qt.MouseButton.LeftButton)
        assert dialog.fresh.isChecked() and not dialog.current.isChecked()
        dialog.location.setText(str(target))
        dialog.start_button.click()
        wait_until(qt, lambda: dialog.worker is None)
        assert dialog.result is not None and not dialog.result.includes_profile
        assert not (target / "profiles").exists() and controller.manager.active
    finally:
        dialog.reject()


def test_busy_operation_defers_deployment(qt, controller):
    dialog = ui.PortableDeploymentDialog(controller.manager, controller.window)
    target = controller.manager.application_root.parent / "busy destination"
    try:
        controller.window.thread = SimpleNamespace(isRunning=lambda: True)
        dialog.location.setText(str(target))
        dialog._start()
        assert "Wait for the current" in dialog.status.text() and dialog.worker is None and not target.exists()
    finally:
        controller.window.thread = None
        dialog.reject()


@pytest.mark.parametrize("lock_profile", [False, True])
def test_cancel_or_lock_during_copy_drains_worker_and_removes_partial(qt, controller, monkeypatch, lock_profile):
    source_session = controller.manager.session
    actual_deploy = ui.deploy_node
    reached_copy = []
    def slow(*args, **kwargs):
        report = kwargs["progress"]
        def gate(value, text):
            report(value, text)
            if text == "Copying your profile…" and not reached_copy:
                reached_copy.append(True)
                kwargs["token"].wait(5)
        kwargs["progress"] = gate
        return actual_deploy(*args, **kwargs)
    monkeypatch.setattr(ui, "deploy_node", slow)
    dialog = ui.PortableDeploymentDialog(controller.manager, controller.window)
    target = controller.manager.application_root.parent / "cancelled from controls"
    dialog.location.setText(str(target))
    dialog.show()
    dialog._start()
    wait_until(qt, lambda: bool(reached_copy))
    if lock_profile:
        controller.transition(controller.manager.lock)
        assert controller.window.login_panel.isVisible() and not controller.manager.active
        assert not source_session._resources
    else:
        dialog.reject()
        wait_until(qt, lambda: dialog.worker is None)
        assert controller.manager.active and controller.manager.session is source_session
        assert "cancelled" in dialog.status.text().lower()
    assert not target.exists() and not list(target.parent.glob(".orsi-node-*.partial"))


def test_shutdown_cancels_fresh_deployment_without_a_profile(qt, source, monkeypatch):
    from app.ui.main_window import MainWindow
    manager = ProfileManager(source)
    window = MainWindow(None, "synthetic", None, None)
    dialog = ui.PortableDeploymentDialog(manager, window)
    target = source.parent / "unprofiled fresh deployment"
    reached_copy = []
    actual_deploy = ui.deploy_node
    def slow(*args, **kwargs):
        report = kwargs["progress"]
        def gate(value, text):
            report(value, text)
            if text == "Copying node…" and not reached_copy:
                reached_copy.append(True)
                kwargs["token"].wait(5)
        kwargs["progress"] = gate
        return actual_deploy(*args, **kwargs)
    monkeypatch.setattr(ui, "deploy_node", slow)
    try:
        assert dialog.fresh.isChecked() and not dialog.current.isEnabled()
        dialog.location.setText(str(target))
        dialog._start()
        wait_until(qt, lambda: bool(reached_copy))
        dialog._shutdown()
        wait_until(qt, lambda: dialog.worker is None)
        assert not target.exists() and not list(target.parent.glob(".orsi-node-*.partial"))
        assert manager.locator is None and not manager.active
    finally:
        dialog.reject()
        window.close()
