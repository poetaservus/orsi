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
from app.capabilities.host_access import HostAccessPolicy, HostReadScope
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
    host_access_policy: HostAccessPolicy | None = None,
) -> AgentRuntime | None:
    """Build the sole metadata capability under an explicit host-read policy."""
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

    policy = host_access_policy or HostAccessPolicy.portable_root(root)
    if not isinstance(policy, HostAccessPolicy):
        raise TypeError("Agent bootstrap requires a HostAccessPolicy.")
    if policy.application_root != root:
        raise AgentBootstrapError(
            "The host-access policy does not match the portable application root."
        )
    expects_full_local = config.full_local_read_enabled
    is_full_local = policy.read_scope == HostReadScope.FULL_LOCAL
    if expects_full_local != is_full_local:
        raise AgentBootstrapError(
            "Full local read configuration and acknowledged authority do not match."
        )
    try:
        permission_roots = policy.permission_roots()
    except (OSError, RuntimeError, ValueError) as exc:
        raise AgentBootstrapError(
            "The enabled host-read permission roots could not be resolved safely."
        ) from exc

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
    if policy.read_scope == HostReadScope.PORTABLE_ROOT:
        permission_rules = (
            PermissionRule(
                "phase8-portable-root-stat",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=root,
            ),
        )
    else:
        permission_rules = tuple(
            PermissionRule(
                f"phase9-local-{permission_root.drive[0].casefold()}-stat",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=permission_root,
            )
            for permission_root in permission_roots
        )
    permission_gate = PermissionGate(permission_rules)
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
