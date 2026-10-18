"""Bounded native report composition; all supplied content becomes Word body text."""
from hashlib import sha256
import posixpath
from xml.etree.ElementTree import SubElement, tostring

from defusedxml import ElementTree as ET

from app.mcp.office_contracts import canonical_json
from app.mcp.office_word_native import W, PKG, WORD_STYLES, reject

MAX_DOCUMENT_XML = 2 * 1024 * 1024
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
                  and key.rsplit("}", 1)[-1] not in {"paraId", "textId", "dirty", "editId", "anchorId"}
                  and not (key == "id" and node.tag.rsplit("}", 1)[-1] in {"docPr", "cNvPr"})}
    if node.tag == W + "docGrid" and attributes.get(W + "type", "default") == "default":
        # Word recalculates this dormant pitch on section import. In default
        # (no-grid) mode it does not control layout. Active grid pitch remains
        # guarded, along with all other section attributes.
        attributes.pop(W + "linePitch", None)
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
        binary = part.find(PKG + "binaryData")
        if binary is not None:
            import base64
            content = sha256(base64.b64decode("".join((binary.text or "").split()), validate=True)).hexdigest()
            aliases[name] = "media:" + content
            binary.text = content
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
                    for key in (R + "id", R + "embed"):
                        if node.attrib.get(key) == old_id:
                            node.attrib[key] = identity
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
    count = int(document.Sections.Count)
    # Sixteen authored sections may have one empty continuous column terminator.
    terminal = document.Sections.Item(count) if count == 17 else None
    valid_terminal = terminal is not None and (str(terminal.Range.Text) == "\r"
        and int(terminal.PageSetup.SectionStart) == 0 and int(terminal.PageSetup.TextColumns.Count) == 1)
    if int(document.Content.End) > 32768 or not (1 <= count <= 16 or count == 17 and valid_terminal):
        reject("Report authoring supports at most 16 content sections and 32768 native text positions.")
    if int(document.Tables.Count) > 32 or sum(int(document.Tables.Item(i).Range.Cells.Count)
            for i in range(1, int(document.Tables.Count) + 1)) > 512:
        reject("Report authoring supports at most 32 tables and 512 cells.")
    xml = str(document.Content.WordOpenXML)
    if len(xml.encode()) > MAX_DOCUMENT_XML:
        reject("The complete report snapshot exceeds its two-MiB bound.")
    root = ET.fromstring(xml)
    from app.mcp.office_word_assets import validate_package, REL
    pictures = validate_package(root)
    parts = {p.attrib.get(PKG + "name"): p for p in root.findall(PKG + "part")}
    relationships = parts.get("/word/_rels/document.xml.rels")
    mapping = {} if relationships is None else {r.attrib.get("Id"): posixpath.normpath(posixpath.join("/word", r.attrib.get("Target", "")))
        for r in relationships.iter(REL + "Relationship")}
    properties = parts["/word/document.xml"].findall(".//" + W + "sectPr")
    if len(properties) != int(document.Sections.Count):
        reject("Word section metadata and native package disagree.")
    if any(g.attrib.get(W + "type", "default") != "default" for p in properties for g in p.findall(W + "docGrid")):
        reject("Active document grids are unsupported for report authoring.")
    inherited = {}
    running = []
    section_views = []
    for number in range(1, int(document.Sections.Count) + 1):
        section = document.Sections.Item(number)
        setup = section.PageSetup
        columns = setup.TextColumns
        if int(columns.Count) not in {1, 2} or not bool(columns.EvenlySpaced) or int(setup.SectionStart) not in {0, 2}:
            reject("Only one/two equal columns and continuous/new-page sections are supported.")
        section_views.append({"layout_points": {name: round(float(getattr(setup, name)), 3) for name in LAYOUT},
            "columns": int(columns.Count), "column_spacing_points": round(float(columns.Spacing), 3) if int(columns.Count) > 1 else 0,
            "start": int(setup.SectionStart), "different_first": bool(setup.DifferentFirstPageHeaderFooter),
            "odd_even": bool(setup.OddAndEvenPagesHeaderFooter)})
        for name, collection in (("Headers", section.Headers), ("Footers", section.Footers)):
            for index in range(1, 4):
                part = collection.Item(index)
                if bool(part.Exists):
                    if int(part.Range.Hyperlinks.Count) or any(int(part.Range.Fields.Item(i).Type) not in {26, 33}
                            for i in range(1, int(part.Range.Fields.Count) + 1)):
                        reject("Report running matter supports ordinary text and PAGE/NUMPAGES fields only.")
                running.append({"section": number, "collection": name, "index": index,
                    "exists": bool(part.Exists), "linked": bool(part.LinkToPrevious),
                    "body": None})
                kind = {1: "default", 2: "first", 3: "even"}[index]
                tag = W + ("headerReference" if name == "Headers" else "footerReference")
                reference = next((n for n in properties[number - 1] if n.tag == tag and n.attrib.get(W + "type") == kind), None)
                if reference is not None:
                    inherited[(name, index)] = mapping.get(reference.attrib.get(R + "id"))
                source = parts.get(inherited.get((name, index)))
                if bool(part.Exists):
                    if source is None:
                        reject("Word running-matter relationship is unavailable.")
                    data = source.find(PKG + "xmlData")
                    container = list(data)[0] if data is not None and len(data) else None
                    if container is None:
                        reject("Word running-matter package is unavailable.")
                    running[-1]["body"] = "<w:body>" + "".join(tostring(n, encoding="unicode") for n in container) + "</w:body>"
    if any(node.attrib.get("TargetMode") == "External" for node in root.iter()):
        reject("Report authoring cannot replace documents with external relationships.")
    setup = document.Sections.Item(1).PageSetup
    section = document.Sections.Item(1)
    view = {"scope": "Complete body, page setup, styles and running matter; replacement is explicit.",
            "text": str(document.Content.Text), "tables": int(document.Tables.Count),
            "layout_points": {name: round(float(getattr(setup, name)), 3) for name in LAYOUT},
            "header": str(section.Headers.Item(1).Range.Text) if bool(section.Headers.Item(1).Exists) else "",
            "footer": str(section.Footers.Item(1).Range.Text) if bool(section.Footers.Item(1).Exists) else "",
            "styles": backend.word_styles(document), "sections": section_views,
            "pictures": [{k: v for k, v in p.items() if k != "digest"} for p in pictures]}
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
    # The public/COM alignment is called "justify"; WordprocessingML calls
    # that value "both". Emitting "justify" makes Word reject the XML packet.
    add(props, "jc", val="both" if fmt["alignment"] == "justify" else fmt["alignment"])
    add(props, "spacing", before=round(fmt["space_before"] * 20), after=round(fmt["space_after"] * 20),
        line=round(fmt["line_multiple"] * 240), lineRule="auto")
    add(props, "widowControl")
    # False must override the source style too. Omission inherits pagination
    # rules and can turn an otherwise correct import into pages of blank space.
    add(props, "keepNext", val=int(fmt["keep_with_next"]))
    add(props, "keepLines", val=0)
    add(props, "pageBreakBefore", val=int(page_break))
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


