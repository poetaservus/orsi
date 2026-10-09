from __future__ import annotations

import logging
from hashlib import sha256
import socket
from pathlib import Path

from app.agent.bootstrap import build_agent_runtime
from app.conversation import ConversationService, ConversationStore
from app.conversation.store import TurnHistoryError
from app.inference import (
    HybridInferenceEngine,
    InferenceUnavailable,
    LazyInferenceEngine,
    LlamaCppInferenceEngine,
    LlamaServerInferenceEngine,
    OpenAICompatibleInferenceEngine,
    OpenAIResponsesInferenceEngine,
    load_cloud_config,
)
from app.security.host_access import (
    HostAccessPolicy,
)
from app.settings.agent import AgentFeatureConfig, load_agent_feature_config
from app.settings.model import detect_nvidia_memory_mib, load_model_config
from app.settings.local_models import LocalModelCatalog
from app.settings.paths import PATHS
from app.settings.openai_cloud import OpenAICloudConfig
from app.infrastructure.baseline import BaselineRecorder
from app.runtime.skills import SkillRegistry
from app.state.storage import JsonStore


log = logging.getLogger(__name__)


def build_application(
    *,
    agent_config_override: AgentFeatureConfig | None = None,
    full_local_read_acknowledged: bool = False,
    skill_registry_override: SkillRegistry | None = None,
    profile_session=None,
    session_credentials=False,
):
    """Build inference, private conversation state, skills and the optional agent.

    Default skill discovery is global-only. An explicit registry override can
    supply a chosen project scope; the application's checkout is not inferred.
    """
    state = PATHS.state
    credentials = None
    if session_credentials:
        from app.vault.credentials import SessionCredentialProvider
        credentials = SessionCredentialProvider()
    protected_roots = ()
    if profile_session is not None:
        from app.vault.session import ProfileSession
        from app.vault.credentials import CredentialProvider, SessionCredentialProvider
        from app.vault.logging import configure_profile_logging
        if not isinstance(profile_session, ProfileSession):
            raise TypeError("Select an unlocked personal profile session.")
        profile_session.require_active()
        configure_profile_logging(profile_session)
        state = profile_session.storage_path("state")
        credentials = (CredentialProvider(profile_session) if profile_session.encrypted
                       else SessionCredentialProvider(profile_session))
        protected_roots = (*profile_session.protected_roots, PATHS.state)
        if skill_registry_override is not None:
            from app.vault.skills import VaultSkillRegistry
            if profile_session.encrypted and (not isinstance(skill_registry_override, VaultSkillRegistry) or skill_registry_override.session is not profile_session):
                raise TypeError("Personal skills must belong to the selected profile.")
    if skill_registry_override is not None and not isinstance(skill_registry_override, SkillRegistry):
        raise TypeError("Application skills must use a SkillRegistry.")
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
    cloud_engine = None
    cloud_config = None
    cloud_error = None
    try:
        cloud_config = load_cloud_config()
        cloud_engine = (
            OpenAIResponsesInferenceEngine(
                cloud_config,
                **({"api_key": ""} if credentials is not None else {}),
                selection_path=state / "cloud_model_selection_v1.json",
                rate_limits_path=state / "cloud_rate_limits_v1.json",
            )
            if isinstance(cloud_config, OpenAICloudConfig)
            else OpenAICompatibleInferenceEngine(cloud_config,
                **({"api_key": ""} if credentials is not None else {}))
        )
    except Exception as exc:
        log.exception("Cloud inference could not be configured.")
        cloud_error = f"Cloud model configuration failed: {exc}"
    if (agent_config is not None and agent_config.filesystem_stat_enabled
            and not (PATHS.root / "runtime/llama-server/llama-server.exe").is_file()
            and not (isinstance(cloud_config, OpenAICloudConfig) and cloud_engine is not None)):
        # Preserve the established local/legacy chat-only fallback. Responses
        # tools need no local server and keep their separate capability runtime.
        agent_config = AgentFeatureConfig()
        agent_config_error = _AGENT_STARTUP_ERROR
    local_engine = None
    local_error = None
    model_catalog = None
    try:
        model_config = load_model_config()
        model_catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", model_config,
            **({"selection_path": state / "local_model_selection_v1.json"} if profile_session is not None else {}))
        if model_catalog.profiles is not None or any(
            item.id == model_catalog.current_id for item in model_catalog.models
        ):
            model_config = model_catalog.configuration(model_catalog.selected_id())
            model_catalog.current_config = model_config
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
        backend_factory = (LlamaServerInferenceEngine
                           if getattr(model_config, "vision", None) is not None or (agent_config is not None and agent_config.filesystem_stat_enabled)
                           else LlamaCppInferenceEngine)
        if backend_factory is LlamaServerInferenceEngine and not (
            PATHS.root / "runtime" / "llama-server" / "llama-server.exe"
        ).is_file():
            raise InferenceUnavailable("The pinned local tool-call server is missing.")
        initial_model_id = model_catalog.current_id
        def local_factory():
            # Check current free memory again when the lazy backend actually loads.
            config = (model_catalog.configuration(initial_model_id)
                      if any(item.id == initial_model_id for item in model_catalog.models)
                      else model_config)
            backend = backend_factory(config)
            model_catalog.current_config = config
            return backend
        local_engine = LazyInferenceEngine(
            local_factory,
            context_length=context_hint.length,
            max_response_tokens=model_config.max_tokens,
            supports_local_document_inputs=True,
            supports_local_image_inputs=getattr(model_config, "vision", None) is not None,
        )
    except Exception as exc:
        log.exception("Local inference could not be configured.")
        local_error = (
            str(exc)
            if isinstance(exc, InferenceUnavailable)
            else f"Local model configuration failed: {exc}"
        )

    inference = None
    startup_error = None
    try:
        inference = HybridInferenceEngine(
            local=local_engine,
            cloud=cloud_engine,
            default_mode=cloud_config.default_mode if cloud_config else "local",
            local_error=local_error,
            fallback_to_local=cloud_config.fallback_to_local if cloud_config else False,
            model_catalog=model_catalog if agent_config is not None
                and agent_config.filesystem_stat_enabled else None,
            local_factory=LlamaServerInferenceEngine
                if model_catalog is not None and agent_config is not None
                and agent_config.filesystem_stat_enabled else None,
            **({"credential_provider": credentials,
                "connection_id": "cloud-" + sha256(
                    (cloud_config.base_url + "\0" + cloud_config.api_key_environment).encode()).hexdigest()}
               if credentials is not None and cloud_config is not None else {}),
        )
        if credentials is not None and cloud_config is not None:
            setup = JsonStore(profile_session.storage_path("setup/profile_v1.json")).load({}) if profile_session is not None else {}
            if inference.connection_id not in credentials._policies:
                credentials.configure(inference.connection_id, setup.get("credential_policy", "ask_each_session"))
    except InferenceUnavailable:
        startup_error = " ".join(
            error for error in (local_error, cloud_error) if error
        ) or "No inference backend is available."

    service = None
    if inference is not None:
        try:
            if profile_session is not None and profile_session.encrypted:
                from app.vault.attachments import VaultAttachmentStore
                attachments = VaultAttachmentStore(state / "conversation_v1" / "attachments")
            else:
                attachments = None
            store = ConversationStore(state / "conversation_v1" / "conversation.json", attachment_store=attachments)
        except (TurnHistoryError, OSError):
            log.exception("Durable conversation history could not be opened safely.")
            return None, {"hostname": socket.gethostname() or "Windows PC"}, \
                "Conversation outcomes could not be restored safely. History was preserved; review it before continuing.", inference
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
                if protected_roots:
                    from dataclasses import replace
                    host_access_policy = replace(host_access_policy, protected_roots=protected_roots)
                agent_runtime = build_agent_runtime(
                    inference,
                    config=agent_config,
                    portable_root=PATHS.root,
                    state_directory=PATHS.state,
                    host_access_policy=host_access_policy,
                    **({"journal_path": state / "capability_journal_v1.json"} if profile_session is not None else {}),
                )
        except Exception:
            log.exception("The capability agent could not start safely.")
            host_access_policy = None
            agent_error = _AGENT_STARTUP_ERROR
        try:
            if skill_registry_override is not None:
                skill_registry = skill_registry_override
            elif profile_session is not None and profile_session.encrypted:
                from app.vault.skills import VaultSkillRegistry
                skill_registry = VaultSkillRegistry(profile_session)
            elif profile_session is not None:
                skill_registry = SkillRegistry(global_root=profile_session._vault.root / "skills")
            else:
                skill_registry = SkillRegistry()
            skill_registry.discover()
            service = ConversationService(
                inference,
                store,
                skill_registry=skill_registry,
                automatic_skills_enabled=False,
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
            # Every launch starts empty; archive prior turns and their image references.
            service.new_session(preserve_history=True)
        except (TurnHistoryError, OSError):
            log.exception("Durable conversation outcomes could not be reconciled safely.")
            if agent_runtime is not None:
                agent_runtime.shutdown()
            return None, {"hostname": socket.gethostname() or "Windows PC"}, \
                "Conversation outcomes could not be restored safely. History was preserved; review it before continuing.", inference
        if callable(getattr(inference, "record_baseline", None)):
            effective_flags = agent_config if agent_runtime is not None else AgentFeatureConfig()
            inference.baseline_observer = BaselineRecorder(
                PATHS.root, state / "diagnostics" / "effective_baseline_v1.json",
                effective_flags, agent_available=agent_runtime is not None, local_catalog=model_catalog)
            inference.record_baseline()
        if profile_session is not None:
            service.profile_session = profile_session
            profile_session.register(stop=service.stop_for_profile,
                drain=service.drain_for_profile, clear=service.clear_for_profile)
            if not profile_session.encrypted:
                from app.runtime.skills.contracts import SkillDiscoveryReport
                profile_session.register(clear=store.forget_protected_state)
                profile_session.register(clear=lambda: setattr(skill_registry, "_report", SkillDiscoveryReport()))

    host = {"hostname": socket.gethostname() or "Windows PC"}
    return service, host, startup_error, inference


_AGENT_STARTUP_ERROR = (
    "Agent mode could not start safely. Chat-only mode remains available."
)
