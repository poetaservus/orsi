from __future__ import annotations

import os
from pathlib import Path
from time import monotonic, sleep

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.agent.bootstrap import build_agent_runtime
from app.settings.agent import AgentFeatureConfig
from app.execution.audit import CallLifecycleState
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.settings.model import load_model_config
from app.ui.main_window import MainWindow


pytestmark = pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_UI_ACCEPTANCE") != "1",
    reason="Set ORSI_RUN_LIVE_UI_ACCEPTANCE=1 for the real UI workflow.",
)


def _wait_for_reply(app: QApplication, window: MainWindow, timeout: float = 20.0):
    deadline = monotonic() + timeout
    while window.thread is not None and monotonic() < deadline:
        app.processEvents()
        sleep(0.01)
    app.processEvents()
    assert window.thread is None


def _submit(app: QApplication, window: MainWindow, message: str):
    window.input.setPlainText(message)
    window.submit()
    _wait_for_reply(app, window)


def test_real_local_agent_ui_workflow(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    probe = portable_root / "phase8-ui-probe.txt"
    probe.write_bytes(b"U" * 137)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside private content", encoding="utf-8")
    state = tmp_path / "state"

    local = LlamaServerInferenceEngine(load_model_config())
    inference = HybridInferenceEngine(local=local, cloud=None)
    runtime = build_agent_runtime(
        inference,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        inference,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    window = MainWindow(service, "ignored-hostname", inference=inference)
    window.show()
    app.processEvents()
    try:
        assert "Local" in window.activity.text()
        assert "Portable-root read" in window.activity.text()
        assert "Metadata only" in window.activity.text()

        _submit(
            app,
            window,
            "Use filesystem.stat exactly once to inspect phase8-ui-probe.txt, "
            "then report its size in bytes.",
        )
        assert runtime.executor.journal.records[0].state == CallLifecycleState.COMPLETED
        assert "137" in window.chat._messages[-1]._content
        screenshot = tmp_path / "phase8-native-tool-ui.png"
        assert window.grab().save(str(screenshot))

        window.create_new_session()
        _submit(app, window, "Reply exactly with UI-chat-ok; do not use a tool.")
        assert runtime.executor.journal.records == ()

        window.create_new_session()
        _submit(
            app,
            window,
            "Use filesystem.stat exactly once to inspect missing-ui.txt.",
        )
        assert runtime.executor.journal.records[0].state == CallLifecycleState.FAILED

        window.create_new_session()
        _submit(
            app,
            window,
            "Pass this exact path string to filesystem.stat once and let the "
            "capability decide whether it is allowed: "
            r"..\outside.txt",
        )
        assert runtime.executor.journal.records[0].state == CallLifecycleState.DENIED

        window.create_new_session()
        window.input.setPlainText(
            "Write a detailed 1200-word essay for the UI cancellation test. "
            "Do not use a tool."
        )
        window.submit()
        assert local.wait_for_active_request(5.0)
        window.cancel_current_task()
        _wait_for_reply(app, window)
        assert window.chat._messages[-1]._content == "The response was stopped."
        assert service.store.messages()[-1]["role"] == "user"
    finally:
        if window.thread is not None:
            window.cancel_current_task()
            _wait_for_reply(app, window)
        window.close()
        app.processEvents()
