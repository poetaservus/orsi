from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (Capability, CapabilityContext, CapabilityErrorCode,
    CapabilityExecutionError, ExecutionIsolation, PermissionClass)
from app.capabilities.windows_directory import file_identity, pinned_parent
from app.capabilities.write_policy import HostWritePolicy


_MAX_TRASH_BYTES = 16 * 1024 * 1024


class FilesystemTrashArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=32767,
                      description="Exact absolute local-drive path of the regular file to send to trash.")


class FilesystemTrashCapability(Capability[FilesystemTrashArguments]):
    name = "filesystem.trash"
    description = "Send one bounded regular file to the Windows Recycle Bin after approval."
    arguments_model = FilesystemTrashArguments
    permission = PermissionClass.WRITE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 6.0

    def __init__(self, policy: HostWritePolicy):
        if not isinstance(policy, HostWritePolicy):
            raise TypeError("File trashing requires a separate HostWritePolicy.")
        self.policy = policy

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        return self._path(arguments)

    def permission_resource_identity(self, arguments, context) -> str:
        target = self._path(arguments)
        try:
            snapshot = _target_snapshot(target, context.cancellation)
            with pinned_parent(target, context.cancellation) as (_, parent_identity):
                return _precondition_digest(snapshot, parent_identity)
        except OSError as exc:
            _raise_path_error(exc, target=target)

    def approval_preview(self, arguments, context) -> str:
        del context
        target = self._path(arguments)
        return "\n".join((
            f"Path: {target}",
            "Type: regular file",
            "The file will be sent to the Windows Recycle Bin.",
        ))

    def execute(self, arguments: FilesystemTrashArguments, context: CapabilityContext) -> dict:
        target = self._path(arguments)
        trashed = False
        if (context.authorized_resource is None or target != Path(context.authorized_resource)
                or context.authorized_resource_identity is None):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "File trashing requires exact runtime authorization.")
        try:
            snapshot = _target_snapshot(target, context.cancellation)
            with pinned_parent(target, context.cancellation) as (_, parent_identity):
                binding = _precondition_digest(snapshot, parent_identity)
                if binding != context.authorized_resource_identity:
                    raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                        "The file changed after the preview. Request a new approval.")
            context.cancellation.raise_if_cancelled()
            trash_file(target, context.cancellation)
            trashed = True
            context.cancellation.raise_if_cancelled()
            if os.path.lexists(target):
                raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE,
                    "The file was not moved to the Recycle Bin.")
            return {"path": str(target), "trashed": True, "placement": "recycle_bin",
                    "bytes_trashed": snapshot["size_bytes"],
                    "sha256": snapshot["sha256"], "identity": snapshot["identity"]}
        except OSError as exc:
            if trashed:
                raise RuntimeError("The trashed file state could not be verified after placement.") from exc
            _raise_path_error(exc, target=target)

    def _path(self, arguments: FilesystemTrashArguments) -> Path:
        return self.policy.resolve_trash_target(arguments.path)


def trash_file(path: Path, cancellation) -> None:
    cancellation.raise_if_cancelled()
    try:
        _recycle_with_ifileoperation(path)
    except OSError as exc:
        if not os.path.lexists(path):
            raise RuntimeError("The file disappeared while the trash outcome could not be verified.") from exc
        raise


def _target_snapshot(path: Path, cancellation) -> dict[str, object]:
    if path.is_dir():
        raise IsADirectoryError("Only regular files can be sent to trash in this checkpoint.")
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
            if total > _MAX_TRASH_BYTES:
                raise CapabilityExecutionError(CapabilityErrorCode.OUTPUT_LIMITED,
                    "File trashing is limited to 16 MiB in this checkpoint.")
            digest.update(chunk)
    if file_identity(path) != identity:
        raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
            "The file changed while it was being inspected.")
    return {"identity": identity, "size_bytes": total, "sha256": digest.hexdigest()}


