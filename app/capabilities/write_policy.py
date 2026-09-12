from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import re

from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError
from app.capabilities.host_access import _windows_local_drive_roots
from app.capabilities.path_policy import is_path_within


_PROTECTED_NAMES = {
    "windows", "windows.old", "program files", "program files (x86)", "programdata",
    "boot", "efi", "recovery", "$recycle.bin", "system volume information",
    "$windows.~bt", "$windows.~ws", "msocache", "config.msi",
}
_DEVICE_NAME = re.compile(r"^(?:con|prn|aux|nul|com[1-9\u00b9\u00b2\u00b3]|lpt[1-9\u00b9\u00b2\u00b3])(?:[.]|$)", re.I)


@dataclass(frozen=True)
class HostWritePolicy:
    application_root: Path
    protected_roots: tuple[Path, ...] = ()

    def __post_init__(self):
        if os.name != "nt":
            raise ValueError("Host writes require Windows.")
        root = self.application_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("The application root must be an existing directory.")
        protected = [root, *self.protected_roots]
        for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                     "ProgramData", "LOCALAPPDATA", "APPDATA"):
            value = os.environ.get(name)
            if value:
                protected.append(Path(value).resolve(strict=False))
        object.__setattr__(self, "application_root", root)
        object.__setattr__(self, "protected_roots", tuple(p.resolve(strict=False) for p in protected))

    def resolve_new_directory(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="Folder creation",
            location_hint="Choose a folder inside an existing directory, below the drive root.",
        )

    def resolve_text_file(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="Text writing",
            location_hint="Choose a file inside an existing directory, below the drive root.",
        )

    def resolve_copy_source(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="File copy source",
            location_hint="Choose a source file inside an existing directory, below the drive root.",
        )

    def resolve_copy_destination(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="File copy destination",
            location_hint="Choose a destination file inside an existing directory, below the drive root.",
        )

    def resolve_move_source(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="File move source",
            location_hint="Choose a source file inside an existing directory, below the drive root.",
        )

    def resolve_move_destination(self, raw: str) -> Path:
        return self._resolve_write_path(
            raw,
            action="File move destination",
            location_hint="Choose a destination file inside an existing directory, below the drive root.",
        )

    def _resolve_write_path(self, raw: str, *, action: str, location_hint: str) -> Path:
        path = PureWindowsPath(raw)
        if (not path.is_absolute() or not re.fullmatch(r"[A-Za-z]:", path.drive)
                or raw.startswith(("\\\\", "//"))):
            self._deny(f"{action} requires an exact absolute local-drive path.")
        if len(path.parts) < 3 or len(path.parts) > 64:
            self._deny(location_hint)
        for part in path.parts[1:]:
            if (part in {".", ".."} or part.endswith((".", " ")) or _DEVICE_NAME.match(part)
                    or re.search(r'[<>:"|?*\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]', part)):
                self._deny("The requested write path contains an unsafe or ambiguous name.")
        candidate = Path(path)
        try:
            canonical = candidate.resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE,
                "The write path could not be resolved safely.") from exc
        if os.path.normcase(str(candidate)) != os.path.normcase(str(canonical)):
            self._deny("Aliases and redirected folder paths are not allowed for writes.")
        if not any(is_path_within(canonical, root) for root in _windows_local_drive_roots()):
            self._deny("The target is not on an enabled local filesystem drive.")
        if (path.parts[1].casefold() in _PROTECTED_NAMES
                or any(part.casefold() == "appdata" for part in path.parts[1:])
                or any(is_path_within(canonical, root) for root in self.protected_roots)):
            self._deny("O.R.S.I, operating-system, recovery, and application folders are protected.")
        return canonical

    @staticmethod
    def _deny(message: str):
        raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED, message)
