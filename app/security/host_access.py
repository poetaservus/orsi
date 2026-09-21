from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError
from app.security.path_policy import ResolvedPath, resolve_read_path


FULL_LOCAL_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build "
    "exposes metadata only. It does not grant write, delete, execute, administrator, network, "
    "device, or background-indexing authority."
)

FULL_LOCAL_LIST_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata and return bounded names and types from one requested directory, but it "
    "cannot read file content or search the host. It does not grant write, delete, execute, "
    "administrator, network, device, or background-indexing authority."
)

FULL_LOCAL_TEXT_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata and return bounded content from one specifically requested UTF text file, "
    "but it cannot list directories or search the host. It does not grant write, delete, execute, "
    "administrator, network, device, or background-indexing authority."
)

FULL_LOCAL_LIST_TEXT_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata, return bounded names and types from one requested directory, and return "
    "bounded content from one specifically requested UTF text file. It cannot search the host or "
    "grant write, delete, execute, administrator, network, device, or background-indexing "
    "authority."
)

FULL_LOCAL_SEARCH_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata and search for literal text snippets inside one requested directory tree. It "
    "does not grant write, delete, execute, administrator, network, device, or background-indexing "
    "authority."
)

FULL_LOCAL_LIST_SEARCH_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata, return bounded names and types from one requested directory, and search for "
    "literal text snippets inside one requested directory tree. It does not grant write, delete, "
    "execute, administrator, network, device, or background-indexing authority."
)

FULL_LOCAL_TEXT_SEARCH_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata, return bounded content from one specifically requested UTF text file, and "
    "search for literal text snippets inside one requested directory tree. It does not grant write, "
    "delete, execute, administrator, network, device, or background-indexing authority."
)

FULL_LOCAL_LIST_TEXT_SEARCH_READ_WARNING = (
    "Full local read access lets O.R.S.I's enabled read-only capabilities use requested files and "
    "directories across local drives that the current Windows account can access. This build can "
    "inspect metadata, return bounded names and types from one requested directory, return bounded "
    "content from one specifically requested UTF text file, and search for literal text snippets "
    "inside one requested directory tree. It does not grant write, delete, execute, administrator, "
    "network, device, or background-indexing authority."
)

CLOUD_FILE_CONTENT_WARNING = (
    "In Cloud mode, requested host-file content and related conversation context may be sent to "
    "the selected provider. Do not enable Cloud mode for confidential host data."
)


class HostReadScope(StrEnum):
    PORTABLE_ROOT = "portable_root"
    FULL_LOCAL = "full_local"


class WindowsDriveType(IntEnum):
    UNKNOWN = 0
    NO_ROOT_DIRECTORY = 1
    REMOVABLE = 2
    FIXED = 3
    REMOTE = 4
    CDROM = 5
    RAMDISK = 6


_ALLOWED_LOCAL_READ_DRIVE_TYPES = frozenset(
    {
        WindowsDriveType.REMOVABLE,
        WindowsDriveType.FIXED,
        WindowsDriveType.RAMDISK,
    }
)


