from __future__ import annotations

import sys
from pathlib import Path

# Support module execution from the project root and direct file execution.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.infrastructure.logging import configure_logging
from app.settings.agent import load_agent_feature_config
from app.settings.paths import PATHS
from app.startup import build_application, request_full_local_read_acknowledgement
from app.state.storage import JsonStore


def main() -> int:
    """Initialize runtime directories, compose the backend, and start the Qt UI."""
    PATHS.ensure_directories()
    configure_logging(PATHS.state / "orsi.log")

    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    full_local_read_acknowledged = False
    try:
        startup_agent_config = load_agent_feature_config()
    except (OSError, TypeError, ValueError):
        startup_agent_config = None
    if startup_agent_config is not None and startup_agent_config.full_local_read_enabled:
        full_local_read_acknowledged = request_full_local_read_acknowledgement(
            filesystem_list_enabled=(
                startup_agent_config.filesystem_list_enabled
                or startup_agent_config.filesystem_find_enabled
            ),
            filesystem_read_text_enabled=(
                startup_agent_config.filesystem_read_text_enabled
            ),
            filesystem_search_enabled=startup_agent_config.filesystem_search_enabled,
        )
    service, host, error, inference = build_application(
        agent_config_override=startup_agent_config,
        full_local_read_acknowledged=full_local_read_acknowledged,
    )
    preferences = JsonStore(PATHS.state / "ui_preferences_v1.json")
    window = MainWindow(service, host["hostname"], error, inference, preferences)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
