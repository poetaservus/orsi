"""Explicitly approved, bounded project commands and isolated UI inspection."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
import re
from pathlib import Path
import shutil
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

MAX_INSPECTION_IMAGES = 5  # Four explicit checkpoints and the final viewport.
MAX_INSPECTION_IMAGE_BYTES = 8 * 1024 * 1024


class ProjectVerificationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_path: str = Field(min_length=1, max_length=32767)
    kind: Literal["build", "test"]
    executable: str = Field(min_length=1, max_length=32767,
        description="Exact absolute executable, or npm/npm.cmd for the installed Windows npm. Put run/build/test in arguments, not executable. No shell command strings.")
    arguments: list[str] = Field(default_factory=list, max_length=64)
    timeout_seconds: int = Field(default=60, ge=1, le=120)

    @model_validator(mode="after")
    def bounded_arguments(self):
        if any(len(value) > 4096 or "\0" in value for value in self.arguments) or sum(map(len, self.arguments)) > 16000:
            raise ValueError("Command arguments exceed their bounds.")
        return self


class InspectionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["click", "fill", "select_option", "scroll", "visible", "text", "wait", "in_view", "model_loaded",
        "checkpoint", "key", "touch", "scroll_to", "frame_timing"] = Field(
        description="select_option selects one native HTML select option by exact value and verifies its current selected value; use a separate text/checkpoint assertion for the resulting app behavior. fill supports text inputs, not native selects. checkpoint captures current pixels, scroll position, target bounds and selected styles without moving the target. Use named initial/partial/completed/return checkpoints in one session. key and touch use native input; scroll_to sets an absolute scroll position. frame_timing samples bounded animation-frame intervals, not proof of smooth rendering. in_view only moves offscreen targets. Review pixels for visual correctness.")
    target: str = Field(default="", max_length=256, description="Browser CSS selector or unique desktop automation ID/exact accessible name. Empty scroll target means the page.")
    value: str = Field(default="", max_length=1000,
        description="fill/text/key content, or the exact native option value for select_option (explicitly supply even an empty value).")
    amount: int = Field(default=500, ge=-10000, le=10000)
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    timeout_ms: int = Field(default=2000, ge=1, le=15000,
        description="Bounded browser readiness wait. For wait with an empty target, wait this duration. Use wait/hidden for an intro, then in_view for the affected section.")
    label: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_.-]*$",
        description="Unique checkpoint name, such as initial, partial, complete or return.")
    properties: list[str] = Field(default_factory=lambda: ["opacity", "transform", "visibility"], max_length=8,
        description="Checkpoint/frame timing styles: opacity, transform, visibility, display, position, or CSS custom properties such as --words-progress.")
    reference: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_.-]*$",
        description="Earlier checkpoint label for same_state, scroll_up or scroll_down assertions.")
    expectation: Literal["observe", "visible", "same_state", "scroll_up", "scroll_down"] = "observe"

    @model_validator(mode="after")
    def validate_observation(self):
        if any(value not in {"opacity", "transform", "visibility", "display", "position"}
                and re.fullmatch(r"--[A-Za-z0-9_-]{1,60}", value) is None for value in self.properties):
            raise ValueError("Only selected computed properties and bounded CSS custom properties are supported.")
        if self.action == "checkpoint" and (not self.target or not self.label):
            raise ValueError("A checkpoint requires a selector and unique label.")
        if self.action == "select_option" and (not self.target.strip() or "value" not in self.model_fields_set):
            raise ValueError("select_option requires an exact selector and explicit option value.")
        if self.action != "checkpoint" and (self.label or self.reference or self.expectation != "observe"):
            raise ValueError("Checkpoint assertions require a checkpoint action.")
        if self.expectation in {"same_state", "scroll_up", "scroll_down"} and not self.reference:
            raise ValueError("Comparison assertions require an earlier checkpoint reference.")
        if self.action == "key" and self.value not in {"ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", "Space"}:
            raise ValueError("Use a supported navigation key.")
        if self.action == "frame_timing" and self.timeout_ms > 2000:
            raise ValueError("Frame timing is bounded to 2000 milliseconds.")
        return self


class ProjectInspectionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_path: str = Field(min_length=1, max_length=32767)
    kind: Literal["browser", "desktop"]
    url: str | None = Field(default=None, max_length=2048,
        description="Browser only: required unauthenticated HTTP URL on localhost, 127.0.0.1 or ::1. Use null for desktop.")
    pid: int | None = Field(default=None, ge=1,
        description="Desktop only: existing project process ID. Must be null for browser inspection.")
    steps: list[InspectionStep] = Field(default_factory=list, max_length=12)
    width: int = Field(default=1280, ge=320, le=1920)
    height: int = Field(default=800, ge=240, le=1080)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    server_executable: str | None = Field(default=None, max_length=32767,
        description="Optional exact executable, or installed npm/npm.cmd, for a temporary local preview server; all owned children stop after inspection. Put run/dev/preview in server_arguments.")
    server_arguments: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_target(self):
        if self.kind == "browser":
            if self.url is None or self.pid is not None:
                raise ValueError("Browser inspection requires a loopback HTTP URL and no PID.")
            local_origin(self.url)
        elif self.pid is None or self.url is not None or self.server_executable is not None:
            raise ValueError("Desktop inspection requires an existing project process PID and no URL/server.")
        if self.kind == "desktop" and any(step.action in {"wait", "in_view", "model_loaded"} for step in self.steps):
            raise ValueError("Readiness and viewport actions are browser-only.")
        if self.kind == "desktop" and any(step.action in {"checkpoint", "key", "touch", "scroll_to", "frame_timing"} for step in self.steps):
            raise ValueError("Checkpoint and navigation actions are browser-only.")
        if self.kind == "desktop" and any(step.action == "select_option" for step in self.steps):
            raise ValueError("Native option selection is browser-only.")
        labels = set()
        for step in self.steps:
            if step.action == "checkpoint":
                if step.label in labels or step.reference and step.reference not in labels:
                    raise ValueError("Checkpoint labels must be unique and references must name an earlier checkpoint.")
                labels.add(step.label)
        if len(labels) >= MAX_INSPECTION_IMAGES:
            raise ValueError("Inspection supports at most four checkpoints plus the final screenshot.")
        if sum(step.action == "frame_timing" for step in self.steps) > 1:
            raise ValueError("Inspection supports one bounded frame timing capture.")
        if any(step.action in {"in_view", "model_loaded"} and not step.target for step in self.steps):
            raise ValueError("Viewport and model checks require an exact selector.")
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


def inspection_argument_error(details) -> str:
    """Expose schema constraints without echoing submitted values or unknown keys."""
    fields = set(ProjectInspectionArguments.model_fields) | set(InspectionStep.model_fields)
    rules = {
        "missing": "required field is missing",
        "extra_forbidden": "unexpected field; use the advertised schema",
        "literal_error": "use one of the advertised choices",
        "int_type": "must be an integer",
        "string_type": "must be text",
        "list_type": "must be a list",
        "model_type": "must be an object",
    }
    cross_field = {
        "Only selected computed properties and bounded CSS custom properties are supported.",
        "A checkpoint requires a selector and unique label.",
        "select_option requires an exact selector and explicit option value.",
        "Checkpoint assertions require a checkpoint action.",
        "Comparison assertions require an earlier checkpoint reference.",
        "Use a supported navigation key.",
        "Frame timing is bounded to 2000 milliseconds.",
        "Checkpoint and navigation actions are browser-only.",
        "Native option selection is browser-only.",
        "Checkpoint labels must be unique and references must name an earlier checkpoint.",
        "Inspection supports at most four checkpoints plus the final screenshot.",
        "Inspection supports one bounded frame timing capture.",
        "Browser inspection requires a loopback HTTP URL and no PID.",
        "Only unauthenticated local loopback HTTP previews are supported.",
        "Desktop inspection requires an existing project process PID and no URL/server.",
        "Readiness and viewport actions are browser-only.",
        "Viewport and model checks require an exact selector.",
        "Server arguments require a server executable.",
        "Server arguments exceed their bounds.",
    }
    hints = []
    for detail in details[:3]:
        location = detail.get("location", [])
        label = ".".join(part if part in fields or part.isdecimal() and len(part) <= 5
            else "field" for part in location) or "arguments"
        message = detail.get("message", "")
        reason = rules.get(detail.get("type"), "does not match the advertised schema")
        if (re.fullmatch(r"Input should be (?:greater|less) than(?: or equal to)? -?[0-9]+", message)
                or re.fullmatch(r"String should have (?:at most|at least) [0-9]+ characters", message)
                or re.fullmatch(r"List should have at most [0-9]+ items after validation, not [0-9]+", message)):
            reason = message
        elif message.removeprefix("Value error, ") in cross_field:
            reason = message.removeprefix("Value error, ")
        hints.append(f"{label}: {reason}")
    return ("Invalid inspection arguments. " + "; ".join(hints))[:500]


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
        raise Error(Code.INVALID_ARGUMENTS, "Use an exact absolute executable, without a command shell or batch wrapper. "
            "For npm, pass executable='npm' with arguments=['run','build'] (or server_executable='npm' and server_arguments for inspection). "
            "Other shell commands belong in shell.run, with workdir and command, when advertised.")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise Error(Code.NOT_FOUND, "The verification executable does not exist. Select its actual installed path. "
            "For npm scripts use executable='npm' with separate arguments, rather than inventing npm.exe.") from exc
    except (OSError, RuntimeError) as exc:
        raise Error(Code.INACCESSIBLE, "The verification executable could not be resolved safely.") from exc
    if not resolved.is_file() or resolved != path or path.is_symlink():
        raise Error(Code.INVALID_ARGUMENTS, "The executable must be a regular file at its canonical path.")
    return resolved


def project_command(raw: str, arguments: list[str]) -> tuple[list[str], tuple[Path, ...]]:
    """Resolve npm without executing a batch file; bind its real inputs to approval."""
    path = Path(raw)
    if path.name.lower() not in {"npm", "npm.cmd", "npm.exe"}:
        executable = _executable(raw)
        return [str(executable), *arguments], (executable,)
    if path.is_absolute() and path.suffix.lower() == ".exe":
        executable = _executable(raw)
        return [str(executable), *arguments], (executable,)
    if not path.is_absolute():
        if raw.lower() not in {"npm", "npm.cmd", "npm.exe"}:
            _executable(raw)  # Reject relative paths rather than guessing an installation.
        installed = shutil.which("npm.cmd")
        if installed is None:
            raise Error(Code.NOT_FOUND, "Installed npm.cmd was not found on PATH. Use the actual installed npm.cmd path, "
                "or an approved shell.run command; do not invent npm.exe or repeat the same unavailable command.")
        path = Path(installed)
    try:
        wrapper = path.resolve(strict=True)
        if not wrapper.is_file() or path.is_symlink():
            raise Error(Code.INVALID_ARGUMENTS, "The npm launcher must be a regular installed file.")
        cli = (wrapper.parent / "node_modules" / "npm" / "bin" / "npm-cli.js").resolve(strict=True)
        if not cli.is_file():
            raise FileNotFoundError
        node = wrapper.with_name("node.exe")
        if not node.is_file():
            installed_node = shutil.which("node.exe")
            if installed_node is None:
                raise FileNotFoundError
            node = Path(installed_node)
        executable = _executable(str(node.resolve(strict=True)))
    except FileNotFoundError:
        raise Error(Code.NOT_FOUND, "The npm launcher lacks its Node/npm-cli.js installation. "
            "Use the actual installed npm.cmd path or shell.run with the documented package command. "
            "Do not repeat this launcher or guess a nonexistent npm.exe.") from None
    except Error:
        raise
    except (OSError, RuntimeError):
        raise Error(Code.INACCESSIBLE, "The installed npm command could not be resolved safely.") from None
    return [str(executable), str(cli), *arguments], (wrapper, executable, cli)


def worker_environment() -> dict[str, str]:
    # Do not inherit provider keys or arbitrary project hooks from the host environment.
    names = {"systemroot", "windir", "temp", "tmp", "path", "pathext", "userprofile",
        "appdata", "localappdata", "programfiles", "programfiles(x86)", "programw6432", "comspec"}
    values = {key: value for key, value in os.environ.items() if key.lower() in names}
    values.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return values


def run_worker(command: list[str], *, cwd: Path, timeout: int, cancellation, limit=48 * 1024, windows_command_line=None,
               job_memory_bytes=1024 * 1024 * 1024) -> dict:
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
            windows_command_line=windows_command_line, job_memory_bytes=job_memory_bytes)
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
            command, inputs = project_command(executable,
                arguments.arguments if isinstance(arguments, ProjectVerificationArguments) else arguments.server_arguments)
            identities.extend((_file_identity(path) for path in inputs))
            identities.append(command)
        if getattr(arguments, "pid", None) is not None:
            pid, created, executable, working_directory = _process_identity(arguments.pid)
            if working_directory != project:
                raise Error(Code.PERMISSION_DENIED, "The desktop process must belong to the approved project directory.")
            identities.append((pid, created, executable))
        return hashlib.sha256(json.dumps(identities).encode()).hexdigest()

    def approval_preview(self, arguments, context):
        executable = getattr(arguments, "executable", None) or getattr(arguments, "server_executable", None)
        resolved = project_command(executable,
            arguments.arguments if isinstance(arguments, ProjectVerificationArguments) else arguments.server_arguments)[0] if executable else None
        return ("Run project verification/inspection. Project code and UI interactions can change files or application state.\n"
            + json.dumps({**arguments.model_dump(mode="json"), "resolved_command": resolved}, ensure_ascii=False, indent=2))

    def _authorize(self, arguments, context):
        project = self.permission_resource(arguments, context)
        if context.authorized_resource != str(project) or context.authorized_resource_identity != self.permission_resource_identity(arguments, context):
            raise Error(Code.PERMISSION_DENIED, "Verification requires approval for this exact project, executable and arguments.")
        return project


class ProjectVerifyCapability(_ProjectCapability):
    name = "project.verify"
    description = ("Run one explicitly approved project build or relevant test command with a 120-second deadline, "
        "48-KiB output limit and owned process cleanup. Use the project's documented build and selected tests; "
        "this runs project code with account access, not a security sandbox. When browser checks are in the requested scope, "
        "follow UI changes with project.inspect testing the reported interaction. Respect explicit instructions to skip checks. "
        "For Windows npm scripts, use executable='npm' and arguments=['run','build'] or ['test']; "
        "the tool resolves installed Node/npm-cli.js and shows the actual command for approval. "
        "A zero exit code proves only this command; failures/timeouts/unrun checks must be reported.")
    arguments_model = ProjectVerificationArguments

    def execute(self, arguments, context):
        project = self._authorize(arguments, context)
        command, _ = project_command(arguments.executable, arguments.arguments)
        result = run_worker(command,
            cwd=project, timeout=arguments.timeout_seconds, cancellation=context.cancellation)
        return {"project_path": str(project), "kind": arguments.kind, "evidence_version": 2,
            "passed": result["exit_code"] == 0 and result["stop_reason"] is None,
            "command": command, "content_is_untrusted": True, **result}


class ProjectInspectCapability(_ProjectCapability):
    def argument_error_message(self, details):
        return inspection_argument_error(details)

    name = "project.inspect"
    description = ("After building/testing, inspect a local browser preview or a project desktop process. "
        "Runs up to 12 approved interactions/checks in one session, captures up to four named checkpoints and a final screenshot. "
        "For scroll/animation complaints, capture initial, partial, complete and return states with relevant computed properties; "
        "use checkpoint assertions to test visibility, immediate reverse scrolling and restoration at the same position. "
        "Use native key/touch navigation and frame_timing for requested jerkiness investigations. "
        "Use wait (selector/state or a bounded delay) for intro completion, then in_view on the affected section. "
        "model_loaded checks model-viewer readiness; a loaded model still requires screenshot review for visual correctness. "
        "Browser inspection reports broken loaded references, console errors, overflow and actual scroll movement. "
        "If the preview is not already running, supply server_executable and server_arguments in this call. "
        "A server started by shell.run stops when that shell call returns. Desktop targets use automation IDs. "
        "Screenshots and observations are evidence for the inspected surface, not proof of all visual correctness.")
    arguments_model = ProjectInspectionArguments
    timeout_seconds = 75.0

    def execute(self, arguments, context):
        project = self._authorize(arguments, context)
        command = project_command(arguments.server_executable, arguments.server_arguments)[0] if arguments.server_executable else None
        folder = self.state_directory / "verification" / uuid4().hex
        folder.mkdir(parents=True)
        spec = folder / "inspection.json"
        spec.write_text(json.dumps({**arguments.model_dump(mode="json"), "project_path": str(project),
            "server_executable": command[0] if command else None,
            "server_arguments": command[1:] if command else [],
            "screenshot": str(folder / "screenshot.png"),
            "target_created_at": _process_created_at(arguments.pid),
            "browser_directory": str(self.state_directory / "playwright") if (self.state_directory / "playwright").is_dir() else None}), encoding="utf-8")
        worker = Path(__file__).resolve().parents[1] / "runtime" / "inspection_worker.py"
        try:
            result = run_worker([sys.executable, str(worker), str(spec)], cwd=Path(__file__).resolve().parents[2],
                timeout=arguments.timeout_seconds, cancellation=context.cancellation,
                job_memory_bytes=4 * 1024 * 1024 * 1024)
            if result["exit_code"] != 0 or result["stop_reason"] is not None:
                return {"project_path": str(project), "kind": arguments.kind, "passed": False, "evidence_version": 2,
                    "inspection_complete": False, "content_is_untrusted": True, **result}
            try:
                observations = json.loads(result["output"])
                if not isinstance(observations, dict):
                    raise ValueError
            except ValueError:
                raise Error(Code.INVALID_OUTPUT, "Inspection did not return structured observations.") from None
            screenshot = folder / "screenshot.png"
            checkpoints = observations.get("checkpoints", [])
            if not isinstance(checkpoints, list) or len(checkpoints) >= MAX_INSPECTION_IMAGES:
                raise Error(Code.INVALID_OUTPUT, "Inspection returned too many checkpoints.")
            labels = {step.label: step.target for step in arguments.steps if step.action == "checkpoint"}
            total_bytes, seen = 0, set()
            for index, checkpoint in enumerate(checkpoints):
                if (not isinstance(checkpoint, dict) or checkpoint.get("label") not in labels
                        or checkpoint["label"] in seen or checkpoint.get("target") != labels[checkpoint["label"]]):
                    raise Error(Code.INVALID_OUTPUT, "Inspection returned an unexpected checkpoint.")
                seen.add(checkpoint["label"])
                total_bytes += verify_screenshot(checkpoint, folder / f"checkpoint-{index}.png", arguments)
            if observations.get("screenshot_path") is not None:
                total_bytes += verify_screenshot(observations, screenshot, arguments)
                observations["visual_verification_status"] = "requires_review"
            if total_bytes > MAX_INSPECTION_IMAGE_BYTES:
                raise Error(Code.INVALID_OUTPUT, "Combined inspection screenshots exceed their transport bound.")
            return {"project_path": str(project), "kind": arguments.kind, "inspection_complete": True,
                "content_is_untrusted": True, **observations, "owned_processes_released": True, "evidence_version": 2}
        finally:
            spec.unlink(missing_ok=True)


def verify_screenshot(observation, expected, arguments):
    if observation.get("screenshot_path") != str(expected) or expected.is_symlink():
        raise Error(Code.INVALID_OUTPUT, "Inspection returned an unexpected screenshot.")
    from PIL import Image
    with expected.open("rb") as stream:
        pixels = stream.read(MAX_INSPECTION_IMAGE_BYTES + 1)
    if len(pixels) > MAX_INSPECTION_IMAGE_BYTES:
        raise Error(Code.INVALID_OUTPUT, "Inspection screenshot exceeds its transport bound.")
    with Image.open(BytesIO(pixels)) as captured:
        if captured.format != "PNG" or not (0 < captured.width <= arguments.width and 0 < captured.height <= arguments.height):
            raise Error(Code.INVALID_OUTPUT, "Inspection screenshot exceeds its viewport bounds.")
        observation["screenshot_dimensions"] = [captured.width, captured.height]
        captured.verify()
    observation["screenshot_sha256"] = hashlib.sha256(pixels).hexdigest()
    return len(pixels)


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
