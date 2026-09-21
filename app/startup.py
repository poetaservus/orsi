from __future__ import annotations

import logging
import socket
from pathlib import Path

from app.agent.bootstrap import build_agent_runtime
from app.conversation import ConversationService, ConversationStore
from app.inference import (
    HybridInferenceEngine,
    InferenceUnavailable,
    LazyInferenceEngine,
    LlamaCppInferenceEngine,
    LlamaServerInferenceEngine,
    OpenAICompatibleInferenceEngine,
    load_cloud_config,
)
from app.security.host_access import (
    FULL_LOCAL_LIST_READ_WARNING,
    FULL_LOCAL_LIST_SEARCH_READ_WARNING,
    FULL_LOCAL_LIST_TEXT_SEARCH_READ_WARNING,
    FULL_LOCAL_LIST_TEXT_READ_WARNING,
    FULL_LOCAL_READ_WARNING,
    FULL_LOCAL_SEARCH_READ_WARNING,
    FULL_LOCAL_TEXT_SEARCH_READ_WARNING,
    FULL_LOCAL_TEXT_READ_WARNING,
    HostAccessPolicy,
)
from app.settings.agent import AgentFeatureConfig, load_agent_feature_config
from app.settings.model import detect_nvidia_memory_mib, load_model_config
from app.settings.paths import PATHS


log = logging.getLogger(__name__)


def build_application(
    *,
    agent_config_override: AgentFeatureConfig | None = None,
    full_local_read_acknowledged: bool = False,
):
    """Build inference, private conversation state, and the optional capability agent."""
    if not isinstance(full_local_read_acknowledged, bool):
        raise TypeError("Full local read acknowledgement must be a boolean.")
    if agent_config_override is not None and not isinstance(
        agent_config_override, AgentFeatureConfig
    ):
        raise TypeError("Agent configuration overrides must be AgentFeatureConfig values.")

    agent_config = agent_config_override
    agent_config_error = None
    if agent_config is None:
        try:
            agent_config = load_agent_feature_config()
        except (OSError, TypeError, ValueError):
            log.exception("The capability-agent configuration is invalid.")
            agent_config_error = _AGENT_STARTUP_ERROR
    if (
        agent_config is not None
        and agent_config.full_local_read_enabled
        and not full_local_read_acknowledged
    ):
        agent_config = agent_config.model_copy(update={"full_local_read_enabled": False})
    if agent_config is not None and agent_config.filesystem_stat_enabled:
        server_executable = PATHS.root / "runtime" / "llama-server" / "llama-server.exe"
        if not server_executable.is_file():
            agent_config = AgentFeatureConfig()
            agent_config_error = _AGENT_STARTUP_ERROR

    local_engine = None
    local_error = None
    try:
        model_config = load_model_config()
        if not model_config.resolved_model_path.is_file():
            raise InferenceUnavailable(
                f"No local GGUF model found at {model_config.resolved_model_path}. "
                "Update config/model.json."
            )
        gpu_memory = detect_nvidia_memory_mib()
        context_hint = model_config.select_context(
            native_context=model_config.maximum_context_length,
            gpu_offload_available=gpu_memory is not None,
            gpu_memory_mib=gpu_memory,
            model_size_bytes=model_config.resolved_model_path.stat().st_size,
        )
        local_factory = (
            (lambda: LlamaServerInferenceEngine(model_config))
            if agent_config is not None and agent_config.filesystem_stat_enabled
            else (lambda: LlamaCppInferenceEngine(model_config))
        )
        local_engine = LazyInferenceEngine(
            local_factory,
            context_length=context_hint.length,
            max_response_tokens=model_config.max_tokens,
        )
    except Exception as exc:
        log.exception("Local inference could not be configured.")
        local_error = (
            str(exc)
            if isinstance(exc, InferenceUnavailable)
            else f"Local model configuration failed: {exc}"
        )

    cloud_engine = None
    cloud_config = None
    cloud_error = None
    try:
        cloud_config = load_cloud_config()
        cloud_engine = OpenAICompatibleInferenceEngine(cloud_config)
    except Exception as exc:
        log.exception("Cloud inference could not be configured.")
        cloud_error = f"Cloud model configuration failed: {exc}"

    inference = None
    startup_error = None
    try:
        inference = HybridInferenceEngine(
            local=local_engine,
            cloud=cloud_engine,
            default_mode=cloud_config.default_mode if cloud_config else "local",
            local_error=local_error,
            fallback_to_local=cloud_config.fallback_to_local if cloud_config else False,
        )
    except InferenceUnavailable:
        startup_error = " ".join(
            error for error in (local_error, cloud_error) if error
        ) or "No inference backend is available."

    service = None
    if inference is not None:
        store = ConversationStore(
            PATHS.state / "conversation_v1" / "conversation.json",
            start_fresh=True,
        )
        agent_runtime = None
        host_access_policy = None
        agent_error = agent_config_error
        try:
            if agent_config is not None and agent_config.filesystem_stat_enabled:
                host_access_policy = (
                    HostAccessPolicy.full_local(
                        application_root=PATHS.root,
                        user_home=Path.home(),
                        acknowledged=True,
                    )
                    if agent_config.full_local_read_enabled
                    else HostAccessPolicy.portable_root(PATHS.root)
                )
                agent_runtime = build_agent_runtime(
                    inference,
                    config=agent_config,
                    portable_root=PATHS.root,
                    state_directory=PATHS.state,
                    host_access_policy=host_access_policy,
                )
        except Exception:
            log.exception("The capability agent could not start safely.")
            host_access_policy = None
            agent_error = _AGENT_STARTUP_ERROR
        service = ConversationService(
            inference,
            store,
            agent_runtime=agent_runtime,
            portable_root=PATHS.root if agent_runtime is not None else None,
            allowed_read_roots=(
                host_access_policy.permission_roots()
                if host_access_policy is not None
                else ()
            ),
            host_access_policy=host_access_policy,
            agent_error=agent_error,
        )

    host = {"hostname": socket.gethostname() or "Windows PC"}
    return service, host, startup_error, inference