def section_specs(plan):
    from app.mcp.office_contracts import WordSectionBreak
    specs = [dict(columns=plan.layout.columns, column_spacing_mm=plan.layout.column_spacing_mm, start="continuous"),
        *[b.model_dump(exclude={"kind"}) for b in plan.blocks if isinstance(b, WordSectionBreak)]]
    if specs[-1]["columns"] == 2:
        # Word balances a column section when a following continuous section
        # closes it. End-of-document alone leaves the last page unbalanced.
        specs.append(dict(columns=1, column_spacing_mm=0, start="continuous", terminal=True))
    return specs


def column_balance_disabled(root):
    return any(node.attrib.get(W + "val", "1") not in {"0", "false", "off"}
               for node in root.findall(".//" + W + "noColumnBalance"))


def section_xml(parent, layout, spec):
    section = add(parent, "sectPr")
    add(section, "type", val="continuous" if spec["start"] == "continuous" else "nextPage")
    add(section, "pgSz", w=round(points(layout.width_mm) * 20), h=round(points(layout.height_mm) * 20))
    top, right, bottom, left = layout.margins_mm
    add(section, "pgMar", top=round(points(top) * 20), right=round(points(right) * 20),
        bottom=round(points(bottom) * 20), left=round(points(left) * 20),
        header=round(points(layout.header_mm) * 20), footer=round(points(layout.footer_mm) * 20), gutter=0)
    add(section, "cols", num=spec["columns"], space=round(points(spec["column_spacing_mm"]) * 20), equalWidth=1)
    return section


