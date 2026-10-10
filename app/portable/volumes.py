"""Name external Windows volumes without changing internal or system disks."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import struct

from app.portable.identity import node_name


@dataclass(frozen=True)
class Volume:
    root: str
    identity: str
    filesystem: str
    drive_type: int
    bus_type: int = 0


@dataclass(frozen=True)
class DriveLabelResult:
    label: str | None = None
    message: str = ""


@dataclass(frozen=True)
class DriveLabelPlan:
    volume: Volume
    label: str


class WindowsVolumes:
    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "GetVolumePathNameW": ([wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD], wintypes.BOOL),
            "GetVolumeNameForVolumeMountPointW": ([wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD], wintypes.BOOL),
            "GetVolumeInformationW": ([wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                wintypes.LPWSTR, wintypes.DWORD], wintypes.BOOL),
            "GetDriveTypeW": ([wintypes.LPCWSTR], wintypes.UINT),
            "GetWindowsDirectoryW": ([wintypes.LPWSTR, wintypes.UINT], wintypes.UINT),
            "CreateFileW": ([wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE], wintypes.HANDLE),
            "DeviceIoControl": ([wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "SetVolumeLabelW": ([wintypes.LPCWSTR, wintypes.LPCWSTR], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result

    def _require(self, result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def system_directory(self):
        path = ctypes.create_unicode_buffer(32768)
        length = self.api.GetWindowsDirectoryW(path, len(path))
        self._require(0 < length < len(path))
        return path.value

    def _bus_type(self, identity):
        # Metadata access only: no raw disk read/write rights are requested.
        handle = self.api.CreateFileW(identity.rstrip("\\"), 0, 3, None, 3, 0, None)
        if handle == wintypes.HANDLE(-1).value:
            return 0
        try:
            query = ctypes.create_string_buffer(struct.pack("<III", 0, 0, 0))
            descriptor, returned = ctypes.create_string_buffer(4096), wintypes.DWORD()
            if not self.api.DeviceIoControl(handle, 0x2D1400, query, 12, descriptor,
                    len(descriptor), ctypes.byref(returned), None) or returned.value < 32:
                return 0
            # STORAGE_DEVICE_DESCRIPTOR.BusType follows four string offsets.
            return struct.unpack_from("<I", descriptor.raw, 28)[0]
        finally:
            self.api.CloseHandle(handle)

    def inspect(self, path):
        root, identity, filesystem = (ctypes.create_unicode_buffer(32768) for _ in range(3))
        self._require(self.api.GetVolumePathNameW(str(path), root, len(root)))
        self._require(self.api.GetVolumeNameForVolumeMountPointW(root.value, identity, len(identity)))
        serial, maximum, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        self._require(self.api.GetVolumeInformationW(identity.value, None, 0, ctypes.byref(serial),
            ctypes.byref(maximum), ctypes.byref(flags), filesystem, len(filesystem)))
        drive_type = self.api.GetDriveTypeW(root.value)
        return Volume(root.value, identity.value, filesystem.value, drive_type,
                      self._bus_type(identity.value) if drive_type == 3 else 0)

    def set_label(self, identity, label):
        self._require(self.api.SetVolumeLabelW(identity, label))


def _windows_api():
    return WindowsVolumes() if os.name == "nt" else None


def prepare_drive_label(destination, application_root, number):
    """Capture a stable volume identity before copying. No labels change here."""
    try:
        api = _windows_api()
        if api is None:
            return DriveLabelResult(message="Automatic drive naming is available on Windows.")
        volume = api.inspect(destination)
        protected = {api.inspect(application_root).identity.casefold(),
                     api.inspect(api.system_directory()).identity.casefold()}
        if volume.identity.casefold() in protected:
            return DriveLabelResult(message="Drive name unchanged: this drive contains O.R.S.I or Windows.")
        if not (volume.drive_type == 2 or volume.drive_type == 3 and volume.bus_type in {4, 7, 12, 13}):
            return DriveLabelResult(message="Drive name unchanged: the destination is not recognized as external storage.")
        filesystem = volume.filesystem.upper()
        if filesystem == "NTFS":
            label = node_name(number)
        elif filesystem in {"EXFAT", "FAT", "FAT32", "FAT16"}:
            label = f"ORSI {number:03d}"  # FAT and exFAT volume labels allow 11 characters.
        else:
            return DriveLabelResult(message="Automatic drive naming is unavailable for this file system.")
        return DriveLabelPlan(volume, label)
    except OSError:
        return DriveLabelResult(message="Windows could not identify the destination drive; its name will stay unchanged.")


def finish_drive_label(plan, destination):
    """Rename only after publication, addressing the captured volume by GUID."""
    if isinstance(plan, DriveLabelResult):
        return plan
    try:
        api = _windows_api()
        current = api.inspect(destination) if api is not None else None
        if current is None or current.identity.casefold() != plan.volume.identity.casefold():
            return DriveLabelResult(message="The destination drive changed. Its name was left unchanged.")
        api.set_label(plan.volume.identity, plan.label)
        confirmed = "Drive named “" + plan.label + "”."
        if plan.volume.filesystem.upper() != "NTFS":
            confirmed += " This file system requires a shorter name."
        return DriveLabelResult(plan.label, confirmed)
    except OSError:
        return DriveLabelResult(message="The node is ready, but Windows could not rename the drive. You can rename it in File Explorer.")
