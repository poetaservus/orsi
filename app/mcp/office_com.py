"""Read-only Office automation. Every object and call lives on the bridge STA."""
from __future__ import annotations

import ctypes
import gc
import math
from pathlib import Path
import re
from threading import get_ident
from uuid import UUID

from app.mcp.office_discovery import OFFICE_REGISTRATIONS


class OfficeUnavailable(RuntimeError):
    """Only fixed, content-free messages cross the bridge boundary."""


class WindowsOffice:
    def __init__(self):
        import pythoncom
        import win32com.client.dynamic
        self.com, self.dynamic = pythoncom, win32com.client.dynamic
        self.thread = get_ident()
        self.com.CoInitializeEx(self.com.COINIT_APARTMENTTHREADED)

    def check_thread(self):
        if get_ident() != self.thread:
            raise OfficeUnavailable("Office calls require the owning STA.")
        self.com.PumpWaitingMessages()

    def same(self, left, right):
        return (left._oleobj_.QueryInterface(self.com.IID_IUnknown) ==
                right._oleobj_.QueryInterface(self.com.IID_IUnknown))

    def applications(self, enabled):
        self.check_thread()
        applications = []

        def add(kind, value):
            if kind in enabled and not any(kind == k and self.same(value, v) for k, v in applications):
                applications.append((kind, value))

        for kind in enabled:
            try:
                value = self.com.GetActiveObject(OFFICE_REGISTRATIONS[kind][0])
                add(kind, self.dynamic.Dispatch(value.QueryInterface(self.com.IID_IDispatch)))
            except self.com.com_error:
                pass
        # GetActiveObject alone can return only one instance. Native Office window
        # objects also reach unsaved documents in other visible application instances.
        import win32gui
        classes = {"EXCEL7": "excel", "_WwG": "word", "paneClassDC": "powerpoint"}
        roots = {"XLMAIN", "OpusApp", "PPTFrameClass", "PP12FrameClass"}
        handles = []

        def child(hwnd, _):
            try:
                if len(handles) < 2048 and classes.get(win32gui.GetClassName(hwnd)) in enabled:
                    handles.append(hwnd)
            except win32gui.error:
                pass
            return True

        def root(hwnd, _):
            try:
                if win32gui.GetClassName(hwnd) in roots:
                    win32gui.EnumChildWindows(hwnd, child, None)
            except win32gui.error:
                pass
            return True

        win32gui.EnumWindows(root, None)
        oleacc = ctypes.OleDLL("oleacc")
        function = oleacc.AccessibleObjectFromWindow
        function.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                             ctypes.POINTER(ctypes.c_void_p)]
        function.restype = ctypes.c_long
        iid = ctypes.create_string_buffer(UUID(str(self.com.IID_IDispatch)).bytes_le)
        for hwnd in handles:
            pointer = ctypes.c_void_p()
            try:
                if function(hwnd, 0xFFFFFFF0, iid, ctypes.byref(pointer)) != 0 or not pointer.value:
                    continue
                try:
                    dispatch = self.com.ObjectFromAddress(pointer.value, self.com.IID_IDispatch)
                    window = self.dynamic.Dispatch(dispatch)
                    add(classes[win32gui.GetClassName(hwnd)], window.Application)
                finally:
                    # AccessibleObjectFromWindow owns one reference; ObjectFromAddress
                    # obtains its own. Release the original on this same STA.
                    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(pointer)
            except (self.com.com_error, OSError, AttributeError):
                continue
        return applications

    def documents(self, enabled):
        result = []
        for kind, application in self.applications(enabled):
            try:
                collection = getattr(application, {"excel": "Workbooks", "word": "Documents",
                                                    "powerpoint": "Presentations"}[kind])
                for index in range(1, min(int(collection.Count), 256) + 1):
                    document = collection.Item(index)
                    if len(result) >= 256:
                        raise OfficeUnavailable("Too many open Office documents.")
                    if not any(kind == k and self.same(document, d) for k, d in result):
                        result.append((kind, document))
            except self.com.com_error:
                # A busy or closing application never redirects to another instance.
                continue
        return result

    def metadata(self, kind, document):
        self.check_thread()
        path = str(document.FullName) if str(document.Path) else None
        return {"title": str(document.Name)[:256], "dirty": not bool(document.Saved),
                "read_only": bool(document.ReadOnly), "path": path}

    def alive(self, kind, document):
        self.check_thread()
        collection = getattr(document.Application, {"excel": "Workbooks", "word": "Documents",
                                                    "powerpoint": "Presentations"}[kind])
        return any(self.same(document, collection.Item(i))
                   for i in range(1, min(int(collection.Count), 256) + 1))

    def plan(self, kind, document, target):
        """Freeze explicit COM references/coordinates, never an ActiveDocument proxy."""
        self.check_thread()
        if kind == "excel":
            if target == "selection":
                selected = document.Application.Selection
                if not self.same(selected.Parent.Parent, document) or int(selected.Areas.Count) != 1:
                    raise OfficeUnavailable("Select one range in the attached workbook.")
                sheet, address = selected.Parent, str(selected.Address)
            else:
                if "!" not in target:
                    raise OfficeUnavailable("Use SheetName!A1:B2 for an Excel target.")
                name, address = target.rsplit("!", 1)
                if name.startswith("'") and name.endswith("'"):
                    name = name[1:-1].replace("''", "'")
                sheet = document.Worksheets.Item(name)
            from app.mcp.office_contracts import excel_range_shape
            rows, columns = excel_range_shape(address)
            first = sheet.Range(address).Cells.Item(1, 1)
            return [("cell", sheet, int(first.Row) + r, int(first.Column) + c)
                    for r in range(rows) for c in range(columns)]
        if kind == "word":
            if target == "selection":
                window = document.ActiveWindow
                if not self.same(window.Document, document):
                    raise OfficeUnavailable("The Word selection belongs to another document.")
                region = window.Selection.Range
            elif target == "document":
                region = document.Content
            elif re.fullmatch(r"text:[0-9]+:[0-9]+", target):
                start, end = map(int, target.split(":")[1:])
                if not 0 <= start <= end <= int(document.Content.End):
                    raise OfficeUnavailable("The Word range is outside the document.")
                region = document.Range(start, end)
            else:
                raise OfficeUnavailable("Use selection, document or text:start:end for Word.")
            return [("word", document, int(region.Start), int(region.End))]
        if target == "selection":
            # Presentation.Windows belongs to the bound document, regardless of focus.
            window = document.Windows.Item(1)
            selection = window.Selection
            if int(selection.Type) in (2, 3):
                shapes = selection.ShapeRange
                return [("shape", shapes.Item(i)) for i in range(1, min(int(shapes.Count), 1000) + 1)]
            slides = selection.SlideRange
            if int(slides.Count) > 1000:
                raise OfficeUnavailable("The PowerPoint selection is too large.")
            return self._slide_shapes([slides.Item(i) for i in range(1, int(slides.Count) + 1)])
        if target == "slides":
            if int(document.Slides.Count) > 1000:
                raise OfficeUnavailable("Request a specific PowerPoint slide.")
            return self._slide_shapes([document.Slides.Item(i)
                                      for i in range(1, int(document.Slides.Count) + 1)])
        if re.fullmatch(r"slide:[1-9][0-9]*", target):
            slide = document.Slides.Item(int(target.split(":")[1]))
            return self._slide_shapes([slide])
        raise OfficeUnavailable("Use selection, slides or slide:index for PowerPoint.")

    def _slide_shapes(self, slides):
        result = []
        for slide in slides:
            if int(slide.Shapes.Count) + len(result) > 1000:
                raise OfficeUnavailable("Request a smaller PowerPoint target.")
            if int(slide.Shapes.Count) == 0:
                result.append(("slide", slide))
            result.extend(("shape", slide.Shapes.Item(i)) for i in range(1, int(slide.Shapes.Count) + 1))
        return result

    def piece(self, descriptor, offset, chars):
        """Return at most chars characters; offsets freeze a paged target."""
        self.check_thread()
        kind, obj, *coordinates = descriptor
        if kind == "word":
            start, end = coordinates
            region = obj.Range(start + offset, min(end, start + offset + chars))
            text = str(region.Text)
            if text and 0xD800 <= ord(text[-1]) <= 0xDBFF and int(region.End) < end:
                region = obj.Range(start + offset, int(region.End) + 1)
                text = str(region.Text)
            consumed = int(region.End) - int(region.Start)
            return {"label": f"text:{start + offset}:{start + offset + consumed}", "text": text}, (
                offset + consumed if start + offset + consumed < end else None)
        if kind == "cell":
            row, column = coordinates
            cell = obj.Cells.Item(row, column)
            value = cell.Value2
            if not isinstance(value, (str, int, float, bool, type(None))) or (
                    isinstance(value, float) and not math.isfinite(value)):
                raise OfficeUnavailable("The cell value cannot be represented safely.")
            formula = str(self.excel_property(cell, "Formula2")) if bool(cell.HasFormula) else ""
            label = f"{str(obj.Name)}!{str(cell.Address)}"[:220]
            size = len(value) if isinstance(value, str) else 0
            if offset == 0 and size + len(formula) <= chars:
                return {"label": label, "values": [[value]], "formulas": [[formula]]}, None
            text = (str(value) if value is not None else "") + ("\nFormula: " + formula if formula else "")
        elif kind == "slide":
            return {"label": f"slide_id:{int(obj.SlideID)}", "text": ""}, None
        else:
            # TextRange.Characters bounds the COM transfer, even for very large shapes.
            label = f"slide_id:{int(obj.Parent.SlideID)}/shape_id:{int(obj.Id)}"
            text_range = obj.TextFrame.TextRange if bool(obj.HasTextFrame) else None
            length = int(text_range.Length) if text_range is not None else 0
            consumed = 0
            text = ""
            if offset < length:
                region = text_range.Characters(offset + 1, min(chars, length - offset))
                text = str(region.Text)
                consumed = int(region.Length)
                if text and 0xD800 <= ord(text[-1]) <= 0xDBFF and offset + consumed < length:
                    region = text_range.Characters(offset + 1, consumed + 1)
                    text, consumed = str(region.Text), int(region.Length)
            geometry = {name: float(getattr(obj, name.title())) for name in ("left", "top", "width", "height")}
            # The v1 geometry contract cannot represent off-slide negative positions.
            if geometry["left"] < 0 or geometry["top"] < 0 or geometry["width"] <= 0 or geometry["height"] <= 0:
                geometry = None
            return {"label": label, "text": text, "geometry": geometry}, (
                offset + consumed if offset + consumed < length else None)
        part = text[offset:offset + chars]
        return {"label": label + f" [chars {offset}:{offset + len(part)}]", "text": part}, (
            offset + len(part) if offset + len(part) < len(text) else None)

    def close(self):
        self.check_thread()
        gc.collect()
        self.com.CoUninitialize()
        # Never Quit or Close a user-owned Office object.

    def excel_writable(self, document):
        from app.mcp.office_excel import OfficeConflict
        self.check_thread()
        if bool(document.ReadOnly) or bool(document.HasVBProject) or bool(getattr(document, "AutoSaveOn", False)):
            raise OfficeConflict("Use a writable, macro-free workbook with AutoSave disabled.")
        if int(document.Excel4MacroSheets.Count) or int(document.Excel4IntlMacroSheets.Count):
            raise OfficeConflict("Excel macro sheets are not supported.")

    def excel_property(self, obj, name, *values):
        """Use invariant Excel format/formula syntax on non-English Office hosts."""
        self.check_thread()
        member = obj._oleobj_.GetIDsOfNames(name)
        flags = self.com.DISPATCH_PROPERTYPUT if values else self.com.DISPATCH_PROPERTYGET
        return obj._oleobj_.Invoke(member, 1033, flags, not values, *values)

    def capture_excel(self, descriptor):
        from app.mcp.office_excel import OfficeConflict
        self.check_thread()
        _, sheet, row, column = descriptor
        cell = sheet.Cells.Item(row, column)
        spill = False
        try:
            spill = bool(cell.HasSpill)
        except (AttributeError, self.com.com_error):
            pass  # Older Excel has no dynamic arrays.
        if (bool(sheet.ProtectContents) or bool(cell.MergeCells) or bool(cell.HasArray) or spill
                or cell.ListObject is not None or int(cell.Hyperlinks.Count)):
            raise OfficeConflict("Protected, merged, array, spilled, table or hyperlink cells are not supported.")
        value = cell.Value2
        formula = str(self.excel_property(cell, "Formula2")) if bool(cell.HasFormula) else ""
        bold, italic, number_format = cell.Font.Bold, cell.Font.Italic, self.excel_property(cell, "NumberFormat")
        if (not isinstance(value, (str, int, float, bool, type(None))) or
                isinstance(value, float) and not math.isfinite(value) or
                bold is None or italic is None or not isinstance(number_format, str) or
                len(formula) > 4096 or isinstance(value, str) and len(value) > 4096):
            raise OfficeConflict("This cell cannot be captured for bounded restoration.")
        return {"value": value, "formula": formula, "number_format": number_format,
                "bold": bool(bold), "italic": bool(italic)}

    def write_excel(self, descriptor, state, fields):
        self.check_thread()
        _, sheet, row, column = descriptor
        cell = sheet.Cells.Item(row, column)
        if "formula" in fields and state["formula"]:
            self.excel_property(cell, "Formula2", state["formula"])
            cell.Calculate()
            # Excel can inherit a referenced cell's format while inserting a
            # formula. Preserve the approved target format explicitly.
            self.excel_property(cell, "NumberFormat", state["number_format"])
        elif "value" in fields or "formula" in fields:
            # Text format prevents equals, plus, minus and apostrophe strings
            # from becoming formulas or being silently reinterpreted by Excel.
            if isinstance(state["value"], str):
                self.excel_property(cell, "NumberFormat", "@")
            cell.Value2 = state["value"]
            self.excel_property(cell, "NumberFormat", state["number_format"])
        if "number_format" in fields:
            self.excel_property(cell, "NumberFormat", state["number_format"])
        if "bold" in fields:
            cell.Font.Bold = state["bold"]
        if "italic" in fields:
            cell.Font.Italic = state["italic"]

    def save_excel(self, document, save, overwrite):
        self.check_thread()
        path = Path(save["path"])
        if save["save_as"]:
            document.SaveAs(str(path), 51)  # xlOpenXMLWorkbook; macro-free preflight.
        else:
            document.Save()
        if not bool(document.Saved) or Path(str(document.FullName)).resolve(strict=True) != path or not path.is_file():
            raise OfficeUnavailable("Excel did not verify saving to the approved destination.")