def picture_xml(parent, block, metadata, relationship, number):
    from app.mcp.office_word_assets import WP, A, PIC
    from xml.etree.ElementTree import SubElement as node
    p = add(parent, "p")
    props = add(p, "pPr")
    add(props, "keepNext", val=int(bool(block.caption or block.credit)))
    add(props, "keepLines", val=0)
    add(props, "pageBreakBefore", val=0)
    inline = node(add(add(p, "r"), "drawing"), WP + "inline", {"distT": "0", "distB": "0", "distL": "0", "distR": "0"})
    cx, cy = round(block.width_mm * 36000), round(block.width_mm * metadata["height_px"] / metadata["width_px"] * 36000)
    node(inline, WP + "extent", {"cx": str(cx), "cy": str(cy)})
    node(inline, WP + "docPr", {"id": str(number), "name": "Picture " + str(number), "descr": block.alt_text})
    node(node(inline, WP + "cNvGraphicFramePr"), A + "graphicFrameLocks", {"noChangeAspect": "1"})
    graphic = node(node(inline, A + "graphic"), A + "graphicData", {"uri": PIC[1:-1]})
    pic = node(graphic, PIC + "pic")
    nv = node(pic, PIC + "nvPicPr")
    node(nv, PIC + "cNvPr", {"id": "0", "name": "Picture " + str(number)})
    node(nv, PIC + "cNvPicPr")
    fill = node(pic, PIC + "blipFill")
    node(fill, A + "blip", {R + "embed": relationship})
    node(node(fill, A + "stretch"), A + "fillRect")
    props = node(pic, PIC + "spPr")
    transform = node(props, A + "xfrm")
    node(transform, A + "off", {"x": "0", "y": "0"})
    node(transform, A + "ext", {"cx": str(cx), "cy": str(cy)})
    node(node(props, A + "prstGeom", {"prst": "rect"}), A + "avLst")


