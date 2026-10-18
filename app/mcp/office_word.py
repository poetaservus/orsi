"""Guarded Word actions, exact approvals and owned restoration."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re
from uuid import uuid4
from time import monotonic

from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_contracts import MAX_RESULT_BYTES, canonical_json
from app.mcp.office_excel import MAX_STATE_BYTES, OfficeConflict, OfficeUnknown, digest, file_stamp
from app.mcp.office_word_native import replacement
from app.mcp.office_word_document import same_document
from app.mcp.office_write_diagnostics import category, native_step, safe_write_event


class WordNotApplied(OfficeConflict):
    """Readback proved that the failed attempt left the complete target unchanged."""


class WordEdits:
    def __init__(self, live):
        self.live = live
        self.snapshots, self.cursors, self.guards, self.recoveries = {}, {}, OrderedDict(), {}
        self.blocked = False
        self.workflows = {}
        from app.mcp.office_word_render import WordRenders
        self.renders = WordRenders(live)
        from app.mcp.office_word_assets import WordAssets
        self.assets = WordAssets()

    def clear(self):
        self.snapshots.clear()
        self.cursors.clear()
        self.guards.clear()
        self.recoveries.clear()
        self.renders.clear()
        self.assets.clear()
        self.workflows.clear()
        # An unknown outcome is not repaired by clearing in-memory authority.

    def workflow(self, binding):
        from app.mcp.office_word_document import signature
        from app.mcp.office_word_workflow import WordWorkflow
        key = binding["document"]["document"]
        workflow = self.workflows.setdefault(key, WordWorkflow())
        document = self.live.documents[key][1]
        guard = getattr(getattr(self.live, "backend", None), "word_read_guard", None)
        workflow.sync(guard(document) if callable(guard) else signature(str(document.Content.WordOpenXML)))
        return workflow

    def reviewed_call(self, name, arguments, binding, authority=None, operation=None):
        document = self.live.documents[binding["document"]["document"]][1]
        if isinstance(document, dict):
            # Legacy synthetic adapters have no native package or page pixels.
            if name == "office.word_review":
                raise OfficeConflict("This adapter cannot verify native Word pages.")
            return self.read(arguments, binding) if name == "office.read" else self.execute(name, arguments, binding, authority, operation)
        workflow = self.workflow(binding)
        if name == "office.word_review":
            workflow.inspect(arguments)
            return {"session": arguments.session, "word_workflow": workflow.evidence()}
        if name == "office.read":
            output = self.read(arguments, binding)
            if arguments.target == "authoring" and output.get("cursor") is None:
                workflow.authoring = {"snapshot": output["snapshot"], "revision": workflow.revision}
        else:
            output = self.execute(name, arguments, binding, authority, operation)
            if name == "office.word_compose":
                workflow.composed = True
            if output.get("outcome") == "applied":
                try:
                    from app.mcp.office_word_document import signature
                    document = self.live.documents[binding["document"]["document"]][1]
                    workflow.applied(signature(str(document.Content.WordOpenXML)))
                except Exception:
                    # The native action already returned a verified applied receipt.
                    # Losing subsequent workflow evidence must not lose that receipt.
                    workflow.edited = True
                    workflow.invalidate()
            elif output.get("saved") is True:
                try:
                    workflow = self.workflow(binding)
                except Exception:
                    workflow.saves.append({"revision": None, "operation": operation})
                    workflow.invalidate()
                else:
                    workflow.authoring = None
                    workflow.save(operation)
        output["word_workflow"] = workflow.evidence()
        return output

    @staticmethod
    def state_bytes(snapshot):
        return len(canonical_json([[entry["target"], entry["state"]] for entry in snapshot["entries"]]).encode()) + len(
            canonical_json([[d[2], d[3], offset, count, fingerprint] for d, offset, count, fingerprint in snapshot["pages"]]).encode()) + len(snapshot.get("document_guard", ""))

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
            lazy = arguments.target == "document" and callable(getattr(backend, "word_read_guard", None))
            guard = backend.word_read_guard(document) if lazy else None
            plan = read_call("word_plan", backend.plan, "word", document, arguments.target)
            entries = []
            for descriptor in plan:
                state = None
                if not lazy:
                    try:
                        state = read_call("word_capture", backend.capture_word, descriptor)
                    except OfficeUnavailable:
                        state = None  # Unsupported targets remain bounded read-only views.
                entries.append({"descriptor": descriptor, "target": uuid4().hex,
                                "state": state, "complete": False, "captured": not lazy})
            snapshot, index, offset = uuid4().hex, 0, 0
            record = {"signature": signature, "entries": entries, "pages": [], "complete": False}
            if lazy:
                record["document_guard"] = guard
            if self.state_bytes(record) + sum(self.state_bytes(r) for r in self.snapshots.values()) > MAX_STATE_BYTES:
                raise OfficeConflict("The Word snapshot memory limit was reached. Reconnect explicitly.")
        # Recheck every observed fragment and formatting snapshot, not only the
        # last page. Retained native ranges reject shifted duplicate text.
        document_views = {}
        if record.get("document_guard") is not None:
            document = self.live.documents[binding["document"]["document"]][1]
            if backend.word_read_guard(document) != record["document_guard"]:
                raise OfficeConflict("Office conflict: the complete Word document changed during its read.")
        for entry in record["entries"]:
            if entry["state"] is not None:
                if record.get("document_guard") is not None and entry["descriptor"][0] == "word":
                    if not backend.word_read_anchor_valid(entry["descriptor"]):
                        raise OfficeConflict("Office conflict: the retained Word text anchor moved during its read.")
                elif not same_document(read_call("word_capture", backend.capture_word, entry["descriptor"]), entry["state"]):
                    raise OfficeConflict("Office conflict: the Word target changed during its read.")
            if entry["state"] is not None and entry["state"].get("kind") == "document":
                document_views[id(entry["descriptor"][1])] = canonical_json(entry["state"]["view"])
        def piece(descriptor, offset, count):
            # A complete native package already guards this immutable view.
            # Re-exporting all section/header dependencies for every 1200-char
            # slice exceeds the ordinary read deadline. Check the full package
            # before and after this read, while slicing the retained snapshot.
            view = document_views.get(id(descriptor[1])) if descriptor[0] == "word_document" else None
            if view is None:
                return read_call("word_piece", backend.piece, descriptor, offset, count)
            text = view[offset:offset + count]
            return {"label": "Complete report authoring snapshot", "text": text}, (offset + len(text) if offset + len(text) < len(view) else None)
        for descriptor, old_offset, count, fingerprint in record["pages"]:
            fragment, _ = piece(descriptor, old_offset, count)
            if digest(fragment) != fingerprint:
                raise OfficeConflict("Office conflict: an earlier Word read fragment changed.")
        items, consumed, pages, captured = [], 0, [], 0
        while index < len(record["entries"]) and consumed < arguments.max_chars and len(items) < min(arguments.max_items, 32):
            entry = record["entries"][index]
            if not entry.get("captured", True):
                if captured >= 4:
                    break
                try:
                    entry["state"] = read_call("word_capture", backend.capture_word, entry["descriptor"])
                except OfficeUnavailable:
                    entry["state"] = None
                entry["captured"] = True
                captured += 1
            count = min(arguments.max_chars - consumed, 1200)
            fragment, next_offset = piece(entry["descriptor"], offset, count)
            text = fragment.get("text") or ""
            if len(text) > count or (next_offset is not None and next_offset <= offset):
                raise OfficeUnavailable("The Word reader exceeded its bound.")
            item = {"target": entry["target"], **fragment}
            candidate = {"session": arguments.session, "application": "word", "snapshot": snapshot,
                         "items": [*items, item], "cursor": "0" * 32}
            if len(canonical_json(candidate).encode()) > MAX_RESULT_BYTES:
                break
            items.append(item)
            consumed += len(text)
            pages.append((entry["descriptor"], offset, count, digest(fragment)))
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
        for entry in record["entries"]:
            if entry["state"] is not None and entry["state"].get("kind") == "document" and not same_document(
                    read_call("word_capture", backend.capture_word, entry["descriptor"]), entry["state"]):
                raise OfficeConflict("Office conflict: the Word document changed during its read.")
        if record.get("document_guard") is not None and backend.word_read_guard(document) != record["document_guard"]:
            raise OfficeConflict("Office conflict: the complete Word document changed during its read.")
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
        if name in {"office.word_compose", "office.word_edit"} and binding["document"]["document"] in self.workflows:
            self.workflow(binding).before_edit()
        if name == "office.word_compose":
            from app.mcp.office_word_document import compile_packet
            record = self.snapshots.get(arguments.snapshot)
            if record is None or record["signature"][1] != "authoring":
                raise OfficeConflict("Read target=authoring completely before replacing the report. Layout/render snapshots cannot authorize editing. Read fresh authoring only for a justified replacement; never replay a settled edit.")
            entries = self.coverage(arguments, binding)
            if (len(entries) != 1 or entries[0]["state"] is None
                    or entries[0]["state"].get("kind") != "document"):
                raise OfficeConflict("Read target=authoring completely before replacing the report. Layout/render snapshots cannot authorize editing. Read a fresh complete authoring snapshot only if a concrete unresolved defect justifies replacement; never replay a settled edit.")
            descriptor, before = entries[0]["descriptor"], entries[0]["state"]
            if not same_document(backend.capture_word(descriptor), before):
                raise OfficeConflict("Office conflict: the complete report changed after its authoring read.")
            action = "compose"
            from app.inference.word_plan_diagnostics import record_word_plan
            record_word_plan("approval_plan", arguments.model_dump(mode="json"))
            media = self.assets.resolve(arguments)
            if media:
                record_word_plan("approval_plan", {**arguments.model_dump(mode="json"),
                    "_picture_metadata": [metadata for _, metadata in media.values()]})
            from hashlib import sha256
            expected = {"packet": compile_packet(document, arguments, before, media),
                        "plan": arguments.model_dump(mode="json"),
                        "media": {key: sha256(value[0]).hexdigest() for key, value in media.items()}}
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
            checked = expected["fingerprint"] if name == "office.revert" else [expected["plan"], expected["media"]]
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
                       f"{len(arguments.blocks)} native content blocks, "
                       f"{1 + sum(b.kind == 'section_break' for b in arguments.blocks)} sections and "
                       f"{sum(b.kind == 'image' for b in arguments.blocks)} embedded pictures. Save separately.")
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
        started = monotonic()
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
                        verify_document(document, plan, expected.get("media", {}))
                    after_descriptor = ("word_document", document, 0, int(document.Content.End))
                    stage = "recovery_capture"
                    with native_step(stage):
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
            diagnostic = {"tool": name, "stage": getattr(error, "orsi_write_stage", stage),
                "action": "save" if save is not None else "revert" if name == "office.revert" else action,
                "category": category(error), "hresult": getattr(error, "hresult", None),
                "step_ms": getattr(error, "orsi_write_step_ms", None),
                "duration_ms": round((monotonic() - started) * 1000), "outcome": "unknown"}
            # Reconcile on this STA using independent readback. Never rerun a
            # writer, insert, field operation or save after an exception.
            try:
                if save is not None:
                    backend.verify_word_save(document, save)
                    output = {"session": arguments.session, "operation": operation, "saved": True}
                    verified = "saved"
                else:
                    if action == "compose":
                        current_descriptor = ("word_document", document, 0, int(document.Content.End))
                        current = backend.capture_word(current_descriptor)
                        if name == "office.revert":
                            applied = same_document(current, expected)
                        else:
                            from app.mcp.office_word_document import verify_document
                            from app.mcp.office_contracts import WordComposeArguments
                            verify_document(document, WordComposeArguments.model_validate(expected["plan"]), expected.get("media", {}))
                            applied = True
                    else:
                        current_descriptor = ((*descriptor[:2], expected["start"], expected["end"], *descriptor[4:])
                            if action == "edit_table" else backend.word_descriptor(document, expected["start"], expected["end"]))
                        current = backend.capture_word(current_descriptor)
                        compared = set(expected) - ({"target", "uniform"} if action == "apply_style" else set())
                        applied = all(current.get(key) == expected[key] for key in compared)
                    if not applied:
                        raise OfficeUnknown("Word outcome verification did not match the approved result.")
                    recovery = uuid4().hex
                    self.recoveries[recovery] = (arguments.session, binding["document"]["document"],
                        current_descriptor, before, current, action)
                    if name == "office.revert":
                        self.recoveries.pop(arguments.recovery, None)
                    affected = sum(b["text"] != a["text"] or b["paragraph"] != a["paragraph"]
                        for b, a in zip(before["cells"], current["cells"], strict=True)) if action == "edit_table" else 1
                    output = {"session": arguments.session, "operation": operation, "outcome": "applied",
                        "affected_items": affected, "recovery": recovery}
                    verified = "applied"
            except Exception:
                verified = "unknown"
                if before is not None:
                    try:
                        # Original anchors/complete package also guard against
                        # foreign changes and partial formatting/image inserts.
                        if same_document(backend.capture_word(descriptor), before):
                            verified = "not_applied"
                    except Exception:
                        pass
            diagnostic["outcome"] = verified
            self.last_diagnostic = safe_write_event(diagnostic)
            if verified != "unknown":
                self.snapshots.clear()
                self.cursors.clear()
                self.renders.clear()
                self.guards.clear()
                self.blocked = False
                if verified == "not_applied":
                    failure = WordNotApplied("Word verified that the target is unchanged. Read it again and obtain fresh approval before retrying.")
                    failure.diagnostic = self.last_diagnostic
                    raise failure from None
                return output
            failure = OfficeUnknown("The Word mutation outcome is uncertain; inspect before another write.")
            failure.stage, failure.hresult, failure.mismatch = diagnostic["stage"], getattr(error, "hresult", None), mismatch
            failure.diagnostic = self.last_diagnostic
            raise failure from None
