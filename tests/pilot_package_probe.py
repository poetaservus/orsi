"""Run with an extracted pilot's pythonw; observe real startup without providers."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

import app.main as desktop
import app.ui.profile_application as owners
import app.ui.profile_loading as loading
from app.settings.paths import PATHS
from app.ui.instance import DesktopInstance
from app.vault.types import Domain, State


PASSWORD = b"synthetic pilot smoke password"
PERSONAL = b"synthetic pilot personal record"
CREDENTIAL = b"synthetic pilot credential record"
HISTORY = "synthetic pilot history"


def run(root, phase, report_path, *, unlocked_check=None):
    report = {"passed": False, "phase": phase, "network_attempts": 0}
    controller = None
    helpers, opened, inferences = [], [], []

    def forbid_network(event, args):
        if event == "socket.connect":
            report["network_attempts"] += 1
            raise RuntimeError("Network is forbidden in this offline pilot check.")
    sys.addaudithook(forbid_network)

    class ObservedCover(loading.ProfileLoadingCover):
        def __init__(self, previous=None):
            super().__init__(previous)
            self.launch = previous is None

        def present(self):
            super().present()
            assert self.fallback is None and self.process.poll() is None
            helpers.append(self.process)

        def dismiss(self, reveal=None):
            assert reveal is not None and reveal.isVisible()
            super().dismiss(reveal)
            if self.launch:
                QTimer.singleShot(0, controller.exercise)

    class ObservedOwner(owners.ProfileApplication):
        def start(self):
            nonlocal controller
            controller = self
            self.watchdog = QTimer(self)
            self.watchdog.setSingleShot(True)
            self.watchdog.timeout.connect(self.timeout)
            self.watchdog.start(30000)
            super().start()

        def timeout(self):
            report["error_type"] = "TimeoutError"
            self.application.quit()

        def check_cloud(self):
            inference = self.window.inference
            assert self.window.isVisible() and inference.mode == "cloud" and inference.local is None
            assert self.window.service is not None and inference.cloud._client is None
            assert {"filesystem.stat", "filesystem.read_text", "filesystem.edit_text"} <= set(self.window.service.agent_capabilities)
            inferences.append(inference)

        def exercise(self):
            try:
                if phase == "fresh":
                    report["stage"] = "fresh_profile_setup"
                    assert self.manager.locator is None
                    assert self.window.login_panel.isVisible() and self.window.personal_profile_page.setup_required
                    assert self.window.service is None and self.window.inference is None
                    assert [button.text() for button in self.window.personal_profile_page.findChildren(QPushButton)] == ["Create profile"]
                    report["stage"] = "create_profile"
                    self.transition(lambda: self.manager.create(root / "profiles/pilot-fixture",
                        mode="portable", password=PASSWORD))
                    assert self.manager.active
                    self.check_cloud()
                    vault = self.manager.vault()
                    opened.append((vault, vault._keys))
                    vault.put("pilot/personal", PERSONAL)
                    vault.put("pilot/credential", CREDENTIAL, domain=Domain.CREDENTIAL)
                    self.window.service.store.append("user", HISTORY)
                    assert self.manager.bootstrap.load()["relative"] is True
                    report["stage"] = "lock_profile"
                    self.transition(self.manager.lock)
                    assert not self.manager.active and self.window.login_panel.isVisible()
                else:
                    report["stage"] = "locked_startup"
                    assert phase == "restart"
                    assert not self.manager.active and self.window.login_panel.isVisible()
                    assert self.window.service is None and self.window.inference is None
                    assert self.manager.locator.root.resolve() == root / "profiles/pilot-fixture"
                    report["stage"] = "unlock_profile"
                    page = self.window.personal_profile_page
                    page.password.setText(PASSWORD.decode())
                    QTest.keyClick(page.password, Qt.Key.Key_Return)
                    assert self.manager.active
                    report["stage"] = "unlocked_composition"
                    self.check_cloud()
                    vault = self.manager.vault()
                    opened.append((vault, vault._keys))
                    report["stage"] = "retained_records"
                    assert vault.read("pilot/personal") == PERSONAL
                    assert vault.read("pilot/credential", domain=Domain.CREDENTIAL) == CREDENTIAL
                    # Startup deliberately archives prior conversations and opens
                    # an empty chat. Verify durable history in its actual archive.
                    archived = [json.loads(vault.read(key)) for key in vault.list_paths()
                        if key.startswith("state/conversation_v1/archives/")]
                    assert self.window.service.store.messages() == [] and len(archived) == 1
                    assert archived[0]["session_status"] == "closed"
                    assert archived[0]["messages"][0]["content"] == HISTORY
                    report["personal_credential_history_retained"] = True
                    if unlocked_check is not None:
                        # QTest's unlock key release must finish before another
                        # event loop can delete the retired login editor.
                        report["stage"] = "unlocked_check"
                        unlocked_check(self)
                report["scenario_passed"] = True
            except BaseException as error:
                report["error_type"] = type(error).__name__
            finally:
                self.watchdog.stop()
                self.window.close()
                self.application.quit()

    try:
        report["stage"] = "package_root"
        assert PATHS.root.resolve() == root and root.name.startswith("orsi-cloud-pilot-")
        assert phase in {"fresh", "restart"}
        if phase == "fresh":
            assert not (root / "state/profile_locator_v1.json").exists() and not (root / "profiles").exists()
        loading.ProfileLoadingCover = owners.ProfileLoadingCover = ObservedCover
        owners.ProfileApplication = ObservedOwner
        sys.argv = ["orsi-pilot-smoke"]
        report["stage"] = "desktop_entry"
        assert desktop.main() == 0
        assert report.get("scenario_passed") and "error_type" not in report
        report["stage"] = "released_resources"
        assert controller is not None and not controller.manager.active
        assert helpers and all(process.poll() == 0 for process in helpers)
        assert all(vault.state == State.LOCKED and vault._lease is None
            and vault._keys is None and not any(keys) for vault, keys in opened)
        assert all(inference._closed and inference.cloud._client is None for inference in inferences)
        retry = DesktopInstance(root, controller.application)
        try:
            assert retry.claim()
        finally:
            retry.close()
        assert report["network_attempts"] == 0
        report["stage"] = "complete"
        report.update(passed=True, code_from_package=True, real_cloud_composition=True,
            helpers_released=True, vault_resources_released=True, desktop_ownership_released=True)
    except BaseException as error:
        report["error_type"] = type(error).__name__
    finally:
        if controller is not None:
            controller.shutdown()
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3]).resolve())