def compile_packet(document, plan, before, media=None):
    """Build XML internally from typed content, preserving native style definitions."""
    from app.mcp.office_contracts import WordParagraph, WordTable, WordImage, WordSectionBreak, WordColumnBreak
    media = media or {}
    specs, current, images = section_specs(plan), 0, []
    root = ET.fromstring(before["xml"])
    if any(spec["columns"] == 2 for spec in specs) and column_balance_disabled(root):
        reject("This document disables column balancing. Enable column balancing in Word and read fresh authoring before composing columns.")
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
        elif isinstance(block, WordImage):
            data, metadata = media[block.asset]
            number = len(images) + 1
            relationship = "orsiPicture" + str(number)
            images.append((relationship, data, metadata))
            picture_xml(native, block, metadata, relationship, number)
            for text, keep_next in ((block.caption, bool(block.credit)), (block.credit, False)):
                if text:
                    fmt = effective_format(plan)
                    fmt["keep_with_next"] = keep_next
                    paragraph(native, text, ids["Normal"], fmt)
        elif isinstance(block, WordSectionBreak):
            # A dedicated native paragraph owns the preceding section properties.
            boundary = paragraph(native, "", ids["Normal"], effective_format(plan))
            section_xml(boundary.find(W + "pPr"), plan.layout, specs[current])
            current += 1
        else:
            p = paragraph(native, "", ids["Normal"], effective_format(plan))
            add(add(p, "r"), "br", type="column" if isinstance(block, WordColumnBreak) else "page")
    if plan.blocks[-1].kind == "image":
        paragraph(native, "", ids["Normal"], effective_format(plan))
    if specs[-1].get("terminal"):
        fmt = {**effective_format(plan), "size":1, "space_before":0, "space_after":0, "line_multiple":1,
               "keep_with_next":False}
        boundary = paragraph(native, "", ids["Normal"], fmt)
        section_xml(boundary.find(W + "pPr"), plan.layout, specs[current])
        current += 1
        paragraph(native, "", ids["Normal"], fmt)
    section_xml(native, plan.layout, specs[current])
    from app.mcp.office_word_xml import body_xml
    body = body_xml(before["xml"])
    # Preserve Word's namespace declarations, including prefixes referenced
    # by mc:Ignorable attributes. Generic package reserialization drops them.
    value = before["xml"][:body.start()] + tostring(native, encoding="unicode") + before["xml"][body.end():]
    # Body replacement clears running matter too. Remove old media/relationships,
    # retaining style/font/theme namespaces verbatim from Word's captured packet.
    import re, base64
    from xml.etree.ElementTree import Element
    from app.mcp.office_word_assets import REL
    value = re.sub(r'<pkg:part\b[^>]*pkg:name="/word/media/[^\"]+"[^>]*>.*?</pkg:part>', "", value, flags=re.DOTALL)
    value = re.sub(r'<pkg:part\b[^>]*pkg:name="/word/(?:header|footer)[^/\"]*\.xml"[^>]*>.*?</pkg:part>', "", value, flags=re.DOTALL)
    value = re.sub(r'<pkg:part\b[^>]*pkg:name="/word/_rels/(?:header|footer)[^/\"]*\.rels"[^>]*>.*?</pkg:part>', "", value, flags=re.DOTALL)
    value = re.sub(r'<Relationship\b[^>]*Type="[^\"]+/(?:image|header|footer)"[^>]*/>', "", value)
    new_parts, relationships = [], []
    for rid, data, meta in images:
        extension = "png" if meta["format"] == "PNG" else "jpg"
        name = "media/" + rid + "." + extension
        part = Element(PKG + "part", {PKG + "name": "/word/" + name,
            PKG + "contentType": "image/png" if extension == "png" else "image/jpeg", PKG + "compression": "store"})
        SubElement(part, PKG + "binaryData").text = base64.b64encode(data).decode("ascii")
        new_parts.append(tostring(part, encoding="unicode"))
        relation = Element("Relationship", {"Id": rid, "Type": R[1:-1] + "/image", "Target": name})
        relationships.append(tostring(relation, encoding="unicode"))
    if relationships:
        # Flat OPC captured by Word always uses the default Relationships namespace.
        match = re.search(r'<pkg:part\b[^>]*pkg:name="/word/_rels/document.xml.rels"[^>]*>.*?</pkg:part>', value, re.DOTALL)
        if match is None:
            reject("Word returned no document relationship part.")
        changed = match.group().replace("</Relationships>", "".join(relationships) + "</Relationships>")
        value = value[:match.start()] + changed + value[match.end():]
    value = value.replace("</pkg:package>", "".join(new_parts) + "</pkg:package>")
    if len(value.encode()) > MAX_DOCUMENT_XML:
        reject("The composed native package exceeds its two-MiB snapshot limit.")
    from app.mcp.office_word_assets import validate_package
    validate_package(ET.fromstring(value))
    return value


def write_document(backend, document, packet, plan):
    backend.check_thread()
    backend.word_writable(document)
    from app.mcp.office_write_diagnostics import native_step
    with native_step("insert_xml"):
        document.Content.InsertXML(packet)
    with native_step("section_layout"):
        configure_sections(document, plan)
    with native_step("running_matter"):
        write_running_matter(document, plan)
    finalize_layout(document)


