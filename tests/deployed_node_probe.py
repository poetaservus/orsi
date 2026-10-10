"""Exercise a real deployed node with synthetic contents and network disabled."""
import json
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

import app.main as desktop
import app.ui.profile_application as owners
import app.ui.profile_loading as loading
from app.settings.paths import PATHS
from app.ui.instance import DesktopInstance
from app.ui.portable_deployment import PortableDeploymentDialog
from app.vault.types import Domain, State

PASSWORD = b"synthetic deployed node password"
PRIVATE = b"synthetic deployed node document"
SECRET = b"synthetic deployed node credential"
GREETING = "Synthetic deployed node greeting"
HISTORY = "Synthetic deployed node history"


def run(root, report_path):
    report = {"passed": False, "network_attempts": 0}
    owner, vault, keys, inference = None, None, None, None
    helpers = []
    def audit(event, args):
        if event in {"socket.connect", "socket.connect_ex"}:
            report["network_attempts"] += 1
            raise RuntimeError("Network is disabled for this check")
    sys.addaudithook(audit)

    class Cover(loading.ProfileLoadingCover):
        def __init__(self, previous=None):
            super().__init__(previous)
            self.launch = previous is None

        def present(self):
            super().present()
            assert self.fallback is None and self.process.poll() is None
            helpers.append(self.process)

        def dismiss(self, reveal=None):
            super().dismiss(reveal)
            if self.launch:
                QTimer.singleShot(0, owner.exercise)

    class Owner(owners.ProfileApplication):
        def start(self):
            nonlocal owner
            owner = self
            self.watchdog = QTimer(self)
            self.watchdog.setSingleShot(True)
            self.watchdog.timeout.connect(self.timeout)
            self.watchdog.start(30000)
            super().start()

        def timeout(self):
            report["error_type"] = "TimeoutError"
            self.application.quit()

        def exercise(self):
            nonlocal vault, keys, inference
            try:
                report["stage"] = "locked_startup"
                assert self.window.login_panel.isVisible() and self.window.service is None
                assert self.manager.locator.mode == "portable" and self.manager.locator.root == root / "profiles/current"
                assert self.window.login_panel.grab().save(str(report_path.with_name("deployed-login.png")))
                report["stage"] = "unlock"
                page = self.window.personal_profile_page
                page.password.setText(PASSWORD.decode())
                QTest.keyClick(page.password, Qt.Key.Key_Return)
                assert self.manager.active and not hasattr(self.window, "login_panel")
                vault = self.manager.vault()
                keys = vault._keys
                inference = self.window.inference
                assert inference.local is None and inference.mode == "cloud" and inference.cloud._client is None
                report["stage"] = "personal_records"
                assert vault.read("documents/report.txt") == PRIVATE
                assert vault.read("synthetic/credential", domain=Domain.CREDENTIAL) == SECRET
                assert self.window.greeting_input.text() == GREETING
                assert "deployment-sample" in {skill.name for skill in self.window.service.skill_registry.list()}
                assert vault._catalog["backups"]
                report["stage"] = "history"
                archives = [json.loads(vault.read(key)) for key in vault.list_paths()
                            if key.startswith("state/conversation_v1/archives/")]
                assert any(message["content"] == HISTORY for archive in archives for message in archive["messages"])
                assert self.window.service.store.messages() == []
                from app.vault.credentials import CredentialProvider, CredentialPolicy
                report["stage"] = "saved_connections"
                credentials = CredentialProvider(self.manager.session)
                assert credentials.policy("deployment-synthetic") == CredentialPolicy.SAVED
                assert credentials.has_saved_api_key("deployment-synthetic") and credentials.begin("deployment-synthetic")
                assert credentials.saved_token("deployment-synthetic", kind="access_token") == SECRET.decode() + "-access"
                assert not credentials.begin("session-synthetic")
                report["stage"] = "capabilities"
                assert {"filesystem.stat", "filesystem.read_text", "filesystem.edit_text"} <= set(self.window.service.agent_capabilities)
                report.update(saved_connection_retained=True, session_only_connection_not_exported=True,
                              skills_files_preferences_history_retained=True)
                report["stage"] = "packaged_deployment_controls"
                page = self.window.personal_profile_page
                assert not any(button.text() == "Deploy portable node…" for button in page.findChildren(QPushButton))
                from app.portable.deployment import DeploymentError, deploy_node
                forbidden = root.parent / "forbidden offspring"
                try:
                    deploy_node(self.manager, forbidden, include_profile=False)
                except DeploymentError as error:
                    assert "Portable nodes cannot deploy" in str(error)
                else:
                    raise AssertionError("Portable deployment guard was bypassed")
                assert not forbidden.exists()
                dialog = PortableDeploymentDialog(self.manager, self.window, page)
                dialog.show()
                QTest.qWait(100)
                assert not dialog.start_button.isEnabled()
                assert "cannot deploy" in dialog.status.text()
                assert dialog.grab().save(str(report_path.with_name("deployment-dialog.png")))
                dialog.reject()
                report["portable_deployment_disabled"] = True
                report["scenario_passed"] = True
            except BaseException as error:
                report["error_type"] = type(error).__name__
                report["error_frames"] = [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                    for frame in traceback.extract_tb(error.__traceback__)]
            finally:
                self.watchdog.stop()
                self.window.close()
                self.application.quit()

    try:
        assert root.resolve() == PATHS.root.resolve() and not (root / ".git").exists()
        loading.ProfileLoadingCover = owners.ProfileLoadingCover = Cover
        owners.ProfileApplication = Owner
        sys.argv = ["deployed-node-check"]
        report["stage"] = "desktop_entry"
        assert desktop.main() == 0 and report.get("scenario_passed")
        report["stage"] = "released_resources"
        assert owner is not None and not owner.manager.active
        assert vault.state == State.LOCKED and vault._keys is None and not any(keys) and vault._lease is None
        assert inference._closed and inference.cloud._client is None
        assert helpers and all(process.poll() == 0 for process in helpers)
        retry = DesktopInstance(root, owner.application)
        try:
            assert retry.claim()
        finally:
            retry.close()
        assert report["network_attempts"] == 0
        report.update(passed=True, helpers_released=len(helpers), keys_zeroed=True,
                      lease_released=True, independent_profile_opened=True)
    except BaseException as error:
        report.setdefault("error_type", type(error).__name__)
        report.setdefault("error_frames", [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)])
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2])))
