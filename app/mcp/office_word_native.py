"""Word's bounded body-text subset, with private OOXML preservation guards."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from xml.sax.saxutils import escape

from defusedxml import ElementTree as ET

from app.mcp.office_contracts import canonical_json

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PKG = "{http://schemas.microsoft.com/office/2006/xmlPackage}"
MAX_WORD_UNITS = 4096
MAX_PARAGRAPH_UNITS = 8192
MAX_XML_BYTES = 256 * 1024


def reject(message):
    from app.mcp.office_excel import OfficeConflict
    raise OfficeConflict(message)


def units(text):
    try:
        return len(text.encode("utf-16-le")) // 2
    except UnicodeError:
        reject("Word text must end on complete Unicode character boundaries.")


def slice_units(text, start, end):
    try:
        return text.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")
    except UnicodeError:
        reject("Word targets must end on complete Unicode character boundaries.")


def tree(element):
    if element is None:
        return None
    # Word regenerates editing/proofing metadata; it is not text or formatting.
    attrs = {key: value for key, value in element.attrib.items()
             if not key.rsplit("}", 1)[-1].startswith("rsid") and key.rsplit("}", 1)[-1] != "textId"}
    return [element.tag, attrs, element.text or "", [tree(child) for child in element
            if child.tag != W + "proofErr"]]


def compact(runs):
    result = []
    for props, text in runs:
        if not text:
            continue
        if result and result[-1][0] == props:
            result[-1][1] += text
        else:
            result.append([props, text])
    return result


def intersecting_runs(runs, left, right):
    result, offset = [], 0
    for props, text in runs:
        limit = offset + units(text)
        if max(offset, left) < min(limit, right):
            result.append([props, slice_units(text, max(0, left - offset), min(units(text), right - offset))])
        offset = limit
    return compact(result)


def semantics(xml):
    """Reject structures we cannot recreate; retain all supported run/pPr XML."""
    if len(xml.encode("utf-8")) > MAX_XML_BYTES:
        reject("The Word formatting snapshot exceeds its bounded size.")
    root = ET.fromstring(xml)
    body = root.find(".//" + W + "body")
    if body is None:
        reject("Word did not return a body text snapshot.")
    paragraphs = [child for child in body if child.tag != W + "sectPr"]
    if len(paragraphs) != 1 or paragraphs[0].tag != W + "p":
        reject("Word replacements require one ordinary body paragraph.")
    paragraph = paragraphs[0]
    runs = []
    for child in paragraph:
        if child.tag in {W + "pPr", W + "proofErr"}:
            continue
        if child.tag != W + "r" or any(c.tag not in {W + "rPr", W + "t"} for c in child):
            reject("This Word range contains unsupported native structures.")
        runs.append([tree(child.find(W + "rPr")), "".join(c.text or "" for c in child if c.tag == W + "t")])
    ppr = paragraph.find(W + "pPr")
    if ppr is not None and ppr.find(W + "sectPr") is not None:
        reject("Section boundaries cannot be replaced.")
    dependencies = []
    for part in root.findall(PKG + "part"):
        name = part.attrib.get(PKG + "name", "")
        if name.startswith(("/word/styles", "/word/theme/", "/word/fontTable", "/word/numbering")):
            dependencies.append([name, tree(part.find(PKG + "xmlData"))])
    dependency = sha256(canonical_json(sorted(dependencies)).encode()).hexdigest()
    return [tree(paragraph)[1], tree(ppr), compact(runs)], dependency


def replacement(state, text):
    if not text or any(ord(c) < 32 for c in text) or units(text) > MAX_WORD_UNITS:
        reject("Replacement text must be nonempty plain text without paragraph/cell/control markers, up to 4096 UTF-16 units.")
    if not state["uniform"]:
        reject("The replacement target has mixed character formatting. Read one uniform text range.")
    expected = deepcopy(state)
    delta = units(text) - units(state["text"])
    expected.update(text=text, end=state["end"] + delta, pend=state["pend"] + delta)
    props = state["target"][2][0][0]
    expected["target"][2] = [[props, text]]
    left, right = state["start"] - state["pstart"], state["end"] - state["pstart"]
    native_runs = intersecting_runs(state["paragraph"][2], left, right)
    if len(native_runs) != 1:
        reject("The Word target has mixed inherited/direct formatting. Read one uniform text range.")
    paragraph_props = native_runs[0][0]
    offset, runs = 0, []
    for formatting, value in state["paragraph"][2]:
        limit = offset + units(value)
        if offset < left:
            runs.append([formatting, slice_units(value, 0, min(units(value), left - offset))])
        if offset <= left < limit:
            # Partial-range XML materializes inherited fonts; full-paragraph
            # XML retains the actual direct/inherited distinction. Preserve
            # each representation rather than flattening paragraph runs.
            runs.append([paragraph_props, text])
        if limit > right:
            runs.append([formatting, slice_units(value, max(0, right - offset), units(value))])
        offset = limit
    expected["paragraph"][2] = compact(runs)
    expected["paragraph_text"] = slice_units(state["paragraph_text"], 0, left) + text + slice_units(
        state["paragraph_text"], right, units(state["paragraph_text"]))
    return expected


class WordNative:
    def word_descriptor(self, document, start, end):
        return ("word", document, start, end, document.Range(start, end).Duplicate)

    def word_writable(self, document):
        self.check_thread()
        if (bool(document.ReadOnly) or bool(document.HasVBProject) or
                bool(getattr(document, "AutoSaveOn", False)) or int(document.ProtectionType) != -1 or
                bool(document.TrackRevisions) or int(document.Revisions.Count) or
                bool(document.Final) or int(document.Permission.Enabled)):
            reject("Word editing requires a writable macro-free unprotected document with AutoSave and tracked changes off.")
        if str(document.Path) and (Path(str(document.FullName)).suffix.lower() != ".docx" or
                                   int(document.SaveFormat) not in {12, 16}):
            reject("Word editing supports ordinary .docx documents only.")
        # Reject document-wide anchors whose adjustment has not been qualified.
        for collection in (document.Fields, document.Hyperlinks, document.Bookmarks, document.ContentControls):
            if int(collection.Count):
                reject("Word documents with fields, hyperlinks, bookmarks or content controls are read-only in this slice.")

    def word_xml_safe(self, document):
        # WordOpenXML includes related package parts even for a tiny range.
        # Bound those native exports before requesting them, so an unrelated
        # header image or embedded font cannot bypass the snapshot byte limit.
        if (bool(document.EmbedTrueTypeFonts) or int(document.InlineShapes.Count) or
                int(document.Shapes.Count) or int(document.Footnotes.Count) or int(document.Endnotes.Count) or
                int(document.Sections.Count) > 16):
            reject("Word snapshots with embedded fonts, drawings, notes or more than 16 sections are read-only.")
        for index in range(1, int(document.Sections.Count) + 1):
            section = document.Sections.Item(index)
            for collection in (section.Headers, section.Footers):
                for kind in range(1, 4):
                    part = collection.Item(kind)
                    if bool(part.Exists) and (int(part.Range.End) - int(part.Range.Start) > MAX_PARAGRAPH_UNITS or
                            int(part.Range.InlineShapes.Count) or int(part.Shapes.Count)):
                        reject("Word header/footer dependencies exceed the qualified text-only snapshot subset.")

    def capture_word(self, descriptor):
        self.check_thread()
        _, document, start, end, retained = descriptor
        if (not self.same(retained.Document, document) or int(retained.StoryType) != 1 or
                (int(retained.Start), int(retained.End)) != (start, end)):
            reject("Office conflict: the retained Word body anchor moved or changed story.")
        if not 0 <= start < end <= int(document.Content.End) or end - start > MAX_WORD_UNITS:
            reject("Read a nonempty Word target of at most 4096 UTF-16 units.")
        region = document.Range(start, end)
        if int(region.Paragraphs.Count) != 1 or bool(region.Information(12)):
            reject("Word table cells and multi-paragraph replacements are not supported.")
        text = str(region.Text)
        if units(text) != end - start or any(ord(c) < 32 for c in text):
            reject("Word paragraph/cell markers and split Unicode characters cannot be replaced.")
        self.word_xml_safe(document)
        paragraph = region.Paragraphs.Item(1).Range
        pstart, pend = int(paragraph.Start), int(paragraph.End)
        if pend - pstart > MAX_PARAGRAPH_UNITS:
            reject("The containing Word paragraph exceeds the preservation bound.")
        target, dependencies = semantics(str(region.WordOpenXML))
        full, paragraph_dependencies = semantics(str(paragraph.WordOpenXML))
        if dependencies != paragraph_dependencies or "".join(r[1] for r in target[2]) != text:
            reject("Word text and its formatting snapshot disagree.")
        return {"start": start, "end": end, "pstart": pstart, "pend": pend, "text": text,
                "target": target, "paragraph": full, "dependencies": dependencies,
                "paragraph_text": str(paragraph.Text), "uniform": len(target[2]) == 1 and
                    len(intersecting_runs(full[2], start - pstart, end - pstart)) == 1}

    def write_word(self, descriptor, state):
        self.check_thread()
        # Range.Text invokes Word's script-font substitution (including emoji),
        # which can silently change run properties. Insert a native-captured
        # OOXML text run instead, retaining its exact style and direct properties.
        # Only text is supplied by the caller; no caller XML is accepted.
        xml = str(descriptor[4].WordOpenXML)
        semantics(xml)
        body = re.search(r"<w:body\b[^>]*>.*?</w:body>", xml, re.DOTALL)
        if body is None:
            reject("Word returned an unsupported native XML namespace layout.")
        first = True
        def replace_text(match):
            nonlocal first
            text = escape(state["text"]) if first else ""
            first = False
            return '<w:t xml:space="preserve">' + text + '</w:t>'
        changed = re.sub(r"<w:t(?:\s[^>]*)?>.*?</w:t>", replace_text, body.group(), flags=re.DOTALL)
        if first:
            reject("Word returned no ordinary native text run.")
        # Range exports carry section properties (including header references)
        # even for a partial text run. Importing those creates a section/paragraph
        # boundary at the target end. Sections are outside this edit authority.
        changed = re.sub(r"<w:sectPr\b[^>]*>.*?</w:sectPr>|<w:sectPr\s*/>", "", changed, flags=re.DOTALL)
        # A partial range's export omits paragraph properties. Importing it
        # alone resets the containing paragraph to Normal. Carry the retained
        # full paragraph's native pPr explicitly, including its end-mark format.
        paragraph_xml = str(descriptor[4].Paragraphs.Item(1).Range.WordOpenXML)
        semantics(paragraph_xml)
        paragraph_body = re.search(r"<w:body\b[^>]*>.*?</w:body>", paragraph_xml, re.DOTALL)
        if paragraph_body is None:
            reject("Word returned an unsupported paragraph XML layout.")
        properties = re.search(r"<w:pPr\b[^>]*>.*?</w:pPr>|<w:pPr\s*/>", paragraph_body.group(), re.DOTALL)
        changed = re.sub(r"<w:pPr\b[^>]*>.*?</w:pPr>|<w:pPr\s*/>", "", changed, flags=re.DOTALL)
        if properties is not None:
            changed = re.sub(r"<w:p\b[^>]*>", lambda m: m.group() + properties.group(), changed, count=1)
        # Preserve native namespace declarations, including prefixes referenced
        # only by mc:Ignorable. Generic XML serialization drops those bindings.
        packet = xml[:body.start()] + changed + xml[body.end():]
        # Word also exports header/footer parts and their relationships for a
        # partial body range. Even an unused header part can make the importer
        # introduce a section break. Import only text-format dependencies.
        allowed = {"/_rels/.rels", "/word/document.xml", "/word/_rels/document.xml.rels",
                   "/word/styles.xml", "/word/stylesWithEffects.xml", "/word/fontTable.xml",
                   "/word/numbering.xml", "/word/theme/theme1.xml"}
        def keep_part(match):
            name = re.search(r'pkg:name="([^"]+)"', match.group())
            if name is None or name[1] not in allowed:
                return ""
            part = match.group()
            if name[1].endswith(".rels"):
                def keep_relationship(relation):
                    kind = re.search(r'Type="([^"]+)"', relation.group())
                    return relation.group() if kind and kind[1].rsplit("/", 1)[-1] in {
                        "officeDocument", "styles", "stylesWithEffects", "fontTable", "numbering", "theme"} else ""
                part = re.sub(r"<Relationship\b[^>]*/>", keep_relationship, part)
            return part
        packet = re.sub(r"<pkg:part\b[^>]*>.*?</pkg:part>", keep_part, packet, flags=re.DOTALL)
        descriptor[4].InsertXML(packet)
        return self.word_descriptor(descriptor[1], state["start"], state["end"])

    def save_word(self, document, save):
        self.check_thread()
        if save["save_as"]:
            document.SaveAs2(save["path"], 12)  # wdFormatXMLDocument, no macros.
        else:
            document.Save()
        path = Path(save["path"])
        if not bool(document.Saved) or Path(str(document.FullName)).resolve(strict=True) != path or not path.is_file():
            reject("Word did not verify saving to the approved destination.")
