"""Bounded MCP stdio on ORSI's atomic Windows job ownership, with no wire logging."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from threading import RLock

import anyio
from mcp.shared.message import SessionMessage
from mcp.types import jsonrpc_message_adapter

from app.runtime.owned_process import start_owned_process


MAX_FRAME_BYTES = 65_536


class TransportFailure(RuntimeError):
    """Content-free failure suitable for the SDK session boundary."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def bridge_environment(root: Path) -> dict[str, str]:
    names = {"systemroot", "systemdrive", "windir", "path", "pathext", "userprofile",
             "appdata", "localappdata", "programfiles", "programfiles(x86)", "programw6432"}
    result = {key: value for key, value in os.environ.items() if key.lower() in names}
    temporary = root / "state/mcp/tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    result.update(TEMP=str(temporary), TMP=str(temporary), PYTHONIOENCODING="utf-8",
                  PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return result


class _PipeStream:
    def __init__(self, fd):
        self.fd = fd

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        # The owner kills the child before closing descriptors. SDK context exits
        # may call aclose first; ownership remains with the transport.
        pass


class _ReadPipe(_PipeStream):
    def __init__(self, fd, abort):
        super().__init__(fd)
        self.buffer = bytearray()
        self.abort = abort

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    async def receive(self):
        try:
            while b"\n" not in self.buffer:
                chunk = await anyio.to_thread.run_sync(os.read, self.fd, 4096)
                if not chunk:
                    if self.buffer:
                        raise TransportFailure("Incomplete MCP frame.")
                    raise anyio.EndOfStream
                self.buffer.extend(chunk)
                if len(self.buffer.split(b"\n", 1)[0]) > MAX_FRAME_BYTES:
                    raise TransportFailure("MCP frame limit exceeded.")
            line, _, remaining = self.buffer.partition(b"\n")
            self.buffer = bytearray(remaining)
            if len(line) > MAX_FRAME_BYTES:
                raise TransportFailure("MCP frame limit exceeded.")
            decoded = json.loads(line, object_pairs_hook=_unique_object,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            return SessionMessage(jsonrpc_message_adapter.validate_python(decoded, by_name=False))
        except anyio.EndOfStream:
            raise
        except TransportFailure:
            self.abort()
            raise
        except (ValueError, UnicodeError, OSError, RecursionError):
            self.abort()
            raise TransportFailure("Invalid MCP frame; connection closed.") from None


class _WritePipe(_PipeStream):
    async def send(self, item):
        encoded = item.message.model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8") + b"\n"
        if len(encoded) > MAX_FRAME_BYTES:
            raise TransportFailure("MCP request frame limit exceeded.")

        def write():
            remaining = memoryview(encoded)
            while remaining:
                count = os.write(self.fd, remaining)
                remaining = remaining[count:]

        try:
            await anyio.to_thread.run_sync(write)
        except OSError:
            raise TransportFailure("MCP input pipe closed.") from None


class OwnedStdioTransport:
    """Trusted app composition supplies argv; model/config data cannot choose it."""
    def __init__(self, command, *, root: Path):
        self.command, self.root = tuple(command), Path(root)
        self.process = None
        self._lock = RLock()
        self._fds = []
        self._closed = False

    @property
    def pid(self):
        return self.process.pid if self.process is not None else None

    def abort(self):
        with self._lock:
            if self.process is not None:
                self.process.close()

    @asynccontextmanager
    async def open(self):
        with self._lock:
            if self._closed or self.process is not None:
                raise TransportFailure("MCP transports are single-use.")
            child_in, parent_in = os.pipe()
            parent_out, child_out = os.pipe()
            self._fds = [child_in, parent_in, parent_out, child_out]
            try:
                self.process = start_owned_process(self.command, cwd=self.root,
                    env=bridge_environment(self.root), stdin=child_in, stdout=child_out)
                os.close(child_in)
                self._fds.remove(child_in)
                os.close(child_out)
                self._fds.remove(child_out)
            except BaseException:
                for fd in self._fds:
                    os.close(fd)
                self._fds.clear()
                self._closed = True
                raise
        try:
            yield _ReadPipe(parent_out, self.abort), _WritePipe(parent_in)
        finally:
            # No PID lookup and no fallback to an unowned subprocess. Closing the
            # job releases descendants even if a server exits before its child.
            self.abort()
            with self._lock:
                for fd in self._fds:
                    os.close(fd)
                self._fds.clear()
                self._closed = True