def configure_sections(document, plan):
    values = [plan.layout.width_mm, plan.layout.height_mm, *plan.layout.margins_mm,
              plan.layout.header_mm, plan.layout.footer_mm]
    for number, spec in enumerate(section_specs(plan), 1):
        native = document.Sections.Item(number)
        setup = native.PageSetup
        if int(setup.Orientation) != int(plan.layout.width_mm > plan.layout.height_mm):
            setup.Orientation = int(plan.layout.width_mm > plan.layout.height_mm)
        for name, value in zip(LAYOUT, values, strict=True):
            if abs(float(getattr(setup, name)) - points(value)) >= .05:
                setattr(setup, name, points(value))
        start = 0 if spec["start"] == "continuous" else 2
        if int(setup.SectionStart) != start:
            setup.SectionStart = start
        columns = setup.TextColumns
        if int(columns.Count) != spec["columns"]:
            columns.SetCount(spec["columns"])
        if not bool(columns.EvenlySpaced):
            columns.EvenlySpaced = True
        if spec["columns"] == 2:
            if abs(float(columns.Spacing) - points(spec["column_spacing_mm"])) >= .05:
                columns.Spacing = points(spec["column_spacing_mm"])
        setup.DifferentFirstPageHeaderFooter = False
        setup.OddAndEvenPagesHeaderFooter = False
        for collection in (native.Headers, native.Footers):
            for index in range(1, 4):
                part = collection.Item(index)
                part.LinkToPrevious = False
                if bool(part.Exists):
                    part.Range.Text = ""
                part.Exists = False


def write_running_matter(document, plan):
    for number in range(1, int(document.Sections.Count) + 1):
        section = document.Sections.Item(number)
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
        if plan.page_numbers != "none":
            section.Footers.Item(1).PageNumbers.RestartNumberingAtSection = False


def finalize_layout(document):
    """Page totals need pagination before field update and a final reflow."""
    from app.mcp.office_write_diagnostics import native_step
    with native_step("repaginate"):
        document.Repaginate()
    with native_step("fields_update"):
        for number in range(1, int(document.Sections.Count) + 1):
            section = document.Sections.Item(number)
            for part in (section.Headers.Item(1), section.Footers.Item(1)):
                if bool(part.Exists):
                    part.Range.Fields.Update()
    with native_step("repaginate"):
        document.Repaginate()


def matches_line_spacing(paragraph_format, multiple):
    """Word canonicalizes auto 240/360/480 to single/1.5/double COM rules.

    Custom multiples use twelve-point units in COM. Standard rules describe a
    ratio instead; their reported point height varies with the font. Compare
    the requested ratio, without accepting another spacing rule or multiplier.
    """
    rule = int(paragraph_format.LineSpacingRule)
    if rule == 5:
        return abs(float(paragraph_format.LineSpacing) - multiple * 12) < .06
    return rule == {1: 0, 1.5: 1, 2: 2}.get(round(multiple * 240) / 240)


