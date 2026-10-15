"""Native-captured Word packets; caller text never supplies XML or relationships."""
import re
from xml.etree.ElementTree import Element, register_namespace, tostring

from app.mcp.office_word_native import W, reject

register_namespace("w", W[1:-1])


def body_xml(xml):
    body = re.search(r"<w:body\b[^>]*>.*?</w:body>", xml, re.DOTALL)
    if body is None:
        reject("Word returned an unsupported native XML namespace layout.")
    return body


def node_xml(node):
    def element(value):
        tag, attrs, text, children = value
        result = Element(tag, attrs)
        result.text = text or None
        result.extend(element(child) for child in children)
        return result
    return tostring(element(node), encoding="unicode") if node is not None else ""


def paragraph_xml(semantic):
    attrs, properties, runs = semantic
    return node_xml([W + "p", attrs, "", ([properties] if properties is not None else []) + [
        [W + "r", {}, "", ([props] if props is not None else []) + [
            [W + "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"}, text, []]]]
        for props, text in runs]])


def packet(xml, changed):
    body = body_xml(xml)
    changed = re.sub(r"<w:sectPr\b[^>]*>.*?</w:sectPr>|<w:sectPr\s*/>", "", changed, flags=re.DOTALL)
    value = xml[:body.start()] + changed + xml[body.end():]
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
    return re.sub(r"<pkg:part\b[^>]*>.*?</pkg:part>", keep_part, value, flags=re.DOTALL)
