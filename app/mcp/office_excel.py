"""Bounded Excel patches and guarded in-memory restoration. No ordinary Undo."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_contracts import canonical_json, excel_range_shape


class OfficeConflict(OfficeUnavailable):
    """A proven pre-write rejection; never raised after mutation starts."""


class OfficeUnknown(OfficeUnavailable):
    """A dispatched mutation may have completed or partially completed."""


READ_TOOLS = frozenset(("office.documents", "office.attach", "office.read", "office.image_register"))
EXCEL_TOOLS = READ_TOOLS | {"office.excel_edit", "office.revert", "office.save"}
WORD_TOOLS = READ_TOOLS | {"office.word_edit", "office.word_compose", "office.revert", "office.save"}
LIVE_TOOLS = EXCEL_TOOLS | WORD_TOOLS


def live_tools(applications):
    return READ_TOOLS | (EXCEL_TOOLS if "excel" in applications else set()) | (WORD_TOOLS if "word" in applications else set())
MAX_STATE_BYTES = 8 * 1024 * 1024
FUNCTIONS = frozenset("SUM AVERAGE MIN MAX COUNT COUNTA ROUND ROUNDUP ROUNDDOWN ABS IF IFERROR AND OR NOT TRUE FALSE CONCAT CONCATENATE LEN LEFT RIGHT MID TRIM UPPER LOWER SUMIF COUNTIF SUMIFS COUNTIFS DATE YEAR MONTH DAY SUMPRODUCT NUMBERVALUE CHAR GETPIVOTDATA".split())
SHEET_REFERENCE = re.compile(r"('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!(\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}(?:\s*:\s*\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6})?)(?![A-Za-z0-9_.])")


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def same_value(left, right):
    # Excel numbers are doubles; Python's True == 1 must not hide a user change.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def same_state(left, right):
    return left.keys() == right.keys() and all(same_value(left[key], right[key]) for key in left)


def validate_formula(formula, sheet_resolver=None):
    references = {}
    if formula == "":
        return references
    if not formula.startswith("="):
        raise OfficeConflict("Use values for literal content; formulas must start with equals.")
    # The initial adapter supports local cell references and a small set of pure
    # built-in functions. No defined names, external links, DDE, UDFs or network functions.
    remaining = re.sub(r'"(?:[^"]|"")*"', '0', formula[1:])
    def qualified(match):
        if sheet_resolver is None or (match.start() and remaining[match.start() - 1] in ":!]"):
            raise OfficeConflict("This formula is outside the supported local Excel subset.")
        name, address = match.groups()
        name = name[1:-1].replace("''", "'") if name.startswith("'") else name
        # Excel rejects these characters in worksheet names. In particular, a
        # quoted external-workbook path must never be mistaken for a local sheet.
        if any(c in name for c in "[]:*?/\\"):
            raise OfficeConflict("External and 3D Excel references are not supported.")
        references[name] = sheet_resolver(name)
        try:
            excel_range_shape(address.replace(" ", ""))
        except ValueError:
            raise OfficeConflict("A formula reference exceeds the bounded worksheet range limit.") from None
        return address
    remaining = SHEET_REFERENCE.sub(qualified, remaining)
    if re.search(r'[^A-Za-z0-9_$.,:() +*/^%&<>=\-]', remaining):
        raise OfficeConflict("This formula is outside the supported local Excel subset.")
    remaining = remaining.replace("$", "")
    for match in re.finditer(r"[A-Za-z_][A-Za-z_0-9.]*", remaining):
        name = match.group().upper()
        after = remaining[match.end():].lstrip()
        if after.startswith("("):
            if name not in FUNCTIONS:
                raise OfficeConflict("This Excel function is not supported.")
        elif name not in {"TRUE", "FALSE"} and not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", name):
            raise OfficeConflict("Named and external Excel references are not supported.")
        elif name not in {"TRUE", "FALSE"}:
            try:
                excel_range_shape(name)
            except ValueError:
                raise OfficeConflict("A formula reference is outside supported worksheet bounds.") from None
    for address in re.findall(r"[A-Za-z]{1,3}[0-9]+:[A-Za-z]{1,3}[0-9]+", remaining.replace(" ", "")):
        try:
            excel_range_shape(address)
        except ValueError:
            raise OfficeConflict("A formula reference exceeds the bounded local range limit.") from None
    return references


def formula_key(formula):
    return re.sub(r'"(?:[^"]|"")*"|[^\"]+', lambda m:
                  m.group() if m.group().startswith('"') else re.sub(r"\s+", "", m.group()).upper(), formula)


def file_stamp(path):
    """Local metadata fingerprint only; no file contents are retained or transmitted."""
    path = Path(path)
    if not path.parent.is_dir() or path.is_symlink():
        raise OfficeConflict("The save destination is unavailable or redirected.")
    if not path.exists():
        return None
    if not path.is_file():
        raise OfficeConflict("The save destination must be a regular file.")
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


class ExcelEdits:
    def __init__(self, live):
        from app.mcp.office_excel_objects import ExcelObjects
        self.live = live
        self.guards, self.recoveries = OrderedDict(), {}
        self.sheet_references = {}
        self.blocked = False
        self.objects = ExcelObjects(self)

    def clear(self):
        self.guards.clear()
        self.recoveries.clear()
        self.sheet_references.clear()
        # A blocked service cannot become writable again by clearing handles.

    def coverage(self, arguments, binding):
        snapshot = self.live.snapshots.get(arguments.snapshot)
        if snapshot is None or snapshot[:2] != (arguments.session, binding["identity"]):
            raise OfficeConflict("Office conflict: read a fresh snapshot of this exact workbook.")
        return [entry for entry in snapshot[2].values() if len(entry) >= 5 and entry[4] is not None]

    def matching(self, descriptor, coverage):
        backend = self.live.backend
        return next((entry for entry in coverage if descriptor[2:] == entry[0][2:] and
                     backend.same(descriptor[1], entry[0][1])), None)

    def prepare(self, name, arguments, binding):
        if self.blocked or binding["document"]["application"] != "excel":
            raise OfficeConflict("Office mutation is unavailable for this session.")
        backend = self.live.backend
        document = self.live.documents[binding["document"]["document"]][1]
        backend.excel_writable(document)
        cells, save, references, object_plans, object_recovery = [], None, {}, [], []
        def resolve_sheet(name):
            try:
                sheet = backend.excel_sheet(document, name)
            except Exception:
                raise OfficeConflict("A referenced worksheet is unavailable in the attached workbook.") from None
            for key, (owner, retained) in self.sheet_references.items():
                if owner == binding["document"]["document"]:
                    try:
                        if backend.same(sheet, retained):
                            return key
                    except Exception:
                        pass  # Deleted sheets can leave disconnected retained COM references.
            if len(self.sheet_references) >= 1024:
                raise OfficeConflict("The worksheet reference limit was reached. Reconnect explicitly.")
            key = uuid4().hex
            self.sheet_references[key] = (binding["document"]["document"], sheet)
            return key
        if name == "office.excel_edit":
            coverage = self.coverage(arguments, binding)
            for change in arguments.changes:
                plan = backend.plan("excel", document, "'" + change.sheet.replace("'", "''") + "'!" + change.range)
                for index, descriptor in enumerate(plan):
                    prior_index = next((i for i, c in enumerate(cells) if descriptor[2:] == c[0][2:]
                                        and backend.same(descriptor[1], c[0][1])), None)
                    old = self.matching(descriptor, coverage)
                    if old is None:
                        raise OfficeConflict("Office conflict: the snapshot does not cover every requested cell completely.")
                    current = backend.capture_excel(descriptor)
                    if not same_state(current, old[4]):
                        raise OfficeConflict("Office conflict: the cell content or formatting changed since the read.")
                    references.update(validate_formula(current["formula"], resolve_sheet))
                    expected = dict(current)
                    columns = len(change.values[0]) if change.values is not None else (
                              len(change.formulas[0]) if change.formulas is not None else 1)
                    row, column = divmod(index, columns)
                    fields = set()
                    if change.values is not None:
                        value = change.values[row][column]
                        if type(value) is int and abs(value) > 999_999_999_999_999:
                            raise OfficeConflict("Use text for integers beyond Excel's 15-digit precision.")
                        expected.update(value=None if value == "" else value, formula="")
                        fields.update(("value", "formula"))
                    if change.formulas is not None:
                        formula = change.formulas[row][column]
                        references.update(validate_formula(formula, resolve_sheet))
                        expected["formula"] = formula
                        if not formula:
                            expected["value"] = None
                            fields.add("value")
                        fields.add("formula")
                    for field in ("number_format", "bold", "italic", "fill_color"):
                        value = getattr(change, field)
                        if value is not None:
                            if field == "fill_color":
                                value = value.upper() if value != "none" else value
                                if "fill_color" not in current:
                                    raise OfficeConflict("This Excel backend cannot capture native fills for restoration.")
                            expected[field] = value
                            fields.add(field)
                    if prior_index is None:
                        cells.append((descriptor, current, expected, sorted(fields)))
                    else:
                        previous = cells[prior_index]
                        if any(not same_value(previous[2][f], expected[f]) for f in fields & set(previous[3])):
                            raise OfficeConflict("Conflicting assignments to the same Excel cell. Combine compatible fields "
                                                 "in one change; choose one value or formula for each cell.")
                        merged = dict(previous[2])
                        merged.update({f: expected[f] for f in fields})
                        cells[prior_index] = (previous[0], previous[1], merged, sorted(set(previous[3]) | fields))
            object_plans = self.objects.prepare(arguments, binding, cells)
        elif name == "office.revert":
            record = self.recoveries.get(arguments.recovery)
            if record is None or record[:2] != (arguments.session, binding["document"]["document"]):
                raise OfficeConflict("This Excel recovery is unavailable for the session.")
            coverage = self.coverage(arguments, binding)
            for sheet_name, key in record[3].items():
                if resolve_sheet(sheet_name) != key:
                    raise OfficeConflict("A referenced worksheet changed after the owned edit.")
                references[sheet_name] = key
            object_recovery = record[4] if len(record) > 4 else []
            self.objects.check_recovery(object_recovery, document)
            for descriptor, before, after in record[2]:
                old = self.matching(descriptor, coverage)
                current = backend.capture_excel(descriptor)
                if old is None or not same_state(old[4], current) or not same_state(current, after):
                    raise OfficeConflict("Office conflict: later cell changes prevent restoration.")
                cells.append((descriptor, current, before, sorted(before)))
        elif name == "office.save":
            destination = arguments.path or binding["path"]
            if destination is None:
                raise OfficeConflict("An unsaved workbook requires an explicit Save As destination.")
            path = Path(destination)
            if not path.is_absolute() or path.suffix.lower() not in {".xlsx", ".xlsm", ".xlsb", ".xls"}:
                raise OfficeConflict("Use an absolute supported Excel workbook destination.")
            if arguments.path and path.suffix.lower() != ".xlsx":
                raise OfficeConflict("Initial Save As supports .xlsx workbooks only.")
            stamp = file_stamp(path)
            if arguments.path and stamp is not None and not arguments.overwrite:
                raise OfficeConflict("The Save As destination exists; explicit overwrite permission is required.")
            if arguments.path and stamp is not None:
                raise OfficeConflict("Save As replacement is not supported yet; use Save or choose a new destination.")
            # Workbook.Saved is not a revision counter. Save binds the document and
            # destination; the review explicitly saves all its current unsaved changes.
            save = {"path": str(path), "stamp": stamp, "save_as": arguments.path is not None}
        else:
            raise OfficeConflict("This Office mutation is not supported.")
        if len(self.recoveries) >= 64 and name == "office.excel_edit":
            raise OfficeConflict("The Excel recovery limit was reached. Reconnect explicitly.")
        states = [[list(d[2:]), before, expected, fields] for d, before, expected, fields in cells]
        object_states = self.objects.signature(object_plans) + [r["state"] for r in object_recovery]
        state_bytes = len(canonical_json([states, object_states]).encode())
        if object_plans:
            # Reserve both before/after cells plus bounded native metadata, not
            # just the smaller pre-creation source snapshot.
            state_bytes = state_bytes * 2 + 128_000 * len(object_plans)
        retained = sum(len(canonical_json([[[b, a] for _, b, a in rec[2]],
            [r["state"] for r in rec[4]] if len(rec) > 4 else []]).encode()) for rec in self.recoveries.values())
        if state_bytes + retained > MAX_STATE_BYTES:
            raise OfficeConflict("The bounded Excel recovery memory limit was reached.")
        identity = digest([binding["identity"], name, arguments.model_dump(mode="json"), states, save, references, object_states])
        key = uuid4().hex
        self.guards[key] = (identity, name, arguments.model_dump(mode="json"), binding["identity"], cells, save, state_bytes, references, object_plans, object_recovery)
        while len(self.guards) > 128 or sum(value[6] for value in self.guards.values()) > MAX_STATE_BYTES:
            self.guards.popitem(last=False)
        preview = ("Save all current workbook changes" if save else
                   ("Restore" if name == "office.revert" else "Edit") + f" {len(cells)} Excel cells")
        if name == "office.excel_edit":
            preview += ": " + "; ".join(c.sheet + "!" + c.range for c in arguments.changes)
            if object_plans:
                preview += "\nCreate " + "; ".join(p["spec"].kind + " " + p["spec"].sheet + "!" + p["spec"].name for p in object_plans)
        if object_recovery:
            preview += "\nRemove " + "; ".join(r["spec"].kind + " " + r["spec"].sheet + "!" + r["spec"].name for r in object_recovery)
        return {"guard": key, "digest": identity,
                "preview": (binding["document"]["title"] + "\n" + preview)[:2000]}

    def execute(self, name, arguments, binding, authority, operation):
        record = self.guards.pop(authority.get("guard"), None)
        if self.blocked or record is None or record[1:4] != (
                name, arguments.model_dump(mode="json"), binding["identity"]):
            raise OfficeConflict("Office conflict: the approved patch binding is unavailable.")
        _, _, _, _, cells, save, _, references, object_plans, object_recovery = record
        backend = self.live.backend
        document = self.live.documents[binding["document"]["document"]][1]
        backend.excel_writable(document)
        def check_references():
            for sheet_name, key in references.items():
                try:
                    current = backend.excel_sheet(document, sheet_name)
                    retained = self.sheet_references[key][1]
                    matches = backend.same(current, retained)
                except Exception:
                    matches = False
                if not matches:
                    raise OfficeConflict("Office conflict: a referenced worksheet changed after approval.")
        check_references()
        self.objects.check(object_plans, document, inventory=True)
        self.objects.check_recovery(object_recovery, document)
        # Preflight every cell before touching any cell. Recheck each again at its write.
        for descriptor, before, _, _ in cells:
            if not same_state(backend.capture_excel(descriptor), before):
                raise OfficeConflict("Office conflict: the approved cell target changed before writing.")
        if save is not None and file_stamp(save["path"]) != save["stamp"]:
            raise OfficeConflict("Office conflict: the save destination changed after approval.")
        if not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", operation):
            raise OfficeConflict("The Office operation identity is invalid.")
        changed = [c for c in cells if any(not same_value(c[1][f], c[2][f]) for f in c[3])]
        if save is None and not changed and not object_plans and not object_recovery:
            return {"session": arguments.session, "operation": operation, "outcome": "unchanged", "affected_items": 0}
        self.blocked = True
        try:
            if save is not None:
                backend.save_excel(document, save, arguments.overwrite)
                output = {"session": arguments.session, "operation": operation, "saved": True}
            else:
                self.objects.remove(object_recovery, document)
                removed_pivot_cells = [d for r in object_recovery if r["spec"].kind == "pivot"
                    for d in backend.plan("excel", document,
                        "'" + r["spec"].sheet.replace("'", "''") + "'!" + r["spec"].destination)]
                recalculation_started = False
                for descriptor, before, expected, fields in changed:
                    check_references()
                    current = backend.capture_excel(descriptor)
                    # Earlier cells in this approved patch can recalculate a later
                    # formula. Its expression and formatting remain the editable
                    # source; literal values still require an exact match.
                    check_before = dict(before)
                    if any(self.objects.overlaps(descriptor, d) for d in removed_pivot_cells):
                        check_before.update(value=None, formula="")
                        # Removing a native PivotTable resets its data-cell
                        # number formats. Admit only the captured original
                        # format as an alternative to the applied format.
                        if same_value(current["number_format"], expected["number_format"]):
                            check_before["number_format"] = expected["number_format"]
                    checked = set(check_before) - ({"value"} if before["formula"] and recalculation_started else set())
                    if any(not same_value(current[f], check_before[f]) for f in checked):
                        raise OfficeUnknown("An Excel target changed during a patch.")
                    backend.write_excel(descriptor, expected, fields)
                    recalculation_started |= bool({"value", "formula"} & set(fields))
                verified = []
                for descriptor, before, expected, fields in changed:
                    after = backend.capture_excel(descriptor)
                    checked = set(expected) - {"formula"}
                    if "fill_color" in fields and "_fill" not in fields:
                        checked.discard("_fill")
                    if "formula" in fields and expected["formula"]:
                        checked.discard("value")
                    if any(not same_value(after[f], expected[f]) for f in checked) or (
                            formula_key(after["formula"]) != formula_key(expected["formula"])):
                        raise OfficeUnknown("Excel verification did not match the requested patch.")
                    verified.append((descriptor, before, after))
                created = []
                for plan in object_plans:
                    self.objects.check([plan], document, late=True)
                    item, pivot_cells = self.objects.create(plan, document)
                    created.append(item)
                    verified.extend(pivot_cells)
                # Native state is captured after all creations, since later
                # objects can legitimately add relationships to earlier ones.
                for item in created:
                    item["state"] = backend.capture_excel_object(document, item["spec"], item["object"], item["auxiliary"])
                recovery = uuid4().hex
                recoverable = name == "office.excel_edit" or not object_recovery
                if recoverable:
                    self.recoveries[recovery] = (arguments.session, binding["document"]["document"], verified, references, created)
                if name == "office.revert":
                    self.recoveries.pop(arguments.recovery, None)
                self.live.snapshots.pop(arguments.snapshot, None)
                self.live.cursors = {key: value for key, value in self.live.cursors.items()
                                     if value[-1] != arguments.snapshot}
                output = {"session": arguments.session, "operation": operation, "outcome": "applied",
                          "affected_items": len(changed) + len(object_plans) + len(object_recovery),
                          "recovery": recovery if recoverable else None}
            self.blocked = False
            return output
        except Exception:
            raise OfficeUnknown("The Excel mutation outcome is uncertain; inspect before another write.") from None
