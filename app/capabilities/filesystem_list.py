from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
from pathlib import Path
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
from app.security.host_access import HostReadScope
from app.security.path_policy import resolve_candidate_path, resolve_read_path


DEFAULT_PAGE_ENTRIES = 50
MAX_PAGE_ENTRIES = 50
MAX_DIRECTORY_ENTRIES = 4_096
_CURSOR_VERSION = 1


class FilesystemListArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(
        min_length=1,
        max_length=32_767,
        description=(
            "Copy the requested directory path exactly. Absolute paths must preserve their drive "
            "letter, directories, separators, spelling, and capitalization. A relative path is "
            "already relative to the active read scope's documented root, so do not invent or "
            "prefix directories."
        ),
    )
    cursor: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        pattern=r"^[A-Za-z0-9_-]+$",
        description=(
            "For the next page, copy the previous filesystem.list next_cursor exactly. Omit it "
            "for the first page."
        ),
    )
    max_entries: int = Field(
        default=DEFAULT_PAGE_ENTRIES,
        ge=1,
        le=MAX_PAGE_ENTRIES,
        description=(
            "Optional page size from 1 through 50 inclusive. Omit this argument to return the "
            "default and maximum page of 50 entries; never request more than 50."
        ),
    )


class FilesystemListCapability(Capability[FilesystemListArguments]):
    name = "filesystem.list"
    description = (
        "Return one bounded, deterministic page of names and types from an allowed directory."
    )
    arguments_model = FilesystemListArguments
    permission = PermissionClass.READ
    timeout_seconds = 3.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def permission_resource(
        self,
        arguments: FilesystemListArguments,
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
        arguments: FilesystemListArguments,
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
        entries = _scan_directory(resolved.resolved, context)
        snapshot_sha256 = _snapshot_digest(entries)
        path_sha256 = _path_digest(resolved.resolved)
        offset = _decode_cursor(
            arguments.cursor,
            path_sha256=path_sha256,
            snapshot_sha256=snapshot_sha256,
        )
        if offset > len(entries):
            raise CapabilityExecutionError(
                CapabilityErrorCode.INVALID_ARGUMENTS,
                "The directory cursor is outside the current bounded snapshot.",
            )

        page_end = min(len(entries), offset + arguments.max_entries)
        page = entries[offset:page_end]
        next_cursor = (
            _encode_cursor(
                path_sha256=path_sha256,
                snapshot_sha256=snapshot_sha256,
                offset=page_end,
            )
            if page_end < len(entries)
            else None
        )
        context.cancellation.raise_if_cancelled()
        return {
            "path": str(resolved.resolved),
            "entries": page,
            "returned_entries": len(page),
            "total_entries": len(entries),
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        }


def _require_directory(requested: Path, resolved: Path) -> None:
    try:
        requested.lstat()
        target_stat = resolved.stat()
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested directory does not exist.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested directory is not accessible.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested directory could not be inspected.",
        ) from exc
    if not stat.S_ISDIR(target_stat.st_mode):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested path is not a directory.",
        )


def _scan_directory(
    directory: Path,
    context: CapabilityContext,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scanned_entries = 0
    try:
        with os.scandir(directory) as iterator:
            for item in iterator:
                context.cancellation.raise_if_cancelled()
                scanned_entries += 1
                if scanned_entries > MAX_DIRECTORY_ENTRIES:
                    raise CapabilityExecutionError(
                        CapabilityErrorCode.OUTPUT_LIMITED,
                        f"The directory exceeds the bounded {MAX_DIRECTORY_ENTRIES:,}-entry "
                        "listing limit.",
                    )
                summary = _entry_summary(item)
                if summary is not None:
                    entries.append(summary)
    except CapabilityExecutionError:
        raise
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested directory no longer exists.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested directory cannot be listed.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested directory listing failed.",
        ) from exc
    entries.sort(key=lambda entry: (entry["name"].casefold(), entry["name"]))
    return entries


def _entry_summary(item: os.DirEntry[str]) -> dict[str, Any] | None:
    try:
        item_stat = item.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    except (PermissionError, OSError):
        return {
            "name": item.name,
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
        "type": entry_type,
        "is_symlink": is_symlink,
        "is_reparse_point": is_reparse_point,
    }


def _snapshot_digest(entries: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        entries,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_digest(path: Path) -> str:
    canonical = os.path.normcase(os.path.abspath(path))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _encode_cursor(*, path_sha256: str, snapshot_sha256: str, offset: int) -> str:
    payload = {
        "offset": offset,
        "path_sha256": path_sha256,
        "snapshot_sha256": snapshot_sha256,
        "version": _CURSOR_VERSION,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None,
    *,
    path_sha256: str,
    snapshot_sha256: str,
) -> int:
    if cursor is None:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(
            (cursor + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        if len(raw) > 512:
            raise ValueError
        payload = json.loads(raw.decode("ascii"))
        if not isinstance(payload, dict) or set(payload) != {
            "offset",
            "path_sha256",
            "snapshot_sha256",
            "version",
        }:
            raise ValueError
        offset = payload["offset"]
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
            raise ValueError
        if payload["version"] != _CURSOR_VERSION:
            raise ValueError
        if not isinstance(payload["path_sha256"], str) or not isinstance(
            payload["snapshot_sha256"], str
        ):
            raise ValueError
        if _encode_cursor(
            path_sha256=payload["path_sha256"],
            snapshot_sha256=payload["snapshot_sha256"],
            offset=offset,
        ) != cursor:
            raise ValueError
    except (UnicodeError, ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The directory cursor is malformed or unsupported.",
        ) from exc
    if payload["path_sha256"] != path_sha256:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The directory cursor belongs to a different path.",
        )
    if payload["snapshot_sha256"] != snapshot_sha256:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The directory changed after the previous page; start the listing again.",
        )
    return offset