def verify_document(document, plan, media=None):
    """Verify native types, content, styles, formatting and geometry after dispatch."""
    from app.mcp.office_contracts import WordParagraph, WordTable, WordImage, WordColumnBreak, WordSectionBreak
    from app.mcp.office_excel import OfficeUnknown
    def require(condition):
        if not condition:
            raise OfficeUnknown("Native Word report readback differs from the approved structure or formatting.")
    require(int(document.Shapes.Count) == 0)
    pictures = [block for block in plan.blocks if isinstance(block, WordImage)]
    require(int(document.InlineShapes.Count) == len(pictures))
    from app.mcp.office_word_assets import validate_package
    picture_info = validate_package(ET.fromstring(str(document.Content.WordOpenXML)))
    require(len(picture_info) == len(pictures))
    if media is not None:
        require([info["digest"] for info in picture_info] == [media[b.asset] for b in pictures])
    for number, (block, info) in enumerate(zip(pictures, picture_info, strict=True), 1):
        picture = document.InlineShapes.Item(number)
        require(int(picture.Type) == 3 and str(picture.AlternativeText) == block.alt_text)
        require(abs(float(picture.Width) - points(block.width_mm)) < .15)
        require(abs(float(picture.Height) - points(block.width_mm * info["height_px"] / info["width_px"])) < .15)
        paragraph_range = picture.Range.Paragraphs.Item(1).Range
        require(not bool(paragraph_range.ParagraphFormat.PageBreakBefore))
        require(bool(paragraph_range.ParagraphFormat.KeepWithNext) == bool(block.caption or block.credit))
        for text, keep_next in ((block.caption, bool(block.credit)), (block.credit, False)):
            if text:
                start = int(paragraph_range.End)
                paragraph_range = document.Range(start,start).Paragraphs.Item(1).Range
                require(str(paragraph_range.Text) == text + "\r")
                require(not bool(paragraph_range.ParagraphFormat.PageBreakBefore))
                require(bool(paragraph_range.ParagraphFormat.KeepWithNext) == keep_next)
    specs = section_specs(plan)
    require(int(document.Sections.Count) == len(specs))
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
        elif isinstance(block, WordImage):
            # Word's COM text projection uses a printable picture placeholder;
            # verify the actual object/relationship separately above.
            expected.append((None, None))
            expected.extend((text + "\r", None) for text in (block.caption, block.credit) if text)
        elif isinstance(block, WordSectionBreak):
            expected.append(("\x0c", None))
        elif isinstance(block, WordColumnBreak):
            expected.append(("\x0e\r", None))
        elif not isinstance(block, WordTable):
            expected.append(("\x0c\r", None))
        elif index == len(plan.blocks) - 1 or isinstance(plan.blocks[index + 1], WordTable):
            expected.append(("\r", None))
    if plan.blocks[-1].kind == "image":
        expected.append(("\r", None))
    if specs[-1].get("terminal"):
        expected.extend((("\x0c", None), ("\r", None)))
    actual = [document.Paragraphs.Item(i) for i in range(1, int(document.Paragraphs.Count) + 1)
              if not bool(document.Paragraphs.Item(i).Range.Information(12))]
    require(len(actual) == len(expected))
    for native, (text, block) in zip(actual, expected, strict=True):
        if text is None:
            require(int(native.Range.InlineShapes.Count) == 1 and len(str(native.Range.Text)) == 2
                    and str(native.Range.Text).endswith("\r"))
        else:
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
        require(matches_line_spacing(paragraph_format, fmt["line_multiple"]))
        require(bool(paragraph_format.PageBreakBefore) == block.page_break_before)
        require(bool(paragraph_format.WidowControl) and bool(paragraph_format.KeepWithNext) == fmt["keep_with_next"])
        require(not bool(paragraph_format.KeepTogether))
    layout = plan.layout
    values = [layout.width_mm, layout.height_mm, *layout.margins_mm, layout.header_mm, layout.footer_mm]
    def empty_running(part):
        # Word retains a primary empty stub after a many-to-one section import.
        # Its existence is inert; text, fields and drawing objects are not.
        return not bool(part.Exists) or (str(part.Range.Text) in {"", "\r"}
            and int(part.Range.Fields.Count) == int(part.Range.Hyperlinks.Count)
            == int(part.Range.InlineShapes.Count) == int(part.Shapes.Count) == 0)
    for number, spec in enumerate(specs, 1):
        native = document.Sections.Item(number)
        require(all(abs(float(getattr(native.PageSetup, name)) - points(value)) < .15
                    for name, value in zip(LAYOUT, values, strict=True)))
        require(int(native.PageSetup.SectionStart) == (0 if spec["start"] == "continuous" else 2))
        require(int(native.PageSetup.TextColumns.Count) == spec["columns"])
        require(bool(native.PageSetup.TextColumns.EvenlySpaced))
        if spec["columns"] == 2:
            require(abs(float(native.PageSetup.TextColumns.Spacing) - points(spec["column_spacing_mm"])) < .15)
        if plan.header:
            require(str(native.Headers.Item(1).Range.Text) == plan.header + "\r")
            require(int(native.Headers.Item(1).Range.Fields.Count) == 0)
        else:
            require(empty_running(native.Headers.Item(1)))
        if plan.footer or plan.page_numbers != "none":
            require(str(native.Footers.Item(1).Range.Text).startswith(plan.footer))
            fields = native.Footers.Item(1).Range.Fields
            require([int(fields.Item(i).Type) for i in range(1, int(fields.Count) + 1)] ==
                {"none": [], "page": [33], "page_of_total": [33, 26]}[plan.page_numbers])
        else:
            require(empty_running(native.Footers.Item(1)))
        if plan.page_numbers != "none":
            require(not bool(native.Footers.Item(1).PageNumbers.RestartNumberingAtSection))



