"""Persistent, bounded Office MCP service. Qt and model threads never own the SDK loop."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from time import monotonic
from typing import Callable

from mcp import Client
from mcp.types import RequestParamsMeta

from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityExecutionError as Error, PermissionClass
from app.mcp.office_budget import accepted_office_manifest, office_budget_report
from app.mcp.office_contracts import (
    AttachArguments, CONTRACT_VERSION, OfficeExposure, OfficeToolContract,
    canonical_json, office_catalog,
)
from app.mcp.stdio_transport import OwnedStdioTransport
from app.mcp.office_excel import LIVE_TOOLS, READ_TOOLS
from app.runtime.cancellation import CancellationToken, TaskCancelled
from app.mcp.office_read_diagnostics import record_read_failure, read_failure_message


DEFAULT_CALL_TIMEOUT = 10.0
WORD_COMPOSE_CALL_TIMEOUT = 60.0


@dataclass
class _Request:
    contract: OfficeToolContract | None
    arguments: dict
    exposure: OfficeExposure
    operation: str
    timeout_seconds: float = DEFAULT_CALL_TIMEOUT
    future: Future = field(default_factory=Future)
    sent: bool = False
    control: tuple | None = None
    authority: dict | None = None


class OfficeConnection:
    """One app-owned connection, explicit cloud activation, no persisted handles.

    Live connections discover locally and require explicit document selection.
    Trusted injected transports keep the phase 2 fixture interface.
    """
    def __init__(self, root: Path, *, backend: Callable[[], str], applications=(),
                 call_timeout=None, startup_timeout=10.0, _transport_factory=None, discovery=None):
        self.root = Path(root).resolve(strict=True)
        self._backend = backend
        self._applications = OfficeExposure(applications=tuple(applications)).applications
        self._explicit_call_timeout = call_timeout is not None
        call_timeout = DEFAULT_CALL_TIMEOUT if call_timeout is None else call_timeout
        if (not callable(backend) or type(call_timeout) not in (int, float) or
                type(startup_timeout) not in (int, float) or not 0.05 <= call_timeout <= 30 or
                not 0.05 <= startup_timeout <= 30):
            raise ValueError("Office connection settings are invalid.")
        self.call_timeout, self.startup_timeout = float(call_timeout), float(startup_timeout)
        self._transport_factory = _transport_factory or self._bundled_transport
        from app.mcp.office_discovery import OfficeDiscovery
        self.live = _transport_factory is None or discovery is not None
        self.discovery = discovery or OfficeDiscovery()
        self._selected = None
        self._selected_application = None
        self._picture_sources = None
        self._authority = {}
        self._state, self._connect_lock, self._dispatch_lock = RLock(), Lock(), Lock()
        self._started, self._stopped = Event(), Event()
        self._enabled = self._ready = self._closed = False
        self._generation, self._tool_lists, self._calls = 0, 0, 0
        self._thread = self._loop = self._queue = self._transport = None
        self._sessions, self._used_calls = {}, set()
        self._failure_diagnostics = {}

    def tool_timeout(self, contract, arguments=None):
        # Full report writes include pagination, native property verification
        # and a complete recovery snapshot. Explicit test/host overrides stay
        # authoritative, including short deadlines for hung-worker checks.
        if contract.name == "office.word_compose" and not self._explicit_call_timeout:
            return WORD_COMPOSE_CALL_TIMEOUT
        if (contract.name == "office.read" and not self._explicit_call_timeout
                and str(getattr(arguments, "target", "")).startswith("render:")):
            return 30.0  # Bounded three-page print export and rasterization.
        return self.call_timeout

    def _bundled_transport(self):
        python = self.root / "runtime/python/python.exe"
        if not python.is_file():
            raise Error(Code.EXECUTOR_UNAVAILABLE, "The portable MCP runtime is missing.")
        return OwnedStdioTransport([str(python), "-m", "app.mcp.office_server"], root=self.root)

    @property
    def exposure(self):
        with self._state:
            backend = "cloud" if self._backend() == "cloud" else "local"
            process = getattr(self._transport, "process", None)
            if self._ready and process is not None and process.poll() is not None:
                self._invalidate_locked()
                self._signal_stop()
            return OfficeExposure(backend=backend, enabled=self._enabled, ready=self._ready,
                                  generation=self._generation, applications=self._applications)

    @property
    def selected_application(self):
        """Trusted UI selection for model guidance only; execution rechecks identity."""
        with self._state:
            return self._selected_application

    @property
    def diagnostics(self):
        with self._state:
            return {"generation": self._generation, "ready": self.exposure.ready,
                    "tool_list_requests": self._tool_lists, "tool_calls": self._calls,
                    "discovery_runs": self.discovery.runs,
                    "pid": getattr(self._transport, "pid", None),
                    "temporary_released": getattr(self._transport, "temporary_released", True),
                    "worker_alive": self._thread is not None and self._thread.is_alive(), **self._failure_diagnostics}

    def _invalidate_locked(self):
        self._ready = self._enabled = False
        self._generation += 1
        self._sessions.clear()
        self._selected = None
        self._selected_application = None
        self._authority.clear()
        self._picture_sources = None

    def _signal_stop(self):
        if self._loop is not None and self._queue is not None:
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            except RuntimeError:
                pass

    def connect(self, cancellation: CancellationToken | None = None):
        cancellation = cancellation or CancellationToken()
        with self._connect_lock:
            cancellation.raise_if_cancelled()
            with self._state:
                if self._closed or self._backend() != "cloud":
                    raise Error(Code.DISABLED_CAPABILITY, "Office MCP requires an open cloud runtime.")
                if self._ready:
                    return self.exposure
                if self._thread is not None and self._thread.is_alive():
                    raise Error(Code.EXECUTOR_BUSY, "The Office connection is still stopping.")
                if self.live:
                    self._applications = tuple(item.application for item in self.discovery.get())
                accepted = json.loads((self.root / "config/office_mcp_v1.json").read_text(encoding="utf-8"))
                if accepted != accepted_office_manifest() or not office_budget_report()["within_budget"]:
                    raise Error(Code.INVALID_ARGUMENTS, "The accepted Office contract or budget does not match.")
                self._generation += 1
                self._enabled = True
                self._started.clear()
                self._stopped.clear()
                self._used_calls.clear()
                self._failure_diagnostics.clear()
                self._transport = self._transport_factory()
                self._thread = Thread(target=self._worker, name="orsi-office-mcp", daemon=True)
                self._thread.start()
            deadline = monotonic() + self.startup_timeout
            while not self._started.wait(0.01):
                if cancellation.is_cancelled or monotonic() >= deadline:
                    self.disconnect()
                    if cancellation.is_cancelled:
                        raise TaskCancelled("Office connection cancelled.")
                    raise Error(Code.TIMED_OUT, "Office MCP initialization timed out.")
            if not self.exposure.ready:
                self.disconnect()
                raise Error(Code.EXECUTOR_UNAVAILABLE, "Office MCP initialization or contract verification failed.")
            return self.exposure

    async def _check_server(self, client):
        info = client.server_info
        if info is None or info.name != "orsi-office" or info.version != str(CONTRACT_VERSION):
            raise ValueError("Unrecognized Office server identity.")
        expected = {tool["name"]: tool for tool in accepted_office_manifest()["tools"]}
        found, cursor, cursors = {}, None, set()
        for _ in range(4):
            result = await client.list_tools(cursor=cursor)
            self._tool_lists += 1
            for tool in result.tools:
                if tool.name not in expected or tool.name in found:
                    raise ValueError("Unreviewed or duplicate Office tool.")
                accepted = expected[tool.name]
                for schema, key in ((tool.input_schema, "input_schema_sha256"),
                                    (tool.output_schema, "output_schema_sha256")):
                    if sha256(canonical_json(schema).encode()).hexdigest() != accepted[key]:
                        raise ValueError("Unreviewed Office schema.")
                found[tool.name] = True
            cursor = result.next_cursor
            if cursor is None:
                break
            if not isinstance(cursor, str) or len(cursor) > 96 or cursor in cursors:
                raise ValueError("Invalid Office tool-list cursor.")
            cursors.add(cursor)
        if cursor is not None or set(found) != set(expected):
            raise ValueError("Incomplete Office tool catalog.")

    def _worker(self):
        try:
            asyncio.run(self._serve())
        except BaseException:
            # Never store or log SDK errors: they can include document arguments.
            pass
        finally:
            self._transport.abort()
            with self._state:
                self._invalidate_locked()
                self._loop = self._queue = None
            self._started.set()
            self._stopped.set()

    async def _serve(self):
        self._loop, self._queue = asyncio.get_running_loop(), asyncio.Queue(maxsize=16)
        async with Client(self._transport.open(), mode="legacy", read_timeout_seconds=self.startup_timeout) as client:
            try:
                await self._connected(client)
            finally:
                # Wake pipe operations before the SDK waits for its reader tasks.
                # Do not abandon reads on file descriptors a reconnect may reuse.
                self._transport.abort()

    async def _connected(self, client):
        await self._check_server(client)
        if self.live:
            await self._control_request(client, "configure", {"applications": list(self._applications)})
        with self._state:
            if not self._enabled or self._backend() != "cloud":
                return
            self._ready = True
        self._started.set()
        while True:
            request = await self._queue.get()
            if request is None:
                break
            with self._state:
                if request.future.cancelled():
                    continue
                if self.exposure != request.exposure or (not self.exposure.eligible and request.control is None):
                    request.future.set_exception(Error(Code.DISABLED_CAPABILITY, "The Office exposure changed."))
                    continue
                request.sent = True
                if request.control is None:
                    self._calls += 1
            try:
                if request.control is not None:
                    try:
                        output = await self._control_request(client, *request.control)
                    except Error as error:
                        if not request.future.done():
                            request.future.set_exception(error)
                        continue
                    if not request.future.done():
                        request.future.set_result(output)
                    continue
                result = await client.call_tool(request.contract.name, request.arguments,
                    read_timeout_seconds=request.timeout_seconds,
                    meta=RequestParamsMeta(orsiOperation=request.operation,
                        **({"orsiAuthority": request.authority} if self.live else {})))
                failure = result.meta or {}
                if result.is_error and self.live and request.contract.name == "office.read":
                    diagnostic = failure.get("orsiReadDiagnostic")
                    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
                    diagnostic = record_read_failure(request.arguments, diagnostic)
                    with self._state:
                        self._failure_diagnostics["read_failure"] = diagnostic
                if result.is_error and failure.get("orsiStage") in {
                        "word_save", "word_native_insert", "word_readback", "word_verification",
                        "word_document_write", "word_document_readback"}:
                    with self._state:
                        self._failure_diagnostics = {"failure_stage": failure["orsiStage"],
                            "failure_hresult": failure.get("orsiHresult") if type(failure.get("orsiHresult")) is int else None,
                            "failure_mismatch": [key for key in failure.get("orsiMismatch", []) if key in {
                                "start", "end", "pstart", "pend", "text", "target", "paragraph", "dependencies", "paragraph_text", "uniform",
                                "paragraph_identity", "paragraph_properties", "paragraph_runs"}]}
                if result.is_error and self.live and (result.meta or {}).get("orsiFailure") == "conflict":
                    if not request.future.done():
                        request.future.set_exception(Error(Code.INVALID_ARGUMENTS,
                            str((result.meta or {}).get("orsiMessage", "Office conflict: read the target again before changing it."))[:500]))
                    continue
                if result.is_error and self.live and request.contract.permission == PermissionClass.READ:
                    if not request.future.done():
                        if failure.get("orsiFailure") == "read_setup":
                            request.future.set_exception(Error(Code.INVALID_ARGUMENTS,
                                str(failure.get("orsiMessage", "Render a fresh Word page group."))[:500]))
                            continue
                        if request.contract.name == "office.read":
                            request.future.set_exception(Error(
                                Code.INVALID_OUTPUT if failure.get("orsiFailure") == "read_execution" else Code.INVALID_ARGUMENTS,
                                read_failure_message(request.arguments, diagnostic)))
                            continue
                        request.future.set_exception(Error(Code.INVALID_ARGUMENTS,
                            "Office target is unavailable or changed. Refresh and read again. "
                            "Targets: selection; Excel workbook (sheet names/extents), SheetName!used or SheetName!A1:B2; "
                            "finish cursor pages; Word document, text:start:end, styles, tables or table:index; "
                            "PowerPoint slides or slide:index."))
                    continue
                if result.is_error or result.result_type != "complete":
                    raise ValueError("The Office tool did not complete.")
                output = request.contract.validate_result(
                    request.contract.arguments.model_validate(request.arguments), result.structured_content)
                if request.contract.permission == PermissionClass.WRITE and output.operation != request.operation:
                    raise ValueError("The Office receipt belongs to another operation.")
                if isinstance(request.contract.arguments.model_validate(request.arguments), AttachArguments):
                    self._sessions[output.session] = output.document.application
                if self.live and request.contract.name == "office.save" and request.arguments.get("path"):
                    binding = await self._control_request(client, "binding", {"session": output.session})
                    if binding["path"] != str(Path(request.arguments["path"])):
                        raise ValueError("The saved document identity did not match its destination.")
                    with self._state:
                        self._selected = (binding["document"]["document"], binding["identity"])
                if not request.future.done():
                    request.future.set_result(output.model_dump(mode="json"))
            except BaseException:
                with self._state:
                    self._invalidate_locked()
                if not request.future.done():
                    code = Code.OUTCOME_UNKNOWN if request.contract is not None and request.contract.permission == PermissionClass.WRITE else Code.INVALID_OUTPUT
                    request.future.set_exception(Error(code, "Office execution failed; no automatic retry is permitted."))
                break

    async def _control_request(self, client, action, data):
        result = await client.read_resource("orsi-office://local/" + action,
            meta=RequestParamsMeta(orsiControl=data), cache_mode="bypass")
        if len(result.contents) != 1 or len(result.contents[0].text.encode()) > 48000:
            raise ValueError("Invalid local Office response.")
        output = json.loads(result.contents[0].text)
        if not isinstance(output, dict) or "error" in output:
            message = (str(output.get("error", "Office conflict: read a fresh complete snapshot."))[:500]
                       if isinstance(output, dict) and output.get("code") == "conflict" else
                       "Office target is unavailable; refresh the connection or selection.")
            raise Error(Code.INVALID_ARGUMENTS, message)
        return output

    def control(self, action, data=None, cancellation=None):
        """Private app operation; never part of model tools or conversation results."""
        cancellation = cancellation or CancellationToken()
        deadline, acquired = monotonic() + self.call_timeout, False
        try:
            while not acquired:
                acquired = self._dispatch_lock.acquire(timeout=0.01)
                cancellation.raise_if_cancelled()
                if monotonic() >= deadline:
                    raise Error(Code.EXECUTOR_BUSY, "The Office connection is busy.")
            cancellation.raise_if_cancelled()
            expected = self.exposure
            if not self.live or not expected.ready or expected.backend != "cloud":
                raise Error(Code.DISABLED_CAPABILITY, "Office controls require a ready cloud connection.")
            request = _Request(None, {}, expected, "", control=(action, data or {}))
            self._loop.call_soon_threadsafe(self._queue.put_nowait, request)
            while True:
                try:
                    return request.future.result(timeout=0.01)
                except FutureTimeout:
                    if cancellation.is_cancelled or monotonic() >= deadline or self._stopped.is_set():
                        request.future.cancel()
                        self.disconnect()
                        cancellation.raise_if_cancelled()
                        raise Error(Code.TIMED_OUT, "The Office control exceeded its deadline.")
        finally:
            if acquired:
                self._dispatch_lock.release()

    def list_documents(self, *, refresh=True, cancellation=None):
        result, offset = [], 0
        for _ in range(6):
            page = self.control("documents", {"refresh": refresh and offset == 0, "offset": offset}, cancellation)
            result.extend(item["document"] for item in page["documents"])
            offset = page["next"]
            if offset is None:
                return result
        raise Error(Code.INVALID_OUTPUT, "The Office document list exceeded its bound.")

    def render_images(self, output):
        """Retrieve approved render pixels through bounded private resource pages."""
        import base64
        from app.mcp.office_word_render import MAX_PAGE_BYTES, MAX_RENDER_BYTES
        if output.get("application") != "word" or output.get("cursor") is not None:
            raise ValueError("Invalid Word render result.")
        items = output.get("items", [])
        if not 1 <= len(items) <= 3:
            raise ValueError("Invalid Word render image count.")
        result, total = [], 0
        for item in items:
            metadata = json.loads(item["text"])
            size = metadata["bytes"]
            if type(size) is not int or not 0 < size <= MAX_PAGE_BYTES:
                raise ValueError("Invalid Word image size.")
            blob = bytearray()
            while len(blob) < size:
                page = self.control("word-render-image", {"session": output["session"],
                    "snapshot": output["snapshot"], "page": metadata["page"], "offset": len(blob)})
                chunk = base64.b64decode(page["data"], validate=True)
                if (page["offset"] != len(blob) or page["total"] != size or not 0 < len(chunk) <= 24000
                        or page["next"] != len(blob) + len(chunk) or page["next"] > size):
                    raise ValueError("Invalid Word image chunk.")
                blob.extend(chunk)
            total += len(blob)
            if total > MAX_RENDER_BYTES or sha256(blob).hexdigest() != metadata["sha256"]:
                raise ValueError("Word render image integrity failed.")
            result.append((metadata["page"], bytes(blob)))
        return result

    def select_document(self, document, cancellation=None):
        value = self.control("binding", {"document": document}, cancellation)
        with self._state:
            self._selected = (document, value["identity"])
            self._selected_application = value["document"]["application"]
            self._sessions.clear()
            self._authority.clear()
            self._generation += 1
        return value["document"]

    def refresh(self, cancellation=None):
        self.disconnect()
        self.discovery.get(refresh=True)
        self.connect(cancellation)
        return self.list_documents(cancellation=cancellation)

    def resource_policy(self, contract, arguments, context):
        from app.mcp.office_capabilities import OfficeResourceBinding
        if contract.name not in LIVE_TOOLS:
            raise Error(Code.DISABLED_CAPABILITY, "Office editing is unavailable in this phase.")
        if contract.name == "office.image_register":
            attachment = arguments.path.startswith("attachment:")
            if attachment:
                reference, _ = self.picture_source(arguments.path, context.session_id)
                path = None
            elif context.host_access_policy is not None:
                path = context.host_access_policy.resolve_read(arguments.path).resolved
            else:
                from app.security.path_policy import resolve_read_path
                path = resolve_read_path(arguments.path, portable_root=context.portable_root,
                    allowed_roots=context.allowed_read_roots).resolved
            if path is not None and str(path).startswith(("\\\\", "//")):
                raise Error(Code.PERMISSION_DENIED, "Pictures require an accessible local file.")
            with self._state:
                selected = self._selected
            value = self.control("binding", {"session": arguments.session}, context.cancellation)
            if (selected is None or (value["document"]["document"], value["identity"]) != selected
                    or value["document"]["application"] != "word"):
                raise Error(Code.PERMISSION_DENIED, "Choose this exact Word document first.")
            identity = value["identity"] if not attachment else sha256(canonical_json(
                [value["identity"], context.session_id, reference.id, reference.sha256]).encode()).hexdigest()
            return OfficeResourceBinding(path, identity, "Register immutable local picture")
        with self._state:
            selected = self._selected
        if selected is None:
            if contract.name != "office.documents":
                raise Error(Code.PERMISSION_DENIED, "Choose a document in Office settings first.")
            authority = {"document": None}
            binding = OfficeResourceBinding(None, "office-metadata")
        else:
            value = self.control("binding", {"document": selected[0],
                **({"session": arguments.session} if hasattr(arguments, "session") else {})}, context.cancellation)
            if (value["document"]["document"], value["identity"]) != selected:
                raise Error(Code.PERMISSION_DENIED, "The selected Office document changed. Select it again.")
            if hasattr(arguments, "document") and arguments.document != selected[0]:
                raise Error(Code.PERMISSION_DENIED, "Select this exact Office document first.")
            authority = {"document": selected[0], "identity": selected[1]}
            source = Path(value["path"]) if value["path"] else None
            destination = source
            if contract.name not in READ_TOOLS:
                kind = value["document"]["application"]
                if kind not in {"excel", "word"} or (contract.application is not None and contract.application != kind):
                    raise Error(Code.DISABLED_CAPABILITY, "This edit requires its exact supported Office application.")
                if contract.name == "office.save" and arguments.path is not None:
                    destination = Path(arguments.path)
                    if not destination.is_absolute():
                        raise Error(Code.PERMISSION_DENIED, "Save As requires an absolute local destination.")
            binding = OfficeResourceBinding(destination, value["identity"],
                "Selected " + value["document"]["application"] + " document", source)
        with self._state:
            self._authority[context.call_id] = authority
            if len(self._authority) > 128:
                self._authority.pop(next(iter(self._authority)))
        return binding

    def bind_picture_sources(self, session_id, store, references):
        with self._state:
            self._picture_sources = (session_id, store, {r.id: r for r in references if r.kind == "image"})

    def picture_source(self, path, session_id):
        with self._state:
            sources = self._picture_sources
        reference = None if sources is None else sources[2].get(path.removeprefix("attachment:"))
        if sources is None or sources[0] != session_id or reference is None:
            raise Error(Code.PERMISSION_DENIED, "Only images attached to this conversation are available.")
        return reference, sources[1]

    def discover_picture_sources(self, arguments, context):
        with self._state:
            sources = self._picture_sources
        if arguments.cursor:
            raise Error(Code.INVALID_ARGUMENTS, "Picture discovery does not use cursors.")
        references = sources[2].values() if sources is not None and sources[0] == context.session_id else ()
        items = [{"label": "Attached picture", "text": canonical_json({"reference": "attachment:" + r.id,
            "media_type": r.media_type, "bytes": r.size_bytes})} for r in references
            if r.media_type in {"image/png", "image/jpeg"} and r.size_bytes <= 256 * 1024]
        if len(items) > 8:
            raise Error(Code.INVALID_ARGUMENTS, "Picture discovery supports at most eight eligible attached images.")
        if len(items) > arguments.max_items or sum(len(v["text"]) for v in items) > arguments.max_chars:
            raise Error(Code.INVALID_ARGUMENTS, "Picture discovery needs sufficient max_items and max_chars for its bounded metadata.")
        return {"session": arguments.session, "application": "word", "snapshot": "picture_discovery",
            "items": [{"target": "picture_" + str(i), **v} for i, v in enumerate(items)], "cursor": None}

    def register_image(self, arguments, path, cancellation, session_id=None):
        import base64
        from uuid import uuid4
        from app.mcp.office_word_assets import MAX_IMAGE_BYTES, inspect_image
        if arguments.path.startswith("attachment:"):
            reference, store = self.picture_source(arguments.path, session_id)
            if reference.size_bytes > MAX_IMAGE_BYTES or reference.media_type not in {"image/png", "image/jpeg"}:
                raise Error(Code.INVALID_ARGUMENTS, "Attached picture exceeds supported format or byte bounds.")
            with store.open(reference, cancellation=cancellation) as stream:
                data = stream.read(MAX_IMAGE_BYTES + 1)
        else:
            from app.conversation.attachments import _snapshot_stream
            try:
                with _snapshot_stream(path, MAX_IMAGE_BYTES, cancellation) as stream:
                    data = stream.read(MAX_IMAGE_BYTES + 1)
            except (OSError, ValueError):
                raise Error(Code.INVALID_ARGUMENTS, "Picture source must be an ordinary readable local file within 256 KiB.") from None
        try:
            inspect_image(data)
        except Exception as error:
            from app.mcp.office_excel import OfficeConflict
            if isinstance(error, OfficeConflict):
                raise Error(Code.INVALID_ARGUMENTS, str(error)) from None
            raise
        asset = uuid4().hex
        for offset in range(0, len(data), 24000):
            chunk = data[offset:offset + 24000]
            result = self.control("word-asset", {"session": arguments.session, "asset": asset,
                "offset": offset, "data": base64.b64encode(chunk).decode("ascii"),
                "final": offset + len(chunk) == len(data)}, cancellation)
        return result

    def prepare_mutation(self, contract, arguments, context):
        with self._state:
            authority = dict(self._authority.get(context.call_id, {}))
        serialized = arguments.model_dump(mode="json")
        if contract.name == "office.word_compose":
            from app.inference.word_plan_diagnostics import record_word_plan
            record_word_plan("approval_serialized", serialized)
        value = self.control("mutation", {**authority, "tool": contract.name,
            "arguments": serialized}, context.cancellation)
        if contract.name == "office.word_compose":
            from app.inference.word_plan_diagnostics import word_plan_shape
            if value.get("word_plan_shape") == word_plan_shape(serialized):
                record_word_plan("approval_plan", serialized)
            elif "word_plan_shape" in value:
                from app.inference.word_plan_diagnostics import log as diagnostic_log
                diagnostic_log.warning("word_compose approval_shape_mismatch")
        with self._state:
            self._authority[context.call_id] = {**authority, "guard": value["guard"]}
        return value

    def call(self, contract: OfficeToolContract, arguments, *, expected: OfficeExposure,
             operation: str, cancellation: CancellationToken):
        cancellation.raise_if_cancelled()
        timeout = self.tool_timeout(contract, arguments)
        request = _Request(contract, arguments.model_dump(mode="json"), expected, operation,
                           timeout_seconds=timeout)
        if contract.name == "office.word_compose":
            from app.inference.word_plan_diagnostics import record_word_plan
            record_word_plan("dispatch_serialized", request.arguments)
        deadline = monotonic() + timeout
        acquired = False
        try:
            while not acquired:
                acquired = self._dispatch_lock.acquire(timeout=0.01)
                cancellation.raise_if_cancelled()
                if monotonic() >= deadline:
                    raise Error(Code.EXECUTOR_BUSY, "The Office connection is busy.")
            with self._state:
                office_catalog(expected).validate_call(contract.name, request.arguments, current=self.exposure)
                session = getattr(arguments, "session", None)
                if session is not None and (self._sessions.get(session) not in expected.applications or
                        (contract.application is not None and self._sessions.get(session) != contract.application)):
                    raise Error(Code.PERMISSION_DENIED, "The Office session is unavailable or belongs to another application.")
                if operation in self._used_calls:
                    raise Error(Code.CALL_REPLAYED, "Office call IDs cannot be reused in this connection.")
                if len(self._used_calls) >= 512:
                    raise Error(Code.EXECUTOR_UNAVAILABLE, "The Office connection record limit was reached; reconnect explicitly.")
                self._used_calls.add(operation)
                if self.live:
                    request.authority = self._authority.pop(operation, None)
                    if request.authority is None:
                        raise Error(Code.PERMISSION_DENIED, "Office execution requires a checked local document binding.")
                self._loop.call_soon_threadsafe(self._queue.put_nowait, request)
            while True:
                try:
                    return request.future.result(timeout=0.01)
                except FutureTimeout:
                    if cancellation.is_cancelled or monotonic() >= deadline or self._stopped.is_set():
                        with self._state:
                            # A verified receipt can settle between the timed
                            # poll and the deadline/cancellation check. Preserve
                            # it instead of replacing it with an unknown result.
                            if request.future.done():
                                return request.future.result()
                            sent = request.sent
                            if not sent:
                                request.future.cancel()
                            self._failure_diagnostics.update({
                                "confirmation_stop": "cancelled" if cancellation.is_cancelled else (
                                    "deadline" if monotonic() >= deadline else "worker_stopped"),
                                "confirmation_timeout_seconds": timeout,
                            })
                            if contract.name == "office.read":
                                from app.mcp.office_read_diagnostics import read_shape
                                self._failure_diagnostics["confirmation_read_shape"] = read_shape(arguments.model_dump(mode="json"))
                        self.disconnect()
                        if sent and contract.permission == PermissionClass.WRITE:
                            raise Error(Code.OUTCOME_UNKNOWN, "The Office write may have completed; review its outcome before retrying.")
                        if cancellation.is_cancelled:
                            raise TaskCancelled("Office operation cancelled.")
                        raise Error(Code.TIMED_OUT, "Office MCP stopped or exceeded its deadline.")
        except Error:
            # The SDK can settle a failed receipt before the worker's finally
            # block releases its transport. Invalidation is not worker exit.
            with self._state:
                failed_worker = (not self._ready and self._thread is not None
                                 and self._thread.is_alive())
            if failed_worker:
                try:
                    self.disconnect()
                except Exception:
                    # Preserve the original uncertain-write/error classification
                    # even if bounded cleanup fails. Never make it replayable.
                    with self._state:
                        self._failure_diagnostics["confirmation_cleanup_failed"] = True
            raise
        finally:
            if acquired:
                self._dispatch_lock.release()

    def disconnect(self):
        # An idle live bridge can release its COM references on the owning STA
        # before process teardown. Busy/hung operations retain the bounded abort path.
        acquired = self._dispatch_lock.acquire(blocking=False) if self.live else False
        try:
            if acquired and self.exposure.ready and self.exposure.backend == "cloud":
                request = _Request(None, {}, self.exposure, "", control=("release", {}))
                try:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, request)
                    request.future.result(timeout=min(2.0, self.call_timeout))
                except Exception:
                    request.future.cancel()
            with self._state:
                self._invalidate_locked()
                self._signal_stop()
                transport, thread = self._transport, self._thread
            if transport is not None:
                transport.abort()
            if thread is not None:
                thread.join(timeout=6.0)
                if thread.is_alive():
                    raise Error(Code.EXECUTOR_UNAVAILABLE, "The Office worker did not release before its shutdown deadline.")
        finally:
            if acquired:
                self._dispatch_lock.release()

    def close(self):
        with self._state:
            self._closed = True
        self.disconnect()
