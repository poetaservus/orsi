"""Host-local, per-run Office registration discovery. Never starts applications."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from threading import RLock


OFFICE_REGISTRATIONS = {
    "excel": ("Excel.Application", "EXCEL.EXE"),
    "word": ("Word.Application", "WINWORD.EXE"),
    "powerpoint": ("PowerPoint.Application", "POWERPNT.EXE"),
}


@dataclass(frozen=True)
class OfficeInstallation:
    application: str
    clsid: str
    executable: Path | None


def discover_office():
    import winreg

    def read(hive, key, view):
        try:
            with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                value, kind = winreg.QueryValueEx(handle, None)
                return value if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) else None
        except OSError:
            return None

    def executable(value, name):
        if not isinstance(value, str) or len(value) > 32767:
            return None
        value = os.path.expandvars(value.strip().strip('"'))
        path = Path(value)
        try:
            if path.is_absolute() and path.name.lower() == name.lower() and path.is_file():
                return path.resolve(strict=True)
        except OSError:
            pass
        return None

    result = []
    for application, (progid, name) in OFFICE_REGISTRATIONS.items():
        clsid, candidate = None, None
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                value = read(hive, rf"Software\Classes\{progid}\CLSID", view)
                if value:
                    # Parse locally, without activating the registered COM class.
                    try:
                        from uuid import UUID
                        clsid = str(UUID(value.strip("{}")))
                    except (ValueError, AttributeError):
                        continue
                candidate = candidate or executable(read(hive,
                    rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}", view), name)
        if clsid is None:
            continue
        if candidate is None:
            # Fixed, bounded candidates only; no drive scan or recursive search.
            for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
                directory = os.environ.get(variable)
                if not directory:
                    continue
                for version in ("Office16", "Office15", "Office14"):
                    for suffix in (f"Microsoft Office/root/{version}", f"Microsoft Office/{version}"):
                        candidate = executable(str(Path(directory) / suffix / name), name)
                        if candidate is not None:
                            break
                    if candidate is not None:
                        break
                if candidate is not None:
                    break
        result.append(OfficeInstallation(application, clsid, candidate))
    return tuple(result)


class OfficeDiscovery:
    """Kept by the application, so bridge reconnects reuse this run's inventory."""
    def __init__(self, probe=discover_office):
        self._probe, self._value, self._lock = probe, None, RLock()
        self.runs = 0

    def get(self, *, refresh=False):
        with self._lock:
            if refresh or self._value is None:
                self._value = tuple(self._probe())
                self.runs += 1
            return self._value
