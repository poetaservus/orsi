"""Allowlisted, content-free effective baseline diagnostics."""
from datetime import datetime, timezone
import logging
from pathlib import Path
import subprocess
from threading import RLock

from app.settings.model import detect_nvidia_memory_mib
from app.state.storage import JsonStore


log = logging.getLogger(__name__)


def source_revision(root: Path) -> dict:
    options = {"cwd": root, "capture_output": True, "text": True, "timeout": 5,
               "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], **options)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], **options)
        value = commit.stdout.strip()
        if commit.returncode == 0 and dirty.returncode == 0 and len(value) == 40:
            entries = dirty.stdout.splitlines()
            return {"commit": value, "tracked_changes": any(not line.startswith("?? ") for line in entries),
                    "untracked_files": any(line.startswith("?? ") for line in entries)}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"commit": None, "tracked_changes": None, "untracked_files": None}


class BaselineRecorder:
    def __init__(self, root: Path, path: Path, effective_agent_config, *, agent_available: bool,
                 local_catalog=None):
        self.root = root
        self.path = path
        self.flags = effective_agent_config.model_dump(exclude={"runtime_limits"})
        self.runtime_limits = effective_agent_config.runtime_limits.model_dump()
        self.agent_available = agent_available
        self.local_catalog = local_catalog
        self._lock = RLock()
        self._store = JsonStore(path)

    def __call__(self, inference):
        """Diagnostic write failures must never invalidate a successful model load."""
        with self._lock:
            self._capture(inference)

    def _capture(self, inference):
        try:
            catalog = inference.model_catalog or self.local_catalog
            model = catalog.diagnostic() if catalog is not None else None
            memory = detect_nvidia_memory_mib()
            local_loaded = bool(getattr(inference.local, "is_loaded", False))
            cloud_catalog = getattr(inference, "cloud_model_catalog", None)
            cloud_profile = cloud_catalog.current_profile if cloud_catalog is not None else None
            self._store.save({
                "schema_version": 1,
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "revision": source_revision(self.root),
                "mode": inference.mode,
                "agent_available": self.agent_available,
                "effective_flags": self.flags,
                "agent_limits": self.runtime_limits,
                "local_model": model,
                "local_backend_loaded": local_loaded,
                "cloud_model": ({"id": cloud_profile.id,
                                 "context_length": cloud_profile.effective_context_length,
                                 "max_input_tokens": cloud_profile.max_input_tokens,
                                 "max_output_tokens": cloud_profile.max_output_tokens,
                                 "reasoning_effort": cloud_profile.reasoning_effort,
                                 "temperature": cloud_profile.temperature,
                                 "qualified": cloud_profile.qualified} if cloud_profile is not None else None),
                "active_limits": {"context_length": inference.context_length,
                                  "max_response_tokens": inference.max_response_tokens},
                "gpu_at_capture_mib": {"total": memory[0], "free": memory[1]} if memory else None,
            })
        except Exception:
            log.warning("Effective baseline snapshot could not be written.")
