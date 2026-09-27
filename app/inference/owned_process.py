"""Windows child ownership established atomically by CreateProcessW.

JOB_LIST avoids the orphan window in Popen + AssignProcessToJobObject,
including the suspended-child variant. Only this owner holds the job handle.
https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache
import os
import subprocess
from threading import RLock
from time import monotonic, sleep
import weakref


class ProcessOwnershipError(OSError):
    """No child was started because guaranteed ownership was unavailable."""


class _BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_int64), ("job_time", C.c_int64),
                ("flags", W.DWORD), ("min_working_set", C.c_size_t),
                ("max_working_set", C.c_size_t), ("active_limit", W.DWORD),
                ("affinity", C.c_size_t), ("priority", W.DWORD),
                ("scheduling", W.DWORD)]


class _ExtendedLimits(C.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", C.c_uint64 * 6),
                ("process_memory", C.c_size_t), ("job_memory", C.c_size_t),
                ("peak_process_memory", C.c_size_t), ("peak_job_memory", C.c_size_t)]


class _StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR),
                ("desktop", W.LPWSTR), ("title", W.LPWSTR),
                ("x", W.DWORD), ("y", W.DWORD), ("x_size", W.DWORD),
                ("y_size", W.DWORD), ("x_chars", W.DWORD), ("y_chars", W.DWORD),
                ("fill", W.DWORD), ("flags", W.DWORD), ("show", W.WORD),
                ("reserved_size", W.WORD), ("reserved_bytes", C.c_void_p),
                ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class _StartupInfoEx(C.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", C.c_void_p)]


class _ProcessInfo(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


@lru_cache(maxsize=1)
def _api():
    kernel = C.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([C.c_void_p, W.LPCWSTR], W.HANDLE),
        "SetInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
        "InitializeProcThreadAttributeList": (
            [C.c_void_p, W.DWORD, W.DWORD, C.POINTER(C.c_size_t)], W.BOOL),
        "UpdateProcThreadAttribute": (
            [C.c_void_p, W.DWORD, C.c_size_t, C.c_void_p, C.c_size_t,
             C.c_void_p, C.c_void_p], W.BOOL),
        "DeleteProcThreadAttributeList": ([C.c_void_p], None),
        "CreateProcessW": ([W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL,
                            W.DWORD, C.c_void_p, W.LPCWSTR,
                            C.POINTER(_StartupInfoEx), C.POINTER(_ProcessInfo)], W.BOOL),
        "CloseHandle": ([W.HANDLE], W.BOOL),
        "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
        "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
        "TerminateProcess": ([W.HANDLE, W.UINT], W.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


def _release_handles(api, job, process):
    # Windows terminates every descendant when the last private job handle closes.
    api.CloseHandle(job)
    api.CloseHandle(process)


class OwnedProcess:
    """Small Popen-compatible lifecycle surface; never stores command/credentials."""

    def __init__(self, api, job, info):
        self.pid = int(info.pid)
        self.returncode = None
        self._api, self._handle = api, info.process
        self._lock = RLock()
        self._release = weakref.finalize(self, _release_handles, api, job, info.process)

    def poll(self):
        with self._lock:
            if self.returncode is not None:
                return self.returncode
            status = self._api.WaitForSingleObject(self._handle, 0)
            if status == 258:  # WAIT_TIMEOUT
                return None
            if status != 0:
                raise C.WinError(C.get_last_error())
            code = W.DWORD()
            if not self._api.GetExitCodeProcess(self._handle, C.byref(code)):
                raise C.WinError(C.get_last_error())
            self.returncode = int(code.value)
            return self.returncode

    def wait(self, timeout=None):
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            code = self.poll()
            if code is not None:
                return code
            if deadline is not None and monotonic() >= deadline:
                raise subprocess.TimeoutExpired("owned local server", timeout)
            sleep(0.01)

    def terminate(self):
        with self._lock:
            if self.poll() is None:
                if not self._api.TerminateProcess(self._handle, 1) and self.poll() is None:
                    raise C.WinError(C.get_last_error())

    kill = terminate

    def close(self):
        with self._lock:
            if self._release.alive:
                code = self.poll()
                self._release()
                self.returncode = code if code is not None else 1


def start_owned_process(command, *, cwd, env, stderr=None):
    """Start hidden, with only explicit standard handles inherited (Windows 10+).

    stderr is an optional file descriptor. Ownership failure never falls back to
    launching an unguarded server. Neither the command nor environment is logged.
    """
    if os.name != "nt":
        raise ProcessOwnershipError("Local server ownership requires Windows 10 or later.")
    import msvcrt

    api = _api()
    job = api.CreateJobObjectW(None, None)  # unnamed and non-inheritable
    if not job:
        raise ProcessOwnershipError("Could not create the local server ownership guard.")
    limits = _ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    attributes = None
    initialized = False
    descriptors = []
    info = _ProcessInfo()
    try:
        if not api.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)):
            raise ProcessOwnershipError("Could not configure the local server ownership guard.")
        size = C.c_size_t()
        api.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
        attributes = C.create_string_buffer(size.value)
        if not api.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)):
            raise ProcessOwnershipError("Could not initialize local server ownership attributes.")
        initialized = True
        jobs = (W.HANDLE * 1)(job)
        if not api.UpdateProcThreadAttribute(attributes, 0, 0x2000D, jobs,
                                             C.sizeof(jobs), None, None):
            raise ProcessOwnershipError("Could not register atomic local server ownership.")
        null_fd = os.open(os.devnull, os.O_RDWR)
        descriptors.append(null_fd)
        error_fd = null_fd
        if stderr is not None:
            error_fd = os.dup(stderr)
            descriptors.append(error_fd)
        handles = [msvcrt.get_osfhandle(fd) for fd in descriptors]
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        inherited = (W.HANDLE * len(handles))(*handles)
        if not api.UpdateProcThreadAttribute(attributes, 0, 0x20002, inherited,
                                             C.sizeof(inherited), None, None):
            raise ProcessOwnershipError("Could not restrict local server inherited handles.")
        startup = _StartupInfoEx()
        startup.startup.cb = C.sizeof(startup)
        startup.startup.flags = 0x101  # STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
        startup.startup.show = 0  # SW_HIDE
        startup.startup.stdin = startup.startup.stdout = handles[0]
        startup.startup.stderr = msvcrt.get_osfhandle(error_fd)
        startup.attributes = C.cast(attributes, C.c_void_p)
        environment = C.create_unicode_buffer("\0".join(
            f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper())
        ) + "\0\0")
        command_line = C.create_unicode_buffer(subprocess.list2cmdline(command))
        flags = 0x08000000 | 0x00080000 | 0x00000400
        # CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
        if not api.CreateProcessW(str(command[0]), command_line, None, None, True,
                                  flags, environment, str(cwd), C.byref(startup), C.byref(info)):
            raise C.WinError(C.get_last_error())
        process = OwnedProcess(api, job, info)
        job = None  # ownership transferred; all other handles remain scoped here
        info.process = None
        return process
    finally:
        if initialized:
            api.DeleteProcThreadAttributeList(attributes)
        for fd in descriptors:
            os.close(fd)
        if info.thread:
            api.CloseHandle(info.thread)
        if job:
            api.CloseHandle(job)
        if info.process:
            api.CloseHandle(info.process)
