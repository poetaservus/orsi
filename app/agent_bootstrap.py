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
from app.capabilities.filesystem_copy import FilesystemCopyCapability
from app.capabilities.filesystem_list import FilesystemListCapability
from app.capabilities.filesystem_move import FilesystemMoveCapability
from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.capabilities.filesystem_search import FilesystemSearchCapability
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.capabilities.filesystem_trash import FilesystemTrashCapability
from app.capabilities.filesystem_mkdir import FilesystemMkdirCapability
from app.capabilities.filesystem_write_text import FilesystemWriteTextCapability
from app.capabilities.write_policy import HostWritePolicy
from app.capabilities.host_access import _windows_local_drive_roots
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
    """Build enabled reads and separately approved writes under their host policies."""
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

    registrations = [
        CapabilityRegistration(
            FilesystemStatCapability(),
            enabled=True,
            model_visible=True,
        )
    ]
    if config.filesystem_list_enabled:
        registrations.append(
            CapabilityRegistration(
                FilesystemListCapability(),
                enabled=True,
                model_visible=True,
            )
        )
    if config.filesystem_read_text_enabled:
        registrations.append(
            CapabilityRegistration(
                FilesystemReadTextCapability(),
                enabled=True,
                model_visible=True,
            )
        )
    if config.filesystem_search_enabled:
        registrations.append(
            CapabilityRegistration(
                FilesystemSearchCapability(),
                enabled=True,
                model_visible=True,
            )
        )
    if config.filesystem_mkdir_enabled:
        registrations.append(CapabilityRegistration(
            FilesystemMkdirCapability(HostWritePolicy(root, (state_directory,))),
            enabled=True,
            model_visible=True,
        ))
    if config.filesystem_write_text_enabled:
        registrations.append(CapabilityRegistration(
            FilesystemWriteTextCapability(HostWritePolicy(root, (state_directory,))),
            enabled=True,
            model_visible=True,
        ))
    if config.filesystem_copy_enabled:
        registrations.append(CapabilityRegistration(
            FilesystemCopyCapability(HostWritePolicy(root, (state_directory,))),
            enabled=True,
            model_visible=True,
        ))
    if config.filesystem_move_enabled:
        registrations.append(CapabilityRegistration(
            FilesystemMoveCapability(HostWritePolicy(root, (state_directory,))),
            enabled=True,
            model_visible=True,
        ))
    if config.filesystem_trash_enabled:
        registrations.append(CapabilityRegistration(
            FilesystemTrashCapability(HostWritePolicy(root, (state_directory,))),
            enabled=True,
            model_visible=True,
        ))
    registry = CapabilityRegistry(registrations)
    if policy.read_scope == HostReadScope.PORTABLE_ROOT:
        permission_rules = [
            PermissionRule(
                "phase8-portable-root-stat",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=root,
            ),
        ]
        if config.filesystem_list_enabled:
            permission_rules.append(
                PermissionRule(
                    "phase9-portable-root-list",
                    PermissionDecision.ALLOW,
                    permission=PermissionClass.READ,
                    capability_pattern="filesystem.list",
                    resource_root=root,
                )
            )
        if config.filesystem_read_text_enabled:
            permission_rules.append(
                PermissionRule(
                    "phase9-portable-root-read-text",
                    PermissionDecision.ALLOW,
                    permission=PermissionClass.READ,
                    capability_pattern="filesystem.read_text",
                    resource_root=root,
                )
            )
        if config.filesystem_search_enabled:
            permission_rules.append(
                PermissionRule(
                    "phase9-portable-root-search",
                    PermissionDecision.ALLOW,
                    permission=PermissionClass.READ,
                    capability_pattern="filesystem.search",
                    resource_root=root,
                )
            )
    else:
        permission_rules = []
        for permission_root in permission_roots:
            drive = permission_root.drive[0].casefold()
            permission_rules.append(
                PermissionRule(
                    f"phase9-local-{drive}-stat",
                    PermissionDecision.ALLOW,
                    permission=PermissionClass.READ,
                    capability_pattern="filesystem.stat",
                    resource_root=permission_root,
                )
            )
            if config.filesystem_list_enabled:
                permission_rules.append(
                    PermissionRule(
                        f"phase9-local-{drive}-list",
                        PermissionDecision.ALLOW,
                        permission=PermissionClass.READ,
                        capability_pattern="filesystem.list",
                        resource_root=permission_root,
                    )
                )
            if config.filesystem_read_text_enabled:
                permission_rules.append(
                    PermissionRule(
                        f"phase9-local-{drive}-read-text",
                        PermissionDecision.ALLOW,
                        permission=PermissionClass.READ,
                        capability_pattern="filesystem.read_text",
                        resource_root=permission_root,
                    )
                )
            if config.filesystem_search_enabled:
                permission_rules.append(
                    PermissionRule(
                        f"phase9-local-{drive}-search",
                        PermissionDecision.ALLOW,
                        permission=PermissionClass.READ,
                        capability_pattern="filesystem.search",
                        resource_root=permission_root,
                    )
                )
    if config.filesystem_mkdir_enabled:
        for drive_root in _windows_local_drive_roots():
            permission_rules.append(PermissionRule(
                f"phase10-local-{drive_root.drive[0].casefold()}-mkdir",
                PermissionDecision.ASK,
                permission=PermissionClass.WRITE,
                capability_pattern="filesystem.mkdir",
                resource_root=drive_root,
            ))
    if config.filesystem_write_text_enabled:
        for drive_root in _windows_local_drive_roots():
            permission_rules.append(PermissionRule(
                f"phase10-local-{drive_root.drive[0].casefold()}-write-text",
                PermissionDecision.ASK,
                permission=PermissionClass.WRITE,
                capability_pattern="filesystem.write_text",
                resource_root=drive_root,
            ))
    if config.filesystem_copy_enabled:
        for drive_root in _windows_local_drive_roots():
            permission_rules.append(PermissionRule(
                f"phase10-local-{drive_root.drive[0].casefold()}-copy",
                PermissionDecision.ASK,
                permission=PermissionClass.WRITE,
                capability_pattern="filesystem.copy",
                resource_root=drive_root,
            ))
    if config.filesystem_move_enabled:
        for drive_root in _windows_local_drive_roots():
            permission_rules.append(PermissionRule(
                f"phase10-local-{drive_root.drive[0].casefold()}-move",
                PermissionDecision.ASK,
                permission=PermissionClass.WRITE,
                capability_pattern="filesystem.move",
                resource_root=drive_root,
            ))
    if config.filesystem_trash_enabled:
        for drive_root in _windows_local_drive_roots():
            permission_rules.append(PermissionRule(
                f"phase10-local-{drive_root.drive[0].casefold()}-trash",
                PermissionDecision.ASK,
                permission=PermissionClass.WRITE,
                capability_pattern="filesystem.trash",
                resource_root=drive_root,
            ))
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
