"""Document-bound Office reads and guarded Excel/Word operations on one STA."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.mcp.office_com import OfficeUnavailable, WindowsOffice
from app.mcp.office_contracts import APPLICATIONS, MAX_RESULT_BYTES, canonical_json
from app.mcp.office_excel import ExcelEdits, LIVE_TOOLS, READ_TOOLS, OfficeConflict, MAX_STATE_BYTES, same_state, same_value


def token():
    return uuid4().hex


class LiveOffice:
    def __init__(self, backend_factory=WindowsOffice):
        self.factory, self.backend = backend_factory, None
        self.enabled, self.documents, self.sessions, self.cursors = (), {}, {}, {}
        self.snapshots = {}
        self.excel = ExcelEdits(self)
        from app.mcp.office_word import WordEdits
        self.word = WordEdits(self)

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
            self.excel.clear()
            self.word.clear()
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
        if action == "word-render-image":
            binding = self.binding(session=data.get("session"))
            return self.word.renders.chunk(data, binding)
        if action == "mutation":
            from app.mcp.office_contracts import OFFICE_TOOLS
            contract = next((t for t in OFFICE_TOOLS if t.name == data.get("tool") and t.name in LIVE_TOOLS - READ_TOOLS), None)
            if contract is None:
                raise OfficeConflict("Unsupported Office mutation.")
            arguments = contract.arguments.model_validate(data.get("arguments"))
            bound = self.binding(session=arguments.session)
            if bound["document"]["document"] != data.get("document") or bound["identity"] != data.get("identity"):
                raise OfficeConflict("Office conflict: the selected document changed.")
            return self.edits(bound).prepare(contract.name, arguments, bound)
        raise OfficeUnavailable("Unknown local Office control.")

    def call(self, contract, arguments, authority, operation=None):
        if contract.name not in LIVE_TOOLS:
            raise OfficeUnavailable("Office editing is not available in this phase.")
        if not isinstance(authority, dict):
            raise OfficeUnavailable("Office execution requires a local document binding.")
        document = authority.get("document")
        if contract.name == "office.documents" and document is None:
            return {"documents": [], "cursor": None}
        bound = self.binding(document=document, session=getattr(arguments, "session", None))
        if bound["document"]["document"] != document or bound["identity"] != authority.get("identity"):
            raise OfficeConflict("The approved document identity changed.")
        if contract.name in LIVE_TOOLS - READ_TOOLS:
            return self.edits(bound).execute(contract.name, arguments, bound, authority, operation)
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

    def edits(self, binding):
        kind = binding["document"]["application"]
        if kind not in {"excel", "word"}:
            raise OfficeConflict("This Office application is read-only.")
        return self.word if kind == "word" else self.excel

    def read(self, arguments, binding):
        if binding["document"]["application"] == "word" and hasattr(self.backend, "capture_word"):
            return self.word.read(arguments, binding)
        if len(self.snapshots) >= 128 and not arguments.cursor:
            raise OfficeUnavailable("The snapshot limit was reached. Refresh the connection.")
        signature = (arguments.session, arguments.target, binding["identity"])
        if arguments.cursor:
            value = self.cursors.get(arguments.cursor)
            if value is None or value[:3] != signature:
                raise OfficeUnavailable("The read cursor belongs to another target or session.")
            _, _, _, plan, index, offset, guard, previous_snapshot = value
            if binding["document"]["application"] == "excel" and arguments.target.endswith("!used"):
                current = self.backend.plan(*self.documents[binding["document"]["document"]], arguments.target)
                if (len(current) != len(plan) or current.rows != plan.rows or current.columns != plan.columns
                        or current.row != plan.row or current.column != plan.column
                        or not self.backend.same(current.sheet, plan.sheet)):
                    raise OfficeUnavailable("The worksheet used range changed. Read it again.")
            if guard is not None:
                descriptor, old_offset, count, digest = guard
                piece, _ = self.backend.piece(descriptor, old_offset, count)
                if sha256(canonical_json(piece).encode()).hexdigest() != digest:
                    raise OfficeUnavailable("The paged target changed. Read it again.")
        else:
            plan = self.backend.plan(*self.documents[binding["document"]["document"]], arguments.target)
            index = offset = 0
        snapshot = previous_snapshot if arguments.cursor and binding["document"]["application"] == "excel" else token()
        prior = self.snapshots.get(snapshot)
        items, consumed, guard, targets = [], 0, None, dict(prior[2]) if prior else {}
        packed = binding["document"]["application"] == "excel" and arguments.target.endswith("!used")
        read_count, last_descriptor = 0, None
        # A conservative byte allowance handles JSON escaping and 4-byte Unicode.
        while (index < len(plan) and consumed < arguments.max_chars and
               (read_count < arguments.max_items if packed else len(items) < min(arguments.max_items, 32))):
            count = min(arguments.max_chars - consumed, 1200)
            piece, next_offset = self.backend.piece(plan[index], offset, count)
            digest = sha256(canonical_json(piece).encode()).hexdigest()
            characters = len(piece.get("text") or "") + sum(len(c) for matrix in
                (piece.get("values"), piece.get("formulas")) if matrix for row in matrix for c in row if isinstance(c, str))
            if characters > count or (next_offset is not None and next_offset <= offset):
                raise OfficeUnavailable("The Office adapter exceeded its read bound.")
            item = {"target": token(), **piece}
            if packed:
                item = {"text": None, "values": None, "formulas": None, "style": None, "geometry": None, **item}
            candidate_items = [*items, item]
            descriptor = plan[index]
            if (packed and items and item.get("values") is not None and item.get("formulas") is not None
                    and items[-1].get("values") is not None and last_descriptor is not None
                    and descriptor[1] is last_descriptor[1] and descriptor[2] == last_descriptor[2]
                    and descriptor[3] == last_descriptor[3] + 1):
                combined = {**items[-1], "label": items[-1]["label"].split(":", 1)[0] + ":" + item["label"].rsplit("!", 1)[-1],
                    "values": [items[-1]["values"][0] + item["values"][0]],
                    "formulas": [items[-1]["formulas"][0] + item["formulas"][0]]}
                candidate_items = [*items[:-1], combined]
            candidate = {"session": arguments.session, "application": binding["document"]["application"],
                         "snapshot": snapshot, "items": candidate_items, "cursor": "0" * 32}
            if len(canonical_json(candidate).encode()) > MAX_RESULT_BYTES:
                break
            items = candidate_items
            read_count += 1
            last_descriptor = descriptor if item.get("values") is not None else None
            entry = (plan[index], offset, count, digest)
            if isinstance(plan[index], tuple) and plan[index][0] == "cell" and hasattr(self.backend, "capture_excel"):
                try:
                    state = getattr(self.backend, "capture_excel_source", self.backend.capture_excel)(plan[index])
                except OfficeUnavailable:
                    state = None
                if state is not None:
                    for old in targets.values():
                        if len(old) >= 6 and old[0][2:] == plan[index][2:] and self.backend.same(old[0][1], plan[index][1]) and not same_state(old[5], state):
                            raise OfficeConflict("Office conflict: the paged cell changed during the read.")
                    if piece.get("values") is not None and (not same_value(piece["values"][0][0], state["value"]) or piece["formulas"] != [[state["formula"]]]):
                        raise OfficeConflict("Office conflict: the cell changed while its snapshot was captured.")
                    entry += (state if next_offset is None else None, state)
            targets[item["target"]] = entry
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
            self.cursors[cursor] = (*signature, plan, index, offset, guard, snapshot)
        if arguments.cursor:
            self.cursors.pop(arguments.cursor, None)
        def size(entries):
            return sum(len(canonical_json(entry[5]).encode()) for entry in entries.values() if len(entry) >= 6)
        retained = sum(size(value[2]) for key, value in self.snapshots.items() if key != snapshot)
        if retained + size(targets) > MAX_STATE_BYTES:
            raise OfficeUnavailable("The Excel snapshot memory limit was reached. Refresh the connection.")
        self.snapshots[snapshot] = (arguments.session, binding["identity"], targets)
        return {"session": arguments.session, "application": binding["document"]["application"],
                "snapshot": snapshot, "items": items, "cursor": cursor}

    def close(self):
        self.excel.clear()
        self.word.clear()
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
