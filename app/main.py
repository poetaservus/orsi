from __future__ import annotations

import sys
import logging
from pathlib import Path

# Support module execution from the project root and direct file execution.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.infrastructure.logging import configure_logging
from app.settings.agent import load_agent_feature_config
from app.settings.paths import PATHS
from app.state.storage import JsonStore


def build_application(*args, **kwargs):
    from app.startup import build_application as build
    return build(*args, **kwargs)


def main(*, profile_session=None) -> int:
    """Initialize runtime directories, compose the backend, and start the Qt UI."""
    if len(sys.argv) > 1 and sys.argv[1].casefold() == "skill":
        from app.runtime.skills.cli import main as skill_main
        return skill_main(sys.argv[2:])
    PATHS.ensure_directories()
    if profile_session is None:
        configure_logging(PATHS.state / "orsi.log")
    else:
        from app.vault.logging import configure_profile_logging
        configure_profile_logging(profile_session)

    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    try:
        startup_agent_config = load_agent_feature_config()
    except (OSError, TypeError, ValueError):
        startup_agent_config = None
    # Host access follows the configured setting, without a per-launch popup.
    full_local_read_acknowledged = bool(
        startup_agent_config is not None and startup_agent_config.full_local_read_enabled
    )
    service, host, error, inference = build_application(
        agent_config_override=startup_agent_config,
        full_local_read_acknowledged=full_local_read_acknowledged,
        **({"profile_session": profile_session} if profile_session is not None else {}),
    )
    def shutdown():
        try:
            if service is not None:
                service.shutdown()
        except Exception:
            logging.getLogger(__name__).warning("Application service cleanup failed.")
        finally:
            close = getattr(inference, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                if profile_session is not None:
                    profile_session.lock()

    app.aboutToQuit.connect(shutdown)
    try:
        preferences = JsonStore(profile_session.path("state/ui_preferences_v1.json")
            if profile_session is not None else PATHS.state / "ui_preferences_v1.json")
        window = MainWindow(service, host["hostname"], error, inference, preferences)
        if profile_session is not None:
            window.bind_profile(profile_session)
        window.show()
        return app.exec()
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
