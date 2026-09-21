from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    ExecutionIsolation,
    PermissionClass,
)
from app.security.host_access import HostReadScope
from app.security.path_policy import resolve_candidate_path, resolve_read_path


MAX_FIND_DIRECTORY_ENTRIES = 4_096
FindKind = Literal["any", "file", "directory"]


class FilesystemFindArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(
        min_length=1,
        max_length=32_767,
        description=(
            "Copy the requested containing directory path exactly. Absolute paths must preserve "
            "their drive letter, directories, separators, spelling, and capitalization."
        ),
    )
    name: str = Field(
        min_length=1,
        max_length=255,
        description="Exact file or folder name to find inside the containing directory.",
    )
    kind: FindKind = Field(
        default="any",
        description="Limit matches to any entry, a regular file, or a directory.",
    )

    @field_validator("name")
    @classmethod
    def validate_single_entry_name(cls, value: str) -> str:
        if "\x00" in value or any(separator in value for separator in ("/", "\\")):
            raise ValueError("Entry name must not contain path separators.")
        if value.strip() != value or value in {".", ".."}:
            raise ValueError("Entry name must be one exact local name.")
        return value


class FilesystemFindCapability(Capability[FilesystemFindArguments]):
    name = "filesystem.find"
    description = "Find exact file or folder names inside one allowed directory."
    arguments_model = FilesystemFindArguments
    permission = PermissionClass.READ
    timeout_seconds = 3.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def permission_resource(
        self,
        arguments: FilesystemFindArguments,
        context: CapabilityContext,
    ) -> Path:
        policy = context.host_access_policy
        if policy is not None and policy.read_scope == HostReadScope.FULL_LOCAL:
            return policy.resolve_read(arguments.path).resolved
        return resolve_candidate_path(
            arguments.path,
            portable_root=context.portable_root,
        ).resolved

    def execute(
        self,
        arguments: FilesystemFindArguments,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        if context.host_access_policy is not None:
            resolved = context.host_access_policy.resolve_read(arguments.path)
        else:
            resolved = resolve_read_path(
                arguments.path,
                portable_root=context.portable_root,
                allowed_roots=context.allowed_read_roots,
            )
        context.cancellation.raise_if_cancelled()
        _require_directory(resolved.requested, resolved.resolved)
        matches, entries_scanned = _find_exact_entries(
            resolved.resolved,
            name=arguments.name,
            kind=arguments.kind,
            context=context,
        )
        context.cancellation.raise_if_cancelled()
        return {
            "path": str(resolved.resolved),
            "name": arguments.name,
            "kind": arguments.kind,
            "matches": matches,
            "returned_matches": len(matches),
            "entries_scanned": entries_scanned,
        }


def _require_directory(requested: Path, resolved: Path) -> None:
    try:
        requested.lstat()
        target_stat = resolved.stat()
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested lookup directory does not exist.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested lookup directory is not accessible.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested lookup directory could not be inspected.",
        ) from exc
    if not stat.S_ISDIR(target_stat.st_mode):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested lookup path is not a directory.",
        )


def _find_exact_entries(
    directory: Path,
    *,
    name: str,
    kind: FindKind,
    context: CapabilityContext,
) -> tuple[list[dict[str, Any]], int]:
    folded_name = name.casefold()
    matches: list[dict[str, Any]] = []
    scanned = 0
    try:
        with os.scandir(directory) as iterator:
            entries = list(iterator)
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested lookup directory no longer exists.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested lookup directory cannot be listed.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested lookup directory scan failed.",
        ) from exc

    entries.sort(key=lambda item: (item.name.casefold(), item.name))
    for item in entries:
        context.cancellation.raise_if_cancelled()
        scanned += 1
        if scanned > MAX_FIND_DIRECTORY_ENTRIES:
            raise CapabilityExecutionError(
                CapabilityErrorCode.OUTPUT_LIMITED,
                f"The directory exceeds the bounded {MAX_FIND_DIRECTORY_ENTRIES:,}-entry lookup limit.",
            )
        if item.name.casefold() != folded_name:
            continue
        summary = _entry_summary(item)
        if summary is None:
            continue
        if kind != "any" and summary["type"] != kind:
            continue
        matches.append(summary)
    return matches, scanned


def _entry_summary(item: os.DirEntry[str]) -> dict[str, Any] | None:
    try:
        item_stat = item.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    except (PermissionError, OSError):
        return {
            "name": item.name,
            "path": str(Path(item.path)),
            "type": "inaccessible",
            "is_symlink": False,
            "is_reparse_point": False,
        }

    attributes = int(getattr(item_stat, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    is_reparse_point = bool(reparse_flag and attributes & reparse_flag)
    try:
        is_symlink = stat.S_ISLNK(item_stat.st_mode) or item.is_symlink()
    except OSError:
        is_symlink = stat.S_ISLNK(item_stat.st_mode)
    if is_symlink:
        entry_type = "symlink"
    elif stat.S_ISDIR(item_stat.st_mode):
        entry_type = "directory"
    elif stat.S_ISREG(item_stat.st_mode):
        entry_type = "file"
    else:
        entry_type = "other"
    return {
        "name": item.name,
        "path": str(Path(item.path)),
        "type": entry_type,
        "is_symlink": is_symlink,
        "is_reparse_point": is_reparse_point,
    }
