from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceUnavailable
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine


def backend(**kwargs):
    return SimpleNamespace(context_length=4096, max_response_tokens=512,
                           close=Mock(**kwargs), respond=Mock(return_value="ok"))


def test_closing_unloaded_lazy_backend_never_calls_factory():
    factory = Mock()
    engine = LazyInferenceEngine(factory, context_length=4096)
    engine.close()
    engine.close()
    engine.unload()
    engine.cancel_current_request()
    with pytest.raises(InferenceUnavailable, match="closed"):
        engine.respond([])
    factory.assert_not_called()


def test_unload_allows_reload_but_close_is_terminal():
    first, second = backend(), backend()
    factory = Mock(side_effect=[first, second])
    engine = LazyInferenceEngine(factory, context_length=4096)
    assert engine.respond([]) == "ok"
    engine.unload()
    first.close.assert_called_once()
    assert engine.respond([]) == "ok"
    engine.close()
    engine.close()
    second.close.assert_called_once()
    with pytest.raises(InferenceUnavailable, match="closed"):
        engine.count_message_tokens([])
    assert factory.call_count == 2


def test_close_during_initialization_releases_unpublished_backend():
    started, release = Event(), Event()
    instance = backend()

    def factory():
        started.set()
        assert release.wait(3)
        return instance

    engine = LazyInferenceEngine(factory, context_length=4096)
    with ThreadPoolExecutor(2) as pool:
        loading = pool.submit(engine.respond, [])
        assert started.wait(3)
        closing = pool.submit(engine.close)
        assert engine._closed.wait(3)
        release.set()
        closing.result(3)
        with pytest.raises(InferenceUnavailable, match="closed"):
            loading.result(3)
    assert not engine.is_loaded
    instance.respond.assert_not_called()
    instance.close.assert_called_once()


def test_hybrid_closes_every_backend_even_when_one_fails():
    local, cloud = backend(side_effect=RuntimeError("failure")), backend()
    engine = HybridInferenceEngine(local=local, cloud=cloud)
    engine.close()
    engine.close()
    engine.cancel_current_request()
    local.close.assert_called_once()
    cloud.close.assert_called_once()
    for operation in (lambda: engine.respond([]), lambda: engine.set_mode("cloud")):
        with pytest.raises(InferenceUnavailable, match="closed"):
            operation()


def test_model_mode_round_trip_invalidates_context_measurements():
    local, cloud = backend(), backend()
    engine = HybridInferenceEngine(local=local, cloud=cloud)
    assert engine.context_revision == 0
    engine.set_mode("local")
    assert engine.context_revision == 0
    engine.set_mode("cloud")
    assert engine.context_revision == 1
    engine.set_mode("local")
    assert engine.context_revision == 2
    engine.close()


@pytest.mark.parametrize("failure", ["cancel", "runtime", None])
def test_service_shutdown_releases_inference_even_on_cleanup_failure(tmp_path, failure):
    inference = backend()
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    service.cancel_current_task = Mock(side_effect=RuntimeError() if failure == "cancel" else None)
    service.agent_runtime = SimpleNamespace(shutdown=Mock(
        side_effect=RuntimeError() if failure == "runtime" else None))
    if failure:
        with pytest.raises(RuntimeError):
            service.shutdown()
    else:
        service.shutdown()
    service.shutdown()
    inference.close.assert_called_once()
    service.agent_runtime.shutdown.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        service.run("hello")