@dataclass(frozen=True)
class HostAccessPolicy:
    """Immutable Phase 9 authority contract for resolving requested read paths."""

    read_scope: HostReadScope
    application_root: Path
    user_home: Path
    full_local_read_acknowledged: bool = False
    local_read_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.read_scope, HostReadScope):
            raise TypeError("Host read scope must be a HostReadScope value.")
        if not isinstance(self.application_root, Path) or not isinstance(
            self.user_home, Path
        ):
            raise TypeError("Host access roots must be pathlib.Path values.")
        try:
            application_root = self.application_root.resolve(strict=True)
            user_home = self.user_home.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Host access roots must resolve to existing directories.") from exc
        if not application_root.is_dir() or not user_home.is_dir():
            raise ValueError("Host access roots must resolve to existing directories.")
        if self.read_scope == HostReadScope.FULL_LOCAL:
            if self.full_local_read_acknowledged is not True:
                raise ValueError(
                    "Full local read access requires explicit acknowledgement."
                )
            if os.name != "nt":
                raise ValueError(
                    "Full local read access is available only on the Windows host adapter."
                )
            configured_roots = self.local_read_roots or windows_local_drive_roots()
            if not configured_roots:
                raise ValueError("No enabled local filesystem drives are available.")
            if not all(isinstance(root, Path) for root in configured_roots):
                raise TypeError("Local read permission roots must be pathlib.Path values.")
            roots: list[Path] = []
            for configured_root in configured_roots:
                try:
                    root = configured_root.resolve(strict=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ValueError(
                        "Local read permission roots must resolve safely."
                    ) from exc
                if (
                    not root.is_dir()
                    or root.parent != root
                    or _windows_drive_type(root) not in _ALLOWED_LOCAL_READ_DRIVE_TYPES
                ):
                    raise ValueError(
                        "Local read permission roots must be enabled local drive roots."
                    )
                if root not in roots:
                    roots.append(root)
            object.__setattr__(
                self,
                "local_read_roots",
                tuple(sorted(roots, key=lambda item: str(item).casefold())),
            )
        elif self.full_local_read_acknowledged:
            raise ValueError(
                "Full local read acknowledgement is valid only for full-local scope."
            )
        elif self.local_read_roots:
            raise ValueError("Portable-root access cannot contain local-drive permission roots.")
        object.__setattr__(self, "application_root", application_root)
        object.__setattr__(self, "user_home", user_home)

    @classmethod
    def portable_root(cls, application_root: Path) -> HostAccessPolicy:
        return cls(
            read_scope=HostReadScope.PORTABLE_ROOT,
            application_root=application_root,
            user_home=application_root,
        )

    @classmethod
    def full_local(
        cls,
        *,
        application_root: Path,
        user_home: Path,
        acknowledged: bool,
    ) -> HostAccessPolicy:
        return cls(
            read_scope=HostReadScope.FULL_LOCAL,
            application_root=application_root,
            user_home=user_home,
            full_local_read_acknowledged=acknowledged,
        )

    def resolve_read(self, raw_path: str) -> ResolvedPath:
        if self.read_scope == HostReadScope.PORTABLE_ROOT:
            return resolve_read_path(
                raw_path,
                portable_root=self.application_root,
                allowed_roots=(self.application_root,),
            )
        return _resolve_full_local_read_path(raw_path, user_home=self.user_home)

    def permission_roots(self) -> tuple[Path, ...]:
        """Return the immutable startup roots used by the permission gate."""
        if self.read_scope == HostReadScope.PORTABLE_ROOT:
            return (self.application_root,)
        return self.local_read_roots


def _resolve_full_local_read_path(raw_path: str, *, user_home: Path) -> ResolvedPath:
    if not isinstance(raw_path, str):
        raise TypeError("Host read paths must be strings.")
    if not raw_path.strip():
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The path cannot be empty.",
        )
    if "\x00" in raw_path:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The path contains an invalid null character.",
        )
    _reject_special_windows_path(raw_path)

    requested = Path(raw_path)
    if requested.root and not requested.drive:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "Root-relative paths without a drive are ambiguous and are not accepted.",
        )
    if requested.drive and not requested.is_absolute():
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "Drive-relative paths are ambiguous and are not accepted.",
        )
    if not requested.is_absolute():
        requested = user_home / requested

    try:
        resolved = requested.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The path could not be resolved safely.",
        ) from exc

    _reject_special_windows_path(str(resolved))
    if not resolved.is_absolute() or not resolved.drive:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "Full local reads require a deterministic local path.",
        )
    drive_type = _windows_drive_type(Path(f"{resolved.drive}\\"))
    if drive_type in {WindowsDriveType.UNKNOWN, WindowsDriveType.NO_ROOT_DIRECTORY}:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The local drive is not available.",
        )
    if drive_type not in _ALLOWED_LOCAL_READ_DRIVE_TYPES:
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "The path is not on an enabled local filesystem drive.",
        )
    return ResolvedPath(requested=requested, resolved=resolved)


def _reject_special_windows_path(raw_path: str) -> None:
    normalized = raw_path.replace("/", "\\")
    folded = normalized.casefold()
    if folded.startswith(("\\\\.\\", "\\\\?\\", "\\??\\")):
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "Device namespace paths are not enabled for filesystem capabilities.",
        )
    if normalized.startswith("\\\\"):
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "Network paths are not enabled for filesystem capabilities.",
        )


def _windows_drive_type(root: Path) -> WindowsDriveType:
    if os.name != "nt":
        return WindowsDriveType.UNKNOWN
    try:
        value = ctypes.windll.kernel32.GetDriveTypeW(str(root))
        return WindowsDriveType(int(value))
    except (AttributeError, OSError, TypeError, ValueError):
        return WindowsDriveType.UNKNOWN


def windows_local_drive_roots() -> tuple[Path, ...]:
    if os.name != "nt":
        return ()
    try:
        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except (AttributeError, OSError, TypeError, ValueError):
        return ()
    if mask <= 0:
        return ()

    roots: list[Path] = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = Path(f"{chr(ord('A') + index)}:\\")
        if _windows_drive_type(root) not in _ALLOWED_LOCAL_READ_DRIVE_TYPES:
            continue
        try:
            canonical = root.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            continue
        if canonical.is_dir():
            roots.append(canonical)
    return tuple(sorted(roots, key=lambda item: str(item).casefold()))
