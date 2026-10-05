"""Read a bounded package through handle-relative, non-following native opens."""
import ctypes
from ctypes import wintypes
from contextlib import contextmanager, ExitStack
import struct

from app.execution.windows_filesystem import (
    _kernel, _UnicodeString, _ObjectAttributes, _IoStatus, _FileInformation, directory_identity,
)
from app.runtime.skills.package_format import (
    ReferenceFile, MAX_REFERENCE_BYTES, MAX_REFERENCE_FILES, MAX_TOTAL_REFERENCE_BYTES,
    MAX_REFERENCE_DEPTH, validate_reference_path, validate_references,
)
from app.runtime.skills.loader import MAX_SKILL_SIZE
from app.runtime.skills.reference_reader import ReferenceReadError, ReferenceErrorCode


def _native():
    native = ctypes.WinDLL("ntdll")
    native.NtCreateFile.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(_ObjectAttributes), ctypes.POINTER(_IoStatus), ctypes.c_void_p,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG]
    native.NtCreateFile.restype = wintypes.LONG
    native.NtQueryDirectoryFile.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(_IoStatus), ctypes.c_void_p, wintypes.ULONG,
        wintypes.ULONG, ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_ubyte]
    native.NtQueryDirectoryFile.restype = wintypes.LONG
    native.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
    native.RtlNtStatusToDosError.restype = wintypes.ULONG
    return native


def _info(handle):
    info = _FileInformation()
    if not _kernel().GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if info.attributes & (0x400 | 0x4):
        raise ReferenceReadError(ReferenceErrorCode.UNSAFE)
    return info


def _identity(info):
    return f"{info.volume:x}:{info.index_high:x}:{info.index_low:x}"


@contextmanager
def _child(parent, name, *, directory, cancellation):
    cancellation.raise_if_cancelled()
    # Callers supply one validated component; never let NT interpret a path/ADS.
    if not name or name in (".", "..") or any(c in name for c in "\\/:"):
        raise ReferenceReadError(ReferenceErrorCode.UNSAFE)
    native = _native()
    buffer = ctypes.create_unicode_buffer(name)
    length = len(name.encode("utf-16-le"))
    unicode_name = _UnicodeString(length, length + 2, ctypes.cast(buffer, wintypes.LPWSTR))
    attributes = _ObjectAttributes(ctypes.sizeof(_ObjectAttributes), parent,
                                   ctypes.pointer(unicode_name), 0x40, None, None)
    handle, outcome = wintypes.HANDLE(), _IoStatus()
    # READ_DATA/LIST_DIRECTORY | READ_ATTRIBUTES | SYNCHRONIZE; no write access.
    # FILE_OPEN, OPEN_REPARSE_POINT, synchronous, directory/non-directory.
    status = native.NtCreateFile(ctypes.byref(handle), 0x100081, ctypes.byref(attributes),
        ctypes.byref(outcome), None, 0x80, 1, 1, 0x200020 | (1 if directory else 0x40), None, 0)
    if status < 0:
        raise ctypes.WinError(native.RtlNtStatusToDosError(status))
    try:
        info = _info(handle)
        if bool(info.attributes & 0x10) != directory:
            raise ReferenceReadError(ReferenceErrorCode.UNSAFE)
        cancellation.raise_if_cancelled()
        yield handle, _identity(info)
    finally:
        _kernel().CloseHandle(handle)


