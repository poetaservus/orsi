from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (Capability, CapabilityContext, CapabilityErrorCode,
    CapabilityExecutionError, ExecutionIsolation, PermissionClass)
from app.capabilities.windows_directory import file_identity, pinned_parent
from app.capabilities.write_policy import HostWritePolicy


_MAX_MOVE_BYTES = 16 * 1024 * 1024


class FilesystemMoveArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_path: str = Field(min_length=1, max_length=32767,
                            description="Exact absolute local-drive path of the regular file to move.")
    destination_path: str = Field(min_length=1, max_length=32767,
                                 description="Exact absolute local-drive destination file path.")
    on_collision: Literal["fail", "replace"] = Field(
        default="fail",
        description="Use fail to refuse an existing destination, or replace to replace that exact file.",
    )


class FilesystemMoveCapability(Capability[FilesystemMoveArguments]):
    name = "filesystem.move"
    description = "Move one bounded regular file to an exact destination after approval."
    arguments_model = FilesystemMoveArguments
    permission = PermissionClass.WRITE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 6.0

    def __init__(self, policy: HostWritePolicy):
        if not isinstance(policy, HostWritePolicy):
            raise TypeError("File moving requires a separate HostWritePolicy.")
        self.policy = policy

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        source, destination = self._paths(arguments)
        _ensure_distinct(source, destination)
        return destination

    def permission_resource_identity(self, arguments, context) -> str:
        source, destination = self._paths(arguments)
        _ensure_distinct(source, destination)
        try:
            source_snapshot = _source_snapshot(source, context.cancellation)
            with pinned_parent(destination, context.cancellation) as (_, parent_identity):
                destination_state = _destination_state(destination)
                if destination_state != "missing" and arguments.on_collision == "fail":
                    raise FileExistsError()
                return _precondition_digest(source_snapshot, parent_identity,
                                            destination_state, arguments.on_collision)
        except OSError as exc:
            _raise_path_error(exc, source=source, destination=destination)

    def approval_preview(self, arguments, context) -> str:
        del context
        source, destination = self._paths(arguments)
        _ensure_distinct(source, destination)
        return "\n".join((
            f"Source: {source}",
            f"Destination: {destination}",
            f"Collision policy: {arguments.on_collision}",
            "The source file will be removed after the destination is verified.",
        ))

    def execute(self, arguments: FilesystemMoveArguments, context: CapabilityContext) -> dict:
        source, destination = self._paths(arguments)
        _ensure_distinct(source, destination)
        placed = False
        if (context.authorized_resource is None or destination != Path(context.authorized_resource)
                or context.authorized_resource_identity is None):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "File moving requires exact runtime authorization.")
        try:
            source_snapshot = _source_snapshot(source, context.cancellation)
            with pinned_parent(destination, context.cancellation) as (_, parent_identity):
                destination_state = _destination_state(destination)
                binding = _precondition_digest(source_snapshot, parent_identity,
                                               destination_state, arguments.on_collision)
                if binding != context.authorized_resource_identity:
                    raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                        "The source or destination changed after the preview. Request a new approval.")
                if destination_state != "missing" and arguments.on_collision == "fail":
                    raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS,
                        "An entry already exists at the destination path.")
                context.cancellation.raise_if_cancelled()
                placement, identity = move_file(source, destination, source_snapshot["sha256"],
                                                arguments.on_collision, context.cancellation)
                placed = True
                context.cancellation.raise_if_cancelled()
                if os.path.lexists(source):
                    raise RuntimeError("The source file still exists after the move.")
                if _file_sha256(destination, context.cancellation) != source_snapshot["sha256"]:
                    raise RuntimeError("The moved file content could not be verified.")
                return {"source_path": str(source), "destination_path": str(destination),
                        "moved": True, "operation": ("replaced" if destination_state != "missing" else "created"),
                        "placement": placement, "collision_policy": arguments.on_collision,
                        "bytes_moved": source_snapshot["size_bytes"],
                        "sha256": source_snapshot["sha256"], "identity": identity}
        except OSError as exc:
            if placed:
                raise RuntimeError("The moved file state could not be verified after placement.") from exc
            _raise_path_error(exc, source=source, destination=destination)

    def _paths(self, arguments: FilesystemMoveArguments) -> tuple[Path, Path]:
        source = self.policy.resolve_move_source(arguments.source_path)
        destination = self.policy.resolve_move_destination(arguments.destination_path)
        return source, destination


