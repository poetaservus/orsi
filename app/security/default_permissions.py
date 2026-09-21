from __future__ import annotations

from pathlib import Path

from app.capabilities.contracts import PermissionClass
from app.security.host_access import (
    HostAccessPolicy,
    HostReadScope,
    windows_local_drive_roots,
)
from app.security.permissions import (
    PermissionDecision,
    PermissionGate,
    PermissionRule,
)
from app.settings.agent import AgentFeatureConfig


_READ_CAPABILITIES = (
    ("filesystem_stat_enabled", "filesystem.stat", "stat", "phase8"),
    ("filesystem_find_enabled", "filesystem.find", "find", "phase9"),
    ("filesystem_list_enabled", "filesystem.list", "list", "phase9"),
    ("filesystem_read_text_enabled", "filesystem.read_text", "read-text", "phase9"),
    ("filesystem_search_enabled", "filesystem.search", "search", "phase9"),
)

_WRITE_CAPABILITIES = (
    ("filesystem_mkdir_enabled", "filesystem.mkdir", "mkdir"),
    ("filesystem_write_text_enabled", "filesystem.write_text", "write-text"),
    ("filesystem_copy_enabled", "filesystem.copy", "copy"),
    ("filesystem_move_enabled", "filesystem.move", "move"),
    ("filesystem_trash_enabled", "filesystem.trash", "trash"),
)


def build_default_permission_gate(
    config: AgentFeatureConfig,
    policy: HostAccessPolicy,
    read_roots: tuple[Path, ...],
) -> PermissionGate:
    """Build deterministic read, write, and execute rules for built-in capabilities."""
    rules: list[PermissionRule] = []
    scope = "portable-root" if policy.read_scope == HostReadScope.PORTABLE_ROOT else "local"

    for root in read_roots:
        root_label = "" if scope == "portable-root" else f"-{_drive_label(root)}"
        for flag, capability, label, phase in _READ_CAPABILITIES:
            if getattr(config, flag):
                rules.append(
                    PermissionRule(
                        f"{phase}-{scope}{root_label}-{label}",
                        PermissionDecision.ALLOW,
                        permission=PermissionClass.READ,
                        capability_pattern=capability,
                        resource_root=root,
                    )
                )

    write_roots = windows_local_drive_roots()
    for flag, capability, label in _WRITE_CAPABILITIES:
        if not getattr(config, flag):
            continue
        for root in write_roots:
            rules.append(
                PermissionRule(
                    f"phase10-local-{_drive_label(root)}-{label}",
                    PermissionDecision.ASK,
                    permission=PermissionClass.WRITE,
                    capability_pattern=capability,
                    resource_root=root,
                )
            )

    if config.application_launch_enabled:
        rules.append(
            PermissionRule(
                "application-launch-explicit-approval",
                PermissionDecision.ASK,
                permission=PermissionClass.EXECUTE,
                capability_pattern="application.launch",
            )
        )
    return PermissionGate(rules)


def _drive_label(root: Path) -> str:
    drive = root.drive
    return drive[0].casefold() if drive else "root"
