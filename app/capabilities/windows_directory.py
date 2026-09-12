from __future__ import annotations

import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import os
from pathlib import Path


class _FileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("created", wintypes.FILETIME),
        ("accessed", wintypes.FILETIME),
        ("written", wintypes.FILETIME),
        ("volume", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    ]


class _UnicodeString(ctypes.Structure):
    _fields_ = [("length", wintypes.USHORT), ("maximum", wintypes.USHORT),
                ("buffer", wintypes.LPWSTR)]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [("length", wintypes.ULONG), ("root", wintypes.HANDLE),
                ("name", ctypes.POINTER(_UnicodeString)), ("attributes", wintypes.ULONG),
                ("security", ctypes.c_void_p), ("quality", ctypes.c_void_p)]


class _IoStatus(ctypes.Structure):
    _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]


def _kernel():
    if os.name != "nt":
        raise OSError("Folder creation requires Windows.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE,
                                                ctypes.POINTER(_FileInformation)]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    return kernel


def directory_identity(handle, *, drive_root: bool = False) -> str:
    info = _FileInformation()
    if not _kernel().GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if (not info.attributes & 0x10 or info.attributes & 0x400
            or (info.attributes & 0x4 and not drive_root)):
        raise PermissionError("Reparse points and system directories are protected.")
    return f"{info.volume:x}:{info.index_high:x}:{info.index_low:x}"


@contextmanager
def pinned_parent(path: Path, cancellation):
    """Hold every ancestor without write/delete sharing during the filesystem operation."""
    kernel = _kernel()
    handles = []
    try:
        for ancestor in reversed(path.parents):
            cancellation.raise_if_cancelled()
            handle = kernel.CreateFileW(
                str(ancestor), 0x80, 0x1, None, 3, 0x02000000 | 0x00200000, None
            )
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            identity = directory_identity(handle, drive_root=ancestor == Path(ancestor.anchor))
        yield handles[-1], identity
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def create_child_directory(parent_handle, name: str) -> str:
    """Atomically create one new child and inspect its returned handle, without reopening a path."""
    native = ctypes.WinDLL("ntdll")
    native.NtCreateFile.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(_ObjectAttributes), ctypes.POINTER(_IoStatus), ctypes.c_void_p,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p,
        wintypes.ULONG]
    native.NtCreateFile.restype = wintypes.LONG
    native.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
    native.RtlNtStatusToDosError.restype = wintypes.ULONG
    buffer = ctypes.create_unicode_buffer(name)
    length = len(name.encode("utf-16-le"))
    unicode_name = _UnicodeString(length, length + 2, ctypes.cast(buffer, wintypes.LPWSTR))
    attributes = _ObjectAttributes(ctypes.sizeof(_ObjectAttributes), parent_handle,
                                   ctypes.pointer(unicode_name), 0x40, None, None)
    handle = wintypes.HANDLE()
    outcome = _IoStatus()
    # FILE_CREATE fails on collisions; DIRECTORY_FILE and SYNCHRONOUS_IO_NONALERT return a directory.
    status = native.NtCreateFile(ctypes.byref(handle), 0x100080, ctypes.byref(attributes),
        ctypes.byref(outcome), None, 0x80, 1, 2, 0x21, None, 0)
    if status < 0:
        raise ctypes.WinError(native.RtlNtStatusToDosError(status))
    try:
        if outcome.information != 2:
            raise RuntimeError("The folder creation outcome was not verified.")
        try:
            return directory_identity(handle)
        except OSError as exc:
            raise RuntimeError("The created folder could not be verified.") from exc
    finally:
        _kernel().CloseHandle(handle)
