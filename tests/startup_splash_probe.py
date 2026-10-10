"""Exercise the real desktop entry point with synthetic storage and no providers."""
import json
from pathlib import Path
import sys
from time import sleep

from PySide6.QtCore import QTimer

import app.main as desktop
import app.ui.personal_profile as profile_ui
import app.ui.profile_application as owner_ui
import app.ui.profile_loading as loading_ui
from app.settings.paths import RuntimePaths
from app.vault.profiles import ProfileManager
from tests.test_settings_presentation import helper_window
from tests.test_vault_controls import PASSWORD, build_synthetic


def run(root, selection, action):
    root.mkdir()
    report = {"selection": selection, "action": action, "covers": [], "compositions": 0}
    manager = ProfileManager(root)
    if selection != "legacy":
        manager.create(root / "profiles/selected", mode="portable", encrypted=selection == "locked",
                       password=PASSWORD if selection == "locked" else b"")
        manager.lock()
    active_cover = None
    desktop_owner = None
    phase = "launch"

    class ObservedCover(loading_ui.ProfileLoadingCover):
        def present(self):
            nonlocal active_cover
            super().present()
            assert self.fallback is None and self.process.poll() is None
            self.observed_process = self.process
            handle = helper_window(self.process.pid)
            image = loading_ui.QApplication.primaryScreen().grabWindow(handle)
            assert not image.isNull()
            image.save(str(root / f"{phase}-splash.png"))
            report["covers"].append({"phase": phase, "native_visible": True, "topmost": True,
                                     "finished": False})
            active_cover = self

        def dismiss(self, reveal=None):
            nonlocal active_cover
            assert reveal is not None and reveal.isVisible()
            assert reveal.geometry() == self.geometry
            super().dismiss(reveal)
            assert self.observed_process.poll() == 0 and self.process is None
            report["covers"][-1]["finished"] = True
            active_cover = None
            if phase == "launch":
                callback = desktop_owner.application.quit if action == "none" else desktop_owner.continue_login
                QTimer.singleShot(0, callback)

    def build(**kwargs):
        assert active_cover is not None, "Desktop composed without a visible loading splash"
        helper_window(active_cover.process.pid)
        sleep(.2)  # Composition deliberately blocks the parent's Qt event loop.
        report["compositions"] += 1
        return build_synthetic(**kwargs)

    class ObservedOwner(owner_ui.ProfileApplication):
        def start(self):
            nonlocal desktop_owner
            desktop_owner = self
            super().start()
            assert len(report["covers"]) == 1, "Fresh launch did not present the splash"
            if selection == "locked":
                assert self.window.login_panel.isVisible() and report["compositions"] == 0

        def continue_login(self):
            nonlocal phase
            try:
                phase = action
                old = self.window
                old.setGeometry(100, 100, 760, 600)
                page = old.personal_profile_page
                if action == "unlock":
                    page.password.setText(PASSWORD.decode())
                    page._unlock()
                    assert self.manager.active
                else:
                    page._legacy()
                    assert self.manager.locator is None
                assert len(report["covers"]) == 2
                assert self.window.isVisible() and not old.isVisible()
                assert not hasattr(self.window, "login_panel")
            except BaseException as error:
                report["error"] = f"{type(error).__name__}: {error}"
            finally:
                self.application.quit()

    loading_ui.ProfileLoadingCover = owner_ui.ProfileLoadingCover = ObservedCover
    owner_ui.ProfileApplication = ObservedOwner
    profile_ui.confirm = lambda *args: True
    desktop.PATHS = RuntimePaths(root, root / "config", root / "models", root / "state")
    desktop.load_agent_feature_config = lambda: None
    desktop.build_application = build
    try:
        report["exit_code"] = desktop.main()
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        manager.lock()
        (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
