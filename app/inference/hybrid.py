from __future__ import annotations

import logging
from threading import Event, Lock, RLock
from typing import Callable, Iterable

from app.inference.cloud_backend import CloudInferenceError, OpenAICompatibleInferenceEngine
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelResponse,
    model_capability_definitions,
)


log = logging.getLogger(__name__)


class LazyInferenceEngine(InferenceEngine):
    """Loads a heavyweight backend only when that mode is actually used."""

    def __init__(self, factory: Callable[[], InferenceEngine], *, context_length: int,
                 max_response_tokens: int = 512):
        self._factory = factory
        self._engine = None
        self._initialization_error = None
        self._lock = Lock()
        self._closed = Event()
        self.context_length = int(context_length)
        self.max_response_tokens = int(max_response_tokens)

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._engine is not None

    def respond(self, messages: list[dict[str, str]]) -> str:
        return self._get_engine().respond(messages)

    def respond_with_capabilities(
        self,
        messages: list[dict[str, str]],
        capabilities: Iterable[ModelCapabilityDefinition],
    ) -> ModelResponse:
        definitions = model_capability_definitions(
            capabilities,
            require_nonempty=True,
        )
        return self._get_engine().respond_with_capabilities(messages, definitions)

    def unload(self) -> None:
        with self._lock:
            engine, self._engine = self._engine, None
        if engine is None:
            return
        close = getattr(engine, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                log.warning("Could not fully release the local inference backend: %s", exc)

    def close(self) -> None:
        # Set before taking the initialization lock: an in-flight factory must
        # release its result instead of publishing it after shutdown begins.
        self._closed.set()
        self.unload()

    def cancel_current_request(self) -> None:
        with self._lock:
            engine = self._engine
        cancel = getattr(engine, "cancel_current_request", None)
        if callable(cancel):
            cancel()

    def _get_engine(self) -> InferenceEngine:
        with self._lock:
            if self._closed.is_set():
                raise InferenceUnavailable("The local inference backend is closed.")
            if self._engine is not None:
                return self._engine
            if self._initialization_error is not None:
                raise InferenceUnavailable(str(self._initialization_error)) from self._initialization_error
            try:
                engine = self._factory()
                if self._closed.is_set():
                    close = getattr(engine, "close", None)
                    if callable(close):
                        close()
                    raise InferenceUnavailable("The local inference backend is closed.")
                self._engine = engine
                self.context_length = int(getattr(self._engine, "context_length", self.context_length))
                self.max_response_tokens = int(
                    getattr(self._engine, "max_response_tokens", self.max_response_tokens)
                )
                return self._engine
            except Exception as exc:
                error = exc if isinstance(exc, InferenceUnavailable) else InferenceUnavailable(str(exc))
                self._initialization_error = error
                raise error

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        engine = self._get_engine()
        counter = getattr(engine, "count_message_tokens", None)
        return counter(messages) if callable(counter) else super().count_message_tokens(messages)


class HybridInferenceEngine(InferenceEngine):
    """Selects the local or cloud conversational model."""

    def __init__(self, *, local: InferenceEngine | None,
                 cloud: OpenAICompatibleInferenceEngine | None,
                 default_mode: str = "local", local_error: str | None = None,
                 fallback_to_local: bool = True, model_catalog=None, local_factory=None):
        self.local = local
        self.cloud = cloud
        self.local_error = local_error
        self.fallback_to_local = fallback_to_local
        self._lock = RLock()
        self._closed = False
        self.model_catalog = model_catalog
        self._local_factory = local_factory
        self._switch_lock = Lock()
        self._pending_local = None
        self._notice = None
        self.baseline_observer = None
        modes = self.available_modes
        if not modes:
            raise InferenceUnavailable(local_error or "No inference backend is available.")
        self._mode = default_mode if default_mode in modes else modes[0]
        active = self._engine_for(self._mode)
        self.context_length = int(getattr(active, "context_length", 8192))
        self.max_response_tokens = int(getattr(active, "max_response_tokens", 512))

    @property
    def available_modes(self) -> tuple[str, ...]:
        modes = []
        if self.local is not None:
            modes.append("local")
        if self.cloud is not None:
            modes.append("cloud")
        return tuple(modes)

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> None:
        normalized = str(mode).strip().casefold()
        if normalized not in self.available_modes:
            if normalized == "local" and self.local_error:
                raise InferenceUnavailable(self.local_error)
            raise InferenceUnavailable(f"The {normalized or 'selected'} inference mode is unavailable.")
        self._engine_for(normalized)
        if normalized == "cloud":
            unload = getattr(self.local, "unload", None)
            if callable(unload):
                unload()
        with self._lock:
            self._mode = normalized
            self.context_length = int(getattr(self._engine_for(normalized), "context_length", 8192))
            self.max_response_tokens = int(
                getattr(self._engine_for(normalized), "max_response_tokens", 512)
            )
        self.record_baseline()

    def record_baseline(self):
        if self.baseline_observer is not None:
            try:
                self.baseline_observer(self)
            except Exception:
                log.warning("Effective baseline observer failed.")

    @property
    def cloud_has_api_key(self) -> bool:
        return self.cloud is not None and self.cloud.has_api_key

    @property
    def cloud_provider_name(self) -> str:
        return self.cloud.config.provider_name if self.cloud is not None else "Cloud"

    def set_cloud_api_key(self, api_key: str) -> None:
        if self.cloud is None:
            raise InferenceUnavailable("Cloud inference is unavailable.")
        self.cloud.set_api_key(api_key)

    def consume_notice(self) -> str | None:
        with self._lock:
            notice, self._notice = self._notice, None
        return notice

    def cancel_current_request(self) -> None:
        with self._lock:
            if self._closed:
                return
            engine = self._engine_for(self._mode)
        cancel = getattr(engine, "cancel_current_request", None)
        if callable(cancel):
            cancel()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            engines = (self.local, self._pending_local, self.cloud)
        for engine in engines:
            close = getattr(engine, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    log.warning("Could not fully release an inference backend.")

    def select_local_model(self, model_id: str) -> None:
        if self.model_catalog is None or self._local_factory is None:
            raise InferenceUnavailable("Local model selection is unavailable.")
        with self._switch_lock:
            with self._lock:
                if self._closed:
                    raise InferenceUnavailable("Inference is closed.")
                if self._mode != "local":
                    raise InferenceUnavailable("Switch to Local before choosing a local model.")
                if model_id == self.model_catalog.current_id:
                    return
                previous = self.local
            # Release VRAM before calculating the replacement's hardware profile.
            unload = getattr(previous, "unload", None)
            if not callable(unload):
                raise InferenceUnavailable("The current backend cannot switch models safely.")
            unload()
            candidate = None
            try:
                config = self.model_catalog.configuration(model_id)
                def load_selected():
                    current = self.model_catalog.configuration(model_id)
                    backend = self._local_factory(current)
                    with self._lock:
                        if self.local is candidate:
                            self.model_catalog.current_config = current
                    return backend
                candidate = LazyInferenceEngine(
                    load_selected,
                    context_length=config.context_length, max_response_tokens=config.max_tokens)
                with self._lock:
                    if self._closed:
                        raise InferenceUnavailable("Inference is closed.")
                    self._pending_local = candidate
                backend = candidate._get_engine()
                backend.prepare()
                with self._lock:
                    if self._closed:
                        raise InferenceUnavailable("Inference is closed.")
                    self.model_catalog.save(getattr(backend, "config", config))
                    self.local = candidate
                    self.context_length = candidate.context_length
                    self.max_response_tokens = candidate.max_response_tokens
                    self._pending_local = None
                previous.close()
                self.record_baseline()
            except Exception:
                if candidate is not None:
                    candidate.close()
                with self._lock:
                    self._pending_local = None
                raise

    def respond(self, messages: list[dict[str, str]]) -> str:
        mode = self.mode
        engine = self._engine_for(mode)
        if mode != "cloud":
            result = engine.respond(messages)
            self._refresh_limits(engine)
            return result
        try:
            result = engine.respond(messages)
            self._refresh_limits(engine)
            return result
        except CloudInferenceError as exc:
            if not (
                self.fallback_to_local
                and exc.allow_local_fallback
                and self.local is not None
            ):
                raise
            try:
                result = self._engine_for("local").respond(messages)
            except Exception as local_exc:
                raise CloudInferenceError(
                    f"{exc} Local fallback was also unavailable: {local_exc}"
                ) from local_exc
            self._activate_local_fallback()
            return result

    def respond_with_capabilities(
        self,
        messages: list[dict[str, str]],
        capabilities: Iterable[ModelCapabilityDefinition],
    ) -> ModelResponse:
        definitions = model_capability_definitions(
            capabilities,
            require_nonempty=True,
        )
        mode = self.mode
        engine = self._engine_for(mode)
        if mode != "cloud":
            result = engine.respond_with_capabilities(messages, definitions)
            self._refresh_limits(engine)
            return result
        try:
            result = engine.respond_with_capabilities(messages, definitions)
            self._refresh_limits(engine)
            return result
        except CloudInferenceError as exc:
            if not (
                self.fallback_to_local
                and exc.allow_local_fallback
                and self.local is not None
            ):
                raise
            try:
                result = self._engine_for("local").respond_with_capabilities(
                    messages,
                    definitions,
                )
            except Exception as local_exc:
                raise CloudInferenceError(
                    f"{exc} Local fallback was also unavailable: {local_exc}"
                ) from local_exc
            self._activate_local_fallback()
            return result

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        engine = self._engine_for(self.mode)
        counter = getattr(engine, "count_message_tokens", None)
        count = counter(messages) if callable(counter) else super().count_message_tokens(messages)
        self._refresh_limits(engine)
        return count

    def _refresh_limits(self, engine: InferenceEngine) -> None:
        with self._lock:
            self.context_length = int(
                getattr(engine, "context_length", self.context_length)
            )
            self.max_response_tokens = int(
                getattr(engine, "max_response_tokens", self.max_response_tokens)
            )
        self.record_baseline()

    def _activate_local_fallback(self) -> None:
        if self.local is None:
            raise InferenceUnavailable("Local fallback is unavailable.")
        with self._lock:
            self._mode = "local"
            self.context_length = int(getattr(self.local, "context_length", 8192))
            self.max_response_tokens = int(
                getattr(self.local, "max_response_tokens", 512)
            )
            self._notice = (
                "Cloud was unavailable, so O.R.S.I safely switched to the local model."
            )
        self.record_baseline()

    def _engine_for(self, mode: str) -> InferenceEngine:
        with self._lock:
            if self._closed:
                raise InferenceUnavailable("Inference is closed.")
            engine = self.local if mode == "local" else self.cloud
            if engine is None:
                raise InferenceUnavailable(f"The {mode} inference mode is unavailable.")
            return engine