def request_full_local_read_acknowledgement(
    *,
    filesystem_list_enabled: bool = False,
    filesystem_read_text_enabled: bool = False,
    filesystem_search_enabled: bool = False,
) -> bool:
    """Ask once per launch before host-wide read authority can be constructed."""
    from PySide6.QtWidgets import QMessageBox

    for value, label in (
        (filesystem_list_enabled, "Filesystem listing"),
        (filesystem_read_text_enabled, "Filesystem text-read"),
        (filesystem_search_enabled, "Filesystem search"),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{label} acknowledgement state must be a boolean.")
    if filesystem_search_enabled and filesystem_read_text_enabled:
        warning = (
            FULL_LOCAL_LIST_TEXT_SEARCH_READ_WARNING
            if filesystem_list_enabled
            else FULL_LOCAL_TEXT_SEARCH_READ_WARNING
        )
    elif filesystem_search_enabled:
        warning = (
            FULL_LOCAL_LIST_SEARCH_READ_WARNING
            if filesystem_list_enabled
            else FULL_LOCAL_SEARCH_READ_WARNING
        )
    elif filesystem_read_text_enabled:
        warning = (
            FULL_LOCAL_LIST_TEXT_READ_WARNING
            if filesystem_list_enabled
            else FULL_LOCAL_TEXT_READ_WARNING
        )
    else:
        warning = (
            FULL_LOCAL_LIST_READ_WARNING
            if filesystem_list_enabled
            else FULL_LOCAL_READ_WARNING
        )
    answer = QMessageBox.question(
        None,
        "Enable Full local read access?",
        f"{warning}\n\nEnable this access for the current O.R.S.I session?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


_AGENT_STARTUP_ERROR = (
    "Agent mode could not start safely. Chat-only mode remains available."
)
