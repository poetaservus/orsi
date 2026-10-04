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


def main() -> int:
    """Initialize runtime directories, compose the backend, and start the Qt UI."""
    if len(sys.argv) > 1 and sys.argv[1].casefold() == "skill":
        from app.runtime.skills.cli import main as skill_main
        return skill_main(sys.argv[2:])
    PATHS.ensure_directories()
    configure_logging(PATHS.state / "orsi.log")

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
    )
    def shutdown():
        try:
            if service is not None:
                service.shutdown()
        except Exception:
            logging.getLogger(__name__).warning("Application service cleanup failed.")
        finally:
            close = getattr(inference, "close", None)
            if callable(close):
                close()

    app.aboutToQuit.connect(shutdown)
    try:
        preferences = JsonStore(PATHS.state / "ui_preferences_v1.json")
        window = MainWindow(service, host["hostname"], error, inference, preferences)
        window.show()
        return app.exec()
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
