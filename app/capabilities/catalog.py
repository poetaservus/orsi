from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.capabilities.application_launch import ApplicationLaunchCapability
from app.capabilities.contracts import Capability
from app.capabilities.filesystem_copy import FilesystemCopyCapability
from app.capabilities.filesystem_find import FilesystemFindCapability
from app.capabilities.filesystem_list import FilesystemListCapability
from app.capabilities.filesystem_mkdir import FilesystemMkdirCapability
from app.capabilities.filesystem_move import FilesystemMoveCapability
from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.capabilities.filesystem_search import FilesystemSearchCapability
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.capabilities.filesystem_trash import FilesystemTrashCapability
from app.capabilities.filesystem_write_text import FilesystemWriteTextCapability
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.security.write_policy import HostWritePolicy
from app.settings.agent import AgentFeatureConfig


CapabilityFactory = Callable[[], Capability]


def build_builtin_registry(
    config: AgentFeatureConfig,
    *,
    application_root: Path,
    state_directory: Path,
) -> CapabilityRegistry:
    """Construct the one production catalog of enabled built-in capabilities."""
    if not isinstance(config, AgentFeatureConfig):
        raise TypeError("The capability catalog requires an AgentFeatureConfig.")

    factories: list[tuple[bool, CapabilityFactory]] = [
        (config.filesystem_stat_enabled, FilesystemStatCapability),
        (config.filesystem_find_enabled, FilesystemFindCapability),
        (config.filesystem_list_enabled, FilesystemListCapability),
        (config.filesystem_read_text_enabled, FilesystemReadTextCapability),
        (config.filesystem_search_enabled, FilesystemSearchCapability),
        (config.application_launch_enabled, ApplicationLaunchCapability),
    ]
    write_flags = (
        config.filesystem_mkdir_enabled,
        config.filesystem_write_text_enabled,
        config.filesystem_copy_enabled,
        config.filesystem_move_enabled,
        config.filesystem_trash_enabled,
    )
    if any(write_flags):
        write_policy = HostWritePolicy(application_root, (state_directory,))
        factories.extend(
            (
                (config.filesystem_mkdir_enabled, lambda: FilesystemMkdirCapability(write_policy)),
                (
                    config.filesystem_write_text_enabled,
                    lambda: FilesystemWriteTextCapability(write_policy),
                ),
                (
                    config.filesystem_copy_enabled,
                    lambda: FilesystemCopyCapability(write_policy),
                ),
                (
                    config.filesystem_move_enabled,
                    lambda: FilesystemMoveCapability(write_policy),
                ),
                (
                    config.filesystem_trash_enabled,
                    lambda: FilesystemTrashCapability(write_policy),
                ),
            )
        )
    return CapabilityRegistry(
        CapabilityRegistration(factory(), enabled=True, model_visible=True)
        for enabled, factory in factories
        if enabled
    )
