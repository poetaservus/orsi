"""Existing rectangular Word tables: native structure, bounded cells and recovery."""
from copy import deepcopy

from app.mcp.office_contracts import canonical_json
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_word_native import (ET, W, MAX_XML_BYTES, MAX_PARAGRAPH_UNITS,
    MAX_WORD_UNITS, default_styles, dependencies, paragraph_semantic, reject, tree, units)
from app.mcp.office_word_xml import packet, paragraph_xml


def descriptor(backend, document, index):
    table = document.Tables.Item(index)
    region = table.Range.Duplicate
    rows, columns = int(table.Rows.Count), int(table.Columns.Count)
    if rows * columns > 64 or not bool(table.Uniform):
        reject("Word table editing supports at most 64 cells in a uniform rectangle.")
    cells = [table.Cell(row, column).Range.Duplicate for row in range(1, rows + 1) for column in range(1, columns + 1)]
    return "word_table", document, int(region.Start), int(region.End), table, region, cells, index


def _capture(backend, item):
    _, document, start, end, table, retained, owned_cells, index = item
    current_table = document.Tables.Item(index)
    if (not backend.same(retained.Document, document) or
            int(retained.StoryType) != 1 or (int(retained.Start), int(retained.End)) != (start, end) or
            (int(table.Range.Start), int(table.Range.End)) != (start, end) or
            (int(current_table.Range.Start), int(current_table.Range.End)) != (start, end)):
        reject("Office conflict: the retained Word table identity or position changed.")
    rows, columns = int(table.Rows.Count), int(table.Columns.Count)
    if (not bool(table.Uniform) or bool(table.AllowAutoFit) or rows * columns > 64 or
            int(table.Range.Cells.Count) != rows * columns or len(owned_cells) != rows * columns):
        reject("Use a fixed-layout unmerged Word table with at most 64 cells.")
    backend.word_xml_safe(document)
    xml = str(table.Range.WordOpenXML)
    if len(xml.encode()) > MAX_XML_BYTES:
        reject("The Word table snapshot exceeds its XML bound.")
    body = ET.fromstring(xml).find(".//" + W + "body")
    # Word exports a trailing empty paragraph after a table even when that
    # paragraph is outside Table.Range. It grants no edit coverage.
    children = [child for child in body if child.tag != W + "sectPr" and not (
        child.tag == W + "p" and not child.findall(".//" + W + "t") and not child.findall(".//" + W + "r"))]
    if len(children) != 1 or children[0].tag != W + "tbl":
        reject("The Word table snapshot has unsupported surrounding structure.")
    native = children[0]
    native_rows = native.findall(W + "tr")
    if len(native_rows) != rows:
        reject("The Word table rows changed during capture.")
    cells, structures = [], []
    defaults = default_styles(xml)
    for row_index, row in enumerate(native_rows, 1):
        native_cells = row.findall(W + "tc")
        if len(native_cells) != columns:
            reject("Merged or irregular Word table cells are unsupported.")
        structures.append([tree(row.find(W + "trPr")), []])
        for column_index, cell_xml in enumerate(native_cells, 1):
            if any(c.tag not in {W + "tcPr", W + "p"} for c in cell_xml):
                reject("Nested or anchored Word table cells are unsupported.")
            props = cell_xml.find(W + "tcPr")
            if props is not None and any(c.tag in {W + "gridSpan", W + "vMerge", W + "hMerge"} for c in props):
                reject("Merged Word table cells are unsupported.")
            paragraphs = cell_xml.findall(W + "p")
            if len(paragraphs) != 1:
                reject("Word table edits require one ordinary paragraph per cell.")
            semantic = paragraph_semantic(paragraphs[0], defaults)
            cell = table.Cell(row_index, column_index)
            anchor = owned_cells[len(cells)]
            if (not backend.same(anchor.Document, document) or int(anchor.StoryType) != 1 or
                    (int(anchor.Start), int(anchor.End)) != (int(cell.Range.Start), int(cell.Range.End)) or
                    int(cell.RowIndex) != row_index or int(cell.ColumnIndex) != column_index):
                reject("Office conflict: a retained Word cell identity changed.")
            region = cell.Range
            raw = str(region.Text)
            if not raw.endswith("\r\x07"):
                reject("Word returned an unsupported table-cell end marker.")
            text = raw[:-2]
            if (any(ord(c) < 32 for c in text) or units(text) > MAX_WORD_UNITS or
                    "".join(r[1] for r in semantic[2]) != text or int(region.End) - int(region.Start) != units(text) + 1):
                reject("The Word cell contains unsupported text or structure.")
            cells.append({"start": int(region.Start), "end": int(region.End), "text": text, "paragraph": semantic})
            structures[-1][1].append(tree(props))
    if sum(units(c["text"]) for c in cells) > MAX_PARAGRAPH_UNITS:
        reject("The Word table text exceeds its complete-snapshot bound.")
    return {"kind": "table", "index": index, "start": start, "end": end, "rows": rows, "columns": columns,
            "structure": [tree(native)[1], tree(native.find(W + "tblPr")), tree(native.find(W + "tblGrid")), structures],
            "cells": cells, "dependencies": dependencies(xml)}


