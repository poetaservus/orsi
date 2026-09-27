import os
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.hybrid import HybridInferenceEngine
from app.state.storage import JsonStore
from app.ui.main_window import MainWindow


class BlockingBackend(InferenceEngine):
    def __init__(self):
        self.started, self.released = Event(), Event()
        self.close_calls = 0

    def respond(self, messages):
        self.started.set()
        assert self.released.wait(5)
        return "Stopped"

    def close(self):
        self.close_calls += 1
        self.released.set()


def test_window_close_cancels_response_waits_for_worker_and_saves_preferences(tmp_path):
    app = QApplication.instance() or QApplication([])
    backend = BlockingBackend()
    inference = HybridInferenceEngine(local=backend, cloud=None)
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "TEST", inference=inference,
                        preferences_store=JsonStore(tmp_path / "preferences.json"))
    window.show()
    window.input.setPlainText("hello")
    window.submit()
    try:
        assert backend.started.wait(3)
        window.greeting_input.setText("Saved during close")
        save = Mock(wraps=window._save_greeting_message)
        window._save_greeting_message = save
        window.close()
        deadline = monotonic() + 5
        while window.thread is not None and monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert window.thread is None
        assert not window.isVisible()
        assert backend.close_calls == 1
        save.assert_called_once()
    finally:
        backend.released.set()
        service.shutdown()
        if window.thread is not None:
            window.thread.quit()
            window.thread.wait(5000)
        window.close()


def test_preference_failure_still_closes_inference(tmp_path):
    app = QApplication.instance() or QApplication([])
    backend = BlockingBackend()
    inference = HybridInferenceEngine(local=backend, cloud=None)
    window = MainWindow(None, "TEST", inference=inference)
    window._greeting_save_timer.start(1000)
    window._save_greeting_message = Mock(side_effect=OSError("unwritable settings"))
    window.close()
    assert backend.close_calls == 1


@pytest.mark.parametrize("failure", ["window", "loop", None])
def test_entry_point_always_closes_model_even_when_service_cleanup_fails(monkeypatch, failure):
    import app.main as entry
    inference = SimpleNamespace(close=Mock())
    service = SimpleNamespace(shutdown=Mock(side_effect=RuntimeError("cleanup failed")))
    fake_app = SimpleNamespace(aboutToQuit=SimpleNamespace(connect=Mock()), exec=Mock(return_value=0))
    window_factory = Mock(return_value=SimpleNamespace(show=Mock()))
    if failure == "window":
        window_factory.side_effect = RuntimeError("window failed")
    if failure == "loop":
        fake_app.exec.side_effect = RuntimeError("loop failed")
    monkeypatch.setattr("PySide6.QtWidgets.QApplication", lambda *a: fake_app)
    monkeypatch.setattr("app.ui.main_window.MainWindow", window_factory)
    monkeypatch.setattr(entry, "configure_logging", Mock())
    monkeypatch.setattr(entry, "PATHS", SimpleNamespace(ensure_directories=Mock(), state=__import__("pathlib").Path("state")))
    monkeypatch.setattr(entry, "load_agent_feature_config", lambda: SimpleNamespace(full_local_read_enabled=False))
    monkeypatch.setattr(entry, "build_application", lambda **k: (service, {"hostname": "TEST"}, None, inference))
    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            entry.main()
    else:
        assert entry.main() == 0
    inference.close.assert_called_once()
    fake_app.aboutToQuit.connect.call_args.args[0]()
    assert inference.close.call_count == 2
