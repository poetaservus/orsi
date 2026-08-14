from __future__ import annotations

from pathlib import Path

from app.agent_config import AgentFeatureConfig
from app.agent_runtime import AgentRuntime
from app.capabilities.contracts import PermissionClass
from app.capabilities.crash_journal import (
    CapabilityCrashJournal,
    JournaledCapabilityExecutor,
)
from app.capabilities.executor import CapabilityExecutor
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.capabilities.permissions import (
    ApprovalManager,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
)
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.inference.engine import InferenceEngine


class AgentBootstrapError(RuntimeError):
    pass


def build_filesystem_stat_runtime(
    inference: InferenceEngine,
    *,
    config: AgentFeatureConfig,
    portable_root: Path,
    state_directory: Path,
) -> AgentRuntime | None:
    """Build the sole Phase 8 capability runtime when its explicit gate is on."""
    if not isinstance(config, AgentFeatureConfig):
        raise TypeError("Agent bootstrap requires an AgentFeatureConfig.")
    if not config.filesystem_stat_enabled:
        return None
    if not isinstance(inference, InferenceEngine):
        raise TypeError("Agent bootstrap requires an InferenceEngine.")
    if not isinstance(portable_root, Path) or not isinstance(state_directory, Path):
        raise TypeError("Agent bootstrap paths must be pathlib.Path values.")
    try:
        root = portable_root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AgentBootstrapError(
            "The portable root could not be resolved safely."
        ) from exc
    if not root.is_dir():
        raise AgentBootstrapError("The portable root is not an accessible directory.")

    capability = FilesystemStatCapability()
    registry = CapabilityRegistry(
        (
            CapabilityRegistration(
                capability,
                enabled=True,
                model_visible=True,
            ),
        )
    )
    permission_gate = PermissionGate(
        (
            PermissionRule(
                "phase8-portable-root-stat",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=root,
            ),
        )
    )
    journal = CapabilityCrashJournal(
        state_directory / "capability_journal_v1.json"
    )
    if journal.review_required:
        raise AgentBootstrapError(
            "A previous capability call has an unknown outcome that requires review."
        )
    journal.purge()
    executor = JournaledCapabilityExecutor(CapabilityExecutor(), journal)
    return AgentRuntime(
        model=inference,
        registry=registry,
        permission_gate=permission_gate,
        approval_manager=ApprovalManager(),
        executor=executor,
    )