def capture_table(backend, item):
    backend.check_thread()
    try:
        return _capture(backend, item)
    except OfficeConflict:
        raise
    except Exception:
        reject("The native Word table is outside the supported rectangle subset.")


def table_replacement(before, matrix):
    if before.get("kind") != "table" or len(matrix) != before["rows"] or any(len(r) != before["columns"] for r in matrix):
        reject("edit_table requires a complete structured table snapshot and the exact existing matrix dimensions.")
    expected = deepcopy(before)
    delta = 0
    for cell, text in zip(expected["cells"], (v for row in matrix for v in row), strict=True):
        if any(ord(c) < 32 for c in text) or units(text) > MAX_WORD_UNITS:
            reject("Word cell text must be plain text without structural markers, up to 4096 UTF-16 units.")
        cell["start"] += delta
        cell["end"] += delta
        if text != cell["text"]:
            runs = cell["paragraph"][2]
            if len(runs) > 1:
                reject("Changed Word cells must have uniform character formatting.")
            props = runs[0][0] if runs else next((p for p in (cell["paragraph"][1] or [None, {}, "", []])[3] if p[0] == W + "rPr"), None)
            cell["paragraph"][2] = [[deepcopy(props), text]] if text else []
            size = units(text) - units(cell["text"])
            delta += size
            cell["end"] += size
            cell["text"] = text
    expected["end"] += delta
    if sum(units(c["text"]) for c in expected["cells"]) > MAX_PARAGRAPH_UNITS:
        reject("The resulting Word table exceeds its bounded text limit.")
    return expected


def write_table(backend, item, expected):
    backend.check_thread()
    original = capture_table(backend, item)
    current = deepcopy(original)
    document, table, index = item[1], item[4], item[7]
    for offset, (before_cell, after_cell) in enumerate(zip(original["cells"], expected["cells"], strict=True)):
        if before_cell["text"] == after_cell["text"] and before_cell["paragraph"] == after_cell["paragraph"]:
            continue
        backend.word_writable(document)
        retained = (*item[:2], current["start"], current["end"], *item[4:])
        if capture_table(backend, retained) != current:
            raise OfficeUnknown("A Word table cell changed during the approved patch.")
        region = item[6][offset].Duplicate
        region.End = int(region.End) - 1  # CR + BEL is one native Word cell-end unit.
        xml = str(table.Range.WordOpenXML)
        region.InsertXML(packet(xml, "<w:body>" + paragraph_xml(after_cell["paragraph"]) + "</w:body>"))
        # Rebase only this patch's proven preceding text-length transitions.
        delta = units(after_cell["text"]) - units(before_cell["text"])
        current["end"] += delta
        current["cells"][offset] = deepcopy(after_cell)
        for later in current["cells"][offset + 1:]:
            later["start"] += delta
            later["end"] += delta
        refreshed = (*item[:2], current["start"], current["end"], *item[4:])
        if capture_table(backend, refreshed) != current:
            raise OfficeUnknown("Word table readback did not preserve the approved cell and table structure.")
    return (*item[:2], expected["start"], expected["end"], *item[4:])


def table_text(state):
    columns = state["columns"]
    return canonical_json({"rows": state["rows"], "columns": columns, "native_units": "UTF-16",
        "cells": [[c["text"] for c in state["cells"][start:start + columns]] for start in range(0, len(state["cells"]), columns)],
        "cell_ranges": [[c["start"], c["end"] - 1] for c in state["cells"]]})
