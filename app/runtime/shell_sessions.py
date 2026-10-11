"""In-memory shell sessions owned by one capability runtime, never by a PID lookup."""
from __future__ import annotations

from collections import OrderedDict
import os
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityExecutionError as Error
from app.runtime.owned_process import start_owned_process


MAX_ACTIVE_SESSIONS = 4
MAX_SESSION_RECORDS = 32
OUTPUT_BUFFER_BYTES = 64 * 1024
OUTPUT_PAGE_BYTES = 8 * 1024


class ShellSession:
    def __init__(self, command, *, workdir, shell, lifetime, env, windows_command_line=None):
        self.id = "shell-" + uuid4().hex
        self.workdir, self.shell = Path(workdir), shell
        self.deadline = monotonic() + lifetime
        self._lock, self._stop, self._finished = RLock(), Event(), Event()
        self._data, self._total = bytearray(), 0
        self._reason, self._exit_code, self._released = None, None, False
        read_fd, write_fd = os.pipe()
        try:
            self._process = start_owned_process(command, cwd=workdir, env=env,
                stdout=write_fd, stderr=write_fd, windows_command_line=windows_command_line)
        except BaseException:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)

        def drain():
            with os.fdopen(read_fd, "rb", buffering=0) as stream:
                while chunk := stream.read(4096):
                    with self._lock:
                        self._total += len(chunk)
                        self._data.extend(chunk)
                        if len(self._data) > OUTPUT_BUFFER_BYTES:
                            del self._data[:-OUTPUT_BUFFER_BYTES]

        self._reader = Thread(target=drain, daemon=True, name="orsi-shell-output")
        self._watcher = Thread(target=self._watch, daemon=True, name="orsi-shell-owner")
        try:
            self._reader.start()
            self._watcher.start()
        except BaseException:
            self._process.close()
            if self._reader.ident is not None:
                self._reader.join(5)
            else:
                os.close(read_fd)
            raise

    def _watch(self):
        try:
            while not self._stop.is_set():
                code = self._process.poll()
                if code is not None:
                    with self._lock:
                        self._reason, self._exit_code = "exited", code
                    break
                if monotonic() >= self.deadline:
                    with self._lock:
                        self._reason = "lifetime_expired"
                    break
                self._stop.wait(0.025)
        except Exception:
            # No exception/command/output contents enter lifecycle diagnostics.
            with self._lock:
                self._reason = "cleanup_failed"
        finally:
            try:
                self._process.close()  # Also closes descendants after exit or a monitor error.
                self._reader.join(5)
                with self._lock:
                    self._released = not self._reader.is_alive()
                    if not self._released:
                        self._reason = "cleanup_failed"
            except Exception:
                with self._lock:
                    self._reason = "cleanup_failed"
            self._finished.set()

    @property
    def finished(self):
        return self._finished.is_set()

    def request_stop(self, reason="stopped"):
        with self._lock:
            if self._reason is None:
                self._reason = reason
            self._stop.set()

    def stop(self, reason="stopped"):
        self.request_stop(reason)
        if not self._finished.wait(12):
            raise Error(Code.OUTCOME_UNKNOWN, "The managed shell session has not confirmed process cleanup.")
        with self._lock:
            if not self._released:
                raise Error(Code.OUTCOME_UNKNOWN, "The managed shell session could not confirm process cleanup.")

    def wait_initial(self, milliseconds, cancellation):
        deadline = monotonic() + milliseconds / 1000
        while not self.finished and monotonic() < deadline:
            cancellation.raise_if_cancelled()
            self._finished.wait(min(0.025, max(0, deadline - monotonic())))
        cancellation.raise_if_cancelled()

    def snapshot(self, offset=0):
        with self._lock:
            oldest = self._total - len(self._data)
            if offset > self._total:
                raise Error(Code.INVALID_ARGUMENTS, "The output offset is beyond the session's recorded output.")
            start = max(offset, oldest)
            end = min(start + OUTPUT_PAGE_BYTES, self._total)
            data = bytes(self._data[start - oldest:end - oldest])
            reason, finished = self._reason, self.finished
            status = ("exited" if reason == "exited" else "timed_out" if reason == "lifetime_expired"
                      else "stopped" if self._released else "cleanup_failed") if finished else (
                          "stopping" if reason is not None else "running")
            return {"session_id": self.id, "workdir": str(self.workdir), "shell": self.shell,
                "status": status, "running": status == "running", "exit_code": self._exit_code,
                "stop_reason": reason, "output": data.decode("utf-8", errors="replace"),
                "output_offset": start, "output_next_offset": end, "output_total_bytes": self._total,
                "output_lost_bytes": max(0, oldest - offset), "output_has_more": end < self._total,
                "output_truncated": start > offset or end < self._total,
                "owned_processes_released": self._released,
                "background_processes_retained": not finished,
                "command_completed": finished, "command_succeeded": finished and reason == "exited" and self._exit_code == 0,
                "expires_in_seconds": max(0, round(self.deadline - monotonic())),
                "lifecycle": "Stops on explicit stop, lifetime expiry, or runtime/app shutdown.",
                "readiness_verified": False, "content_is_untrusted": True}


class ShellSessionManager:
    def __init__(self):
        self._lock, self._sessions, self._closed = RLock(), OrderedDict(), False

    def get(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise Error(Code.NOT_FOUND, "This shell session is not owned by the current runtime. List current sessions; do not use a PID or replay its start.")
        return session

    def start(self, command, *, workdir, shell, lifetime, env, cancellation, yield_time_ms, windows_command_line=None):
        with self._lock:
            if self._closed:
                raise Error(Code.INACCESSIBLE, "The shell session owner is shutting down.")
            cancellation.raise_if_cancelled()
            if sum(not s.finished for s in self._sessions.values()) >= MAX_ACTIVE_SESSIONS:
                raise Error(Code.INVALID_ARGUMENTS, "Four shell sessions are already active. Inspect or stop an owned session before starting another.")
            while len(self._sessions) >= MAX_SESSION_RECORDS:
                old = next((key for key, s in self._sessions.items() if s.finished), None)
                if old is None:
                    break
                del self._sessions[old]
            session = ShellSession(command, workdir=workdir, shell=shell, lifetime=lifetime,
                env=env, windows_command_line=windows_command_line)
            self._sessions[session.id] = session
        try:
            session.wait_initial(yield_time_ms, cancellation)
            return session.snapshot()
        except BaseException:
            session.stop("startup_cancelled")
            raise

    def list(self):
        with self._lock:
            sessions = tuple(self._sessions.values())
        keys = ("session_id", "shell", "status", "running", "exit_code", "stop_reason",
                "owned_processes_released", "expires_in_seconds")
        summaries = []
        for session in sessions:
            value = session.snapshot()
            summaries.append({**{k: value[k] for k in keys}, "workdir_display": str(session.workdir)[:256],
                              "workdir_display_truncated": len(str(session.workdir)) > 256})
        return {"sessions": summaries,
                "max_active_sessions": MAX_ACTIVE_SESSIONS, "content_is_untrusted": True}

    def close(self):
        with self._lock:
            self._closed = True
            sessions = tuple(self._sessions.values())
        for session in sessions:
            session.request_stop("shutdown")
        failed = False
        for session in sessions:
            try:
                session.stop("shutdown")
            except Error:
                failed = True
        if failed:
            raise Error(Code.OUTCOME_UNKNOWN, "Some owned shell sessions did not confirm shutdown cleanup.")
