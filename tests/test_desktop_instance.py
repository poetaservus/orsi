"""Desktop ownership and activation; no personal data or inference processes."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.instance import DesktopInstance


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def child_claim(root, *, crash=False):
    source = """
import os, sys
from PySide6.QtCore import QCoreApplication
from app.ui.instance import DesktopInstance
app = QCoreApplication([])
owner = DesktopInstance(sys.argv[1], app)
print(owner.claim(), flush=True)
if sys.argv[2] == 'crash':
    os._exit(0)
owner.close()
"""
    result = subprocess.run([sys.executable, "-c", source, str(root), "crash" if crash else "close"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_secondary_activation_never_claims_or_releases_primary(app, tmp_path):
    primary, secondary = DesktopInstance(tmp_path, app), DesktopInstance(tmp_path, app)
    activated = []
    primary.activation_requested.connect(lambda: activated.append(True))
    try:
        assert primary.claim()
        assert not secondary.claim()
        QTest.qWait(30)
        assert activated == [True]
        secondary.close()
        assert primary.owned
        assert not DesktopInstance(tmp_path, app).claim()
        primary.close()
        assert secondary.claim()
    finally:
        primary.close()
        secondary.close()


def test_separate_process_can_only_activate_existing_owner(app, tmp_path):
    primary = DesktopInstance(tmp_path, app)
    activated = []
    primary.activation_requested.connect(lambda: activated.append(True))
    try:
        assert primary.claim()
        assert child_claim(tmp_path) == "False"
        QTest.qWait(30)
        assert activated == [True] and primary.owned
    finally:
        primary.close()


def test_crashed_owner_is_recovered_without_deleting_live_owner(app, tmp_path):
    assert child_claim(tmp_path, crash=True) == "True"
    recovered = DesktopInstance(tmp_path, app)
    try:
        assert recovered.claim()
        assert child_claim(tmp_path) == "False"
    finally:
        recovered.close()


def test_different_application_directories_keep_independent_owners(app, tmp_path):
    first, other = DesktopInstance(tmp_path / "first", app), DesktopInstance(tmp_path / "other", app)
    try:
        assert first.claim() and other.claim()
        assert first.name != other.name
    finally:
        first.close()
        other.close()


def test_entrypoint_secondary_launch_does_not_compose_or_unlock(app, tmp_path, monkeypatch):
    import app.main as entry
    primary = DesktopInstance(tmp_path, app)
    monkeypatch.setattr("PySide6.QtWidgets.QApplication", lambda *a: app)
    monkeypatch.setattr(entry, "PATHS", SimpleNamespace(root=tmp_path, state=tmp_path / "state", ensure_directories=lambda: None))
    monkeypatch.setattr(entry, "load_agent_feature_config", lambda: pytest.fail("Secondary startup read configuration"))
    monkeypatch.setattr(entry, "build_application", lambda **k: pytest.fail("Secondary startup composed private consumers"))
    try:
        assert primary.claim()
        assert entry.main() == 0
        assert primary.owned
    finally:
        primary.close()
