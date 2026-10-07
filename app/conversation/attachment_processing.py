"""Prepare user material without executing files, formulas, macros or instructions."""
from __future__ import annotations

from dataclasses import dataclass
import codecs
import posixpath
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from pydantic import BaseModel, ConfigDict, Field

from app.conversation.attachments import AttachmentStore
from app.inference.attachments import AttachmentError, AttachmentReference
from app.runtime.cancellation import CancellationToken, TaskCancelled
from app.state.storage import JsonStore


MAX_TEXT_CHARACTERS = 2_000_000
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
_TEXT_EXTENSIONS = frozenset("txt md rst log py pyw js jsx ts tsx json jsonl yaml yml toml ini cfg conf "
    "csv tsv html htm css scss less xml sql sh bat cmd ps1 c h cpp hpp cs java go rs rb php "
    "swift kt vue svelte r tex ipynb gitignore env".split())
_OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
SUPPORTED_FILE_FILTER = ("Images and documents (*.png *.jpg *.jpeg *.webp *.gif *.pdf *.docx *.pptx *.xlsx "
                         "*.txt *.md *.py *.csv *.tsv *.json *.js *.ts *.yaml *.yml);;All files (*)")
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class ProcessedAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1] = 1
    attachment_id: str
    sha256: str
    input_kind: Literal["text", "visual"]
    text: str = Field(default="", max_length=MAX_TEXT_CHARACTERS)
    summary: str
    warnings: tuple[str, ...] = ()
    units: int = Field(default=1, ge=0)
    readable_units: int | None = Field(default=None, ge=0)
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedAttachment:
    reference: AttachmentReference
    processed: ProcessedAttachment
    thumbnail: object = None  # QImage; converted to QPixmap only in the GUI thread.


def _bounded_text(parts, token):
    result, size = [], 0
    for part in parts:
        token.raise_if_cancelled()
        size += len(part) + 1
        if size > MAX_TEXT_CHARACTERS:
            raise AttachmentError("The extracted text is too large. Attach a smaller document or split it.")
        result.append(part)
    return "\n".join(result)


def _text_file(stream, token):
    prefix = stream.read(4)
    stream.seek(0)
    encoding = ("utf-32" if prefix.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)) else
                "utf-16" if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig")
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    parts, size = [], 0
    while data := stream.read(65536):
        token.raise_if_cancelled()
        part = decoder.decode(data)
        if "\x00" in part:
            raise AttachmentError("This file contains binary data rather than readable text.")
        size += len(part)
        if size > MAX_TEXT_CHARACTERS:
            raise AttachmentError("The text file is too large. Attach a smaller file or split it.")
        parts.append(part)
    tail = decoder.decode(b"", final=True)
    if size + len(tail) > MAX_TEXT_CHARACTERS:
        raise AttachmentError("The text file is too large. Attach a smaller file or split it.")
    return "".join(parts) + tail


class _OfficePackage:
    def __init__(self, stream, token):
        self.zip = ZipFile(stream)
        self.token = token
        items = self.zip.infolist()
        if len(items) > 10_000 or len({i.filename for i in items}) != len(items):
            raise AttachmentError("This document has too many or duplicate package entries.")
        if sum(i.file_size for i in items) > MAX_PACKAGE_BYTES or any(
                i.file_size > MAX_XML_BYTES or i.flag_bits & 1 for i in items):
            raise AttachmentError("This document exceeds the unpacked processing limit or is encrypted.")
        self.names = {i.filename for i in items}

    def xml(self, name):
        self.token.raise_if_cancelled()
        if name not in self.names:
            raise AttachmentError("The document is missing a required package component.")
        with self.zip.open(name) as source:
            data = source.read(MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES:
            raise AttachmentError("A document component exceeds the processing limit.")
        return fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)

    def relations(self, source):
        folder, base = posixpath.split(source)
        rel_name = posixpath.join(folder, "_rels", base + ".rels")
        if rel_name not in self.names:
            return {}
        result = {}
        for node in self.xml(rel_name):
            if node.get("TargetMode") == "External":
                continue
            target = node.get("Target", "")
            target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else
                                         posixpath.join(folder, target))
            if target.startswith("../") or "\\" in target or ":" in target:
                raise AttachmentError("The document contains an invalid internal reference.")
            result[node.get("Id")] = (target, node.get("Type", ""))
        return result

    def typed_xml(self, name, tag):
        root = self.xml(name)
        if root.tag != tag:
            raise AttachmentError("This document component has the wrong format.")
        return root


