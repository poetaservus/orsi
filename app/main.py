from __future__ import annotations

import logging
import socket
import sys
from pathlib import Path

# Support both `python -m app.main` from the project root and
# `python main.py` while the current directory is the app folder.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.agent_bootstrap import build_filesystem_stat_runtime
from app.agent_config import load_agent_feature_config
from app.conversation import ConversationService, ConversationStore
from app.inference import (
    HybridInferenceEngine,
    InferenceUnavailable,
    LazyInferenceEngine,
    LlamaCppInferenceEngine,
    OpenAICompatibleInferenceEngine,
    load_cloud_config,
)
from app.inference.model_config import detect_nvidia_memory_mib, load_model_config
from app.paths import PATHS


log = logging.getLogger(__name__)


def build_application():
    """Build chat plus the optional gated file-metadata runtime."""
    local_engine = None
    local_error = None
    try:
        model_config = load_model_config()
        if not model_config.resolved_model_path.is_file():
            raise InferenceUnavailable(
                f"No local GGUF model found at {model_config.resolved_model_path}. Update config/model.json."
            )
        gpu_memory = detect_nvidia_memory_mib()
        context_hint = model_config.select_context(
            native_context=model_config.maximum_context_length,
            gpu_offload_available=gpu_memory is not None,
            gpu_memory_mib=gpu_memory,
            model_size_bytes=model_config.resolved_model_path.stat().st_size,
        )
        local_engine = LazyInferenceEngine(
            lambda: LlamaCppInferenceEngine(model_config),
            context_length=context_hint.length,
            max_response_tokens=model_config.max_tokens,
        )
    except Exception as exc:
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
        conversation_state = PATHS.state / "conversation_v1"
        # Every application launch is a new private session. Overwrite the
        # single active state file so a previous window can never feed hidden
        # context into the newly opened one.
        store = ConversationStore(
            conversation_state / "conversation.json",
            start_fresh=True,
        )
        agent_runtime = None
        agent_error = None
        try:
            agent_config = load_agent_feature_config()
            if agent_config.filesystem_stat_enabled:
                agent_runtime = build_filesystem_stat_runtime(
                    inference,
                    config=agent_config,
                    portable_root=PATHS.root,
                    state_directory=PATHS.state,
                )
        except Exception:
            log.exception("The gated filesystem metadata agent could not start.")
            agent_error = (
                "Agent mode could not start safely. Chat-only mode remains available."
            )
        service = ConversationService(
            inference,
            store,
            agent_runtime=agent_runtime,
            portable_root=PATHS.root if agent_runtime is not None else None,
            allowed_read_roots=(PATHS.root,) if agent_runtime is not None else (),
            agent_error=agent_error,
        )

    host = {"hostname": socket.gethostname() or "Windows PC"}
    return service, host, startup_error, inference


def main() -> int:
    logging.basicConfig(
        filename=PATHS.state / "orsi.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    service, host, error, inference = build_application()
    window = MainWindow(service, host["hostname"], error, inference)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