@contextmanager
def _root(path, cancellation):
    """Only the drive anchor uses a pathname; all descendants use parent handles."""
    kernel = _kernel()
    with ExitStack() as stack:
        cancellation.raise_if_cancelled()
        handle = kernel.CreateFileW(str(path.anchor), 0x100081, 1, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        stack.callback(kernel.CloseHandle, handle)
        identity = directory_identity(handle, drive_root=True)
        for name in path.parts[1:]:
            handle, identity = stack.enter_context(_child(handle, name, directory=True, cancellation=cancellation))
        yield handle, identity


def _entries(handle, cancellation):
    native, entries, restart = _native(), [], True
    # One FILE_DIRECTORY_INFORMATION at a time: fixed 64-byte header + UTF-16 name.
    while True:
        cancellation.raise_if_cancelled()
        buffer, outcome = ctypes.create_string_buffer(4096), _IoStatus()
        status = native.NtQueryDirectoryFile(handle, None, None, None, ctypes.byref(outcome),
                                             buffer, len(buffer), 1, 1, None, restart)
        restart = False
        if status & 0xFFFFFFFF == 0x80000006:  # STATUS_NO_MORE_FILES
            break
        if status < 0:
            raise ctypes.WinError(native.RtlNtStatusToDosError(status))
        used = outcome.information
        if not 64 <= used <= len(buffer):
            raise ReferenceReadError(ReferenceErrorCode.INACCESSIBLE)
        header = struct.unpack_from("<II6qII", buffer)
        length = header[9]
        if length % 2 or not 0 < length <= used - 64 or header[0] != 0:
            raise ReferenceReadError(ReferenceErrorCode.INACCESSIBLE)
        name = buffer.raw[64:64 + length].decode("utf-16-le")
        if name in (".", ".."):
            continue
        if len(entries) >= 2048:
            raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
        entries.append((name, header[8]))
    return tuple(sorted(entries))


def _read(handle, max_bytes, cancellation):
    cancellation.raise_if_cancelled()
    info = _info(handle)
    if ((info.size_high << 32) | info.size_low) > max_bytes:
        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
    kernel = _kernel()
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.ReadFile.restype = wintypes.BOOL
    chunks, total = [], 0
    while True:
        cancellation.raise_if_cancelled()
        buffer, count = ctypes.create_string_buffer(min(4096, max_bytes + 1 - total)), wintypes.DWORD()
        if not kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if not count.value:
            break
        chunks.append(buffer.raw[:count.value])
        total += count.value
        if total > max_bytes:
            raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
    cancellation.raise_if_cancelled()
    return b"".join(chunks)


def package_snapshot(root, cancellation):
    with ExitStack() as stack:
        root_handle, identity = stack.enter_context(_root(root, cancellation))
        opened, inventories, references, count, total = [], [], [], 0, 0
        def open_child(parent, name, directory):
            handle, child_id = stack.enter_context(_child(parent, name, directory=directory, cancellation=cancellation))
            opened.append((parent, name, directory, child_id))
            return handle
        main_handle = open_child(root_handle, "SKILL.md", False)
        main = _read(main_handle, MAX_SKILL_SIZE, cancellation)
        try:
            refs_handle = open_child(root_handle, "references", True)
        except FileNotFoundError:
            refs_handle = None
        def visit(handle, prefix, depth):
            nonlocal count, total
            entries = _entries(handle, cancellation)
            inventories.append((handle, entries))
            count += len(entries)
            if count > 2048:
                raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
            for name, attributes in entries:
                cancellation.raise_if_cancelled()
                if attributes & (0x400 | 0x4):
                    raise ReferenceReadError(ReferenceErrorCode.UNSAFE)
                relative = prefix + "/" + name
                if attributes & 0x10:
                    if depth >= MAX_REFERENCE_DEPTH:
                        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
                    validate_reference_path(relative + "/_directory.md")
                    visit(open_child(handle, name, True), relative, depth + 1)
                elif name.endswith(".md"):
                    validate_reference_path(relative)
                    if len(references) >= MAX_REFERENCE_FILES:
                        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
                    data = _read(open_child(handle, name, False), MAX_REFERENCE_BYTES, cancellation)
                    total += len(data)
                    if total > MAX_TOTAL_REFERENCE_BYTES:
                        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
                    references.append(ReferenceFile(relative, data))
        if refs_handle is not None:
            visit(refs_handle, "references", 0)
        references = tuple(sorted(references, key=lambda r: r.path))
        validate_references(references)
        # Directory handles can survive a rename. Recheck namespace membership,
        # while all supported files remain locked against writing/replacement.
        for handle, before in inventories:
            if _entries(handle, cancellation) != before:
                raise ReferenceReadError(ReferenceErrorCode.STALE)
        for parent, name, directory, before in opened:
            with _child(parent, name, directory=directory, cancellation=cancellation) as (_, current):
                if current != before:
                    raise ReferenceReadError(ReferenceErrorCode.STALE)
        if refs_handle is None:
            try:
                with _child(root_handle, "references", directory=True, cancellation=cancellation):
                    raise ReferenceReadError(ReferenceErrorCode.STALE)
            except FileNotFoundError:
                pass
        with _root(root, cancellation) as (_, current):
            if current != identity:
                raise ReferenceReadError(ReferenceErrorCode.STALE)
        cancellation.raise_if_cancelled()
        return identity, main, references
