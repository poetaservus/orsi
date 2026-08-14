from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    ExecutionIsolation,
    PermissionClass,
)
from app.capabilities.path_policy import resolve_candidate_path, resolve_read_path


class FilesystemStatArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(
        min_length=1,
        max_length=32_767,
        description=(
            "Copy a user-provided absolute path exactly, including its drive letter, directories, "
            "separators, spelling, and capitalization; never shorten or rewrite it. A relative "
            "path is already relative to the portable root, so do not prefix the root directory's "
            "name. Let the capability decide whether the path exists and is allowed."
        ),
    )


class FilesystemStatCapability(Capability[FilesystemStatArguments]):
    name = "filesystem.stat"
    description = "Return bounded metadata for one allowed file or directory without reading content."
    arguments_model = FilesystemStatArguments
    permission = PermissionClass.READ
    timeout_seconds = 2.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def permission_resource(
        self,
        arguments: FilesystemStatArguments,
        context: CapabilityContext,
    ):
        return resolve_candidate_path(
            arguments.path,
            portable_root=context.portable_root,
        ).resolved

    def execute(
        self,
        arguments: FilesystemStatArguments,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        resolved = resolve_read_path(
            arguments.path,
            portable_root=context.portable_root,
            allowed_roots=context.allowed_read_roots,
        )
        context.cancellation.raise_if_cancelled()

        try:
            requested_stat = resolved.requested.lstat()
            target_stat = resolved.resolved.stat()
        except FileNotFoundError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.NOT_FOUND,
                "The requested path does not exist.",
            ) from exc
        except PermissionError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INACCESSIBLE,
                "The requested path is not accessible.",
            ) from exc
        except OSError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INACCESSIBLE,
                "The requested path metadata could not be read.",
            ) from exc

        target_type = _file_type(target_stat.st_mode)
        attributes = int(getattr(requested_stat, "st_file_attributes", 0))
        reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        is_reparse_point = bool(reparse_flag and attributes & reparse_flag)
        is_symlink = stat.S_ISLNK(requested_stat.st_mode)

        return {
            "path": str(resolved.resolved),
            "type": target_type,
            "size_bytes": int(target_stat.st_size) if target_type == "file" else None,
            "modified_at": _utc_timestamp(target_stat.st_mtime),
            "created_at": _utc_timestamp(target_stat.st_ctime) if os.name == "nt" else None,
            "is_symlink": is_symlink,
            "is_reparse_point": is_reparse_point,
        }


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "other"


def _utc_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
