from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (Capability, CapabilityContext, CapabilityErrorCode,
    CapabilityExecutionError, ExecutionIsolation, PermissionClass)
from app.capabilities.windows_directory import file_identity, pinned_parent
from app.capabilities.write_policy import HostWritePolicy


_MAX_TEXT_BYTES = 65_536
_MAX_TEXT_LINES = 1_000


class FilesystemWriteTextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=32767,
                     description="Exact absolute local-drive path of the text file to create or replace.")
    text: str = Field(max_length=_MAX_TEXT_BYTES,
                     description="Exact UTF-8 text content that will become the entire file.")


class FilesystemWriteTextCapability(Capability[FilesystemWriteTextArguments]):
    name = "filesystem.write_text"
    description = "Create or replace one UTF-8 text file after exact approval."
    arguments_model = FilesystemWriteTextArguments
    permission = PermissionClass.WRITE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 3.0

    def __init__(self, policy: HostWritePolicy):
        if not isinstance(policy, HostWritePolicy):
            raise TypeError("Text writing requires a separate HostWritePolicy.")
        self.policy = policy

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        _encoded_text(arguments.text)
        return self.policy.resolve_text_file(arguments.path)

    def permission_resource_identity(self, arguments, context) -> str:
        path = self.permission_resource(arguments, context)
        try:
            with pinned_parent(path, context.cancellation) as (_, parent_identity):
                return _target_binding(path, parent_identity)
        except OSError as exc:
            _raise_path_error(exc)

    def approval_preview(self, arguments, context) -> str:
        del context
        _encoded_text(arguments.text)
        return arguments.text

    def execute(self, arguments: FilesystemWriteTextArguments, context: CapabilityContext) -> dict:
        path = self.permission_resource(arguments, context)
        if (context.authorized_resource is None or path != Path(context.authorized_resource)
                or context.authorized_resource_identity is None):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "Text writing requires exact runtime authorization.")
        data = _encoded_text(arguments.text)
        digest = hashlib.sha256(data).hexdigest()
        try:
            with pinned_parent(path, context.cancellation) as (_, parent_identity):
                binding = _target_binding(path, parent_identity)
                if binding != context.authorized_resource_identity:
                    raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                        "The target file changed after the preview. Request a new approval.")
                operation = "replaced" if os.path.lexists(path) else "created"
                context.cancellation.raise_if_cancelled()
                identity = atomic_write_text_file(path, data, context.cancellation)
                context.cancellation.raise_if_cancelled()
                if _read_digest(path) != digest:
                    raise RuntimeError("The written file content could not be verified.")
                return {"path": str(path), "written": True, "operation": operation,
                        "encoding": "utf-8", "bytes_written": len(data),
                        "sha256": digest, "identity": identity}
        except OSError as exc:
            _raise_path_error(exc)


def atomic_write_text_file(path: Path, data: bytes, cancellation) -> str:
    temp_path = _temporary_path(path)
    replaced = False
    try:
        with open(temp_path, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        cancellation.raise_if_cancelled()
        os.replace(temp_path, path)
        replaced = True
        try:
            return file_identity(path)
        except OSError as exc:
            raise RuntimeError("The written file could not be verified.") from exc
    except BaseException:
        if not replaced and os.path.lexists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as exc:
                raise RuntimeError("The temporary write file could not be removed safely.") from exc
        raise


def _temporary_path(path: Path) -> Path:
    for _ in range(8):
        candidate = path.with_name(f".orsi-write-{uuid4().hex}.tmp")
        if not os.path.lexists(candidate):
            return candidate
    raise FileExistsError("A unique temporary file name could not be reserved.")


def _target_binding(path: Path, parent_identity: str) -> str:
    if os.path.lexists(path):
        if path.is_dir():
            raise IsADirectoryError("The target is a directory, not a text file.")
        return f"{parent_identity}|file:{file_identity(path)}"
    return f"{parent_identity}|missing"


def _encoded_text(text: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) > _MAX_TEXT_BYTES:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "Text writes are limited to 65,536 UTF-8 bytes.",
        )
    if len(text.splitlines()) > _MAX_TEXT_LINES:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "Text writes are limited to 1,000 lines.",
        )
    return data


def _read_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raise_path_error(exc: OSError):
    if isinstance(exc, FileNotFoundError):
        code, message = CapabilityErrorCode.NOT_FOUND, "The parent folder does not exist."
    elif isinstance(exc, IsADirectoryError) or getattr(exc, "winerror", None) == 267:
        code, message = CapabilityErrorCode.INVALID_ARGUMENTS, "The target is not a writable text file path."
    else:
        code, message = CapabilityErrorCode.INACCESSIBLE, "The target file path is protected, redirected, or unavailable."
    raise CapabilityExecutionError(code, message) from exc
