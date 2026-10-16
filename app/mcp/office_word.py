"""Guarded Word actions, exact approvals and owned restoration."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re
from uuid import uuid4

from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_contracts import MAX_RESULT_BYTES, canonical_json
from app.mcp.office_excel import MAX_STATE_BYTES, OfficeConflict, OfficeUnknown, digest, file_stamp
from app.mcp.office_word_native import replacement
from app.mcp.office_word_document import same_document


class WordEdits:
    def __init__(self, live):
        self.live = live
        self.snapshots, self.cursors, self.guards, self.recoveries = {}, {}, OrderedDict(), {}
        self.blocked = False
        from app.mcp.office_word_render import WordRenders
        self.renders = WordRenders(live)

    def clear(self):
        self.snapshots.clear()
        self.cursors.clear()
        self.guards.clear()
        self.recoveries.clear()
        self.renders.clear()
        # An unknown outcome is not repaired by clearing in-memory authority.

    @staticmethod
    def state_bytes(snapshot):
        return len(canonical_json([[entry["target"], entry["state"]] for entry in snapshot["entries"]]).encode()) + len(
            canonical_json([[d[2], d[3], offset, count, fingerprint] for d, offset, count, fingerprint in snapshot["pages"]]).encode())

    def read(self, arguments, binding):
        from app.mcp.office_read_diagnostics import read_call
        if arguments.target.startswith("render:"):
            return read_call("word_render", self.renders.read, arguments, binding)
        backend = self.live.backend
        signature = (arguments.session, arguments.target, binding["identity"])
        if arguments.cursor:
            continuation = self.cursors.get(arguments.cursor)
            if continuation is None or continuation[:3] != signature:
                raise OfficeConflict("The Word read cursor belongs to another target or session.")
            snapshot, index, offset = continuation[3:]
            record = self.snapshots.get(snapshot)
            if record is None:
                raise OfficeConflict("Read a fresh Word snapshot.")
        else:
            if len(self.snapshots) >= 128:
                raise OfficeConflict("The Word snapshot limit was reached. Reconnect explicitly.")
            document = self.live.documents[binding["document"]["document"]][1]
            plan = read_call("word_plan", backend.plan, "word", document, arguments.target)
            entries = []
            for descriptor in plan:
                try:
                    state = read_call("word_capture", backend.capture_word, descriptor)
                except OfficeUnavailable:
                    state = None  # Unsupported targets remain bounded read-only views.
                entries.append({"descriptor": descriptor, "target": uuid4().hex,
                                "state": state, "complete": False})
            snapshot, index, offset = uuid4().hex, 0, 0
            record = {"signature": signature, "entries": entries, "pages": [], "complete": False}
            if self.state_bytes(record) + sum(self.state_bytes(r) for r in self.snapshots.values()) > MAX_STATE_BYTES:
                raise OfficeConflict("The Word snapshot memory limit was reached. Reconnect explicitly.")
        # Recheck every observed fragment and formatting snapshot, not only the
        # last page. Retained native ranges reject shifted duplicate text.
        for entry in record["entries"]:
            if entry["state"] is not None and not same_document(read_call("word_capture", backend.capture_word, entry["descriptor"]), entry["state"]):
                raise OfficeConflict("Office conflict: the Word target changed during its read.")
        for descriptor, old_offset, count, fingerprint in record["pages"]:
            piece, _ = read_call("word_piece", backend.piece, descriptor, old_offset, count)
            if digest(piece) != fingerprint:
                raise OfficeConflict("Office conflict: an earlier Word read fragment changed.")
        items, consumed, pages = [], 0, []
        while index < len(record["entries"]) and consumed < arguments.max_chars and len(items) < min(arguments.max_items, 32):
            entry = record["entries"][index]
            count = min(arguments.max_chars - consumed, 1200)
            piece, next_offset = read_call("word_piece", backend.piece, entry["descriptor"], offset, count)
            text = piece.get("text") or ""
            if len(text) > count or (next_offset is not None and next_offset <= offset):
                raise OfficeUnavailable("The Word reader exceeded its bound.")
            item = {"target": entry["target"], **piece}
            candidate = {"session": arguments.session, "application": "word", "snapshot": snapshot,
                         "items": [*items, item], "cursor": "0" * 32}
            if len(canonical_json(candidate).encode()) > MAX_RESULT_BYTES:
                break
            items.append(item)
            consumed += len(text)
            pages.append((entry["descriptor"], offset, count, digest(piece)))
            if next_offset is None:
                entry["complete"] = True
                index, offset = index + 1, 0
            else:
                offset = next_offset
        if index < len(record["entries"]) and not items:
            raise OfficeUnavailable("The Word item cannot fit the read limits.")
        if len(record["pages"]) + len(pages) > 8192:
            raise OfficeUnavailable("The Word read fragment limit was reached. Read a smaller target.")
        added = len(canonical_json([[d[2], d[3], off, count, fingerprint] for d, off, count, fingerprint in pages]).encode())
        retained = sum(self.state_bytes(value) for key, value in self.snapshots.items() if key != snapshot)
        if retained + self.state_bytes(record) + added > MAX_STATE_BYTES:
            raise OfficeUnavailable("The Word snapshot memory limit was reached. Reconnect explicitly.")
        record["pages"].extend(pages)
        cursor = None
        if index < len(record["entries"]):
            if len(self.cursors) >= 128 and not arguments.cursor:
                raise OfficeUnavailable("The Word cursor limit was reached. Reconnect explicitly.")
            cursor = uuid4().hex
            self.cursors[cursor] = (*signature, snapshot, index, offset)
        else:
            record["complete"] = True
        if arguments.cursor:
            self.cursors.pop(arguments.cursor, None)
        self.snapshots[snapshot] = record
        return {"session": arguments.session, "application": "word", "snapshot": snapshot,
                "items": items, "cursor": cursor}

    def coverage(self, arguments, binding):
        record = self.snapshots.get(arguments.snapshot)
        if record is None or (record["signature"][0], record["signature"][2]) != (arguments.session, binding["identity"]) or not record["complete"]:
            raise OfficeConflict("Read every cursor page of a fresh snapshot of this exact Word document first.")
        return record["entries"]

    def prepare(self, name, arguments, binding):
        if self.blocked or binding["document"]["application"] != "word":
            raise OfficeConflict("Word mutation is unavailable for this session.")
        backend = self.live.backend
        document = self.live.documents[binding["document"]["document"]][1]
        backend.word_writable(document)
        descriptor = before = expected = save = None
        action = "replace_text"
        if name == "office.word_compose":
            from app.mcp.office_word_document import compile_packet
            entries = self.coverage(arguments, binding)
            if (len(entries) != 1 or entries[0]["state"] is None
                    or entries[0]["state"].get("kind") != "document"):
                raise OfficeConflict("Read target=authoring completely before replacing the report.")
            descriptor, before = entries[0]["descriptor"], entries[0]["state"]
            if not same_document(backend.capture_word(descriptor), before):
                raise OfficeConflict("Office conflict: the complete report changed after its authoring read.")
            action = "compose"
            from app.inference.word_plan_diagnostics import record_word_plan
            record_word_plan("approval_plan", arguments.model_dump(mode="json"))
            expected = {"packet": compile_packet(document, arguments, before),
                        "plan": arguments.model_dump(mode="json")}
        elif name == "office.word_edit":
            entries = self.coverage(arguments, binding)
            if len(arguments.changes) != 1:
                raise OfficeConflict("Word patches support one exact action at a time.")
            change = arguments.changes[0]
            entry = next((e for e in entries if e["target"] == change.target and e["complete"]), None)
            if entry is None or entry["state"] is None:
                raise OfficeConflict("The Word snapshot does not cover this supported text anchor completely.")
            descriptor, before = entry["descriptor"], entry["state"]
            if not same_document(backend.capture_word(descriptor), before):
                raise OfficeConflict("Office conflict: Word text, formatting or anchor changed since the read.")
            action = change.action
            if action == "edit_table":
                from app.mcp.office_word_tables import table_replacement
                expected = table_replacement(before, change.cells)
            elif before.get("kind") == "table":
                raise OfficeConflict("Use edit_table for a structured table snapshot.")
            elif action == "apply_style":
                expected = backend.styled_word(descriptor, before, change.style)
            else:
                if action == "insert_after" and not change.text:
                    raise OfficeConflict("Insertion text must be nonempty.")
                expected = replacement(before, before["text"] + change.text if action == "insert_after" else change.text)
        elif name == "office.revert":
            entries = self.coverage(arguments, binding)
            recovery = self.recoveries.get(arguments.recovery)
            if recovery is None or recovery[:2] != (arguments.session, binding["document"]["document"]):
                raise OfficeConflict("This Word recovery is unavailable for the session.")
            descriptor, expected, before = recovery[2:5]
            action = recovery[5] if len(recovery) > 5 else "replace_text"
            current = backend.capture_word(descriptor)
            covered = any(e["complete"] and e["state"] is not None and
                same_document(e["state"], before) and
                backend.same(e["descriptor"][1], descriptor[1]) for e in entries) if action == "compose" else any(e["complete"] and e["state"] is not None and
                e["state"]["start"] <= before["start"] < before["end"] <= e["state"]["end"] and
                (e["state"] == before if before.get("kind") == "table" else
                 e["state"].get("paragraph") == before["paragraph"] and e["state"]["dependencies"] == before["dependencies"]) and
                backend.same(e["descriptor"][1], descriptor[1]) for e in entries)
            if not covered or not same_document(current, before):
                raise OfficeConflict("Office conflict: later Word changes or incomplete reads prevent restoration.")
        elif name == "office.save":
            destination = arguments.path or binding["path"]
            if destination is None:
                raise OfficeConflict("An unsaved Word document requires an explicit Save As destination.")
            path = Path(destination)
            if not path.is_absolute() or str(path).startswith(("\\\\", "//")) or path.suffix.lower() != ".docx":
                raise OfficeConflict("Word Save/Save As requires an absolute .docx destination.")
            stamp = file_stamp(path)
            if arguments.path and stamp is not None:
                raise OfficeConflict("Word Save As requires a new destination; replacement is unsupported.")
            save = {"path": str(path), "stamp": stamp, "save_as": arguments.path is not None}
        else:
            raise OfficeConflict("This Word action is not implemented.")
        if len(self.recoveries) >= 64 and save is None:
            raise OfficeConflict("The Word recovery limit was reached. Reconnect explicitly.")
        size = len(canonical_json([before, expected]).encode())
        if size + sum(len(canonical_json(r[3:]).encode()) for r in self.recoveries.values()) > MAX_STATE_BYTES:
            raise OfficeConflict("The Word recovery memory limit was reached.")
        if action == "compose":
            # Raw native exports contain fresh revision IDs on each capture.
            # Approval binds the complete semantic snapshot and typed plan.
            checked = expected["fingerprint"] if name == "office.revert" else expected["plan"]
            identity = digest([binding["identity"], name, arguments.model_dump(mode="json"),
                               before["fingerprint"], checked])
        else:
            identity = digest([binding["identity"], name, arguments.model_dump(mode="json"), before, expected, save])
        key = uuid4().hex
        self.guards[key] = (name, arguments.model_dump(mode="json"), binding["identity"], descriptor, before, expected, save, size, action)
        while len(self.guards) > 128 or sum(r[7] for r in self.guards.values()) > MAX_STATE_BYTES:
            self.guards.popitem(last=False)
        preview = "Save all current Word document changes" if save else (
            ("Restore" if name == "office.revert" else "Replace") + f" Word body text:{before['start']}:{before['end']} (UTF-16); preserve formatting")
        if action == "compose":
            preview = ("Restore the complete owned report revision" if name == "office.revert" else
                       "Replace ALL report body text, tables, page layout, headers and footers with "
                       f"{len(arguments.blocks)} native content blocks. No text boxes; save separately.")
        elif save is None and name != "office.revert" and action != "replace_text":
            preview = {"insert_after": "Insert after Word body text", "apply_style": "Apply Word paragraph style " + (arguments.changes[0].style or ""),
                       "edit_table": "Edit Word table"}[action] + f" at {before['start']}:{before['end']}; preserve unrelated text and structure"
        result = {"guard": key, "digest": identity, "preview": (binding["document"]["title"] + "\n" + preview)[:2000]}
        if name == "office.word_compose":
            from app.inference.word_plan_diagnostics import word_plan_shape
            # Private control response: summarize the complete plan actually
            # bound into the approval guard, never the document text or packet.
            result["word_plan_shape"] = word_plan_shape(expected["plan"])
        return result

    def execute(self, name, arguments, binding, authority, operation):
        record = self.guards.pop(authority.get("guard"), None)
        if self.blocked or record is None or record[:3] != (name, arguments.model_dump(mode="json"), binding["identity"]):
            raise OfficeConflict("Office conflict: the exact approved Word operation is unavailable.")
        _, _, _, descriptor, before, expected, save, _, action = record
        backend = self.live.backend
        document = self.live.documents[binding["document"]["document"]][1]
        backend.word_writable(document)
        if before is not None and not same_document(backend.capture_word(descriptor), before):
            raise OfficeConflict("Office conflict: the approved Word target changed before writing.")
        if save is not None and file_stamp(save["path"]) != save["stamp"]:
            raise OfficeConflict("Office conflict: the Word save destination changed after approval.")
        if not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", operation):
            raise OfficeConflict("The Office operation identity is invalid.")
        if save is None and before == expected:
            return {"session": arguments.session, "operation": operation, "outcome": "unchanged", "affected_items": 0}
        self.blocked = True
        stage, mismatch = "word_save" if save is not None else "word_native_insert", []
        try:
            if save is not None:
                backend.save_word(document, save)
                output = {"session": arguments.session, "operation": operation, "saved": True}
                # New path identity cannot inherit a read snapshot or approval.
                self.snapshots.clear()
                self.cursors.clear()
            else:
                if action == "compose":
                    from app.mcp.office_contracts import WordComposeArguments
                    from app.mcp.office_word_document import write_document, restore_document, verify_document
                    stage = "word_document_write"
                    if name == "office.revert":
                        restore_document(backend, document, expected)
                    else:
                        plan = WordComposeArguments.model_validate(expected["plan"])
                        write_document(backend, document, expected["packet"], plan)
                        stage = "word_document_readback"
                        verify_document(document, plan)
                    after_descriptor = ("word_document", document, 0, int(document.Content.End))
                    after = backend.capture_word(after_descriptor)
                    if name == "office.revert" and not same_document(after, expected):
                        raise OfficeUnknown("Word report restoration did not match its complete owned snapshot.")
                    if same_document(before, after):
                        self.snapshots.clear()
                        self.cursors.clear()
                        self.renders.clear()
                        self.blocked = False
                        return {"session": arguments.session, "operation": operation,
                                "outcome": "unchanged", "affected_items": 0}
                    recovery = uuid4().hex
                    self.recoveries[recovery] = (arguments.session, binding["document"]["document"],
                        after_descriptor, before, after, action)
                    if name == "office.revert":
                        self.recoveries.pop(arguments.recovery, None)
                    self.snapshots.clear()
                    self.cursors.clear()
                    self.renders.clear()
                    self.blocked = False
                    return {"session": arguments.session, "operation": operation, "outcome": "applied",
                            "affected_items": 1, "recovery": recovery}
                writer = backend.write_word_style if action == "apply_style" else (
                    backend.write_word_table if action == "edit_table" else backend.write_word)
                after_descriptor = writer(descriptor, expected)
                stage = "word_readback"
                after = backend.capture_word(after_descriptor)
                compared = set(expected) - ({"target", "uniform"} if action == "apply_style" else set())
                if any(after.get(key) != expected[key] for key in compared):
                    stage = "word_verification"
                    mismatch = [key for key in expected if after.get(key) != expected[key]]
                    if "paragraph" in mismatch and "paragraph" in expected:
                        for index, field in enumerate(("paragraph_identity", "paragraph_properties", "paragraph_runs")):
                            if after["paragraph"][index] != expected["paragraph"][index]:
                                mismatch.append(field)
                    raise OfficeUnknown("Word readback did not preserve the approved text and formatting.")
                recovery = uuid4().hex
                self.recoveries[recovery] = (arguments.session, binding["document"]["document"], after_descriptor, before, after, action)
                if name == "office.revert":
                    self.recoveries.pop(arguments.recovery, None)
                self.snapshots.pop(arguments.snapshot, None)
                self.cursors = {key: value for key, value in self.cursors.items() if value[3] != arguments.snapshot}
                output = {"session": arguments.session, "operation": operation, "outcome": "applied", "affected_items": 1, "recovery": recovery}
                if action == "edit_table":
                    output["affected_items"] = sum(b["text"] != a["text"] or b["paragraph"] != a["paragraph"]
                        for b, a in zip(before["cells"], after["cells"], strict=True))
            self.blocked = False
            return output
        except Exception as error:
            failure = OfficeUnknown("The Word mutation outcome is uncertain; inspect before another write.")
            failure.stage, failure.hresult, failure.mismatch = stage, getattr(error, "hresult", None), mismatch
            raise failure from None
