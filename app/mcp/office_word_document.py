"""Bounded native report composition; all supplied content becomes Word body text."""
from hashlib import sha256
import posixpath
from xml.etree.ElementTree import SubElement, tostring

from defusedxml import ElementTree as ET

from app.mcp.office_contracts import canonical_json
from app.mcp.office_word_native import W, PKG, WORD_STYLES, reject

MAX_DOCUMENT_XML = 1024 * 1024
ALIGNMENTS = {"left": 0, "center": 1, "right": 2, "justify": 3}
LAYOUT = ("PageWidth", "PageHeight", "TopMargin", "RightMargin", "BottomMargin", "LeftMargin",
          "HeaderDistance", "FooterDistance")
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def points(mm):
    return mm * 72 / 25.4


def rgb(value):
    value = value.lstrip("#")
    return sum(int(value[i:i + 2], 16) << (8 * (i // 2)) for i in (0, 2, 4))


def normalized(node):
    """Ignore Word's revision IDs/gallery state, retaining content and formatting."""
    attributes = {key: value for key, value in node.attrib.items()
                  if not key.rsplit("}", 1)[-1].startswith("rsid")
                  and key.rsplit("}", 1)[-1] not in {"paraId", "textId", "dirty"}}
    text = node.text or ""
    if node.tag not in {W + "t", W + "instrText"} and not text.strip():
        text = ""
    return [node.tag, attributes, text, [normalized(child) for child in node
            if child.tag not in {W + "semiHidden", W + "proofErr", W + "lastRenderedPageBreak", W + "rsids"}]]


def signature(xml):
    root = ET.fromstring(xml)
    for part in root.findall(PKG + "part"):
        name = part.attrib.get(PKG + "name", "")
        if name.startswith("/docProps/"):
            continue
        def field_result(container):
            for text in container.findall(".//" + W + "t"):
                text.text = "{field-result}"
            for props in container.findall(".//" + W + "rPr"):
                for child in list(props):
                    if child.tag == W + "noProof":
                        props.remove(child)  # Word refreshes proofing flags on field results.
        for field in part.findall(".//" + W + "fldSimple"):
            code = field.attrib.get(W + "instr", "").strip().upper().split()
            if code and code[0] in {"PAGE", "NUMPAGES"}:
                field_result(field)
        # PAGE/NUMPAGES values vary with repagination, while their field codes,
        # formatting and relationships remain guarded.
        for paragraph in part.findall(".//" + W + "p"):
            field, code = False, ""
            for run in paragraph.findall(W + "r"):
                marker = run.find(W + "fldChar")
                if marker is not None:
                    kind = marker.attrib.get(W + "fldCharType")
                    if kind == "begin":
                        code, field = "", False
                    elif kind == "separate":
                        tokens = code.strip().upper().split()
                        field = bool(tokens) and tokens[0] in {"PAGE", "NUMPAGES"}
                    elif kind == "end":
                        field = False
                for instruction in run.findall(W + "instrText"):
                    code += instruction.text or ""
                if field:
                    field_result(run)
    return sha256(canonical_json(package_state(root)).encode()).hexdigest()


def package_state(root):
    """Compare the package graph, independent of Word's reassigned relationship IDs.

    Word prunes unused, empty first/even running parts on first pagination.
    Real text, fields, drawings and direct formatting in those parts remain
    included, even when currently disabled. Only the default empty stub is inert.
    """
    parts = {part.attrib[PKG + "name"]: part for part in root.findall(PKG + "part")
             if not part.attrib.get(PKG + "name", "").startswith("/docProps/")}
    aliases, ignored = {}, set()
    for name, part in parts.items():
        if name.startswith(("/word/header", "/word/footer")) and name.endswith(".xml"):
            data = part.find(PKG + "xmlData")
            role = "header" if name.startswith("/word/header") else "footer"
            aliases[name] = role + ":" + sha256(canonical_json(normalized(data)).encode()).hexdigest()
    relations = {}
    for name, part in parts.items():
        if not name.endswith(".rels"):
            continue
        source = "/" if name == "/_rels/.rels" else name.replace("/_rels/", "/")[:-5]
        data = part.find(PKG + "xmlData")
        collection = list(data)[0] if data is not None and len(data) else None
        if collection is None:
            continue
        mapping = {}
        for relation in collection:
            target = relation.attrib.get("Target", "")
            absolute = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
            mapping[relation.attrib.get("Id")] = (relation, absolute)
        relations[source] = mapping
    document_relations = relations.get("/word/document.xml", {})
    even_setting = root.find(".//" + W + "evenAndOddHeaders")
    even_enabled = even_setting is not None and even_setting.attrib.get(W + "val", "1") not in {"0", "false", "off"}
    for section in root.findall(".//" + W + "sectPr"):
        for reference in list(section):
            if (reference.tag not in {W + "headerReference", W + "footerReference"}
                    or reference.attrib.get(W + "type") not in {"first", "even"}):
                continue
            first_setting = section.find(W + "titlePg")
            first_enabled = first_setting is not None and first_setting.attrib.get(W + "val", "1") not in {"0", "false", "off"}
            if (reference.attrib.get(W + "type") == "first" and first_enabled
                    or reference.attrib.get(W + "type") == "even" and even_enabled):
                continue
            relation = document_relations.get(reference.attrib.get(R + "id"))
            if relation is None:
                continue
            target = relation[1]
            part = parts.get(target)
            if part is None:
                continue
            data = part.find(PKG + "xmlData")
            container = list(data)[0] if data is not None and len(data) else None
            # Default empty stubs have only paragraph/style/revision metadata.
            allowed = {W + "p", W + "pPr", W + "pStyle"}
            inert = container is not None and all(node.tag in allowed for p in container for node in p.iter())
            if inert:
                ignored.add(target)
                section.remove(reference)
    for source, mapping in relations.items():
        source_part = parts.get(source)
        for old_id, (relation, target) in mapping.items():
            if target in ignored:
                continue
            logical = aliases.get(target, target) if relation.attrib.get("TargetMode") != "External" else relation.attrib["Target"]
            relation.attrib["Target"] = logical
            identity = sha256(canonical_json([relation.attrib.get("Type"), logical,
                                              relation.attrib.get("TargetMode")]).encode()).hexdigest()
            relation.attrib["Id"] = identity
            if source_part is not None:
                for node in source_part.iter():
                    if node.attrib.get(R + "id") == old_id:
                        node.attrib[R + "id"] = identity
    result = {}
    for name, part in parts.items():
        if name in ignored:
            continue
        if name.endswith(".rels"):
            data = part.find(PKG + "xmlData")
            collection = list(data)[0] if data is not None and len(data) else None
            if collection is not None:
                for relation in list(collection):
                    if any(relation is original and target in ignored
                           for mapping in relations.values() for original, target in mapping.values()):
                        collection.remove(relation)
                collection[:] = sorted(collection, key=lambda value: canonical_json(value.attrib))
        logical = aliases.get(name, name)
        part.attrib[PKG + "name"] = logical
        result[logical] = normalized(part)
    return sorted(result.items())


def same_document(left, right):
    if left.get("kind") == right.get("kind") == "document":
        return left["fingerprint"] == right["fingerprint"]
    return left == right


def capture_document(backend, document):
    backend.check_thread()
    backend.word_writable(document)
    backend.word_xml_safe(document)
    if int(document.Content.End) > 32768 or int(document.Sections.Count) != 1:
        reject("Report authoring supports one bounded section with at most 32768 native text positions.")
    if int(document.Tables.Count) > 32 or sum(int(document.Tables.Item(i).Range.Cells.Count)
            for i in range(1, int(document.Tables.Count) + 1)) > 512:
        reject("Report authoring supports at most 32 tables and 512 cells.")
    running = []
    for name, collection in (("Headers", document.Sections.Item(1).Headers),
                             ("Footers", document.Sections.Item(1).Footers)):
        for index in range(1, 4):
            part = collection.Item(index)
            if bool(part.Exists):
                if int(part.Range.Hyperlinks.Count) or any(int(part.Range.Fields.Item(i).Type) not in {26, 33}
                        for i in range(1, int(part.Range.Fields.Count) + 1)):
                    reject("Report running matter supports ordinary text and PAGE/NUMPAGES fields only.")
            running.append({"collection": name, "index": index, "exists": bool(part.Exists),
                            "xml": str(part.Range.WordOpenXML) if bool(part.Exists) else None})
    xml = str(document.Content.WordOpenXML)
    if len(xml.encode()) > MAX_DOCUMENT_XML:
        reject("The complete report snapshot exceeds its one-MiB bound.")
    root = ET.fromstring(xml)
    if any(node.attrib.get("TargetMode") == "External" for node in root.iter()):
        reject("Report authoring cannot replace documents with external relationships.")
    setup = document.PageSetup
    section = document.Sections.Item(1)
    view = {"scope": "Complete body, page setup, styles and running matter; replacement is explicit.",
            "text": str(document.Content.Text), "tables": int(document.Tables.Count),
            "layout_points": {name: round(float(getattr(setup, name)), 3) for name in LAYOUT},
            "header": str(section.Headers.Item(1).Range.Text) if bool(section.Headers.Item(1).Exists) else "",
            "footer": str(section.Footers.Item(1).Range.Text) if bool(section.Footers.Item(1).Exists) else "",
            "styles": backend.word_styles(document)}
    return {"kind": "document", "start": 0, "end": int(document.Content.End),
            "fingerprint": signature(xml), "xml": xml, "view": view, "running": running}


def effective_format(plan, block=None):
    values = dict(font="Calibri", size=11, color="#1F2937", bold=False, italic=False,
                  alignment="left", space_before=0, space_after=6, line_multiple=1.1,
                  keep_with_next=False)
    values.update({key: value for key, value in plan.format.model_dump().items() if value is not None})
    if block is not None:
        style = getattr(block, "style", "Normal")
        values.update({"Title": dict(size=24, bold=True, space_after=12, keep_with_next=True),
                       "Subtitle": dict(size=12, color="#64748B", space_after=12, keep_with_next=True),
                       "Heading 1": dict(size=16, bold=True, space_before=12, space_after=6, keep_with_next=True),
                       "Heading 2": dict(size=12, bold=True, space_before=8, space_after=4, keep_with_next=True)}.get(style, {}))
        if block.format is not None:
            values.update({key: value for key, value in block.format.model_dump().items() if value is not None})
    return values


def add(parent, name, **attrs):
    return SubElement(parent, W + name, {W + key: str(value) for key, value in attrs.items()})


def paragraph(parent, text, style_id, fmt, *, page_break=False):
    p = add(parent, "p")
    props = add(p, "pPr")
    add(props, "pStyle", val=style_id)
    add(props, "jc", val=fmt["alignment"])
    add(props, "spacing", before=round(fmt["space_before"] * 20), after=round(fmt["space_after"] * 20),
        line=round(fmt["line_multiple"] * 240), lineRule="auto")
    add(props, "widowControl")
    if fmt["keep_with_next"]:
        add(props, "keepNext")
    if page_break:
        add(props, "pageBreakBefore")
    run = add(p, "r")
    fonts = add(run, "rPr")
    add(fonts, "rFonts", ascii=fmt["font"], hAnsi=fmt["font"], eastAsia=fmt["font"], cs=fmt["font"])
    add(fonts, "sz", val=round(fmt["size"] * 2))
    add(fonts, "szCs", val=round(fmt["size"] * 2))
    add(fonts, "color", val=fmt["color"][1:])
    add(fonts, "b", val=int(fmt["bold"]))
    add(fonts, "i", val=int(fmt["italic"]))
    if text:
        node = add(run, "t")
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text
    return p


def compile_packet(document, plan, before):
    """Build XML internally from typed content, preserving native style definitions."""
    from app.mcp.office_contracts import WordParagraph, WordTable
    root = ET.fromstring(before["xml"])
    native = root.find(".//" + W + "body")
    styles = root.findall(".//" + W + "style")
    ids = {}
    for label, number in WORD_STYLES.items():
        local = str(document.Styles.Item(number).NameLocal).casefold()
        matches = [style for style in styles if style.attrib.get(W + "type") == "paragraph"
                   and style.find(W + "name") is not None and
                   style.find(W + "name").attrib.get(W + "val", "").casefold() in {label.casefold(), local}]
        if len(matches) != 1:
            reject("The report's built-in paragraph styles are unavailable. Read another ordinary Word document.")
        ids[label] = matches[0].attrib[W + "styleId"]
    native.clear()
    for index, block in enumerate(plan.blocks):
        if isinstance(block, WordParagraph):
            paragraph(native, block.text, ids[block.style], effective_format(plan, block),
                      page_break=block.page_break_before)
        elif isinstance(block, WordTable):
            table = add(native, "tbl")
            props = add(table, "tblPr")
            widths = [round(points(value) * 20) for value in block.widths_mm]
            add(props, "tblW", w=sum(widths), type="dxa")
            add(props, "tblLayout", type="fixed")
            borders = add(props, "tblBorders")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                add(borders, side, val="single", sz=4, color=block.border_color[1:])
            grid = add(table, "tblGrid")
            for width in widths:
                add(grid, "gridCol", w=width)
            for row_index, cells in enumerate(block.cells):
                row = add(table, "tr")
                row_props = add(row, "trPr")
                add(row_props, "cantSplit")
                if row_index == 0 and block.header:
                    add(row_props, "tblHeader")
                for width, value in zip(widths, cells, strict=True):
                    cell = add(row, "tc")
                    cell_props = add(cell, "tcPr")
                    add(cell_props, "tcW", w=width, type="dxa")
                    fmt = effective_format(plan, block)
                    if row_index == 0 and block.header:
                        add(cell_props, "shd", val="clear", fill=block.header_fill[1:])
                        fmt["bold"] = True
                    paragraph(cell, value, ids["Normal"], fmt)
            # Keep adjacent native tables distinct and retain Word's final paragraph.
            if index == len(plan.blocks) - 1 or isinstance(plan.blocks[index + 1], WordTable):
                paragraph(native, "", ids["Normal"], effective_format(plan))
        else:
            p = add(native, "p")
            add(add(p, "r"), "br", type="page")
    section = add(native, "sectPr")
    layout = plan.layout
    add(section, "pgSz", w=round(points(layout.width_mm) * 20), h=round(points(layout.height_mm) * 20))
    top, right, bottom, left = layout.margins_mm
    add(section, "pgMar", top=round(points(top) * 20), right=round(points(right) * 20),
        bottom=round(points(bottom) * 20), left=round(points(left) * 20),
        header=round(points(layout.header_mm) * 20), footer=round(points(layout.footer_mm) * 20), gutter=0)
    from app.mcp.office_word_xml import body_xml
    body = body_xml(before["xml"])
    # Preserve Word's namespace declarations, including prefixes referenced
    # by mc:Ignorable attributes. Generic package reserialization drops them.
    return before["xml"][:body.start()] + tostring(native, encoding="unicode") + before["xml"][body.end():]


def write_document(backend, document, packet, plan):
    backend.check_thread()
    backend.word_writable(document)
    document.Content.InsertXML(packet)
    setup = document.PageSetup
    setup.Orientation = int(plan.layout.width_mm > plan.layout.height_mm)
    values = [plan.layout.width_mm, plan.layout.height_mm, *plan.layout.margins_mm,
              plan.layout.header_mm, plan.layout.footer_mm]
    for name, value in zip(LAYOUT, values, strict=True):
        setattr(setup, name, points(value))
    setup.DifferentFirstPageHeaderFooter = False
    setup.OddAndEvenPagesHeaderFooter = False
    for collection in (document.Sections.Item(1).Headers, document.Sections.Item(1).Footers):
        for index in range(1, 4):
            part = collection.Item(index)
            if bool(part.Exists):
                part.Range.Text = ""
            part.Exists = False
    section = document.Sections.Item(1)
    if plan.header:
        section.Headers.Item(1).Exists = True
        section.Headers.Item(1).Range.Text = plan.header
    if plan.footer or plan.page_numbers != "none":
        section.Footers.Item(1).Exists = True
        footer = section.Footers.Item(1).Range
        footer.Text = plan.footer + ("  |  " if plan.footer and plan.page_numbers != "none" else "")
    if plan.page_numbers != "none":
        end = section.Footers.Item(1).Range.Duplicate
        end.End -= 1
        end.Collapse(0)
        end.InsertAfter("Page ")
        end.Collapse(0)
        end.Fields.Add(end, 33)
        if plan.page_numbers == "page_of_total":
            end = section.Footers.Item(1).Range.Duplicate
            end.End -= 1
            end.Collapse(0)
            end.InsertAfter(" of ")
            end.Collapse(0)
            end.Fields.Add(end, 26)
    fmt = effective_format(plan)
    for part in (section.Headers.Item(1), section.Footers.Item(1)):
        if bool(part.Exists):
            part.Range.Font.Name = fmt["font"]
            part.Range.Font.Size = 9
            part.Range.Font.Color = rgb(fmt["color"])
            part.Range.ParagraphFormat.SpaceBefore = 0
            part.Range.ParagraphFormat.SpaceAfter = 0
            part.Range.Fields.Update()
    document.Repaginate()
    for part in (section.Headers.Item(1), section.Footers.Item(1)):
        if bool(part.Exists):
            part.Range.Fields.Update()
    document.Repaginate()


def verify_document(document, plan):
    """Verify native types, content, styles, formatting and geometry after dispatch."""
    from app.mcp.office_contracts import WordParagraph, WordTable
    from app.mcp.office_excel import OfficeUnknown
    def require(condition):
        if not condition:
            raise OfficeUnknown("Native Word report readback differs from the approved structure or formatting.")
    require(int(document.Shapes.Count) == int(document.InlineShapes.Count) == 0)
    require(int(document.Sections.Count) == 1)
    expected_tables = [block for block in plan.blocks if isinstance(block, WordTable)]
    require(int(document.Tables.Count) == len(expected_tables))
    for index, block in enumerate(expected_tables, 1):
        table = document.Tables.Item(index)
        require(int(table.Rows.Count) == len(block.cells) and int(table.Columns.Count) == len(block.cells[0]))
        require(not bool(table.AllowAutoFit))
        for column, width in enumerate(block.widths_mm, 1):
            require(abs(float(table.Columns.Item(column).Width) - points(width)) < .15)
        for row, values in enumerate(block.cells, 1):
            for column, value in enumerate(values, 1):
                region = table.Cell(row, column).Range
                require(str(region.Text) == value + "\r\x07")
                if value:
                    region.End -= 1
                    fmt = effective_format(plan, block)
                    bold = True if row == 1 and block.header else fmt["bold"]
                    require(str(region.Font.Name).casefold() == fmt["font"].casefold())
                    require(abs(float(region.Font.Size) - fmt["size"]) < .05)
                    require(int(region.Font.Color) == rgb(fmt["color"]) and bool(region.Font.Bold) == bold)
                    require(bool(region.Font.Italic) == fmt["italic"])
        for border in (-1, -2, -3, -4, -5, -6):
            require(int(table.Borders.Item(border).LineStyle) == 1)
            require(int(table.Borders.Item(border).Color) == rgb(block.border_color))
        require(not bool(table.Rows.AllowBreakAcrossPages))
        if block.header:
            require(bool(table.Rows.Item(1).HeadingFormat))
            require(int(table.Cell(1, 1).Shading.BackgroundPatternColor) == rgb(block.header_fill))
    expected = []
    for index, block in enumerate(plan.blocks):
        if isinstance(block, WordParagraph):
            expected.append((block.text + "\r", block))
        elif not isinstance(block, WordTable):
            expected.append(("\x0c\r", None))
        elif index == len(plan.blocks) - 1 or isinstance(plan.blocks[index + 1], WordTable):
            expected.append(("\r", None))
    actual = [document.Paragraphs.Item(i) for i in range(1, int(document.Paragraphs.Count) + 1)
              if not bool(document.Paragraphs.Item(i).Range.Information(12))]
    require(len(actual) == len(expected))
    for native, (text, block) in zip(actual, expected, strict=True):
        require(str(native.Range.Text) == text)
        if block is None:
            continue
        require(str(native.Style.NameLocal) == str(document.Styles.Item(WORD_STYLES[block.style]).NameLocal))
        fmt = effective_format(plan, block)
        require(str(native.Range.Font.Name).casefold() == fmt["font"].casefold())
        require(abs(float(native.Range.Font.Size) - fmt["size"]) < .05)
        require(int(native.Range.Font.Color) == rgb(fmt["color"]))
        require(bool(native.Range.Font.Bold) == fmt["bold"] and bool(native.Range.Font.Italic) == fmt["italic"])
        paragraph_format = native.Range.ParagraphFormat
        require(int(paragraph_format.Alignment) == ALIGNMENTS[fmt["alignment"]])
        require(abs(float(paragraph_format.SpaceBefore) - fmt["space_before"]) < .05)
        require(abs(float(paragraph_format.SpaceAfter) - fmt["space_after"]) < .05)
        require(int(paragraph_format.LineSpacingRule) == 5)
        require(abs(float(paragraph_format.LineSpacing) - fmt["line_multiple"] * 12) < .06)
        require(bool(paragraph_format.PageBreakBefore) == block.page_break_before)
        require(bool(paragraph_format.WidowControl) and bool(paragraph_format.KeepWithNext) == fmt["keep_with_next"])
    layout = plan.layout
    values = [layout.width_mm, layout.height_mm, *layout.margins_mm, layout.header_mm, layout.footer_mm]
    require(all(abs(float(getattr(document.PageSetup, name)) - points(value)) < .15
                for name, value in zip(LAYOUT, values, strict=True)))
    section = document.Sections.Item(1)
    if plan.header:
        require(str(section.Headers.Item(1).Range.Text) == plan.header + "\r")
    else:
        require(not bool(section.Headers.Item(1).Exists))
    if not plan.footer and plan.page_numbers == "none":
        require(not bool(section.Footers.Item(1).Exists))
        return
    fields = section.Footers.Item(1).Range.Fields
    require([int(fields.Item(i).Type) for i in range(1, int(fields.Count) + 1)] ==
            {"none": [], "page": [33], "page_of_total": [33, 26]}[plan.page_numbers])
    require(str(section.Footers.Item(1).Range.Text).startswith(plan.footer))


def restore_document(backend, document, state):
    backend.check_thread()
    backend.word_writable(document)
    document.Content.InsertXML(state["xml"])
    setup = state["view"]["layout_points"]
    document.PageSetup.Orientation = int(setup["PageWidth"] > setup["PageHeight"])
    for name, value in state["view"]["layout_points"].items():
        setattr(document.PageSetup, name, value)
    from app.mcp.office_word_xml import packet, body_xml
    section = document.Sections.Item(1)
    for item in state["running"]:
        part = getattr(section, item["collection"]).Item(item["index"])
        if item["exists"]:
            part.Exists = True
            part.Range.InsertXML(packet(item["xml"], body_xml(item["xml"]).group()))
        else:
            part.Exists = False
    document.Repaginate()
    for collection in (section.Headers, section.Footers):
        for index in range(1, 4):
            if bool(collection.Item(index).Exists):
                collection.Item(index).Range.Fields.Update()
