from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (Capability, CapabilityContext, CapabilityErrorCode,
    CapabilityExecutionError, ExecutionIsolation, PermissionClass)
from app.capabilities.windows_directory import create_child_directory, pinned_parent
from app.capabilities.write_policy import HostWritePolicy


class FilesystemMkdirArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=32767,
                     description="Exact absolute path of one new folder with an existing parent.")


class FilesystemMkdirCapability(Capability[FilesystemMkdirArguments]):
    name = "filesystem.mkdir"
    description = "Create one empty folder after explicit approval; never replace an existing entry."
    arguments_model = FilesystemMkdirArguments
    permission = PermissionClass.WRITE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 3.0

    def __init__(self, policy: HostWritePolicy):
        if not isinstance(policy, HostWritePolicy):
            raise TypeError("Folder creation requires a separate HostWritePolicy.")
        self.policy = policy

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        return self.policy.resolve_new_directory(arguments.path)

    def permission_resource_identity(self, arguments, context) -> str:
        path = self.permission_resource(arguments, context)
        try:
            with pinned_parent(path, context.cancellation) as (_, identity):
                if os.path.lexists(path):
                    raise FileExistsError()
                return identity
        except OSError as exc:
            _raise_path_error(exc)

    def execute(self, arguments: FilesystemMkdirArguments, context: CapabilityContext) -> dict:
        path = self.permission_resource(arguments, context)
        if (context.authorized_resource is None or path != Path(context.authorized_resource)
                or context.authorized_resource_identity is None):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "Folder creation requires exact runtime authorization.")
        try:
            with pinned_parent(path, context.cancellation) as (parent, identity):
                if identity != context.authorized_resource_identity:
                    raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                        "The parent folder changed after the preview. Request a new approval.")
                context.cancellation.raise_if_cancelled()
                created_identity = create_child_directory(parent, path.name)
                return {"path": str(path), "created": True, "type": "directory",
                        "identity": created_identity, "parents_created": False}
        except OSError as exc:
            _raise_path_error(exc)


def _raise_path_error(exc: OSError):
    if isinstance(exc, FileExistsError) or getattr(exc, "winerror", None) in {80, 183}:
        code, message = CapabilityErrorCode.INVALID_ARGUMENTS, "An entry already exists at that path."
    elif isinstance(exc, FileNotFoundError):
        code, message = CapabilityErrorCode.NOT_FOUND, "The parent folder does not exist."
    else:
        code, message = CapabilityErrorCode.INACCESSIBLE, "The parent folder is protected, redirected, or unavailable."
    raise CapabilityExecutionError(code, message) from exc
