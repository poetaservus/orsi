"""Word print-quality page pixels, retained only in bounded bridge memory."""
import base64
from collections import OrderedDict
from hashlib import sha256
from io import BytesIO
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.mcp.office_contracts import canonical_json
from app.mcp.office_com import OfficeUnavailable

MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_RENDER_BYTES = 2 * 1024 * 1024


class WordRenderUnavailable(OfficeUnavailable):
    """Only fixed, content-free renderer setup/consistency messages."""


def layout_view(document):
    document.Repaginate()
    count = int(document.Range(0, 0).Information(4))
    if not 1 <= count <= 1000:
        raise WordRenderUnavailable("Word page count exceeds the inspection bound.")
    setup = document.Sections.Item(1).PageSetup
    sections = []
    for number in range(1, int(document.Sections.Count) + 1):
        page = document.Sections.Item(number).PageSetup
        columns = page.TextColumns
        sections.append({"columns": int(columns.Count), "column_spacing_mm":
            round(float(columns.Spacing) * 25.4 / 72, 2) if int(columns.Count) > 1 else 0})
    overflow = []
    for index in range(1, min(int(document.Tables.Count), 32) + 1):
        table = document.Tables.Item(index)
        try:
            page = table.Range.Sections.Item(1).PageSetup
            body_width = (float(page.PageWidth) - float(page.LeftMargin) - float(page.RightMargin)
                - (int(page.TextColumns.Count) - 1) * float(page.TextColumns.Spacing)) / int(page.TextColumns.Count)
            width = sum(float(table.Columns.Item(i).Width) for i in range(1, int(table.Columns.Count) + 1))
            if width > body_width + 1:
                overflow.append(index)
        except Exception:
            overflow.append(index)  # Irregular widths require visual inspection.
    return {"page_count": count, "page_width_mm": round(float(setup.PageWidth) * 25.4 / 72, 2),
            "page_height_mm": round(float(setup.PageHeight) * 25.4 / 72, 2),
            "tables_outside_body_or_irregular": overflow,
            "sections": sections, "inline_pictures": int(document.InlineShapes.Count),
            "visual_verification_status": "requires_review",
            "render_target": "render:1:" + str(min(count, 3)),
            "scope": "Native Word pagination and table widths. Inspect every rendered page for whitespace, clipping and headings."}


def render_document_pages(document, first, last):
    """Word exports the exact bound document, independent of active UI windows.

    Native Page.EnhMetaFileBits omits repeated headers and can retain stale
    page totals. Use the print-quality PDF pipeline and rasterize its bytes.
    The export is private temporary data, removed before returning.
    """
    import pypdfium2
    with TemporaryDirectory(prefix="word-render-") as directory:
        path = Path(directory) / "pages.pdf"
        document.ExportAsFixedFormat(str(path), 17, False, 0, 3, first, last,
                                    0, False, True, 0, True, True, False)
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise WordRenderUnavailable("The Word print export exceeds its bounded size.")
        data = path.read_bytes()
    result = []
    pdf = pypdfium2.PdfDocument(data)
    try:
        if len(pdf) != last - first + 1:
            raise WordRenderUnavailable("The Word print export did not contain the requested pages.")
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                width, height = page.get_size()
                if not 72 <= width <= 1440 or not 72 <= height <= 1440:
                    raise WordRenderUnavailable("The Word page size exceeds the rendering bound.")
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_bounded()
                finally:
                    textpage.close()
                bitmap = page.render(scale=2, may_draw_forms=False)
                try:
                    with bitmap.to_pil() as image:
                        output = BytesIO()
                        image.save(output, format="PNG")
                        size = image.size
                finally:
                    bitmap.close()
                pixels = output.getvalue()
                if len(pixels) > MAX_PAGE_BYTES:
                    raise WordRenderUnavailable("The rendered Word page exceeds its image bound.")
                result.append((first + index, pixels, size, text))
            finally:
                page.close()
    finally:
        pdf.close()
    return result


