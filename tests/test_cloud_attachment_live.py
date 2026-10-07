"""Opt-in real cloud qualification; synthetic sources and content-free diagnostics."""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject

from app.agent.bootstrap import build_agent_runtime
from app.agent.runtime import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config
from tests.test_attachment_processing import make_pdf, package, W


pytestmark = pytest.mark.skipif(os.environ.get('ORSI_RUN_CLOUD_ATTACHMENT_LIVE') != '1',
    reason='Optional live cloud attachment qualification; requires explicit API credential authorization')


def image_bytes(color):
    image = QImage(160, 160, QImage.Format.Format_RGB32); image.fill(QColor(color))
    buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'PNG')
    return bytes(buffer.data())


def scanned_color_pdf():
    """Raster-only page: a local selectable-text parser cannot answer its color."""
    writer = PdfWriter(); page = writer.add_blank_page(width=160, height=160)
    bitmap = DecodedStreamObject(); bitmap.set_data(bytes([0, 255, 0]) * 160 * 160)
    bitmap.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
        NameObject('/Width'): NumberObject(160), NameObject('/Height'): NumberObject(160),
        NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im1'): writer._add_object(bitmap)})})
    contents = DecodedStreamObject(); contents.set_data(b'q 160 0 0 160 0 0 cm /Im1 Do Q')
    page[NameObject('/Contents')] = writer._add_object(contents)
    output = BytesIO(); writer.write(output); return output.getvalue()


def word_document():
    # A complete OOXML package, including its content types and root relation.
    # The parser-only unit fixture intentionally omits those and is not a DOCX
    # accepted by a native cloud document parser.
    return package({
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Word acceptance code: 164</w:t></w:r></w:p></w:body></w:document>',
    })


def test_native_cloud_sources_followups_restore_and_tool_continuation(tmp_path):
    key_path = os.environ.get('ORSI_CLOUD_ATTACHMENT_KEY_FILE')
    assert key_path, 'Set the authorized existing credential file path; do not put a key in test arguments.'
    with Path(key_path).open(encoding='utf-8-sig') as stream:
        key = stream.readline().strip()
    assert key, 'The authorized credential file is empty.'
    settings = load_cloud_config()
    engine = OpenAIResponsesInferenceEngine(settings, api_key=key)
    del key
    store = ConversationStore(tmp_path / 'chat.json')
    service = ConversationService(engine, store)
    summaries = []
    def record():
        completion = service.store.turns()[-1].outcome.completion
        summaries.append({'input_tokens': completion.usage.input_tokens,
                          'output_tokens': completion.usage.output_tokens,
                          'capability_calls': service.store.turns()[-1].outcome.capability_calls})
    try:
        sources = [(image_bytes('red'), 'image.png'),
            (make_pdf(text='PDF acceptance code: 731'), 'document.pdf'),
            (b'Text acceptance code: 842', 'note.txt'),
            (b'kind,code\nacceptance,953\n', 'table.csv'),
            (word_document(), 'office.docx'),
            (scanned_color_pdf(), 'scan.pdf')]
        refs = [store.attachment_store.import_bytes(data, name=name) for data, name in sources]
        answer = service.run('Report the dominant color in image.png, the acceptance codes from document.pdf, note.txt, table.csv and office.docx, and the dominant page color in scan.pdf. Use the supplied attachments. Keep the answer brief.', attachments=refs)
        assert all(value in answer.lower() for value in ['red', '731', '842', '953', '164', 'green']), 'Native source recognition failed.'
        record()
        blue = store.attachment_store.import_bytes(image_bytes('blue'), name='second.png')
        answer = service.run('State the colors of the first image and this new image in order, followed by the original PDF acceptance code. Keep it brief.', attachments=[blue])
        assert all(value in answer.lower() for value in ['red', 'blue', '731']), 'Cross-turn source recall failed.'
        record()
        service = ConversationService(engine, ConversationStore(store.path))
        answer = service.run('Recall the image colors in order and the original PDF acceptance code. Keep it brief.')
        assert all(value in answer.lower() for value in ['red', 'blue', '731']), 'Reopened source recall failed.'
        record()
        service.new_session(preserve_history=True)
        archive = next((tmp_path / 'archives').glob('*.json'))
        restored = ConversationStore(archive)
        portable = tmp_path / 'portable'; portable.mkdir()
        (portable / 'probe.txt').write_text('Synthetic stat target', encoding='utf-8')
        # Use the unchanged production catalog, sampling, limits and prompts;
        # fixture read roots prevent access to unrelated user files.
        # Scope the fixture to its own portable root while retaining the complete
        # enabled tool catalog and production runtime limits.
        flags = load_agent_feature_config().model_copy(update={'full_local_read_enabled': False})
        runtime = build_agent_runtime(engine, config=flags,
            portable_root=portable, state_directory=portable / 'state')
        service = ConversationService(engine, restored, agent_runtime=runtime, portable_root=portable,
            allowed_read_roots=(portable,))
        answer = service.run('Use filesystem.stat to check probe.txt in the portable root. After the tool succeeds, state the two attached image colors in order and the original PDF acceptance code. Keep it brief.')
        turn = restored.turns()[-1]
        assert turn.outcome.status == AgentRunStatus.COMPLETED, 'Native tool turn did not complete.'
        assert any(call.call.capability == 'filesystem.stat' and call.result.success for call in turn.settled_calls), 'Native stat did not execute.'
        assert all(value in answer.lower() for value in ['red', 'blue', '731']), 'Source recall after native tool continuation failed.'
        record()
        diagnostic = {'passed': True, 'source_count': len(refs) + 1,
            'production_catalog_size': len(runtime.registry.model_definitions()),
            'effective_context': engine.context_length, 'output_reserve': engine.max_response_tokens,
            'steps': summaries}
        (tmp_path / 'live-summary.json').write_text(json.dumps(diagnostic), encoding='utf-8')
        print(json.dumps(diagnostic))
    finally:
        engine.close()
        assert engine._runner is None and not engine.has_api_key
