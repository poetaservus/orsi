"""Opt-in acceptance against the shipped GGUF/runtime, with no host file edits."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("ORSI_RUN_SERVER_LIFECYCLE") != "1",
    reason="Opt-in real model lifecycle acceptance",
)


@pytest.mark.parametrize("shutdown_path", ["service", "window"])
def test_shipped_model_loads_and_shutdown_releases_actual_process(tmp_path, shutdown_path):
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
    from app.inference.llama_server_backend import LlamaServerInferenceEngine
    from app.inference.owned_process import _api
    from app.settings.model import load_model_config

    config = load_model_config()
    local = LazyInferenceEngine(lambda: LlamaServerInferenceEngine(config),
                                context_length=config.maximum_context_length)
    inference = HybridInferenceEngine(local=local, cloud=None)
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    handle = None
    started = monotonic()
    try:
        backend = local._get_engine()
        _, _, process = backend._ensure_started()
        api = _api()
        api.OpenProcess.argtypes, api.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        handle = api.OpenProcess(0x100000, False, process.pid)
        assert handle and api.WaitForSingleObject(handle, 0) == 258
        if shutdown_path == "service":
            assert backend.respond([{"role": "user", "content": "Reply with OK only."}]).strip()
            service.shutdown()
        else:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
            from app.ui.main_window import MainWindow
            app = QApplication.instance() or QApplication([])
            window = MainWindow(service, "LIFECYCLE TEST", inference=inference)
            window.show()
            window.close()
            app.processEvents()
        assert api.WaitForSingleObject(handle, 5000) == 0
        assert not backend.is_running
        assert not local.is_loaded
        print(f"Real model {shutdown_path} lifecycle passed in {monotonic() - started:.1f}s; PID {process.pid} exited.")
    finally:
        service.shutdown()
        inference.close()
        if handle:
            api.CloseHandle(handle)


def test_forced_owner_death_releases_loaded_model():
    from app.inference.owned_process import _api

    code = (
        "import time; from app.inference.llama_server_backend import LlamaServerInferenceEngine; "
        "from app.settings.model import load_model_config; "
        "engine=LlamaServerInferenceEngine(load_model_config()); "
        "process=engine._ensure_started()[2]; print(process.pid,flush=True); time.sleep(120)"
    )
    owner = subprocess.Popen([sys.executable, "-c", code],
                             cwd=Path(__file__).resolve().parents[1],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    handle = None
    api = _api()
    try:
        # The child's own startup deadline bounds this read.
        child_pid = int(owner.stdout.readline())
        api.OpenProcess.argtypes, api.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        handle = api.OpenProcess(0x100000, False, child_pid)
        assert handle and api.WaitForSingleObject(handle, 0) == 258
        owner.kill()
        owner.wait(5)
        assert api.WaitForSingleObject(handle, 5000) == 0
        print(f"Forced owner death released real model PID {child_pid}.")
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(5)
        owner.stdout.close()
        if handle:
            api.CloseHandle(handle)