class WordRenders:
    def __init__(self, live):
        self.live = live
        self.images = OrderedDict()
        self.revisions = {}
        self.transfers = {}

    def clear(self):
        self.images.clear()
        self.revisions.clear()
        self.transfers.clear()

    def read(self, arguments, binding):
        match = re.fullmatch(r"render:([1-9][0-9]{0,3}):([1-9][0-9]{0,3})", arguments.target)
        if match is None or arguments.cursor is not None:
            raise WordRenderUnavailable("Use render:first:last without a cursor, with at most three pages per call.")
        first, last = map(int, match.groups())
        if last < first or last - first >= 3 or last - first + 1 > arguments.max_items:
            raise WordRenderUnavailable("Render one to three consecutive pages within the requested item limit.")
        backend = self.live.backend
        backend.check_thread()
        document = self.live.documents[binding["document"]["document"]][1]
        from app.mcp.office_word_document import signature
        source = str(document.Content.WordOpenXML)
        if len(source.encode()) > 8 * 1024 * 1024:
            raise WordRenderUnavailable("The source document exceeds the bounded page-render snapshot.")
        fingerprint = signature(source)
        layout = layout_view(document)
        if last > layout["page_count"]:
            raise WordRenderUnavailable("The requested render page exceeds Word's actual page count.")
        snapshot, items, images = uuid4().hex, [], {}
        header = ""
        if int(document.Sections.Count) == 1 and not bool(document.PageSetup.DifferentFirstPageHeaderFooter):
            part = document.Sections.Item(1).Headers.Item(1)
            if bool(part.Exists):
                header = " ".join(str(part.Range.Text).split())
        for number, data, size, text in render_document_pages(document, first, last):
            metadata = {"page": number, "page_count": layout["page_count"], "width": size[0],
                        "height": size[1], "bytes": len(data), "sha256": sha256(data).hexdigest(),
                        "text_characters": len(text),
                        "header_present": header in " ".join(text.split()) if header else None,
                        "visual_verification_status": "requires_review"}
            items.append({"target": uuid4().hex, "label": "Rendered Word page " + str(number),
                          "text": canonical_json(metadata)})
            images[number] = data
        current = str(document.Content.WordOpenXML)
        if len(current.encode()) > 8 * 1024 * 1024 or signature(current) != fingerprint:
            raise WordRenderUnavailable("The Word document changed during page rendering. Render a fresh page group.")
        if sum(len(item["text"]) for item in items) > arguments.max_chars:
            raise WordRenderUnavailable("Increase max_chars to receive the requested rendered-page metadata.")
        if sum(map(len, images.values())) > MAX_RENDER_BYTES:
            raise WordRenderUnavailable("Render fewer pages per call; the combined PNG output exceeds two MiB.")
        # A single bounded group; fresh rendering invalidates prior pixels.
        self.clear()
        self.images[snapshot] = (arguments.session, binding["identity"], images)
        workflow = self.live.word.workflow(binding)
        workflow.page_count = layout["page_count"]
        workflow.rendered.update(images)
        self.revisions = {snapshot: fingerprint}
        return {"session": arguments.session, "application": "word", "snapshot": snapshot,
                "items": items, "cursor": None}

    def chunk(self, data, binding):
        record = self.images.get(data.get("snapshot"))
        number, offset = data.get("page"), data.get("offset")
        if (record is None or record[:2] != (data.get("session"), binding["identity"])
                or type(number) is not int or number not in record[2] or type(offset) is not int
                or not 0 <= offset < len(record[2][number])):
            raise OfficeUnavailable("The rendered Word page is unavailable for this exact session.")
        workflow = self.live.word.workflow(binding)
        if self.revisions.get(data.get("snapshot")) != workflow.revision:
            raise OfficeUnavailable("The rendered Word page belongs to an old revision.")
        blob = record[2][number]
        part = blob[offset:offset + 24000]
        key = (data.get("snapshot"), number)
        prefix = self.transfers.get(key, 0)
        if offset <= prefix:
            prefix = max(prefix, offset + len(part))
            self.transfers[key] = prefix
        if prefix == len(blob):
            workflow.delivered.add(number)
        return {"data": base64.b64encode(part).decode("ascii"), "offset": offset,
                "next": offset + len(part), "total": len(blob)}
