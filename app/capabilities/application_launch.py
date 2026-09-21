from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    ExecutionIsolation,
    PermissionClass,
)


class ApplicationLaunchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    application: Literal["blender"] = Field(
        description=(
            "Allowlisted application identifier. Use 'blender' when the user asks to open, "
            "launch, start, or fire up Blender, including when they call it their 3D program."
        )
    )
    file: str | None = Field(
        default=None,
        min_length=1,
        max_length=32_767,
        description=(
            "Optional existing Blender project or other file to open. Preserve a user-provided "
            "Windows or relative path exactly; omit this field when launching Blender alone."
        ),
    )

    @field_validator("application", mode="before")
    @classmethod
    def normalize_allowlisted_application(cls, value):
        if isinstance(value, str) and value.strip().casefold() == "blender":
            return "blender"
        return value


class ApplicationLaunchCapability(Capability[ApplicationLaunchArguments]):
    name = "application.launch"
    description = (
        "Launch the installed Blender desktop application after explicit user approval. Select "
        "this for natural requests such as open Blender, launch Blender, start Blender, fire up "
        "Blender, or open my 3D program Blender. It cannot launch commands, shells, scripts, or "
        "any application outside the fixed allowlist. An optional existing file may be opened."
    )
    arguments_model = ApplicationLaunchArguments
    permission = PermissionClass.EXECUTE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 5.0

    def __init__(
        self,
        *,
        locator: Callable[[str], Path] | None = None,
        launcher: Callable[[list[str], Path], object] | None = None,
    ):
        self._locator = locator or _locate_allowlisted_application
        self._launcher = launcher or _launch_process

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        return self._executable(arguments.application)

    def permission_resource_identity(self, arguments, context) -> str:
        return _file_identity(self.permission_resource(arguments, context))

    def approval_preview(self, arguments, context) -> str:
        executable = self.permission_resource(arguments, context)
        target = self._target_file(arguments.file, context)
        if target is None:
            return f"Launch Blender\nExecutable: {executable}"
        return f"Launch Blender\nExecutable: {executable}\nOpen file: {target}"

    def execute(
        self,
        arguments: ApplicationLaunchArguments,
        context: CapabilityContext,
    ) -> dict:
        executable = self.permission_resource(arguments, context)
        if (
            context.authorized_resource is None
            or executable != Path(context.authorized_resource)
            or context.authorized_resource_identity is None
            or _file_identity(executable) != context.authorized_resource_identity
        ):
            raise CapabilityExecutionError(
                CapabilityErrorCode.PERMISSION_DENIED,
                "Application launch requires approval for the exact executable and arguments.",
            )
        target = self._target_file(arguments.file, context)
        command = [str(executable)]
        if target is not None:
            command.append(str(target))
        context.cancellation.raise_if_cancelled()
        try:
            process = self._launcher(command, executable.parent)
        except OSError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INACCESSIBLE,
                "Blender could not be launched by the current Windows account.",
            ) from exc
        pid = getattr(process, "pid", None)
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INVALID_OUTPUT,
                "The Blender launcher did not return a valid process identity.",
            )
        return {
            "application": "blender",
            "executable": str(executable),
            "file": str(target) if target is not None else None,
            "pid": pid,
            "started": True,
        }

    def _executable(self, application: str) -> Path:
        if application != "blender":
            raise CapabilityExecutionError(
                CapabilityErrorCode.PERMISSION_DENIED,
                "The requested application is not allowlisted.",
            )
        try:
            executable = self._locator(application).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.NOT_FOUND,
                "Blender is not installed in an allowlisted location.",
            ) from exc
        if (
            executable.name.casefold() != "blender.exe"
            or not executable.is_file()
            or _is_reparse_point(executable)
        ):
            raise CapabilityExecutionError(
                CapabilityErrorCode.PERMISSION_DENIED,
                "The resolved Blender executable is not an allowlisted regular file.",
            )
        return executable

    @staticmethod
    def _target_file(raw: str | None, context: CapabilityContext) -> Path | None:
        if raw is None:
            return None
        try:
            if context.host_access_policy is not None:
                target = context.host_access_policy.resolve_read(raw).resolved
            else:
                candidate = Path(raw)
                if not candidate.is_absolute():
                    candidate = context.portable_root / candidate
                target = candidate.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INACCESSIBLE,
                "The optional Blender file is outside the allowed read scope or unavailable.",
            ) from exc
        if not target.is_file() or _is_reparse_point(target):
            raise CapabilityExecutionError(
                CapabilityErrorCode.INVALID_ARGUMENTS,
                "The optional Blender target must be an existing regular file.",
            )
        return target


def _locate_allowlisted_application(application: str) -> Path:
    if application != "blender":
        raise FileNotFoundError(application)
    roots: list[Path] = []
    for variable in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA"):
        value = os.environ.get(variable)
        if value:
            root = Path(value)
            if variable == "LOCALAPPDATA":
                root = root / "Programs"
            if root not in roots:
                roots.append(root)
    candidates: list[Path] = []
    for root in roots:
        foundation = root / "Blender Foundation"
        try:
            candidates.extend(foundation.glob("Blender */blender.exe"))
            candidates.append(foundation / "Blender" / "blender.exe")
        except OSError:
            continue
    valid = [
        candidate
        for candidate in candidates
        if candidate.is_file()
        and candidate.name.casefold() == "blender.exe"
        and not _is_reparse_point(candidate)
    ]
    if not valid:
        raise FileNotFoundError("Blender")
    return sorted(valid, key=lambda path: str(path).casefold(), reverse=True)[0]


def _file_identity(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The Blender executable could not be verified.",
        ) from exc
    value = json.dumps(
        {
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "modified_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return True
    reparse_attribute = int(getattr(stat, "st_file_attributes", 0)) & 0x400
    return path.is_symlink() or bool(reparse_attribute)


def _launch_process(command: list[str], cwd: Path):
    return subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        close_fds=True,
        creationflags=(
            int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
        ),
    )
