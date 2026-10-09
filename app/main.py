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


def build_application(*args, **kwargs):
    from app.startup import build_application as build
    return build(*args, **kwargs)


def main(*, profile_session=None) -> int:
    """Initialize runtime directories, compose the backend, and start the Qt UI."""
    if len(sys.argv) > 1 and sys.argv[1].casefold() == "skill":
        from app.runtime.skills.cli import main as skill_main
        return skill_main(sys.argv[2:])
    PATHS.ensure_directories()
    from PySide6.QtWidgets import QApplication

    from app.ui.instance import DesktopInstance

    app = QApplication(sys.argv)
    instance = DesktopInstance(PATHS.root, app)
    try:
        if not instance.claim():
            return 0
        from app.ui.profile_application import ProfileApplication
        try:
            startup_agent_config = load_agent_feature_config()
        except (OSError, TypeError, ValueError):
            startup_agent_config = None
        # Host access follows the configured setting, without a per-launch popup.
        full_local_read_acknowledged = bool(
            startup_agent_config is not None and startup_agent_config.full_local_read_enabled
        )
        def compose(**kwargs):
            return build_application(agent_config_override=startup_agent_config,
                full_local_read_acknowledged=full_local_read_acknowledged, **kwargs)
        owner = ProfileApplication(app, PATHS.root, compose, initial_session=profile_session,
            legacy_logging=lambda: configure_logging(PATHS.state / "orsi.log"))
        instance.activation_requested.connect(owner.activate)
        try:
            owner.start()
            return app.exec()
        finally:
            owner.shutdown()
    finally:
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