def _paragraphs(root, paragraph_suffix, text_suffix):
    for paragraph in root.iter():
        if paragraph.tag.endswith(paragraph_suffix):
            pieces = []
            for node in paragraph.iter():
                if node.tag.endswith(text_suffix):
                    pieces.append(node.text or "")
                elif node.tag.endswith("}tab"):
                    pieces.append("\t")
                elif node.tag.endswith(("}br", "}cr")):
                    pieces.append("\n")
            yield "".join(pieces)


def _office(stream, suffix, token):
    package = _OfficePackage(stream, token)
    try:
        if suffix == ".docx":
            text = _bounded_text(_paragraphs(package.typed_xml("word/document.xml", _W + "document"), "}p", "}t"), token)
            return text, 1, ("Text only; page layout, headers, comments and embedded visuals are not read.",)
        if suffix == ".pptx":
            source = "ppt/presentation.xml"
            root, relations = package.typed_xml(source, _P + "presentation"), package.relations(source)
            parts, count = [], 0
            for node in root.iter():
                if not node.tag.endswith("}sldId"):
                    continue
                target, _ = relations[node.get(_R + "id")]
                count += 1
                parts.append(f"Slide {count}")
                parts.extend(_paragraphs(package.typed_xml(target, _P + "sld"), "}p", "}t"))
                for notes, rel_type in package.relations(target).values():
                    if rel_type.endswith("/notesSlide"):
                        parts.append("Speaker notes")
                        parts.extend(_paragraphs(package.xml(notes), "}p", "}t"))
                # Check per slide as well as the final joined text.
                if sum(len(p) + 1 for p in parts) > MAX_TEXT_CHARACTERS:
                    raise AttachmentError("The presentation text is too large. Split the presentation.")
            return _bounded_text(parts, token), count, ("Text and speaker notes only; slide design and embedded visuals are not read.",)
        source = "xl/workbook.xml"
        root, relations = package.typed_xml(source, _S + "workbook"), package.relations(source)
        shared = []
        for target, rel_type in relations.values():
            if rel_type.endswith("/sharedStrings"):
                shared = ["".join(n.text or "" for n in node.iter() if n.tag.endswith("}t"))
                          for node in package.xml(target) if node.tag.endswith("}si")]
        parts, count = [], 0
        for sheet in root.iter():
            if not sheet.tag.endswith("}sheet"):
                continue
            token.raise_if_cancelled()
            target, _ = relations[sheet.get(_R + "id")]
            parts.append("Sheet: " + sheet.get("name", str(count + 1)))
            count += 1
            for cell in package.typed_xml(target, _S + "worksheet").iter():
                if not cell.tag.endswith("}c"):
                    continue
                token.raise_if_cancelled()
                value = next((n.text or "" for n in cell if n.tag.endswith("}v")), "")
                if cell.get("t") == "s":
                    index = int(value)
                    if index < 0 or index >= len(shared):
                        raise AttachmentError("A spreadsheet cell references a missing stored value.")
                    value = shared[index]
                elif cell.get("t") == "inlineStr":
                    value = "".join(n.text or "" for n in cell.iter() if n.tag.endswith("}t"))
                formula = next((n.text or "" for n in cell if n.tag.endswith("}f")), None)
                if formula is not None:
                    value = "=" + formula + " [stored value: " + (value or "unavailable") + "]"
                parts.append((cell.get("r") or "Cell") + "\t" + value)
            if sum(len(p) + 1 for p in parts) > MAX_TEXT_CHARACTERS:
                raise AttachmentError("The spreadsheet text is too large. Split the workbook.")
        return _bounded_text(parts, token), count, ("Stored cell values and formulas only; formulas are not recalculated. Formatting, charts and images are not read.",)
    finally:
        package.zip.close()


def _pdf(stream, token):
    from pypdf import PdfReader
    stream.seek(0, 2)
    if stream.tell() > 64 * 1024 * 1024:
        raise AttachmentError("This PDF exceeds the document-processing limit. Split the document.")
    stream.seek(0)
    reader = PdfReader(stream, strict=True)
    if reader.is_encrypted:
        raise AttachmentError("Password-protected PDFs are not supported. Attach an unlocked copy.")
    if len(reader.pages) > 2000:
        raise AttachmentError("This PDF has too many pages to process. Split the document.")
    parts, empty = [], 0
    for index, page in enumerate(reader.pages, 1):
        token.raise_if_cancelled()
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_XML_BYTES:
            raise AttachmentError("A PDF page exceeds the text-processing limit.")
        text = page.extract_text() or ""
        empty += not text.strip()
        parts.append(f"Page {index}\n{text}")
        if sum(len(p) + 1 for p in parts) > MAX_TEXT_CHARACTERS:
            raise AttachmentError("The PDF text is too large. Split the document.")
    warnings = ["Selectable text only; scanned text, charts and page visuals are not read or OCRed."]
    if empty:
        warnings.append(f"{empty} page(s) contain no selectable text and need visual reading.")
    return _bounded_text(parts, token), len(reader.pages), tuple(warnings), len(reader.pages) - empty


