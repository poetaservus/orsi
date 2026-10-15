"""Creation-only native dashboard plans, bound to complete local cell snapshots."""
from __future__ import annotations

from app.mcp.office_contracts import ExcelPivot, ExcelSlicer, excel_range_shape
from app.mcp.office_excel import OfficeConflict, OfficeUnknown, same_state


def target(sheet, address):
    return "'" + sheet.replace("'", "''") + "'!" + address


class ExcelObjects:
    def __init__(self, edits):
        self.edits = edits

    @property
    def backend(self):
        return self.edits.live.backend

    def cells(self, source, binding, session, *, writable=False):
        from app.mcp.office_contracts import EditArguments
        entries = self.edits.coverage(EditArguments(session=session, snapshot=source.snapshot), binding)
        document = self.edits.live.documents[binding["document"]["document"]][1]
        plan = self.backend.plan("excel", document, target(source.sheet, source.range))
        captured = []
        for descriptor in plan:
            old = self.edits.matching(descriptor, entries)
            capture = self.backend.capture_excel if writable else getattr(self.backend, "capture_excel_source", self.backend.capture_excel)
            current = capture(descriptor)
            if old is None or not same_state(old[4], current):
                raise OfficeConflict("Read every dashboard source and destination cell completely before editing.")
            captured.append((descriptor, current))
        return captured

    def prepare(self, arguments, binding, ordinary_cells):
        backend = self.backend
        document = self.edits.live.documents[binding["document"]["document"]][1]
        result, names = [], set()
        for spec in arguments.objects:
            name = spec.name.casefold()
            if name in names:
                raise OfficeConflict("Dashboard object names must be unique within the patch.")
            names.add(name)
            destination = spec.destination if isinstance(spec, ExcelPivot) else "A1"
            from app.mcp.office_contracts import ExcelSource
            dest = self.cells(ExcelSource(snapshot=arguments.snapshot, sheet=spec.sheet, range=destination), binding, arguments.session, writable=spec.kind == "pivot")
            sheet = dest[0][0][1]
            backend.excel_drawing_writable(document, sheet)
            inventory = backend.excel_object_names(document, sheet)
            if spec.name.casefold() in {n.casefold() for n in inventory["names"]}:
                raise OfficeConflict("A dashboard object with this name already exists; choose a new name.")
            source = getattr(spec, "source", None) or getattr(spec, "link", None)
            source_cells = self.cells(source, binding, arguments.session) if source is not None else []
            source_sheet = source_cells[0][0][1] if source_cells else None
            pivot = None
            if isinstance(spec, ExcelPivot):
                rows, columns = excel_range_shape(spec.source.range)
                height, width = excel_range_shape(spec.destination)
                if height < 2 * (rows - 1) * len(spec.rows) + 8 or width < len(spec.rows) + 1:
                    raise OfficeConflict("The reserved PivotTable rectangle is too small for bounded creation.")
                if any(s["value"] is not None or s["formula"] for _, s in dest):
                    raise OfficeConflict("Reserve an empty rectangle for the new PivotTable.")
                backend.excel_pivot_destination(sheet, spec.destination)
                headers = [s["value"] for _, s in source_cells[:columns]]
                if (rows < 2 or any(not isinstance(h, str) or not h.strip() or h != h.strip() for h in headers)
                        or len({h.casefold() for h in headers}) != len(headers)
                        or any(field not in headers for field in [*spec.rows, spec.value_field])):
                    raise OfficeConflict("Pivot sources need unique text headers and the exact requested field names.")
                values = [s["value"] for _, s in source_cells[columns + headers.index(spec.value_field)::columns]]
                if spec.aggregate != "count" and any(v is not None and type(v) not in (int, float) for v in values):
                    raise OfficeConflict("This Pivot aggregation requires numeric values or empty cells.")
            elif isinstance(spec, ExcelSlicer):
                pivot = backend.excel_slicer_pivot(document, source_sheet, spec.source.range, spec.field)
            elif spec.kind == "chart":
                rows, columns = excel_range_shape(spec.source.range)
                if rows < 2 or not 2 <= columns <= 9 or (spec.chart_type in {"pie", "doughnut", "scatter"} and columns != 2):
                    raise OfficeConflict("Chart sources need a header row, a label/X column and one to eight value columns.")
                if any(not isinstance(s["value"], str) or not s["value"].strip() for _, s in source_cells[:columns]):
                    raise OfficeConflict("Chart sources require text headers in their first row.")
                if spec.chart_type == "scatter" and any(type(s["value"]) not in (int, float) for _, s in source_cells[columns::columns]):
                    raise OfficeConflict("Scatter charts require numeric X values.")
            if any(self.overlaps(d, c[0]) for d, _ in source_cells for c in ordinary_cells):
                raise OfficeConflict("Read object sources after their cell edits; create linked objects in a separate patch.")
            result.append({"spec": spec, "sheet": sheet, "source_sheet": source_sheet,
                           "source_cells": source_cells, "destination": dest, "pivot": pivot,
                           "inventory": inventory,
                           "pivot_state": backend.capture_excel_pivot(pivot) if pivot is not None else None})
        # A PivotTable writes cells. Its reserved footprint must not overlap another
        # object source/destination or a cell patch in the same operation.
        for index, plan in enumerate(result):
            if plan["spec"].kind != "pivot":
                continue
            others = [c[0] for c in ordinary_cells]
            others += [d for p in result for d, _ in p["source_cells"]]
            others += [d for j, p in enumerate(result) if j != index and p["spec"].kind == "pivot" for d, _ in p["destination"]]
            if any(self.overlaps(d, other) for d, _ in plan["destination"] for other in others):
                raise OfficeConflict("Keep PivotTable reserved cells separate from patch targets and object sources.")
        self.check(result, document, inventory=True)
        return result

    def overlaps(self, left, right):
        return left[2:] == right[2:] and self.backend.same(left[1], right[1])

    def signature(self, plans):
        return [{"spec": p["spec"].model_dump(mode="json"), "inventory": p["inventory"],
                 "source": [s for _, s in p["source_cells"]],
                 "destination": [s for _, s in p["destination"]], "pivot": p["pivot_state"]} for p in plans]

    def check(self, plans, document, *, inventory=False, late=False):
        backend = self.backend
        for plan in plans:
            spec = plan["spec"]
            if not backend.same(backend.excel_sheet(document, spec.sheet), plan["sheet"]):
                raise OfficeConflict("The dashboard destination worksheet changed.")
            source = getattr(spec, "source", None) or getattr(spec, "link", None)
            if source is not None and not backend.same(backend.excel_sheet(document, source.sheet), plan["source_sheet"]):
                raise OfficeConflict("The dashboard source worksheet changed.")
            backend.excel_drawing_writable(document, plan["sheet"])
            if inventory and backend.excel_object_names(document, plan["sheet"]) != plan["inventory"]:
                raise OfficeConflict("The dashboard object inventory changed after review.")
            destination = plan["destination"] if not late or spec.kind == "pivot" else []
            capture = getattr(backend, "capture_excel_source", backend.capture_excel)
            for descriptor, before in [*plan["source_cells"], *destination]:
                if not same_state(capture(descriptor), before):
                    raise OfficeConflict("The dashboard source or reserved cells changed after the read.")
            if plan["pivot"] is not None and backend.capture_excel_pivot(plan["pivot"]) != plan["pivot_state"]:
                raise OfficeConflict("The slicer's source PivotTable changed after review.")

    def create(self, plan, document):
        spec = plan["spec"]
        backend = self.backend
        names = backend.excel_object_names(document, plan["sheet"])["names"]
        if spec.name.casefold() in {n.casefold() for n in names}:
            raise OfficeUnknown("A dashboard object name became occupied during the patch.")
        obj, auxiliary = backend.create_excel_object(document, spec, plan["sheet"], plan["source_sheet"], plan["pivot"])
        state = backend.capture_excel_object(document, spec, obj, auxiliary)
        backend.verify_excel_object(spec, state)
        cells = []
        if spec.kind == "pivot":
            cells = [(d, before, backend.capture_excel(d)) for d, before in plan["destination"]]
        return {"spec": spec, "object": obj, "auxiliary": auxiliary, "state": state,
                "sheet": plan["sheet"], "source_sheet": plan["source_sheet"]}, cells

    def check_recovery(self, records, document):
        for record in records:
            spec = record["spec"]
            if (not self.backend.same(self.backend.excel_sheet(document, spec.sheet), record["sheet"])
                    or not self.backend.excel_object_matches(document, spec, record["object"], record["auxiliary"])
                    or self.backend.capture_excel_object(document, spec, record["object"], record["auxiliary"]) != record["state"]):
                raise OfficeConflict("Later changes to an owned dashboard object prevent restoration.")
            source = getattr(spec, "source", None) or getattr(spec, "link", None)
            if source is not None and not self.backend.same(self.backend.excel_sheet(document, source.sheet), record["source_sheet"]):
                raise OfficeConflict("The dashboard source worksheet changed before restoration.")
            if spec.kind == "pivot" and self.backend.excel_pivot_has_slicers(document, record["object"]):
                raise OfficeConflict("Remove the dependent slicer's owned edit before restoring this PivotTable.")

    def remove(self, records, document):
        self.check_recovery(records, document)
        for record in reversed(records):
            self.backend.delete_excel_object(document, record["spec"], record["object"], record["auxiliary"])
