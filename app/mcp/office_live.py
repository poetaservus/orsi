"""Document-bound read service and private local controls; no Office mutations."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.mcp.office_com import OfficeUnavailable, WindowsOffice
from app.mcp.office_contracts import APPLICATIONS, MAX_RESULT_BYTES, canonical_json


def token():
    return uuid4().hex


class LiveOffice:
    def __init__(self, backend_factory=WindowsOffice):
        self.factory, self.backend = backend_factory, None
        self.enabled, self.documents, self.sessions, self.cursors = (), {}, {}, {}
        self.snapshots = {}

    def _backend(self):
        if self.backend is None:
            self.backend = self.factory()
        return self.backend

    def scan(self):
        backend = self._backend()
        found = {}
        for kind, obj in backend.documents(self.enabled):
            existing = next((key for key, record in self.documents.items()
                             if kind == record[0] and backend.same(obj, record[1])), None)
            found[existing or token()] = (kind, obj)
        self.documents = found
        self.sessions = {key: value for key, value in self.sessions.items() if value in found}
        self.cursors = {key: value for key, value in self.cursors.items() if value[0] in self.sessions}
        self.snapshots = {key: value for key, value in self.snapshots.items() if value[0] in self.sessions}

    def binding(self, document=None, session=None):
        document = self.sessions.get(session) if session is not None else document
        record = self.documents.get(document)
        if record is None or not self._backend().alive(*record):
            raise OfficeUnavailable("The attached document is closed or unavailable. Refresh documents.")
        kind, obj = record
        metadata = self.backend.metadata(kind, obj)
        path = metadata.pop("path")
        if path is not None:
            # Reject URLs, relative names and remote paths rather than inventing authority.
            if not Path(path).is_absolute() or path.startswith(("\\\\", "//")):
                raise OfficeUnavailable("This document requires an accessible local file path.")
            path = str(Path(path).resolve(strict=True))
        identity = sha256(canonical_json([document, kind, path]).encode()).hexdigest()
        return {"document": {"document": document, "application": kind,
                "has_path": path is not None, **metadata}, "path": path, "identity": identity}

    def control(self, action, data):
        if action == "release":
            self.close()
            return {"released": True}
        if action == "configure":
            applications = data.get("applications")
            if not isinstance(applications, list) or any(a not in APPLICATIONS for a in applications):
                raise OfficeUnavailable("Invalid local Office configuration.")
            self.enabled = tuple(applications)
            self.sessions.clear()
            self.cursors.clear()
            self.snapshots.clear()
            self.scan()
            return {"applications": list(self.enabled)}
        if action == "documents":
            if data.get("refresh"):
                self.scan()
            offset = data.get("offset", 0)
            if type(offset) is not int or not 0 <= offset <= 256:
                raise OfficeUnavailable("Invalid local document page.")
            keys = list(self.documents)
            values = []
            for key in keys[offset:offset + 50]:
                try:
                    values.append({"document": self.binding(document=key)["document"]})
                except (OfficeUnavailable, OSError):
                    continue
            return {"documents": values, "next": offset + 50 if offset + 50 < len(keys) else None}
        if action == "binding":
            return self.binding(document=data.get("document"), session=data.get("session"))
        raise OfficeUnavailable("Unknown local Office control.")

    def call(self, contract, arguments, authority):
        if contract.name not in ("office.documents", "office.attach", "office.read"):
            raise OfficeUnavailable("Office editing is not available in this phase.")
        if not isinstance(authority, dict):
            raise OfficeUnavailable("Office execution requires a local document binding.")
        document = authority.get("document")
        if contract.name == "office.documents" and document is None:
            return {"documents": [], "cursor": None}
        bound = self.binding(document=document, session=getattr(arguments, "session", None))
        if bound["document"]["document"] != document or bound["identity"] != authority.get("identity"):
            raise OfficeUnavailable("The approved document identity changed.")
        if contract.name == "office.documents":
            if arguments.cursor is not None:
                raise OfficeUnavailable("The document cursor is unavailable.")
            return {"documents": [bound["document"]] if arguments.application in
                    (None, bound["document"]["application"]) else [], "cursor": None}
        if contract.name == "office.attach":
            if arguments.document != document or arguments.application != bound["document"]["application"]:
                raise OfficeUnavailable("Select this exact document in Office settings first.")
            if len(self.sessions) >= 128:
                raise OfficeUnavailable("The session limit was reached. Refresh the connection.")
            session = token()
            self.sessions[session] = document
            return {"session": session, "document": bound["document"]}
        return self.read(arguments, bound)

    def read(self, arguments, binding):
        if len(self.snapshots) >= 128:
            raise OfficeUnavailable("The snapshot limit was reached. Refresh the connection.")
        signature = (arguments.session, arguments.target, binding["identity"])
        if arguments.cursor:
            value = self.cursors.get(arguments.cursor)
            if value is None or value[:3] != signature:
                raise OfficeUnavailable("The read cursor belongs to another target or session.")
            _, _, _, plan, index, offset, guard = value
            if guard is not None:
                descriptor, old_offset, count, digest = guard
                piece, _ = self.backend.piece(descriptor, old_offset, count)
                if sha256(canonical_json(piece).encode()).hexdigest() != digest:
                    raise OfficeUnavailable("The paged target changed. Read it again.")
        else:
            plan = self.backend.plan(*self.documents[binding["document"]["document"]], arguments.target)
            index = offset = 0
        snapshot = token()
        items, consumed, guard, targets = [], 0, None, {}
        # A conservative byte allowance handles JSON escaping and 4-byte Unicode.
        while index < len(plan) and len(items) < min(arguments.max_items, 32) and consumed < arguments.max_chars:
            count = min(arguments.max_chars - consumed, 1200)
            piece, next_offset = self.backend.piece(plan[index], offset, count)
            digest = sha256(canonical_json(piece).encode()).hexdigest()
            characters = len(piece.get("text") or "") + sum(len(c) for matrix in
                (piece.get("values"), piece.get("formulas")) if matrix for row in matrix for c in row if isinstance(c, str))
            if characters > count or (next_offset is not None and next_offset <= offset):
                raise OfficeUnavailable("The Office adapter exceeded its read bound.")
            item = {"target": token(), **piece}
            candidate = {"session": arguments.session, "application": binding["document"]["application"],
                         "snapshot": snapshot, "items": [*items, item], "cursor": "0" * 32}
            if len(canonical_json(candidate).encode()) > MAX_RESULT_BYTES:
                break
            items.append(item)
            targets[item["target"]] = (plan[index], offset, count, digest)
            consumed += characters
            guard = (plan[index], offset, count, digest)
            if next_offset is None:
                index, offset = index + 1, 0
            else:
                offset = next_offset
        if index < len(plan) and not items:
            raise OfficeUnavailable("The Office item cannot fit the read limits.")
        cursor = None
        if index < len(plan):
            if len(self.cursors) >= 128 and arguments.cursor not in self.cursors:
                raise OfficeUnavailable("The read cursor limit was reached. Refresh the connection.")
            cursor = token()
            self.cursors[cursor] = (*signature, plan, index, offset, guard)
        if arguments.cursor:
            self.cursors.pop(arguments.cursor, None)
        self.snapshots[snapshot] = (arguments.session, binding["identity"], targets)
        return {"session": arguments.session, "application": binding["document"]["application"],
                "snapshot": snapshot, "items": items, "cursor": cursor}

    def close(self):
        self.snapshots.clear()
        self.cursors.clear()
        self.sessions.clear()
        self.documents.clear()
        if self.backend is not None:
            self.backend.close()
            self.backend = None


class OfficeSTA:
    """Only this executor may construct, use or release the COM service."""
    def __init__(self, factory=LiveOffice):
        self.factory, self.service = factory, None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orsi-office-sta")

    def _invoke(self, method, args):
        if self.service is None:
            self.service = self.factory()
        return getattr(self.service, method)(*args)

    async def invoke(self, method, *args):
        return await asyncio.wrap_future(self.executor.submit(self._invoke, method, args))

    async def close(self):
        if self.service is not None:
            await self.invoke("close")
        self.executor.shutdown(wait=False, cancel_futures=True)