def restore_document(backend, document, state):
    backend.check_thread()
    backend.word_writable(document)
    document.Content.InsertXML(state["xml"])
    for number, view in enumerate(state["view"]["sections"], 1):
        setup = document.Sections.Item(number).PageSetup
        values = view["layout_points"]
        orientation = int(values["PageWidth"] > values["PageHeight"])
        if int(setup.Orientation) != orientation:
            setup.Orientation = orientation
        for name, value in values.items():
            if abs(float(getattr(setup, name)) - value) > .001:
                setattr(setup, name, value)
        for name, value in (("SectionStart", view["start"]),
                ("DifferentFirstPageHeaderFooter", view.get("different_first", False)),
                ("OddAndEvenPagesHeaderFooter", view.get("odd_even", False))):
            current = getattr(setup, name)
            if (int(current) if name == "SectionStart" else bool(current)) != value:
                setattr(setup, name, value)
        # Reapplying an already imported width/margin/column setting can make
        # Word recalculate docGrid pitch in unrelated continuous sections.
        # Keep the captured XML properties when they already match exactly.
        if int(setup.TextColumns.Count) != view["columns"]:
            setup.TextColumns.SetCount(view["columns"])
        if not bool(setup.TextColumns.EvenlySpaced):
            setup.TextColumns.EvenlySpaced = True
        if view["columns"] == 2 and abs(float(setup.TextColumns.Spacing) - view["column_spacing_points"]) > .001:
            setup.TextColumns.Spacing = view["column_spacing_points"]
    from app.mcp.office_word_xml import packet, body_xml
    for item in state["running"]:
        section = document.Sections.Item(item.get("section", 1))
        part = getattr(section, item["collection"]).Item(item["index"])
        if item.get("section", 1) > 1:
            part.LinkToPrevious = False
        if item["exists"]:
            part.Exists = True
            part.Range.InsertXML(packet(state["xml"], item["body"]))
        else:
            part.Exists = False
    # Set links only after every source and destination story exists. Applying
    # links while later stories are still being replaced can resolve a missing
    # continuous header to the first section or materialize an empty final part.
    for item in state["running"]:
        view = state["view"]["sections"][item.get("section", 1) - 1]
        active = item["index"] == 1 or item["index"] == 2 and view.get("different_first") or item["index"] == 3 and view.get("odd_even")
        if item.get("section", 1) > 1 and item["exists"] and item.get("linked") and active:
            part = getattr(document.Sections.Item(item["section"]), item["collection"]).Item(item["index"])
            if not bool(part.LinkToPrevious):
                part.LinkToPrevious = True
    document.Repaginate()
    for number in range(1, int(document.Sections.Count) + 1):
        section = document.Sections.Item(number)
        for collection in (section.Headers, section.Footers):
            for index in range(1, 4):
                if bool(collection.Item(index).Exists):
                    collection.Item(index).Range.Fields.Update()