class AttachmentProcessor:
    def __init__(self, store: AttachmentStore):
        self.store = store

    def prepare(self, reference, *, cancellation=None) -> PreparedAttachment:
        token = cancellation or CancellationToken()
        suffix = Path(reference.name).suffix.lower()
        thumbnail, fields = None, {}
        reader = None
        try:
            with self.store.open(reference, cancellation=token) as stream:
                if reference.kind == "image":
                    from PySide6.QtCore import QSize, Qt
                    from PySide6.QtGui import QImageReader
                    reader = QImageReader(str(self.store.root / reference.id / "content"))
                    reader.setAutoTransform(True)
                    reader.setDecideFormatFromContent(True)
                    image_format = bytes(reader.format()).decode("ascii", errors="ignore")
                    expected = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp", ".gif": "gif"}
                    if image_format != expected.get(suffix):
                        raise AttachmentError("The image contents do not match its file type or are unreadable.")
                    if reader.imageCount() > 1:
                        raise AttachmentError("Animated images are not supported. Attach a still image.")
                    size = reader.size()
                    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > MAX_IMAGE_PIXELS:
                        raise AttachmentError("This image is invalid or too large to decode safely.")
                    reader.setScaledSize(size.scaled(QSize(96, 96), Qt.AspectRatioMode.KeepAspectRatio))
                    thumbnail = reader.read()
                    if thumbnail.isNull():
                        raise AttachmentError("This image could not be decoded.")
                    fields = dict(input_kind="visual", summary=f"Image · {size.width()} × {size.height()}",
                                  width=size.width(), height=size.height(), warnings=("Requires visual input support.",))
                elif suffix == ".pdf":
                    text, units, warnings, readable = _pdf(stream, token)
                    fields = dict(input_kind="text", text=text, units=units, readable_units=readable,
                                  warnings=warnings, summary=f"PDF · {units} pages · text only")
                elif suffix in _OFFICE_EXTENSIONS:
                    text, units, warnings = _office(stream, suffix, token)
                    fields = dict(input_kind="text", text=text, units=units, warnings=warnings,
                                  summary=suffix[1:].upper() + " · text only")
                elif suffix.lstrip(".") in _TEXT_EXTENSIONS or reference.name in {".gitignore", ".env", "Dockerfile", "Makefile"}:
                    text = _text_file(stream, token)
                    fields = dict(input_kind="text", text=text, summary=f"Text · {len(text):,} characters")
                else:
                    raise AttachmentError("Unsupported file type. Choose an image, text/code file, PDF, DOCX, PPTX, CSV or XLSX.")
                token.raise_if_cancelled()
                processed = ProcessedAttachment(attachment_id=reference.id, sha256=reference.sha256, **fields)
                JsonStore(self.store.root / reference.id / "prepared_v1.json").save(processed.model_dump(mode="json"))
                return PreparedAttachment(reference, processed, thumbnail)
        except (AttachmentError, TaskCancelled):
            raise
        except Exception as exc:
            # Parser errors can contain user text. Surface only a fixed, content-free message.
            raise AttachmentError("This attachment could not be processed. Check its format and encoding, then try again.") from exc
        finally:
            # Tracebacks retain this frame on decode failure. Drop the reader's
            # owned Windows file handle before the caller cleans up its draft.
            reader = None

    def load(self, reference, *, cancellation=None) -> ProcessedAttachment:
        token = cancellation or CancellationToken()
        try:
            with self.store.open(reference, cancellation=token):
                path = self.store.root / reference.id / "prepared_v1.json"
                from app.conversation.attachments import _snapshot_stream
                with _snapshot_stream(path, 32 * 1024 * 1024, token) as stream:
                    processed = ProcessedAttachment.model_validate_json(stream.read(32 * 1024 * 1024 + 1))
                token.raise_if_cancelled()
                if processed.attachment_id != reference.id or processed.sha256 != reference.sha256:
                    raise AttachmentError("The prepared document does not match its attachment.")
                return processed
        except AttachmentError:
            raise
        except (OSError, ValueError) as exc:
            raise AttachmentError("The prepared attachment is unavailable. Prepare the original file again.") from exc
