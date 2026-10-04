"""Own one async SDK loop, connection pool and cancellable request at a time."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Event, Lock, Thread, current_thread


@dataclass
class _Request:
    cancelled: Event = field(default_factory=Event)
    finished: Event = field(default_factory=Event)
    task: asyncio.Task | None = None


class OpenAIRequestRunner:
    def __init__(self):
        self._lock = Lock()
        self._gate = Lock()
        self._ready = Event()
        self._loop = None
        self._thread = None
        self._active = None
        self._closed = False
        self._revision = 0
        self.client = None
        self.http_client = None

    def _serve(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def _invoke(self, request, operation):
        request.task = asyncio.current_task()
        try:
            if request.cancelled.is_set():
                request.task.cancel()
            return await operation()
        finally:
            request.finished.set()

    def run(self, operation):
        with self._lock:
            revision = self._revision
        with self._gate:
            with self._lock:
                if self._closed:
                    raise RuntimeError("The OpenAI request runner is closed.")
                if self._thread is None:
                    self._thread = Thread(target=self._serve, name="orsi-openai-transport", daemon=True)
                    self._thread.start()
                self._ready.wait()
                request = _Request()
                if revision != self._revision:
                    request.cancelled.set()
                self._active = request
                future = asyncio.run_coroutine_threadsafe(self._invoke(request, operation), self._loop)
            try:
                return future.result()
            finally:
                with self._lock:
                    if self._active is request:
                        self._active = None

    def cancel(self):
        with self._lock:
            self._revision += 1
            request = self._active
            if request is None:
                return
            if not request.cancelled.is_set():
                request.cancelled.set()
                def cancel_task():
                    if request.task is not None and not request.task.done():
                        request.task.cancel()
                self._loop.call_soon_threadsafe(cancel_task)
        if current_thread() is not self._thread:
            request.finished.wait(2)

    def close(self, close_client):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.cancel()
        thread, loop = self._thread, self._loop
        if thread is None:
            return
        # The async SDK closes the request before its task settles. Run client
        # closure on the same loop to release keep-alive sockets too.
        asyncio.run_coroutine_threadsafe(close_client(), loop).result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        if thread.is_alive():
            raise RuntimeError("The OpenAI transport could not finish shutting down.")
