"""Fixed Excel object-model operations. No VBA, external data, or active-window writes."""
from __future__ import annotations

from uuid import uuid4
import re
from app.mcp.office_contracts import canonical_json, excel_range_shape


CHART_TYPES = {"column": 51, "bar": 57, "line": 4, "line_markers": 65,
               "area": 1, "pie": 5, "doughnut": -4120, "scatter": -4169, "stacked_column": 52}
SHAPE_TYPES = {"rectangle": 1, "rounded_rectangle": 5, "oval": 9, "chevron": 52,
               "up_arrow": 35, "down_arrow": 36}
AGGREGATES = {"sum": -4157, "count": -4112, "average": -4106, "min": -4139, "max": -4136}


def rgb(color):
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return red | green << 8 | blue << 16


def color(value):
    value = int(value)
    return "#" + "".join(f"{value >> shift & 255:02X}" for shift in (0, 8, 16))


def geometry(obj):
    return {key: round(float(getattr(obj, key.title())), 3) for key in ("left", "top", "width", "height")}


def link_key(formula):
    sheet, address = formula.strip().removeprefix("=").rsplit("!", 1)
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet.casefold(), address.replace("$", "").upper()


def items(collection, limit):
    from app.mcp.office_excel import OfficeConflict
    count = int(collection.Count)
    if not 0 <= count <= limit:
        raise OfficeConflict("The native dashboard collection exceeds its inspection limit.")
    return [collection.Item(i) for i in range(1, count + 1)]


