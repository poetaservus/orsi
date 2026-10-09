from __future__ import annotations

import logging
from threading import Event, Lock, RLock
from typing import Callable, Iterable

from app.inference.cloud_errors import CloudInferenceError
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.attachments import AttachmentError, has_attachments
from app.inference.openai_replay import neutral_messages
from app.runtime.activity import report_activity
from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelResponse,
    model_capability_definitions,
)


log = logging.getLogger(__name__)


class LazyInferenceEngine(InferenceEngine):
    """Loads a heavyweight backend only when that mode is actually used."""

    def __init__(self, factory: Callable[[], InferenceEngine], *, context_length: int,
                 max_response_tokens: int = 512, supports_local_document_inputs: bool | None = None,
                 supports_local_image_inputs: bool = False):
        self._factory = factory
        self._engine = None
        self._initialization_error = None
        self._lock = Lock()
        self._closed = Event()
        self.context_length = int(context_length)
        self.max_response_tokens = int(max_response_tokens)
        self._local_document_hint = supports_local_document_inputs
        self._local_image_hint = supports_local_image_inputs

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._engine is not None

    def respond(self, messages: list[dict[str, str]]) -> str:
        return self._get_engine().respond(messages)

    @property
    def supports_attachment_inputs(self):
        return getattr(self._get_engine(), "supports_attachment_inputs", False) is True

    @property
    def supports_local_document_inputs(self):
        if self._local_document_hint is not None:
            return self._local_document_hint
        return getattr(self._get_engine(), "supports_local_document_inputs", False) is True

    def respond_with_attachments(self, messages, *, attachment_store):
        if not self.supports_attachment_inputs:
            raise AttachmentError("Image and file input is not enabled for this model yet.")
        return self._get_engine().respond_with_attachments(messages, attachment_store=attachment_store)

    @property
    def supports_local_image_inputs(self):
        return (getattr(self._engine, "supports_local_image_inputs", False) is True
                if self._engine is not None else self._local_image_hint)

    def prepare_image_inputs(self):
        return self._get_engine().prepare_image_inputs()

    def count_image_message_tokens(self, messages):
        return self._get_engine().count_image_message_tokens(messages)

    def count_attachment_message_tokens(self, messages, **kwargs):
        return self._get_engine().count_attachment_message_tokens(messages, **kwargs)

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
                report_activity(getattr(self, "_activity_observer", None), "Loading local model…")
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
                report_activity(getattr(self, "_activity_observer", None), "Thinking…")
                return self._engine
            except Exception as exc:
                error = exc if isinstance(exc, InferenceUnavailable) else InferenceUnavailable(str(exc))
                self._initialization_error = error
                raise error

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        engine = self._get_engine()
        counter = getattr(engine, "count_message_tokens", None)
        return counter(messages) if callable(counter) else super().count_message_tokens(messages)

    def count_capability_schema_tokens(self, definitions) -> int:
        from app.conversation.context import capability_schema_reserve
        return capability_schema_reserve(definitions, inference=self._get_engine())