def move_file(source: Path, destination: Path, expected_sha256: str,
              on_collision: str, cancellation) -> tuple[str, str]:
    if _same_drive(source, destination):
        placed = False
        try:
            if on_collision == "replace":
                os.replace(source, destination)
            else:
                os.rename(source, destination)
            placed = True
            identity = file_identity(destination)
            if _file_sha256(destination, cancellation) != expected_sha256:
                raise RuntimeError("The renamed file content could not be verified.")
            return "rename", identity
        except OSError:
            if placed:
                raise RuntimeError("The renamed file could not be verified.")
            raise
    return _copy_then_remove(source, destination, expected_sha256, on_collision, cancellation)


def _copy_then_remove(source: Path, destination: Path, expected_sha256: str,
                      on_collision: str, cancellation) -> tuple[str, str]:
    temp_path = _temporary_path(destination)
    placed = False
    try:
        digest = hashlib.sha256()
        total = 0
        with open(source, "rb") as src, open(temp_path, "xb") as dst:
            while True:
                cancellation.raise_if_cancelled()
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_MOVE_BYTES:
                    raise CapabilityExecutionError(CapabilityErrorCode.OUTPUT_LIMITED,
                        "File moving is limited to 16 MiB in this checkpoint.")
                digest.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if digest.hexdigest() != expected_sha256:
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                "The source file changed after the preview. Request a new approval.")
        cancellation.raise_if_cancelled()
        if on_collision == "replace":
            os.replace(temp_path, destination)
        else:
            os.rename(temp_path, destination)
        placed = True
        identity = file_identity(destination)
        if _file_sha256(destination, cancellation) != expected_sha256:
            raise RuntimeError("The copied destination could not be verified before source removal.")
        try:
            os.unlink(source)
        except OSError as exc:
            raise RuntimeError("The destination was placed, but the source could not be removed.") from exc
        if os.path.lexists(source):
            raise RuntimeError("The source still exists after cross-drive move cleanup.")
        return "copy_remove", identity
    except BaseException:
        if not placed and os.path.lexists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as exc:
                raise RuntimeError("The temporary move file could not be removed safely.") from exc
        raise


def _source_snapshot(path: Path, cancellation) -> dict[str, object]:
    identity = file_identity(path)
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as handle:
        while True:
            cancellation.raise_if_cancelled()
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_MOVE_BYTES:
                raise CapabilityExecutionError(CapabilityErrorCode.OUTPUT_LIMITED,
                    "File moving is limited to 16 MiB in this checkpoint.")
            digest.update(chunk)
    if file_identity(path) != identity:
        raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
            "The source file changed while it was being inspected.")
    return {"identity": identity, "size_bytes": total, "sha256": digest.hexdigest()}


def _destination_state(path: Path) -> str:
    if not os.path.lexists(path):
        return "missing"
    if path.is_dir():
        raise IsADirectoryError("The destination is a directory, not a file path.")
    return f"file:{file_identity(path)}"


def _precondition_digest(source_snapshot: dict[str, object], parent_identity: str,
                         destination_state: str, collision: str) -> str:
    return hashlib.sha256(json.dumps({
        "collision": collision,
        "destination_parent": parent_identity,
        "destination_state": destination_state,
        "source": source_snapshot,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _file_sha256(path: Path, cancellation) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            cancellation.raise_if_cancelled()
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_path(path: Path) -> Path:
    for _ in range(8):
        candidate = path.with_name(f".orsi-move-{uuid4().hex}.tmp")
        if not os.path.lexists(candidate):
            return candidate
    raise FileExistsError("A unique temporary move file name could not be reserved.")


def _same_drive(source: Path, destination: Path) -> bool:
    return source.drive.casefold() == destination.drive.casefold()


def _ensure_distinct(source: Path, destination: Path) -> None:
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
        raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS,
            "The source and destination must be different file paths.")


def _raise_path_error(exc: OSError, *, source: Path, destination: Path):
    if isinstance(exc, FileNotFoundError):
        missing_source = not os.path.lexists(source)
        message = "The source file does not exist." if missing_source else "The destination parent folder does not exist."
        code = CapabilityErrorCode.NOT_FOUND
    elif isinstance(exc, FileExistsError) or getattr(exc, "winerror", None) in {80, 183}:
        code, message = CapabilityErrorCode.INVALID_ARGUMENTS, "An entry already exists at the destination path."
    elif (isinstance(exc, IsADirectoryError) or getattr(exc, "winerror", None) == 267
          or source.is_dir() or destination.is_dir()):
        code, message = CapabilityErrorCode.INVALID_ARGUMENTS, "The source or destination is not a regular file path."
    else:
        code, message = CapabilityErrorCode.INACCESSIBLE, "The source or destination path is protected, redirected, or unavailable."
    raise CapabilityExecutionError(code, message) from exc