class ExcelDrawing:
    def excel_drawing_writable(self, document, sheet):
        from app.mcp.office_excel import OfficeConflict
        self.excel_writable(document)
        if (bool(sheet.ProtectContents) or bool(sheet.ProtectDrawingObjects)
                or not self.same(sheet.Parent, document)):
            raise OfficeConflict("Use an unprotected worksheet in the attached workbook for dashboard objects.")

    def excel_object_names(self, document, sheet):
        self.check_thread()
        shapes = items(sheet.Shapes, 256)
        pivots = [(str(s.Name), str(p.Name)) for s in items(document.Worksheets, 256)
                  for p in items(s.PivotTables(), 128)]
        caches = items(document.SlicerCaches, 128)
        slicer_names = [str(s.Name) for c in caches for s in items(c.Slicers, 128)]
        if len(slicer_names) > 1024:
            from app.mcp.office_excel import OfficeConflict
            raise OfficeConflict("The workbook exceeds the native slicer inspection limit.")
        cache_names = [str(c.Name) for c in caches]
        return {"names": [str(s.Name) for s in shapes] + [n for _, n in pivots] + cache_names + slicer_names,
                "shapes": [[str(s.Name), int(s.ID)] for s in shapes], "pivots": pivots, "slicer_caches": cache_names}

    def excel_pivot_destination(self, sheet, address):
        from app.mcp.office_excel import OfficeConflict
        bounds = sheet.Range(address)
        for pivot in items(sheet.PivotTables(), 128):
            if sheet.Application.Intersect(bounds, pivot.TableRange2) is not None:
                raise OfficeConflict("The reserved cells intersect an existing PivotTable.")

    def excel_object_plan(self, document, sheet):
        """Metadata only; expose exact PivotTable rectangles for subsequent reads."""
        self.check_thread()
        result = []
        shapes = items(sheet.Shapes, 256)
        chart_names, slicer_names = set(), set()
        for pivot in items(sheet.PivotTables(), 128):
            result.append(("excel_drawing", sheet, "pivot", pivot, None))
        for chart in items(sheet.ChartObjects(), 256):
            chart_names.add(str(chart.Name))
            result.append(("excel_drawing", sheet, "chart", chart, None))
        for cache in items(document.SlicerCaches, 128):
            for slicer in items(cache.Slicers, 128):
                if self.same(slicer.Shape.Parent, sheet):
                    slicer_names.add(str(slicer.Shape.Name))
                    result.append(("excel_drawing", sheet, "slicer", slicer, cache))
        result.extend(("excel_drawing", sheet, "shape", shape, None) for shape in shapes
                      if str(shape.Name) not in chart_names | slicer_names)
        if len(result) > 256:
            from app.mcp.office_excel import OfficeConflict
            raise OfficeConflict("The worksheet exceeds the dashboard object inventory limit.")
        return result

    def excel_object_metadata(self, descriptor):
        _, sheet, kind, obj, auxiliary = descriptor
        data = {"kind": kind, "sheet": str(sheet.Name), "name": str(obj.Name)}
        if kind == "pivot":
            data.update(range=str(obj.TableRange2.Address), fields=[str(f.SourceName) for f in items(obj.PivotFields(), 128)])
        else:
            data["geometry"] = geometry(obj)
            if kind == "chart":
                data.update(chart_type=int(obj.Chart.ChartType), title=str(obj.Chart.ChartTitle.Text) if bool(obj.Chart.HasTitle) else "")
            elif kind == "shape":
                try:
                    data["text"] = str(obj.TextFrame2.TextRange.Text)[:4096]
                except (self.com.com_error, AttributeError):
                    data["text"] = ""
            else:
                data.update(field=str(auxiliary.SourceName), pivots=[str(p.Name) for p in items(auxiliary.PivotTables, 128)])
        return data

    def capture_excel_fill(self, interior):
        self.check_thread()
        def theme(name):
            try:
                value = int(getattr(interior, name))
                return value if 1 <= value <= 12 else None
            except (self.com.com_error, AttributeError, TypeError):
                return None
        return {"pattern": int(interior.Pattern), "color": int(interior.Color),
                "theme": theme("ThemeColor"), "tint": float(interior.TintAndShade),
                "pattern_color": int(interior.PatternColor), "pattern_theme": theme("PatternThemeColor"),
                "pattern_tint": float(interior.PatternTintAndShade)}

    def restore_excel_fill(self, interior, state):
        interior.Pattern = state["pattern"]
        if state["theme"] is None:
            interior.Color = state["color"]
        else:
            interior.ThemeColor = state["theme"]
        interior.TintAndShade = state["tint"]
        if state["pattern_theme"] is None:
            interior.PatternColor = state["pattern_color"]
        else:
            interior.PatternThemeColor = state["pattern_theme"]
        interior.PatternTintAndShade = state["pattern_tint"]
        interior.Pattern = state["pattern"]

    def excel_slicer_pivot(self, document, sheet, address, field):
        from app.mcp.office_excel import OfficeConflict
        self.check_thread()
        region = sheet.Range(address)
        matches = [p for p in items(sheet.PivotTables(), 128)
                   if str(p.TableRange2.Address) == str(region.Address)]
        if len(matches) != 1:
            raise OfficeConflict("Read the exact full output rectangle of one existing PivotTable for a slicer source.")
        pivot = matches[0]
        cache = pivot.PivotCache()
        if bool(cache.OLAP) or int(cache.SourceType) != 1:
            raise OfficeConflict("Only local worksheet PivotTables support slicer creation in this connector.")
        if not 0 <= int(cache.RecordCount) <= 1000:
            raise OfficeConflict("The PivotTable cache exceeds the bounded slicer record limit.")
        source = cache.SourceData
        if not isinstance(source, str):
            raise OfficeConflict("The PivotTable must have one local worksheet source.")
        if "!" in source:
            name, address = source.rsplit("!", 1)
            if name.startswith("'") and name.endswith("'"):
                name = name[1:-1].replace("''", "'")
            prefix = "[" + str(document.Name) + "]"
            if name.casefold().startswith(prefix.casefold()):
                name = name[len(prefix):]
            if any(c in name for c in "[]:*?/\\"):
                raise OfficeConflict("External PivotTable sources are not supported.")
            self.excel_sheet(document, name)
            match = re.fullmatch(r"R([1-9][0-9]*)C([1-9][0-9]*):R([1-9][0-9]*)C([1-9][0-9]*)", address)
            if match:
                top, left, bottom, right = map(int, match.groups())
                if not (top <= bottom <= 1048576 and left <= right <= 16384 and (bottom - top + 1) * (right - left + 1) <= 1000):
                    raise OfficeConflict("The local PivotTable source exceeds its range limit.")
            else:
                excel_range_shape(address)
        else:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", source):
                raise OfficeConflict("External or named PivotTable sources are not supported.")
            tables = [t for s in items(document.Worksheets, 256) for t in items(s.ListObjects, 128) if str(t.Name).casefold() == source.casefold()]
            if len(tables) != 1 or int(tables[0].Range.Cells.CountLarge) > 1000:
                raise OfficeConflict("The PivotTable source must be a bounded local Table or cell range.")
        fields = items(pivot.PivotFields(), 128)
        if field not in {str(f.SourceName) for f in fields}:
            raise OfficeConflict("The slicer field is absent from the selected PivotTable.")
        selected = next(f for f in fields if str(f.SourceName) == field)
        items(selected.PivotItems(), 1000)
        return pivot

    def capture_excel_pivot(self, pivot):
        from app.mcp.office_excel import OfficeConflict
        region = pivot.TableRange2
        rows, columns = int(region.Rows.Count), int(region.Columns.Count)
        if rows * columns > 1000:
            raise OfficeConflict("The PivotTable output exceeds the bounded dashboard limit.")
        fields = []
        for field in [*items(pivot.PivotFields(), 128), *items(pivot.DataFields, 16)]:
            data = {"source": str(field.SourceName), "name": str(field.Name), "orientation": int(field.Orientation)}
            if data["orientation"] in (1, 2, 3):
                data["visible"] = [str(i.Name) for i in items(field.PivotItems(), 1000) if bool(i.Visible)]
            if data["orientation"] == 4:
                data["function"] = int(field.Function)
                data["number_format"] = str(self.excel_property(field, "NumberFormat"))
            fields.append(data)
        return {"name": str(pivot.Name), "tag": str(pivot.Tag), "address": str(region.Address),
                "rows": rows, "columns": columns, "fields": fields,
                "source": str(pivot.PivotCache().SourceData), "cache_index": int(pivot.CacheIndex),
                "style": str(pivot.TableStyle2), "row_grand": bool(pivot.RowGrand),
                "column_grand": bool(pivot.ColumnGrand),
                "values": [[region.Cells.Item(r, c).Value2 for c in range(1, columns + 1)] for r in range(1, rows + 1)]}

    def create_excel_object(self, document, spec, sheet, source_sheet, pivot):
        self.check_thread()
        if spec.kind == "chart":
            g = spec.geometry
            obj = sheet.ChartObjects().Add(g.left, g.top, g.width, g.height)
            obj.Name = spec.name
            chart = obj.Chart
            chart.ChartType = CHART_TYPES[spec.chart_type]
            chart.SetSourceData(source_sheet.Range(spec.source.range), 2)  # xlColumns
            chart.HasTitle = bool(spec.title)
            if spec.title:
                chart.ChartTitle.Text = spec.title
            chart.HasLegend = spec.legend
            for index, series in enumerate(items(chart.SeriesCollection(), 8)):
                if spec.colors:
                    tint = rgb(spec.colors[index % len(spec.colors)])
                    series.Format.Fill.Solid()
                    series.Format.Fill.ForeColor.RGB = tint
                    series.Format.Line.ForeColor.RGB = tint
            return obj, None
        if spec.kind == "shape":
            g = spec.geometry
            obj = sheet.Shapes.AddShape(SHAPE_TYPES[spec.shape_type], g.left, g.top, g.width, g.height)
            obj.Name = spec.name
            for component, tint in ((obj.Fill, spec.fill_color), (obj.Line, spec.line_color)):
                component.Visible = tint != "none"
                if tint != "none":
                    if hasattr(component, "Solid"):
                        component.Solid()
                    component.ForeColor.RGB = rgb(tint)
            if spec.link is not None:
                address = str(source_sheet.Range(spec.link.range).Address)
                self.excel_property(obj.DrawingObject, "Formula", "='" + str(source_sheet.Name).replace("'", "''") + "'!" + address)
            else:
                obj.TextFrame2.TextRange.Text = spec.text or ""
            text = obj.TextFrame2.TextRange
            text.Font.Size = spec.font_size
            text.Font.Bold = -1 if spec.bold else 0
            text.Font.Fill.ForeColor.RGB = rgb(spec.font_color)
            text.ParagraphFormat.Alignment = 2  # centered
            obj.TextFrame2.VerticalAnchor = 3  # middle
            return obj, None
        if spec.kind == "pivot":
            # SourceData is host-generated from the retained bound range. No
            # caller-provided external workbook, connection, query or VBA runs.
            source = source_sheet.Range(spec.source.range)
            address = source._oleobj_.Invoke(source._oleobj_.GetIDsOfNames("Address"), 1033,
                self.com.DISPATCH_PROPERTYGET, True, True, True, 1, True)
            cache = document.PivotCaches().Create(1, address, 5)
            obj = cache.CreatePivotTable(sheet.Range(spec.destination).Cells.Item(1, 1), spec.name)
            obj.Tag = "orsi_" + uuid4().hex
            obj.ManualUpdate = True
            obj.TableStyle2 = ""
            for position, name in enumerate(spec.rows, 1):
                field = obj.PivotFields(name)
                field.Orientation = 1
                field.Position = position
                field.Subtotals = (False,) * 12
            obj.RowAxisLayout(1)  # xlTabularRow
            data = obj.AddDataField(obj.PivotFields(spec.value_field), spec.aggregate.title() + " of " + spec.value_field, AGGREGATES[spec.aggregate])
            self.excel_property(data, "NumberFormat", spec.number_format)
            obj.ManualUpdate = False
            obj.RefreshTable()
            # The conservative reserve includes intermediate default layouts.
            bounds = sheet.Range(spec.destination)
            actual = obj.TableRange2
            if (int(actual.Row) < int(bounds.Row) or int(actual.Column) < int(bounds.Column)
                    or int(actual.Row) + int(actual.Rows.Count) > int(bounds.Row) + int(bounds.Rows.Count)
                    or int(actual.Column) + int(actual.Columns.Count) > int(bounds.Column) + int(bounds.Columns.Count)):
                from app.mcp.office_excel import OfficeUnknown
                raise OfficeUnknown("The new PivotTable did not remain inside its reserved cells.")
            return obj, None
        cache = document.SlicerCaches.Add(pivot, spec.field, spec.name)
        g = spec.geometry
        obj = cache.Slicers.Add(sheet)
        # Some late-bound Office builds silently ignore optional Add arguments.
        # Set and verify the writable native properties explicitly.
        obj.Name = spec.name
        obj.Caption = spec.caption or spec.field
        obj.NumberOfColumns = spec.columns
        obj.Style = "SlicerStyleLight1" if spec.style == "light" else "SlicerStyleDark1"
        for key in ("left", "top", "width", "height"):
            setattr(obj, key.title(), getattr(g, key))
        return obj, cache

    def capture_excel_object(self, document, spec, obj, auxiliary):
        self.check_thread()
        result = {"name": str(obj.Name)}
        if spec.kind == "pivot":
            return self.capture_excel_pivot(obj)
        result["geometry"] = geometry(obj)
        if spec.kind == "chart":
            chart = obj.Chart
            result.update(shape_id=int(obj.ShapeRange.Item(1).ID), chart_type=int(chart.ChartType), legend=bool(chart.HasLegend),
                          title=str(chart.ChartTitle.Text) if bool(chart.HasTitle) else "",
                          style=int(chart.ChartStyle),
                          series=[{"formula": str(self.excel_property(s, "Formula")),
                                   "fill": color(s.Format.Fill.ForeColor.RGB),
                                   "line": color(s.Format.Line.ForeColor.RGB)} for s in items(chart.SeriesCollection(), 8)])
        elif spec.kind == "shape":
            text = obj.TextFrame2.TextRange
            formula = str(self.excel_property(obj.DrawingObject, "Formula"))
            result.update(shape_type=int(obj.AutoShapeType), formula=formula,
                          shape_id=int(obj.ID),
                          text="" if formula else str(text.Text),
                          fill=color(obj.Fill.ForeColor.RGB) if bool(obj.Fill.Visible) else "none",
                          line=color(obj.Line.ForeColor.RGB) if bool(obj.Line.Visible) else "none",
                          line_weight=float(obj.Line.Weight), font_color=color(text.Font.Fill.ForeColor.RGB),
                          font_size=float(text.Font.Size), bold=bool(text.Font.Bold),
                          alignment=int(text.ParagraphFormat.Alignment), anchor=int(obj.TextFrame2.VerticalAnchor),
                          action=str(obj.OnAction), rotation=float(obj.Rotation),
                          adjustments=[float(obj.Adjustments.Item(i)) for i in range(1, int(obj.Adjustments.Count) + 1)])
        else:
            result.update(caption=str(obj.Caption), columns=int(obj.NumberOfColumns), style=str(obj.Style.Name),
                          field=str(auxiliary.SourceName), shape_id=int(obj.Shape.ID), cache_name=str(auxiliary.Name),
                          pivots=sorted(str(p.Name) for p in items(auxiliary.PivotTables, 128)),
                          selection=[str(i.Name) for i in items(auxiliary.SlicerItems, 1000) if bool(i.Selected)])
        if len(canonical_json(result).encode()) > 128_000:
            from app.mcp.office_excel import OfficeUnknown
            raise OfficeUnknown("Native dashboard verification exceeded its bound.")
        return result

    def verify_excel_object(self, spec, state):
        from app.mcp.office_excel import OfficeUnknown
        if state["name"] != spec.name:
            raise OfficeUnknown("The native dashboard object name did not verify.")
        if spec.kind != "pivot" and any(abs(state["geometry"][k] - getattr(spec.geometry, k)) > 0.1 for k in state["geometry"]):
            raise OfficeUnknown("The native dashboard object geometry did not verify.")
        if spec.kind == "chart":
            if (state["chart_type"] != CHART_TYPES[spec.chart_type] or state["title"] != spec.title
                    or state["legend"] != spec.legend or not state["series"]):
                raise OfficeUnknown("The native chart did not verify.")
            for index, series in enumerate(state["series"]):
                if spec.colors:
                    expected = spec.colors[index % len(spec.colors)].upper()
                    if series["fill"] != expected or series["line"] != expected:
                        raise OfficeUnknown("The native chart palette did not verify.")
        elif spec.kind == "shape":
            expected = {"shape_type": SHAPE_TYPES[spec.shape_type], "fill": spec.fill_color.upper() if spec.fill_color != "none" else "none",
                        "line": spec.line_color.upper() if spec.line_color != "none" else "none",
                        "font_color": spec.font_color.upper(), "font_size": spec.font_size, "bold": spec.bold}
            if any(state[k] != v for k, v in expected.items()):
                raise OfficeUnknown("The native KPI shape did not verify.")
            if spec.link is None and state["text"] != (spec.text or ""):
                raise OfficeUnknown("The native shape text did not verify.")
            if spec.link is not None:
                expected_formula = "='" + spec.link.sheet.replace("'", "''") + "'!" + spec.link.range
                if link_key(state["formula"]) != link_key(expected_formula):
                    raise OfficeUnknown("The native KPI shape link did not verify.")
        elif spec.kind == "pivot":
            if (set(spec.rows) != {f["source"] for f in state["fields"] if f["orientation"] == 1}
                    or not any(f["source"] == spec.value_field and f.get("function") == AGGREGATES[spec.aggregate] for f in state["fields"])):
                raise OfficeUnknown("The native PivotTable fields did not verify.")
        elif (state["field"] != spec.field or state["columns"] != spec.columns
                or state["caption"] != (spec.caption or spec.field)):
            raise OfficeUnknown("The native slicer did not verify.")

    def excel_object_matches(self, document, spec, obj, auxiliary):
        try:
            sheet = self.excel_sheet(document, spec.sheet)
            if spec.kind == "pivot":
                current = sheet.PivotTables(spec.name)
                return bool(str(obj.Tag)) and str(current.Tag) == str(obj.Tag)
            elif spec.kind == "chart":
                current = sheet.ChartObjects(spec.name)
                return int(current.ShapeRange.Item(1).ID) == int(obj.ShapeRange.Item(1).ID) and self.same(current.Parent, sheet)
            elif spec.kind == "shape":
                current = sheet.Shapes.Item(spec.name)
                return int(current.ID) == int(obj.ID) and self.same(current.Parent, sheet)
            else:
                cache = document.SlicerCaches.Item(str(auxiliary.Name))
                current = cache.Slicers.Item(spec.name)
                # Excel returns different IUnknown wrappers for the same
                # Slicer/SlicerCache. The worksheet-bound native Shape.ID is
                # retained in the recovery state and changes on replacement.
                return (int(current.Shape.ID) == int(obj.Shape.ID)
                        and self.same(current.Shape.Parent, sheet))
        except (self.com.com_error, AttributeError):
            return False

    def excel_pivot_has_slicers(self, document, pivot):
        # PivotTable names are unique in this bound workbook; collection
        # wrappers are not stable IUnknown identities on every Excel build.
        return any(any(str(p.Name).casefold() == str(pivot.Name).casefold() for p in items(cache.PivotTables, 128))
                   for cache in items(document.SlicerCaches, 128))

    def delete_excel_object(self, document, spec, obj, auxiliary):
        if spec.kind == "pivot":
            obj.TableRange2.ClearContents()
        elif spec.kind == "slicer":
            auxiliary.Delete()
        else:
            obj.Delete()
        if self.excel_object_matches(document, spec, obj, auxiliary):
            from app.mcp.office_excel import OfficeUnknown
            raise OfficeUnknown("The owned dashboard object removal did not verify.")
