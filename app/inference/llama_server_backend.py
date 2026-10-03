from __future__ import annotations

import json
from hashlib import sha256
import logging
import os
import secrets
import socket
import subprocess
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock, RLock
from time import monotonic, sleep
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.diagnostics import record_completion_diagnostics
from app.inference.completion import CompletionText, IncompleteResponseError
from app.inference.owned_process import OwnedProcess, ProcessOwnershipError, start_owned_process
from app.inference.startup_diagnostics import StartupDiagnostics
from app.settings.model import ModelConfig, detect_nvidia_memory_mib
from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelResponse,
    ModelResponseKind,
    model_capability_definitions,
    native_chat_messages,
    native_function_tools,
    normalize_native_chat_completion,
)
from app.settings.paths import PATHS


log = logging.getLogger(__name__)

_LOOPBACK_HOST = "127.0.0.1"
_PINNED_SERVER_BUILD = 9976
_PINNED_SERVER_COMMIT = "e3546c794"
_PINNED_SERVER_FINGERPRINT = (
    f"b{_PINNED_SERVER_BUILD}-{_PINNED_SERVER_COMMIT}"
)
_MAX_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_HEALTH_RESPONSE_BYTES = 16 * 1024


class LlamaServerInferenceEngine(InferenceEngine):
    """Local inference through llama.cpp's native OpenAI tool-call parser."""

    def __init__(
        self,
        config: ModelConfig,
        *,
        server_executable: Path | None = None,
        startup_timeout_seconds: float = 90.0,
        shutdown_timeout_seconds: float = 5.0,
        request_timeout_seconds: float = 150.0,
    ):
        if not isinstance(config, ModelConfig):
            raise TypeError("llama-server inference requires a ModelConfig.")
        model_path = config.resolved_model_path
        if not model_path.is_file():
            raise InferenceUnavailable(
                f"No local GGUF model found at {model_path}. Update config/model.json."
            )
        executable = (
            server_executable
            if server_executable is not None
            else PATHS.root / "runtime" / "llama-server" / "llama-server.exe"
        )
        if not isinstance(executable, Path):
            raise TypeError("The llama-server executable must be a pathlib.Path.")
        executable = executable.resolve(strict=False)
        if not executable.is_file():
            raise InferenceUnavailable(
                "The pinned local tool-call server is missing. Rebuild O.R.S.I's "
                "portable runtime."
            )
        for label, value in (
            ("startup", startup_timeout_seconds),
            ("shutdown", shutdown_timeout_seconds),
            ("request", request_timeout_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < float(value) <= 3_600
            ):
                raise ValueError(
                    f"The llama-server {label} timeout must be a bounded positive number."
                )

        gpu_memory = detect_nvidia_memory_mib()
        selection = config.select_context(
            native_context=config.maximum_context_length,
            gpu_offload_available=gpu_memory is not None,
            gpu_memory_mib=gpu_memory,
            model_size_bytes=model_path.stat().st_size,
        )
        self.config = config
        self.context_length = selection.length
        self.max_response_tokens = config.max_tokens
        self.server_executable = executable
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self._process: OwnedProcess | None = None
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._closed = False
        self._lifecycle_lock = RLock()
        self._request_lock = Lock()
        self._request_active = Event()
        self._token_count_cache: dict[str, int] = {}

    @property
    def is_running(self) -> bool:
        with self._lifecycle_lock:
            return self._process is not None and self._process.poll() is None

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        """Tokenize content on an idle owned server, retaining wrapper allowances.

        This is still a request estimate: template/schema headroom is separate.
        Offline/failed counting keeps the existing byte heuristic and never loads
        a model solely to refresh the UI or estimate admission.
        """
        encoded_bytes = sum(
            len(str(message.get("content", "")).encode("utf-8", errors="replace"))
            for message in messages
        )
        text = "\n".join(str(message.get("content", "")) for message in messages)
        tokens = self._live_token_count(text)
        content_tokens = (encoded_bytes + 3) // 4 if tokens is None else tokens
        return max(1, content_tokens + 16 * len(messages) + 256)

    def count_capability_schema_tokens(self, definitions) -> int:
        values = tuple(definitions)
        if not values:
            return 0
        # Count the same projected function envelopes that inference submits;
        # runtime-only validation hints are not sent to the native provider.
        encoded = json.dumps(_llama_server_function_tools(values), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        tokens = self._live_token_count(encoded)
        return (tokens if tokens is not None else (len(encoded.encode("utf-8")) + 2) // 3) + 48 * len(values)

    def _live_token_count(self, content: str) -> int | None:
        if not hasattr(self, "_lifecycle_lock"):
            return None
        with self._lifecycle_lock:
            process, url, key = self._process, self._base_url, self._api_key
            if self._closed or process is None or process.poll() is not None or self._request_active.is_set():
                return None
            digest = sha256(content.encode("utf-8")).hexdigest()
            cached = self._token_count_cache.get(digest)
            if cached is not None:
                return cached
        payload = json.dumps({"content": content, "add_special": False,
                              "parse_special": False, "with_pieces": False}, ensure_ascii=False).encode("utf-8")
        if len(payload) > 1024 * 1024:
            return None
        request = Request(url + "/tokenize", data=payload, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=0.5) as response:
                raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                return None
            value = json.loads(raw.decode("utf-8"))
            tokens = value.get("tokens") if isinstance(value, dict) else None
            if (not isinstance(tokens, list) or (content and not tokens)
                    or any(type(token) is not int or token < 0 for token in tokens)):
                return None
            count = len(tokens)
            with self._lifecycle_lock:
                if self._process is process and not self._closed:
                    if len(self._token_count_cache) >= 128:
                        self._token_count_cache.clear()
                    self._token_count_cache[digest] = count
            return count
        except (OSError, URLError, ValueError, UnicodeError, RecursionError):
            return None

    def respond(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            raise InferenceUnavailable("Local inference received an empty conversation.")
        completion = self._request_completion(
            {
                "model": "local",
                "messages": deepcopy(messages),
                **self.config.sampling_parameters(),
                "max_tokens": self.config.max_tokens,
            }
        )
        record_completion_diagnostics(log, completion, provider="local-llama-server")
        response = normalize_native_chat_completion(completion, ())
        if response.kind != ModelResponseKind.ASSISTANT_TEXT:
            if response.completion.incomplete:
                raise IncompleteResponseError("The model response was cut off.", response.completion,
                                              response.partial_text)
            raise InferenceUnavailable(
                "The local model returned an invalid conversational response."
            )
        return CompletionText(response.assistant_text, response.completion)

    def respond_with_capabilities(
        self,
        messages: list[dict[str, str]],
        capabilities: Iterable[ModelCapabilityDefinition],
    ) -> ModelResponse:
        if not messages:
            raise InferenceUnavailable("Local inference received an empty conversation.")
        definitions = model_capability_definitions(
            capabilities,
            require_nonempty=True,
        )
        completion = self._request_completion(
            {
                "model": "local",
                "messages": native_chat_messages(messages, definitions),
                **self.config.sampling_parameters(),
                "max_tokens": self.config.max_tokens,
                "tools": _llama_server_function_tools(definitions),
                "tool_choice": "auto",
            }
        )
        diagnostics = record_completion_diagnostics(
            log,
            completion,
            provider="local-llama-server",
        )
        # Keep this shared normalizer as the only authority boundary. The
        # server decodes Qwen's native envelope but cannot relax O.R.S.I's
        # call IDs, names, argument, size, or mixed-response rules.
        response = normalize_native_chat_completion(completion, definitions)
        if response.protocol_failure is not None:
            log.warning(
                "Local model returned protocol failure %s; finish_reason=%s "
                "input_tokens=%s output_tokens=%s.",
                response.protocol_failure.code.value,
                diagnostics.finish_reason,
                diagnostics.input_tokens,
                diagnostics.output_tokens,
            )
        return response

    def cancel_current_request(self) -> None:
        """Bound cancellation by stopping the isolated inference server."""
        process = self._detach_process()
        if process is not None:
            self._stop_process(process)

    def wait_for_active_request(self, timeout: float) -> bool:
        """Testable lifecycle signal; it exposes no request data."""
        return self._request_active.wait(timeout)

    def prepare(self) -> None:
        """Load and health-check a model before committing a settings switch."""
        with self._request_lock:
            self._ensure_started()

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closed = True
            process = self._process
            self._process = None
            self._base_url = None
            self._api_key = None
            self._token_count_cache.clear()
        if process is not None:
            self._stop_process(process)

    def _request_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(
                body,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("Local inference requests require valid JSON data.") from exc

        with self._request_lock:
            base_url, api_key, process = self._ensure_started()
            self._request_active.set()
            try:
                request = Request(
                    f"{base_url}/v1/chat/completions",
                    data=encoded,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=self.request_timeout_seconds) as response:
                        raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
                except HTTPError as exc:
                    exc.read(4_096)
                    raise InferenceUnavailable(
                        "The local tool-call server rejected the model request."
                    ) from exc
                except (URLError, TimeoutError, OSError) as exc:
                    if process.poll() is not None:
                        self._clear_process(process)
                        self._stop_process(process)
                    raise InferenceUnavailable(
                        "The local tool-call server became unavailable."
                    ) from exc
            finally:
                self._request_active.clear()
            if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                raise InferenceUnavailable(
                    "The local tool-call server response exceeded its size limit."
                )
            try:
                completion = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("non-finite JSON number")
                    ),
                )
            except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError) as exc:
                raise InferenceUnavailable(
                    "The local tool-call server returned unreadable JSON."
                ) from exc
            if not isinstance(completion, dict):
                raise InferenceUnavailable(
                    "The local tool-call server returned an invalid response."
                )
            if completion.get("system_fingerprint") != _PINNED_SERVER_FINGERPRINT:
                raise InferenceUnavailable(
                    "The local tool-call server build did not match O.R.S.I's pinned runtime."
                )
            return completion

    def _ensure_started(self) -> tuple[str, str, OwnedProcess]:
        with self._lifecycle_lock:
            if self._closed:
                raise InferenceUnavailable("The local tool-call server is closed.")
            if self._process is not None and self._process.poll() is None:
                return self._base_url, self._api_key, self._process
            if self._process is not None:
                self._stop_process(self._process)
            self._process = None
            self._base_url = None
            self._api_key = None

            port = _free_loopback_port()
            api_key = secrets.token_urlsafe(32)
            base_url = f"http://{_LOOPBACK_HOST}:{port}"
            command = [
                str(self.server_executable),
                "--model",
                str(self.config.resolved_model_path),
                "--host",
                _LOOPBACK_HOST,
                "--port",
                str(port),
                "--ctx-size",
                str(self.context_length),
                "--n-gpu-layers",
                str(self.config.gpu_layers),
                "--jinja",
                "--flash-attn",
                "on",
                "--parallel",
                "1",
                "--cache-type-k",
                self.config.cache_type,
                "--cache-type-v",
                self.config.cache_type,
                "--no-webui",
                "--api-key",
                api_key,
                "--log-verbosity",
                "1",
                "--log-colors",
                "off",
            ]
            try:
                process = _launch_owned_server(
                    command,
                    cwd=self.server_executable.parent,
                    env=_server_environment(self.server_executable.parent),
                )
            except ProcessOwnershipError as exc:
                raise InferenceUnavailable(
                    "The local server could not establish safe process ownership."
                ) from exc
            except OSError as exc:
                raise InferenceUnavailable(
                    "The pinned local tool-call server could not start."
                ) from exc
            self._process = process
            self._base_url = base_url
            self._api_key = api_key

        try:
            self._wait_until_healthy(process, base_url, api_key)
            with self._lifecycle_lock:
                if self._closed or self._process is not process:
                    raise InferenceUnavailable("Local server startup was cancelled.")
            diagnostics = getattr(process, "startup_diagnostics", None)
            if diagnostics is not None:
                diagnostics.finish()
        except Exception:
            self._clear_process(process)
            self._stop_process(process)
            raise
        return base_url, api_key, process

    def _wait_until_healthy(
        self,
        process: OwnedProcess,
        base_url: str,
        api_key: str,
    ) -> None:
        deadline = monotonic() + self.startup_timeout_seconds
        request = Request(
            f"{base_url}/health",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        while monotonic() < deadline:
            with self._lifecycle_lock:
                if self._closed or self._process is not process:
                    raise InferenceUnavailable("Local server startup was cancelled.")
            exit_code = process.poll()
            if exit_code is not None:
                diagnostics = getattr(process, "startup_diagnostics", None)
                category = (diagnostics.failure_category(exit_code) if diagnostics is not None
                            else "unclassified native startup failure")
                error = ("The local tool-call server exited during startup "
                         f"(exit {exit_code}, 0x{exit_code & 0xFFFFFFFF:08X}): {category}.")
                log.warning("%s", error)
                raise InferenceUnavailable(error)
            try:
                with urlopen(request, timeout=0.5) as response:
                    raw = response.read(_MAX_HEALTH_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_HEALTH_RESPONSE_BYTES:
                    raise InferenceUnavailable(
                        "The local tool-call server health response was invalid."
                    )
                health = json.loads(raw.decode("utf-8"))
                if isinstance(health, dict) and health.get("status") == "ok":
                    return
            except HTTPError as exc:
                if exc.code not in {503}:
                    raise InferenceUnavailable(
                        "The local tool-call server health check was rejected."
                    ) from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeError):
                pass
            sleep(0.05)
        raise InferenceUnavailable(
            "The local tool-call server exceeded its startup deadline."
        )

    def _detach_process(self) -> OwnedProcess | None:
        with self._lifecycle_lock:
            process = self._process
            self._process = None
            self._base_url = None
            self._api_key = None
            return process

    def _clear_process(self, process: OwnedProcess) -> None:
        with self._lifecycle_lock:
            if self._process is process:
                self._process = None
                self._base_url = None
                self._api_key = None

    def _stop_process(self, process: OwnedProcess) -> None:
        try:
            self._terminate_process(process)
        finally:
            try:
                close = getattr(process, "close", None)
                if callable(close):
                    close()
            finally:
                diagnostics = getattr(process, "startup_diagnostics", None)
                if diagnostics is not None:
                    diagnostics.finish(wait=True)

    def _terminate_process(self, process: OwnedProcess) -> None:
        if process.poll() is not None:
            return
        deadline = monotonic() + self.shutdown_timeout_seconds
        try:
            process.terminate()
            process.wait(timeout=max(0.01, deadline - monotonic()))
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.kill()
            process.wait(timeout=max(0.01, deadline - monotonic()))
        except (OSError, subprocess.TimeoutExpired):
            log.warning("The local tool-call server did not stop within its deadline.")


def _launch_owned_server(command, *, cwd, env):
    read_fd, write_fd = os.pipe()
    diagnostics = None
    succeeded = False
    try:
        diagnostics = StartupDiagnostics(read_fd)
        process = start_owned_process(command, cwd=cwd, env=env, stderr=write_fd)
        process.startup_diagnostics = diagnostics
        succeeded = True
        return process
    finally:
        os.close(write_fd)
        if not succeeded and diagnostics is not None:
            diagnostics.finish(wait=True)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((_LOOPBACK_HOST, 0))
        port = listener.getsockname()[1]
    if not 1 <= int(port) <= 65_535:
        raise InferenceUnavailable("A safe loopback port could not be allocated.")
    return int(port)


def _llama_server_function_tools(
    definitions: tuple[ModelCapabilityDefinition, ...],
) -> list[dict[str, Any]]:
    """Project strict schemas onto llama.cpp's bounded grammar subset.

    llama.cpp b9976 rejects validation-only annotations and schema defaults
    while building the native tool grammar. Runtime Pydantic validation
    remains authoritative, so removing those generation hints cannot authorize
    an invalid call or change O.R.S.I's applied defaults.
    """
    tools = native_function_tools(definitions)
    for tool in tools:
        parameters = tool["function"]["parameters"]
        tool["function"]["parameters"] = _server_schema_node(parameters)
    return tools


def _server_schema_node(value: Any, *, properties: bool = False) -> Any:
    if isinstance(value, list):
        return [_server_schema_node(item) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    projected: dict[str, Any] = {}
    for key, item in value.items():
        if not properties and key in {
            "title",
            "minLength",
            "maxLength",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "pattern",
            "default",
        }:
            continue
        if not properties and key not in {
            "type",
            "description",
            "properties",
            "required",
            "additionalProperties",
            "items",
            "enum",
            "const",
            "anyOf",
            "oneOf",
        }:
            raise ValueError(
                f"llama-server does not support JSON-schema keyword: {key}"
            )
        projected[key] = _server_schema_node(
            item,
            properties=not properties and key == "properties",
        )
    return projected


def _server_environment(server_directory: Path) -> dict[str, str]:
    environment = dict(os.environ)
    current_path = ""
    for key in tuple(environment):
        if key.upper().startswith(("LLAMA_ARG_LOG", "LLAMA_LOG")):
            environment.pop(key)
            continue
        if key.casefold() == "path":
            current_path = environment.pop(key)
    entries = [str(server_directory)]
    if os.name == "nt":
        cuda_directory = (
            PATHS.root
            / "runtime"
            / "python"
            / "Lib"
            / "site-packages"
            / "nvidia"
            / "cu13"
            / "bin"
            / "x86_64"
        )
        if cuda_directory.is_dir():
            entries.append(str(cuda_directory))
    if current_path:
        entries.append(current_path)
    environment["PATH"] = os.pathsep.join(entries)
    return environment


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value
