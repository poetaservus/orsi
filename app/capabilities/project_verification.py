"""Explicitly approved, bounded project commands and isolated UI inspection."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread
from time import monotonic, sleep
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.capabilities.contracts import (Capability, CapabilityErrorCode as Code,
    CapabilityExecutionError as Error, ExecutionIsolation, PermissionClass)
from app.runtime.owned_process import start_owned_process
from app.security.path_policy import resolve_read_path


class ProjectVerificationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_path: str = Field(min_length=1, max_length=32767)
    kind: Literal["build", "test"]
    executable: str = Field(min_length=1, max_length=32767, description="Exact absolute executable; scripts use their interpreter. No shell command strings.")
    arguments: list[str] = Field(default_factory=list, max_length=64)
    timeout_seconds: int = Field(default=60, ge=1, le=120)

    @model_validator(mode="after")
    def bounded_arguments(self):
        if any(len(value) > 4096 or "\0" in value for value in self.arguments) or sum(map(len, self.arguments)) > 16000:
            raise ValueError("Command arguments exceed their bounds.")
        return self


class InspectionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["click", "fill", "scroll", "visible", "text"]
    target: str = Field(default="", max_length=256, description="Browser CSS selector or unique desktop automation ID/exact accessible name. Empty scroll target means the page.")
    value: str = Field(default="", max_length=1000)
    amount: int = Field(default=500, ge=-10000, le=10000)


class ProjectInspectionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_path: str = Field(min_length=1, max_length=32767)
    kind: Literal["browser", "desktop"]
    url: str | None = Field(default=None, max_length=2048)
    pid: int | None = Field(default=None, ge=1)
    steps: list[InspectionStep] = Field(default_factory=list, max_length=12)
    width: int = Field(default=1280, ge=320, le=1920)
    height: int = Field(default=800, ge=240, le=1080)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    server_executable: str | None = Field(default=None, max_length=32767,
        description="Optional exact interpreter/executable for a temporary local preview server; all owned children stop after inspection.")
    server_arguments: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_target(self):
        if self.kind == "browser":
            if self.url is None or self.pid is not None:
                raise ValueError("Browser inspection requires a loopback HTTP URL and no PID.")
            local_origin(self.url)
        elif self.pid is None or self.url is not None or self.server_executable is not None:
            raise ValueError("Desktop inspection requires an existing project process PID and no URL/server.")
        if self.server_arguments and self.server_executable is None:
            raise ValueError("Server arguments require a server executable.")
        if any(len(value) > 4096 or "\0" in value for value in self.server_arguments) or sum(map(len, self.server_arguments)) > 16000:
            raise ValueError("Server arguments exceed their bounds.")
        return self


def local_origin(url: str) -> tuple[str, str, int]:
    value = urlsplit(url)
    if value.scheme != "http" or value.hostname not in {"127.0.0.1", "localhost", "::1"} or value.username or value.password:
        raise ValueError("Only unauthenticated local loopback HTTP previews are supported.")
    return value.scheme, value.hostname, value.port or 80


def _file_identity(path: Path) -> tuple:
    try:
        value = path.stat()
    except OSError as exc:
        raise Error(Code.INACCESSIBLE, "The approved executable is no longer accessible.") from exc
    return (str(path), value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _executable(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or path.suffix.lower() != ".exe" or path.name.lower() in {
            "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe"}:
        raise Error(Code.INVALID_ARGUMENTS, "Use an exact absolute executable, without a command shell or batch wrapper.")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise Error(Code.NOT_FOUND, "The verification executable does not exist. Select its actual installed path.") from exc
    except (OSError, RuntimeError) as exc:
        raise Error(Code.INACCESSIBLE, "The verification executable could not be resolved safely.") from exc
    if not resolved.is_file() or resolved != path or path.is_symlink():
        raise Error(Code.INVALID_ARGUMENTS, "The executable must be a regular file at its canonical path.")
    return resolved


def worker_environment() -> dict[str, str]:
    # Do not inherit provider keys or arbitrary project hooks from the host environment.
    names = {"systemroot", "windir", "temp", "tmp", "path", "pathext", "userprofile",
        "appdata", "localappdata", "programfiles", "programfiles(x86)", "programw6432", "comspec"}
    values = {key: value for key, value in os.environ.items() if key.lower() in names}
    values.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return values


def run_worker(command: list[str], *, cwd: Path, timeout: int, cancellation, limit=48 * 1024, windows_command_line=None) -> dict:
    """Drain capped pipe output; atomically own and release all worker descendants."""
    read_fd, write_fd = os.pipe()
    data, exceeded, finished = bytearray(), Event(), Event()
    process = None
    def drain():
        with os.fdopen(read_fd, "rb", buffering=0) as stream:
            while chunk := stream.read(4096):
                room = max(0, limit - len(data))
                data.extend(chunk[:room])
                if len(chunk) > room:
                    exceeded.set()
        finished.set()
    reader = Thread(target=drain, daemon=True)
    reader.start()
    reason = None
    try:
        cancellation.raise_if_cancelled()
        process = start_owned_process(command, cwd=cwd, env=worker_environment(), stdout=write_fd, stderr=write_fd,
            windows_command_line=windows_command_line)
        os.close(write_fd)
        write_fd = None
        deadline = monotonic() + timeout
        while True:
            cancellation.raise_if_cancelled()
            if exceeded.is_set():
                reason = "output_limit"
                break
            if monotonic() >= deadline:
                reason = "timeout"
                break
            if process.poll() is not None:
                break
            sleep(0.01)
        exit_code = process.poll()
    finally:
        if process is not None:
            process.close()  # Includes descendants even after the parent has exited.
        if write_fd is not None:
            os.close(write_fd)
        reader.join(5)
    if not finished.is_set():
        raise Error(Code.OUTCOME_UNKNOWN, "The owned worker output did not settle after cleanup.")
    if exceeded.is_set():
        reason = "output_limit"
    return {"exit_code": exit_code, "stop_reason": reason,
        "output": bytes(data).decode("utf-8", errors="replace"), "output_truncated": exceeded.is_set(),
        "owned_processes_released": True}


class _ProjectCapability(Capability):
    permission = PermissionClass.EXECUTE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 135.0

    def __init__(self, state_directory: Path):
        self.state_directory = state_directory

    def permission_resource(self, arguments, context):
        if context.host_access_policy is not None:
            path = context.host_access_policy.resolve_read(arguments.project_path).resolved
        else:
            path = resolve_read_path(arguments.project_path, portable_root=context.portable_root,
                allowed_roots=context.allowed_read_roots).resolved
        if not path.is_dir() or path == path.parent:
            raise Error(Code.INVALID_ARGUMENTS, "Verification requires an existing project directory below a drive root.")
        return path

    def permission_resource_identity(self, arguments, context):
        project = self.permission_resource(arguments, context)
        # Directory timestamps change during a build; approval binds the directory identity,
        # command executable and exact arguments, not its generated outputs.
        st = project.stat()
        executable = getattr(arguments, "executable", None) or getattr(arguments, "server_executable", None)
        identities = [str(project), st.st_dev, st.st_ino]
        if executable is not None:
            identities.append(_file_identity(_executable(executable)))
        if getattr(arguments, "pid", None) is not None:
            pid, created, executable, working_directory = _process_identity(arguments.pid)
            if working_directory != project:
                raise Error(Code.PERMISSION_DENIED, "The desktop process must belong to the approved project directory.")
            identities.append((pid, created, executable))
        return hashlib.sha256(json.dumps(identities).encode()).hexdigest()

    def approval_preview(self, arguments, context):
        return ("Run project verification/inspection. Project code and UI interactions can change files or application state.\n"
            + json.dumps(arguments.model_dump(mode="json"), ensure_ascii=False, indent=2))

    def _authorize(self, arguments, context):
        project = self.permission_resource(arguments, context)
        if context.authorized_resource != str(project) or context.authorized_resource_identity != self.permission_resource_identity(arguments, context):
            raise Error(Code.PERMISSION_DENIED, "Verification requires approval for this exact project, executable and arguments.")
        return project


class ProjectVerifyCapability(_ProjectCapability):
    name = "project.verify"
    description = ("Run one explicitly approved project build or relevant test command with a 120-second deadline, "
        "48-KiB output limit and owned process cleanup. Use the project's documented build and selected tests; "
        "this runs project code with account access, not a security sandbox. Follow UI changes with project.inspect. "
        "A zero exit code proves only this command; failures/timeouts/unrun checks must be reported.")
    arguments_model = ProjectVerificationArguments

    def execute(self, arguments, context):
        project = self._authorize(arguments, context)
        result = run_worker([str(_executable(arguments.executable)), *arguments.arguments],
            cwd=project, timeout=arguments.timeout_seconds, cancellation=context.cancellation)
        return {"project_path": str(project), "kind": arguments.kind,
            "passed": result["exit_code"] == 0 and result["stop_reason"] is None,
            "command": [arguments.executable, *arguments.arguments], "content_is_untrusted": True, **result}


class ProjectInspectCapability(_ProjectCapability):
    name = "project.inspect"
    description = ("After building/testing, inspect a local browser preview or a project desktop process. "
        "Runs up to 12 approved click/fill/scroll/visible/text checks, captures a screenshot and bounded layout/control evidence. "
        "Browser inspection reports broken loaded references, console errors, overflow and actual scroll movement. "
        "Use a temporary server executable when needed. Desktop targets use automation IDs. "
        "Screenshots and observations are evidence for the inspected surface, not proof of all visual correctness.")
    arguments_model = ProjectInspectionArguments
    timeout_seconds = 75.0

    def execute(self, arguments, context):
        project = self._authorize(arguments, context)
        folder = self.state_directory / "verification" / uuid4().hex
        folder.mkdir(parents=True)
        spec = folder / "inspection.json"
        spec.write_text(json.dumps({**arguments.model_dump(mode="json"), "project_path": str(project),
            "screenshot": str(folder / "screenshot.png"),
            "target_created_at": _process_created_at(arguments.pid),
            "browser_directory": str(self.state_directory / "playwright") if (self.state_directory / "playwright").is_dir() else None}), encoding="utf-8")
        worker = Path(__file__).resolve().parents[1] / "runtime" / "inspection_worker.py"
        try:
            result = run_worker([sys.executable, str(worker), str(spec)], cwd=Path(__file__).resolve().parents[2],
                timeout=arguments.timeout_seconds, cancellation=context.cancellation)
            if result["exit_code"] != 0 or result["stop_reason"] is not None:
                return {"project_path": str(project), "kind": arguments.kind, "passed": False,
                    "inspection_complete": False, "content_is_untrusted": True, **result}
            try:
                observations = json.loads(result["output"])
                if not isinstance(observations, dict):
                    raise ValueError
            except ValueError:
                raise Error(Code.INVALID_OUTPUT, "Inspection did not return structured observations.") from None
            return {"project_path": str(project), "kind": arguments.kind, "inspection_complete": True,
                "content_is_untrusted": True, **observations, "owned_processes_released": True}
        finally:
            spec.unlink(missing_ok=True)


def _process_created_at(pid: int | None) -> float | None:
    if pid is None:
        return None
    return _process_identity(pid)[1]


def _process_identity(pid: int) -> tuple:
    try:
        import psutil
    except ImportError as exc:
        raise Error(Code.EXECUTOR_UNAVAILABLE, "Desktop inspection requires the verification dependencies.") from exc
    try:
        process = psutil.Process(pid)
        return process.pid, process.create_time(), process.exe(), Path(process.cwd()).resolve()
    except psutil.NoSuchProcess as exc:
        raise Error(Code.NOT_FOUND, "The desktop target exited. Select the current project process.") from exc
    except (psutil.AccessDenied, OSError) as exc:
        raise Error(Code.INACCESSIBLE, "The desktop target identity could not be inspected.") from exc
