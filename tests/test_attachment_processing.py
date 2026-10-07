import base64
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PySide6.QtGui import QImage, QColor
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.conversation.attachments import AttachmentStore
from app.conversation.attachment_processing import AttachmentProcessor
from app.inference.attachments import AttachmentError
from app.runtime.cancellation import CancellationSource, TaskCancelled


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def package(parts):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return output.getvalue()


def relations(items):
    return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
        f'<Relationship Id="{id}" Type="{R}/{kind}" Target="{target}" {mode}/>'
        for id, kind, target, mode in items) + "</Relationships>"


def make_pdf(*, text="PDF words", encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    if encrypted:
        writer.encrypt("test password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def prepare(tmp_path, data, name):
    store = AttachmentStore(tmp_path / "attachments")
    reference = store.import_bytes(data, name=name)
    processor = AttachmentProcessor(store)
    prepared = processor.prepare(reference)
    assert processor.load(reference) == prepared.processed
    return prepared


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
def test_text_encoding_content_and_lines_are_preserved(tmp_path, encoding):
    text = "# café 😀\r\nprint('exact')\n/skill python-coder\n"
    result = prepare(tmp_path, text.encode(encoding), "file.py")
    assert result.processed.text == text and result.processed.input_kind == "text"
    assert result.thumbnail is None


@pytest.mark.parametrize("name,data", [("sheet.csv", b'a,b\n"quoted,cell",2\n'),
                                      ("empty.txt", b""), ("Dockerfile", b"RUN echo test"),
                                      (".gitignore", b"state/**")])
def test_plain_files_remain_literal_user_data(tmp_path, name, data):
    assert prepare(tmp_path, data, name).processed.text == data.decode()


def test_docx_paragraphs_runs_tabs_and_table_text(tmp_path):
    document = f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Hello </w:t></w:r><w:r><w:t>world</w:t><w:tab/><w:t>end</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    result = prepare(tmp_path, package({"word/document.xml": document}), "file.docx")
    assert result.processed.text == "Hello world\tend\nCell"
    assert "text only" in result.processed.summary.lower()
    assert "embedded visuals" in result.processed.warnings[0]


def test_pptx_uses_presentation_order_and_includes_notes(tmp_path):
    slide = lambda text: f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>'
    data = package({
        "ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId r:id="second"/><p:sldId r:id="first"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": relations([("first", "slide", "slides/slide1.xml", ""), ("second", "slide", "slides/slide2.xml", "")]),
        "ppt/slides/slide1.xml": slide("One"), "ppt/slides/slide2.xml": slide("Two"),
        "ppt/slides/_rels/slide2.xml.rels": relations([("notes", "notesSlide", "../notesSlides/notesSlide2.xml", "")]),
        "ppt/notesSlides/notesSlide2.xml": f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>Speaker detail</a:t></a:r></a:p></p:notes>'})
    result = prepare(tmp_path, data, "slides.pptx")
    assert result.processed.text == "Slide 1\nTwo\nSpeaker notes\nSpeaker detail\nSlide 2\nOne"
    assert result.processed.units == 2


def test_xlsx_preserves_sheet_names_coordinates_values_and_formulas(tmp_path):
    data = package({
        "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="Budget" r:id="sheet"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": relations([("sheet", "worksheet", "worksheets/sheet1.xml", ""), ("strings", "sharedStrings", "sharedStrings.xml", "")]),
        "xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><t>Name</t></si></sst>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1" t="inlineStr"><is><t>Hello</t></is></c><c r="D1"><f>SUM(B2:B3)</f><v>5</v></c></row></sheetData></worksheet>'})
    result = prepare(tmp_path, data, "budget.xlsx")
    assert result.processed.text == "Sheet: Budget\nA1\tName\nC1\tHello\nD1\t=SUM(B2:B3) [stored value: 5]"
    assert "not recalculated" in result.processed.warnings[0]


def test_pdf_text_is_extracted_with_explicit_visual_limitations(tmp_path):
    result = prepare(tmp_path, make_pdf(), "file.pdf")
    assert "PDF words" in result.processed.text and "Page 1" in result.processed.text
    assert "text only" in result.processed.summary and "not read or OCRed" in result.processed.warnings[0]


def test_pdf_without_text_remains_available_for_later_visual_adapter(tmp_path):
    result = prepare(tmp_path, make_pdf(text=""), "scan.pdf")
    assert "no selectable text" in result.processed.warnings[1]
    assert result.reference.kind == "file"


def image_data(image_format="PNG"):
    from PySide6.QtCore import QBuffer, QIODevice
    image = QImage(180, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#778899"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, image_format)
    return bytes(buffer.data())


@pytest.mark.parametrize("suffix,format", [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP")])
def test_images_have_real_thumbnails_and_dimensions_without_text_claim(tmp_path, suffix, format):
    result = prepare(tmp_path, image_data(format), "image." + suffix)
    assert result.processed.width == 180 and result.processed.height == 120
    assert result.thumbnail.width() <= 96 and result.thumbnail.height() <= 96
    assert result.processed.input_kind == "visual" and result.processed.text == ""


def test_static_gif_is_supported(tmp_path):
    data = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")
    result = prepare(tmp_path, data, "still.gif")
    assert result.processed.width == 1


def test_animated_gif_is_not_silently_reduced_to_first_frame(tmp_path):
    still = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")
    start = still.index(b"\x2c")
    animated = still[:start] + still[start:-1] * 2 + b";"
    with pytest.raises(AttachmentError, match="Animated"):
        prepare(tmp_path, animated, "animated.gif")


@pytest.mark.parametrize("name,data", [("bad.pdf", b"broken PDF"), ("bad.docx", b"not a zip"),
    ("bad.py", b"\xff\xfe\x00"), ("binary.txt", b"abc\0def"), ("program.exe", b"MZ binary"),
    ("mismatch.jpg", image_data()), ("broken.png", b"\x89PNG\r\n"),
    ("secret.pdf", make_pdf(encrypted=True))])
def test_unreadable_unsupported_mismatched_and_encrypted_files_fail_without_cache(tmp_path, name, data):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(data, name=name)
    with pytest.raises(AttachmentError):
        AttachmentProcessor(store).prepare(ref)
    assert not (store.root / ref.id / "prepared_v1.json").exists()
    store.verify(ref)


def test_xml_entities_are_not_resolved_or_expanded(tmp_path):
    xml = f'<!DOCTYPE x [<!ENTITY content SYSTEM "file:///private">]><w:document xmlns:w="{W}"><w:p><w:t>&content;</w:t></w:p></w:document>'
    with pytest.raises(AttachmentError):
        prepare(tmp_path, package({"word/document.xml": xml}), "unsafe.docx")


def test_external_slide_reference_is_not_fetched(tmp_path):
    data = package({"ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldId r:id="remote"/></p:presentation>',
        "ppt/_rels/presentation.xml.rels": relations([("remote", "slide", "https://example.com/private", 'TargetMode="External"')])})
    with pytest.raises(AttachmentError):
        prepare(tmp_path, data, "remote.pptx")


def test_processing_bounds_fail_instead_of_silently_truncating(tmp_path, monkeypatch):
    import app.conversation.attachment_processing as processing
    monkeypatch.setattr(processing, "MAX_TEXT_CHARACTERS", 4)
    with pytest.raises(AttachmentError, match="too large"):
        prepare(tmp_path, b"12345", "large.txt")
    monkeypatch.setattr(processing, "MAX_PACKAGE_BYTES", 8)
    with pytest.raises(AttachmentError, match="unpacked"):
        prepare(tmp_path, package({"word/document.xml": "x" * 10}), "large.docx")


def test_cancelled_preparation_retains_original_without_partial_cache(tmp_path):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(b"file", name="file.txt")
    source = CancellationSource()
    source.cancel()
    with pytest.raises(TaskCancelled):
        AttachmentProcessor(store).prepare(ref, cancellation=source.token)
    assert not (store.root / ref.id / "prepared_v1.json").exists()
    store.verify(ref)


def test_cached_extraction_is_bound_to_snapshot_identity(tmp_path):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(b"file", name="file.txt")
    processor = AttachmentProcessor(store)
    processor.prepare(ref)
    path = store.root / ref.id / "prepared_v1.json"
    payload = json.loads(path.read_text())
    payload["sha256"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(AttachmentError, match="does not match"):
        processor.load(ref)


def test_missing_or_corrupt_prepared_cache_reports_a_content_free_error(tmp_path):
    store = AttachmentStore(tmp_path / "attachments")
    ref = store.import_bytes(b"private contents", name="file.txt")
    processor = AttachmentProcessor(store)
    with pytest.raises(AttachmentError, match="unavailable"):
        processor.load(ref)
    (store.root / ref.id / "prepared_v1.json").write_text("private contents, not JSON")
    with pytest.raises(AttachmentError) as error:
        processor.load(ref)
    assert "private contents" not in str(error.value)
    store.verify(ref)