class HybridInferenceEngine(InferenceEngine):
    """Selects the local or cloud conversational model."""

    def __init__(self, *, local: InferenceEngine | None,
                 cloud: InferenceEngine | None,
                 default_mode: str = "local", local_error: str | None = None,
                 fallback_to_local: bool = True, model_catalog=None, local_factory=None,
                 credential_provider=None, connection_id="cloud-chat"):
        self.local = local
        self.cloud = cloud
        self.credential_provider = credential_provider
        self.connection_id = connection_id
        if credential_provider is not None and cloud is not None:
            credential_provider.bind(connection_id, cloud)
        self.local_error = local_error
        self.fallback_to_local = fallback_to_local
        self._lock = RLock()
        self._closed = False
        self.context_revision = 0
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

    @property
    def supports_openai_replay(self) -> bool:
        with self._lock:
            return getattr(self._engine_for(self._mode), "supports_openai_replay", False) is True

    @property
    def supports_attachment_inputs(self):
        return getattr(self._engine_for(self.mode), "supports_attachment_inputs", False) is True

    @property
    def supports_native_attachment_tools(self):
        return getattr(self._engine_for(self.mode), "supports_native_attachment_tools", False) is True

    def set_attachment_store(self, store):
        setter = getattr(self.cloud, "set_attachment_store", None)
        if callable(setter):
            setter(store)

    @property
    def supports_image_generation(self):
        return self.mode == "cloud" and getattr(self.cloud, "supports_image_generation", False) is True

    def generate_images(self, messages):
        if not self.supports_image_generation:
            raise InferenceUnavailable("Switch to Cloud to generate images.")
        return self._engine_for("cloud").generate_images(messages)

    def admit_attachment_inputs(self, references, *, cancellation=None):
        admit = getattr(self._engine_for(self.mode), "admit_attachment_inputs", None)
        if callable(admit):
            admit(references, cancellation=cancellation)

    def prepare_attachment_context(self, messages, *, cancellation=None):
        prepare = getattr(self._engine_for(self.mode), "prepare_attachment_context", None)
        if callable(prepare):
            prepare(messages, cancellation=cancellation)

    def validate_attachment_selection(self, references):
        validate = getattr(self._engine_for(self.mode), "validate_attachment_selection", None)
        if callable(validate):
            validate(references)

    @property
    def supports_local_document_inputs(self):
        return self.mode == "local" and getattr(
            self._engine_for(self.mode), "supports_local_document_inputs", False) is True

    @property
    def supports_local_image_inputs(self):
        return self.mode == "local" and getattr(self.local, "supports_local_image_inputs", False) is True

    def prepare_image_inputs(self):
        if not self.supports_local_image_inputs:
            raise AttachmentError("The selected mode/model does not support local images.")
        self.local.prepare_image_inputs()
        self._refresh_limits(self.local)

    def count_image_message_tokens(self, messages):
        if not self.supports_local_image_inputs:
            raise AttachmentError("The selected mode/model cannot account for local images.")
        return self.local.count_image_message_tokens(messages)

    def respond_with_attachments(self, messages, *, attachment_store):
        engine = self._engine_for(self.mode)
        if getattr(engine, "supports_attachment_inputs", False) is not True:
            raise AttachmentError("Image and file input is not enabled for this model yet.")
        # The existing text fallback cannot preserve multimodal input. A failed
        # attachment request remains in the explicitly selected mode.
        result = engine.respond_with_attachments(messages, attachment_store=attachment_store)
        self._refresh_limits(engine)
        return result

    def count_attachment_message_tokens(self, messages, **kwargs):
        engine = self._engine_for(self.mode)
        count = engine.count_attachment_message_tokens(messages, **kwargs)
        self._refresh_limits(engine)
        return count

    @property
    def supports_openai_context(self):
        with self._lock:
            return getattr(self._engine_for(self._mode), "supports_openai_context", False) is True

    @property
    def context_identity(self):
        with self._lock:
            engine = self._engine_for(self._mode)
            return (self._mode, getattr(engine, "active_model", None), getattr(engine, "context_revision", 0))

    def count_context_message_tokens(self, messages):
        engine = self._engine_for(self.mode)
        if getattr(engine, "supports_openai_context", False) is True:
            return engine.count_context_message_tokens(messages)
        from app.conversation.context import count_message_tokens
        return count_message_tokens(engine, messages)

    @property
    def supports_text_streaming(self) -> bool:
        with self._lock:
            return getattr(self._engine_for(self._mode), "supports_text_streaming", False) is True

    def set_text_observer(self, observer=None):
        setter = getattr(self.cloud, "set_text_observer", None)
        if callable(setter):
            setter(observer)

    def set_activity_observer(self, observer=None):
        for engine in (self.local, self.cloud):
            setter = getattr(engine, "set_activity_observer", None)
            if callable(setter):
                setter(observer)

    def set_request_cancellation(self, token=None):
        setter = getattr(self.cloud, "set_request_cancellation", None)
        if callable(setter):
            setter(token)

    def set_mode(self, mode: str) -> None:
        normalized = str(mode).strip().casefold()
        if normalized not in self.available_modes:
            if normalized == "local" and self.local_error:
                raise InferenceUnavailable(self.local_error)
            raise InferenceUnavailable(f"The {normalized or 'selected'} inference mode is unavailable.")
        self._engine_for(normalized)
        if self.credential_provider is not None:
            if normalized == "cloud":
                self.prepare_cloud_credentials()
            else:
                self.credential_provider.end(self.connection_id)
        if normalized == "cloud":
            unload = getattr(self.local, "unload", None)
            if callable(unload):
                try:
                    unload()
                except Exception:
                    if self.credential_provider is not None and self.mode != "cloud":
                        self.credential_provider.end(self.connection_id)
                    raise
        with self._lock:
            if normalized != self._mode:
                self.context_revision += 1
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
        if self.credential_provider is not None:
            self.credential_provider.begin(self.connection_id)
            self.credential_provider.supply(self.connection_id, api_key)
        else:
            self.cloud.set_api_key(api_key)

    def prepare_cloud_credentials(self):
        if self.credential_provider is not None:
            return self.credential_provider.begin(self.connection_id)
        return self.cloud_has_api_key

    @property
    def cloud_model_catalog(self):
        return getattr(self.cloud, "catalog", None)

    def select_cloud_model(self, model_id: str) -> None:
        with self._lock:
            if self._closed:
                raise InferenceUnavailable("Inference is closed.")
            if self._mode != "cloud":
                raise InferenceUnavailable("Switch to Cloud before choosing a cloud model.")
            if self.cloud_model_catalog is None:
                raise InferenceUnavailable("Cloud model selection is unavailable.")
            previous = self.cloud.active_model
            self.cloud.select_model(model_id)
            if previous != self.cloud.active_model:
                self.context_revision += 1
            self.context_length = self.cloud.context_length
            self.max_response_tokens = self.cloud.max_response_tokens
        self.record_baseline()

    def consume_notice(self) -> str | None:
        with self._lock:
            notice, self._notice = self._notice, None
        return notice

    def cancel_current_request(self) -> None:
        with self._lock:
            if self._closed:
                return
            engine = self.local if self._mode == "local" else self.cloud
        cancel = getattr(engine, "cancel_current_request", None)
        if callable(cancel):
            cancel()

    def close(self) -> None:
        credential_failure = False
        with self._lock:
            if self._closed:
                return
            if self.credential_provider is not None:
                try:
                    self.credential_provider.end(self.connection_id)
                except Exception:
                    credential_failure = True
            self._closed = True
            engines = (self.local, self._pending_local, self.cloud)
        for engine in engines:
            close = getattr(engine, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    log.warning("Could not fully release an inference backend.")
        if credential_failure:
            raise RuntimeError("Connection credentials could not be fully released.") from None

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
                    context_length=config.context_length, max_response_tokens=config.max_tokens,
                    supports_local_document_inputs=True, supports_local_image_inputs=config.vision is not None)
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
                    self.context_revision += 1
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
            result = engine.respond(neutral_messages(messages))
            self._refresh_limits(engine)
            return result
        try:
            result = engine.respond(messages)
            self._refresh_limits(engine)
            return result
        except CloudInferenceError as exc:
            if not (
                self.fallback_to_local
                and not has_attachments(messages)
                and exc.allow_local_fallback
                and self.local is not None
            ):
                raise
            try:
                result = self._engine_for("local").respond(neutral_messages(messages))
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
            result = engine.respond_with_capabilities(neutral_messages(messages), definitions)
            self._refresh_limits(engine)
            return result
        try:
            result = engine.respond_with_capabilities(messages, definitions)
            self._refresh_limits(engine)
            return result
        except CloudInferenceError as exc:
            if not (
                self.fallback_to_local
                and not has_attachments(messages)
                and exc.allow_local_fallback
                and self.local is not None
            ):
                raise
            try:
                result = self._engine_for("local").respond_with_capabilities(
                    neutral_messages(messages),
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

    def count_capability_schema_tokens(self, definitions) -> int:
        from app.conversation.context import capability_schema_reserve
        engine = self._engine_for(self.mode)
        count = capability_schema_reserve(definitions, inference=engine)
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
        if self.credential_provider is not None:
            self.credential_provider.end(self.connection_id)
        with self._lock:
            self.context_revision += 1
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
            if self.credential_provider is not None:
                self.credential_provider.session.require_active()
            engine = self.local if mode == "local" else self.cloud
            if engine is None:
                raise InferenceUnavailable(f"The {mode} inference mode is unavailable.")
            return engine
