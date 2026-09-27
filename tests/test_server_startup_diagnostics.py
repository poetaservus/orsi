from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from app.inference.engine import InferenceUnavailable
from app.inference.llama_server_backend import (
    LlamaServerInferenceEngine, _launch_owned_server, _server_environment,
)
from app.inference.owned_process import ProcessOwnershipError
from app.inference.startup_diagnostics import StartupDiagnostics
from app.settings.model import ModelConfig


def test_noisy_native_output_is_drained_and_only_category_retained():
    code = (
        "import os; "
        "[os.write(2,b'private-key-and-prompt'*200) for _ in range(2000)]; "
        "os.write(2,b'CUDA error: out of memory private-api-key'); raise SystemExit(42)"
    )
    process = _launch_owned_server([sys.executable, "-c", code],
                                   cwd=Path.cwd(), env=os.environ.copy())
    try:
        assert process.wait(10) == 42
        diagnostics = process.startup_diagnostics
        assert diagnostics.failure_category(42) == "memory allocation failure"
        diagnostics.finish(wait=True)
        assert diagnostics._categories == {"memory allocation failure"}
        assert diagnostics._tail == b""
        assert not diagnostics._thread.is_alive()
    finally:
        process.close()


def test_capture_stops_after_health_but_output_keeps_draining():
    read_fd, write_fd = os.pipe()
    diagnostics = StartupDiagnostics(read_fd)
    diagnostics.finish()
    try:
        for _ in range(1000):
            os.write(write_fd, b"out of memory: private conversation" * 100)
    finally:
        os.close(write_fd)
    diagnostics.finish(wait=True)
    assert not diagnostics._categories
    assert not diagnostics._tail
    assert not diagnostics._thread.is_alive()


def test_inherited_environment_cannot_enable_raw_log_files(monkeypatch):
    monkeypatch.setenv("LLAMA_ARG_LOG_FILE", "private.log")
    monkeypatch.setenv("LLAMA_ARG_LOG_PROMPTS_DIR", "private-prompts")
    environment = _server_environment(Path.cwd())
    assert "LLAMA_ARG_LOG_FILE" not in environment
    assert "LLAMA_ARG_LOG_PROMPTS_DIR" not in environment


@pytest.fixture
def engine(tmp_path, monkeypatch):
    model, server = tmp_path / "model.gguf", tmp_path / "server.exe"
    model.touch()
    server.touch()
    monkeypatch.setattr("app.inference.llama_server_backend.detect_nvidia_memory_mib", lambda: None)
    instance = LlamaServerInferenceEngine(ModelConfig(model_path=str(model)),
                                         server_executable=server,
                                         startup_timeout_seconds=0.03)
    yield instance
    instance.close()


def fake_process(code=None):
    return SimpleNamespace(poll=Mock(return_value=code), terminate=Mock(), kill=Mock(),
                           wait=Mock(return_value=1), close=Mock())


def test_early_exit_reports_code_and_category_without_raw_output(engine, monkeypatch, caplog):
    process = fake_process(0xC000012D)
    read_fd, write_fd = os.pipe()
    process.startup_diagnostics = StartupDiagnostics(read_fd)
    os.write(write_fd, b"private API key and private prompt: out of memory")
    os.close(write_fd)
    monkeypatch.setattr("app.inference.llama_server_backend._launch_owned_server", lambda *a, **k: process)
    with pytest.raises(InferenceUnavailable, match="0xC000012D.*memory allocation failure") as error:
        engine._ensure_started()
    assert "private" not in str(error.value) + caplog.text
    assert engine._process is None
    process.close.assert_called_once()


def test_timeout_releases_child_and_retry_can_start(engine, monkeypatch):
    first, second = fake_process(), fake_process()
    launcher = Mock(side_effect=[first, second])
    monkeypatch.setattr("app.inference.llama_server_backend._launch_owned_server", launcher)
    monkeypatch.setattr("app.inference.llama_server_backend.urlopen", Mock(side_effect=URLError("unready")))
    with pytest.raises(InferenceUnavailable, match="startup deadline"):
        engine._ensure_started()
    first.terminate.assert_called_once()
    first.close.assert_called_once()
    monkeypatch.setattr(engine, "_wait_until_healthy", lambda *a: None)
    assert engine._ensure_started()[2] is second
    engine.close()
    second.close.assert_called_once()
    with pytest.raises(InferenceUnavailable, match="closed"):
        engine._ensure_started()
    assert launcher.call_count == 2


def test_close_during_health_check_cannot_publish_a_ready_server(engine, monkeypatch):
    process = fake_process()
    entered, release = Event(), Event()
    monkeypatch.setattr("app.inference.llama_server_backend._launch_owned_server", lambda *a, **k: process)

    def health(*args):
        entered.set()
        assert release.wait(3)

    monkeypatch.setattr(engine, "_wait_until_healthy", health)
    with ThreadPoolExecutor(1) as pool:
        startup = pool.submit(engine._ensure_started)
        assert entered.wait(3)
        engine.close()
        release.set()
        with pytest.raises(InferenceUnavailable, match="cancelled"):
            startup.result(3)
    assert engine._process is None
    assert process.close.called


@pytest.mark.parametrize("error,match", [
    (ProcessOwnershipError("guard failed"), "safe process ownership"),
    (OSError("launch failed"), "could not start"),
])
def test_launch_errors_are_distinguished_and_retryable(engine, monkeypatch, error, match):
    launcher = Mock(side_effect=error)
    monkeypatch.setattr("app.inference.llama_server_backend._launch_owned_server", launcher)
    with pytest.raises(InferenceUnavailable, match=match):
        engine._ensure_started()
    assert engine._process is None
    assert not engine._closed