def _precondition_digest(snapshot: dict[str, object], parent_identity: str) -> str:
    return hashlib.sha256(json.dumps({
        "destination": "windows_recycle_bin",
        "parent": parent_identity,
        "target": snapshot,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


class _GUID(ctypes.Structure):
    _fields_ = (("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8))


def _guid(value: str) -> _GUID:
    raw = uuid.UUID(value)
    data4 = (ctypes.c_ubyte * 8).from_buffer_copy(raw.bytes[8:])
    return _GUID(raw.time_low, raw.time_mid, raw.time_hi_version, data4)


_CLSID_FILE_OPERATION = _guid("3ad05575-8857-4850-9277-11b85bdb8e09")
_IID_IFILE_OPERATION = _guid("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8")
_IID_ISHELL_ITEM = _guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = 0x80010106
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_FOFX_RECYCLEONDELETE = 0x00080000


def _recycle_with_ifileoperation(path: Path) -> None:
    if os.name != "nt":
        raise OSError("File trashing requires Windows.")
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = ()
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = (ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    ole32.CoCreateInstance.restype = ctypes.c_long
    shell32.SHCreateItemFromParsingName.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p,
                                                   ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    initialized = False
    operation = ctypes.c_void_p()
    item = ctypes.c_void_p()
    try:
        hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        if _failed(hr) and _unsigned(hr) != _RPC_E_CHANGED_MODE:
            raise OSError(f"COM initialization failed: HRESULT 0x{_unsigned(hr):08x}")
        initialized = not _failed(hr)
        _check_hresult(ole32.CoCreateInstance(ctypes.byref(_CLSID_FILE_OPERATION), None,
            _CLSCTX_INPROC_SERVER, ctypes.byref(_IID_IFILE_OPERATION), ctypes.byref(operation)))
        _check_hresult(shell32.SHCreateItemFromParsingName(str(path), None,
            ctypes.byref(_IID_ISHELL_ITEM), ctypes.byref(item)))
        flags = (_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_NOERRORUI
                 | _FOF_SILENT | _FOFX_RECYCLEONDELETE)
        _check_hresult(_com_method(operation, 5, wintypes.DWORD)(operation, flags))
        _check_hresult(_com_method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, item, None))
        _check_hresult(_com_method(operation, 21)(operation))
        aborted = wintypes.BOOL()
        _check_hresult(_com_method(operation, 22, ctypes.POINTER(wintypes.BOOL))(operation, ctypes.byref(aborted)))
        if aborted.value:
            raise RuntimeError("The shell reported an aborted trash operation after dispatch.")
    finally:
        _release(item)
        _release(operation)
        if initialized:
            ole32.CoUninitialize()


def _com_method(instance: ctypes.c_void_p, index: int, *argtypes):
    table = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def _release(instance: ctypes.c_void_p) -> None:
    if not instance:
        return
    table = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(table[2])(instance)


def _failed(hr: int) -> bool:
    return ctypes.c_long(hr).value < 0


def _unsigned(hr: int) -> int:
    return ctypes.c_ulong(hr).value


def _check_hresult(hr: int) -> None:
    if _failed(hr):
        raise OSError(f"Shell file operation failed: HRESULT 0x{_unsigned(hr):08x}")


def _raise_path_error(exc: OSError, *, target: Path):
    if isinstance(exc, FileNotFoundError):
        code, message = CapabilityErrorCode.NOT_FOUND, "The file does not exist."
    elif isinstance(exc, IsADirectoryError) or target.is_dir():
        code, message = CapabilityErrorCode.INVALID_ARGUMENTS, "Only regular files can be sent to trash in this checkpoint."
    else:
        code, message = CapabilityErrorCode.INACCESSIBLE, "The file path is protected, redirected, unavailable, or could not be sent to the Recycle Bin."
    raise CapabilityExecutionError(code, message) from exc
