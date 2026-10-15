"""Basic controls, worker ownership and between-turn catalog changes."""
import os
from pathlib import Path
from types import SimpleNamespace
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.settings.personality import PersonalitySettings
from app.settings.response_language import ResponseLanguageSettings
from tests.test_office_mcp_live import live_connection


def wait(predicate):
    deadline = monotonic() + 10
    while not predicate() and monotonic() < deadline:
        QTest.qWait(15)
    assert predicate()


def test_controls_require_cloud_and_explicit_document_selection_and_release_worker(tmp_path):
    app = QApplication.instance() or QApplication([])
    bridge = live_connection()
    service = SimpleNamespace(office_connection=bridge, personality_settings=PersonalitySettings(),
                              response_language_settings=ResponseLanguageSettings())
    window = MainWindow(service, "SYNTHETIC")
    try:
        window.inference = SimpleNamespace(mode="local")
        controls = window.settings_panel.office_controls
        controls.sync()
        assert not controls.connect_button.isEnabled()
        window.inference = SimpleNamespace(mode="cloud")
        # The synthetic owner only needs the existing busy state, not model catalogs.
        busy = []
        window._settings_worker_busy = lambda value: (busy.append(value), setattr(window, "_settings_busy", value))
        controls.sync()
        controls.connect_button.click()
        assert controls.worker is not None and window._settings_busy
        wait(lambda: controls.worker is None)
        assert controls.documents.count() == 3
        assert bridge._selected is None and not controls.select_button.isEnabled()
        controls.documents.setCurrentIndex(1)
        assert bridge._selected is None
        controls.select_button.click()
        wait(lambda: controls.worker is None)
        assert bridge._selected is not None
        window.thread = object()
        controls.sync()
        assert not controls.refresh_button.isEnabled()
        window.thread = None
        controls.sync()
        window.resize(1100, 850)
        window.show()
        window.settings_panel.show_section("Models")
        window.settings_panel.show()
        window.settings_panel.page_transition.cancel()
        app.processEvents()
        window.grab().save(str(tmp_path / "office-controls.png"))
        controls.disconnect_button.click()
        wait(lambda: controls.worker is None)
        assert not bridge.diagnostics["worker_alive"] and not bridge.exposure.ready
        assert busy == [True, False] * 3
    finally:
        bridge.close()
        window.inference = None
        window.close()
        app.processEvents()
