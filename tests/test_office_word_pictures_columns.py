"""Focused section/picture contracts and native preservation qualification."""
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path

from PIL import Image
import jsonschema
import pytest

from app.mcp.office_contracts import OFFICE_TOOLS, WordComposeArguments
from app.mcp.office_word_assets import WordAssets, inspect_image, MAX_IMAGE_BYTES
from app.mcp.office_excel import OfficeConflict
from app.inference.completion import CompletionMetadata
from app.inference.openai_tools import _arguments, normalize_responses_calls, responses_function_tools


def image_bytes(format="PNG", color="#216074", size=(600, 300)):
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format=format)
    return stream.getvalue()


def section_plan(session="s", snapshot="r", assets=("first", "second")):
    def p(text, style="Normal"):
        return {"kind": "paragraph", "text": text, "style": style}
    def picture(asset, title):
        return {"kind": "image", "asset": asset, "width_mm": 70, "alt_text": title,
            "caption": "Figure: " + title, "credit": "Original synthetic test illustration"}
    return {"session": session, "snapshot": snapshot, "header": "ORSI native qualification",
        "footer": "Original synthetic test illustrations", "sections": [
        {"columns": 1, "start": "continuous", "column_spacing_mm": 8,
         "blocks": [p("Native illustrated report", "Title"), p("A full-width introduction.")]},
        {"columns": 2, "column_spacing_mm": 10, "start": "continuous", "blocks": [
            p("Flowing body", "Heading 1"), p("Editable two-column text. " * 50), picture(assets[0], "First diagram"),
            {"kind": "column_break"}, p("Second column", "Heading 2"), picture(assets[1], "Second diagram"),
            {"kind": "table", "cells": [["Metric", "Value"], ["Synthetic", "42"]], "widths_mm": [45, 30]},
            p("Native flow continues across pages. " * 80)]},
        {"columns": 1, "column_spacing_mm": 8, "start": "new_page", "blocks": [p("Full-width conclusion", "Heading 1"), p("Editable closing text.")]}]}


def test_sections_provider_projection_and_canonical_plan_are_lossless():
    contract = next(t for t in OFFICE_TOOLS if t.name == "office.word_compose")
    value = section_plan()
    original = deepcopy(value)
    schema = contract.definition().input_schema
    jsonschema.validate(value, schema)
    wire = _arguments(schema, value, schema, from_wire=False)
    tool = responses_function_tools((contract.definition(),))[0]
    jsonschema.validate(wire, tool["parameters"])
    response = normalize_responses_calls([{"call_id": "sections", "name": tool["name"],
        "arguments": json.dumps(wire)}], (contract.definition(),), CompletionMetadata())
    assert response.protocol_failure is None
    plan = WordComposeArguments.model_validate(response.capability_calls[0].arguments)
    assert plan == WordComposeArguments.model_validate(value)
    assert value == original
    assert [b.kind for b in plan.blocks].count("section_break") == 2
    assert WordComposeArguments.model_validate(plan.model_dump()) == plan


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(blocks=[{"text": "competing"}]),
    lambda v: v.update(pages=[{"blocks": [{"text": "competing"}]}]),
    lambda v: v.update(layout={"columns": 2}),
    lambda v: v["sections"][0].update(start="new_page"),
    lambda v: v["sections"][1].update(blocks=[{"kind": "column_break"}]),
    lambda v: v["sections"][1].update(blocks=[{"kind": "table", "cells": [["a"]], "widths_mm": [81]}]),
    lambda v: v["sections"][1].update(blocks=[{"kind": "image", "asset": "a", "alt_text": "diagram", "width_mm": 81}]),
    lambda v: v["sections"][0].update(blocks=[{"kind": "column_break"}, {"text": "body"}]),
    lambda v: v["sections"][1].update(blocks=[{"kind": "image", "asset": "a", "alt_text": "", "width_mm": 20}]),
    lambda v: v["sections"][1].update(blocks=[{"kind": "image", "asset": "a", "alt_text": " ", "width_mm": 20}]),
])
def test_sections_refuse_competing_empty_and_out_of_column_plans(mutation):
    value = section_plan()
    mutation(value)
    with pytest.raises(ValueError):
        WordComposeArguments.model_validate(value)


def test_pages_blocks_and_single_section_share_one_canonical_plan():
    body = [{"kind": "paragraph", "text": "Editable"}]
    plans = [WordComposeArguments.model_validate({"session": "s", "snapshot": "r", **shape})
        for shape in ({"blocks": body}, {"pages": [{"blocks": body}]}, {"sections": [{"blocks": body}]})]
    assert plans[0] == plans[1] == plans[2]


def test_asset_registration_is_immutable_bounded_and_session_scoped():
    assets = WordAssets()
    data = image_bytes()
    metadata = assets.chunk("s", "first", 0, base64.b64encode(data).decode(), True)
    assert metadata["bytes"] == len(data) and metadata["width_px"] == 600
    with pytest.raises(OfficeConflict, match="immutable"):
        assets.chunk("s", "first", 0, base64.b64encode(image_bytes(color="red")).decode(), True)
    plan = WordComposeArguments.model_validate({"session": "s", "snapshot": "r", "sections": [
        {"blocks": [{"kind": "image", "asset": "first", "width_mm": 70, "alt_text": "Original diagram"}]}]})
    assert assets.resolve(plan)["first"][0] == data
    with pytest.raises(OfficeConflict, match="session"):
        assets.resolve(plan.model_copy(update={"session": "other"}))
    for data in (b"x" * (MAX_IMAGE_BYTES + 1), image_bytes(size=(2049, 1)), image_bytes("GIF")):
        with pytest.raises(OfficeConflict):
            inspect_image(data)


def test_new_diagnostics_persist_only_bounded_structure():
    from app.inference.word_plan_diagnostics import word_plan_shape, safe_word_event
    value = section_plan()
    shape = word_plan_shape(value)
    assert shape["sections"] == 3 and shape["images"] == 2 and shape["column_breaks"] == 1
    event = safe_word_event({"stage": "approval_plan", "shape": {**shape, "path": "secret", "bytes": "secret"}})
    text = json.dumps(event)
    assert "secret" not in text and "diagram" not in text and "Original" not in text
    assert event["shape"]["section_columns"][1] == {"columns": 2, "spacing_mm": 10}


def picture_package(data=None):
    from xml.etree.ElementTree import Element, SubElement, tostring
    from app.mcp.office_word_native import PKG, W
    from app.mcp.office_word_assets import REL, R
    from app.mcp.office_word_document import picture_xml
    from app.mcp.office_contracts import WordImage
    data = data or image_bytes()
    root = Element(PKG + 'package')
    def part(name):
        return SubElement(root, PKG + 'part', {PKG + 'name': name})
    body = SubElement(SubElement(SubElement(part('/word/document.xml'), PKG + 'xmlData'), W + 'document'), W + 'body')
    picture_xml(body, WordImage(kind='image',asset='opaque',width_mm=70,alt_text='Original test'), inspect_image(data), 'image1', 1)
    rels = SubElement(SubElement(part('/word/_rels/document.xml.rels'), PKG + 'xmlData'), REL + 'Relationships')
    SubElement(rels, REL + 'Relationship', {'Id': 'image1', 'Target': 'media/picture.png', 'Type': R[1:-1] + '/image'})
    binary_part = part('/word/media/picture.png')
    binary_part.set(PKG + 'contentType','image/png')
    SubElement(binary_part, PKG + 'binaryData').text = base64.b64encode(data).decode()
    return root


def test_supported_package_identity_binds_bytes_alt_and_geometry_not_relationship_numbers():
    from xml.etree.ElementTree import tostring
    from app.mcp.office_word_document import signature
    from app.mcp.office_word_assets import validate_package
    value = picture_package()
    assert len(validate_package(value)) == 1
    xml = tostring(value, encoding='unicode')
    assert signature(xml) == signature(xml.replace('image1','renumbered').replace('picture.png','renamed.png'))
    assert signature(xml) != signature(tostring(picture_package(image_bytes(color='red')), encoding='unicode'))
    assert signature(xml) != signature(xml.replace('Original test','Changed alt'))
    assert signature(xml) != signature(xml.replace('2520000','2160000'))


def test_only_dormant_default_grid_pitch_is_bookkeeping():
    from types import SimpleNamespace
    from xml.etree.ElementTree import SubElement, tostring
    from app.mcp.office_word_document import signature
    from app.mcp.office_word_native import W
    root = picture_package()
    grid = SubElement(SubElement(root.find('.//' + W + 'body'), W + 'sectPr'), W + 'docGrid', {W+'linePitch':'360'})
    original = tostring(root,encoding='unicode')
    assert signature(original) == signature(original.replace('360','326'))
    grid.set(W+'type','lines')
    active = tostring(root,encoding='unicode')
    assert signature(active) != signature(active.replace('360','326'))
    from app.mcp.office_word_document import capture_document
    backend = SimpleNamespace(check_thread=lambda:None,word_writable=lambda _:None,word_xml_safe=lambda _:None)
    document = SimpleNamespace(Content=SimpleNamespace(End=1,WordOpenXML=active),
        Sections=SimpleNamespace(Count=1),Tables=SimpleNamespace(Count=0))
    with pytest.raises(OfficeConflict,match='Active document grids'):
        capture_document(backend,document)
    grid.set(W+'type','default')
    default = tostring(root,encoding='unicode')
    assert signature(default) == signature(default.replace('360','326'))


@pytest.mark.parametrize('kind', ['floating','linked','crop','unknown_extension','external'])
def test_unsupported_picture_dependencies_are_refused_before_writing(kind):
    from xml.etree.ElementTree import SubElement
    from app.mcp.office_word_assets import validate_package, WP, A, R, REL
    value = picture_package()
    if kind == 'floating':
        value.find('.//' + WP + 'inline').tag = WP + 'anchor'
    elif kind == 'linked':
        value.find('.//' + A + 'blip').set(R + 'link','untrusted')
    elif kind == 'crop':
        SubElement(value.find('.//' + A + 'blip'), A + 'srcRect')
    elif kind == 'unknown_extension':
        SubElement(value.find('.//' + A + 'blip'), A + 'extLst').append(__import__('xml.etree.ElementTree', fromlist=['Element']).Element(A+'ext', {'uri':'unknown'}))
    else:
        value.find('.//' + REL + 'Relationship').set('TargetMode','External')
    with pytest.raises(OfficeConflict):
        validate_package(value)


def test_registration_access_policy_and_conversation_scope(tmp_path):
    from types import SimpleNamespace
    from app.mcp.office_connection import OfficeConnection
    from app.mcp.office_contracts import WordImageRegisterArguments
    from app.security.host_access import HostAccessPolicy
    from app.runtime.cancellation import CancellationToken
    from app.capabilities.contracts import CapabilityExecutionError
    from tests.test_office_mcp_connection import ROOT
    bridge = OfficeConnection(ROOT, backend=lambda:'cloud')
    contract = next(t for t in OFFICE_TOOLS if t.name == 'office.image_register')
    bridge._selected = ('document','identity')
    bridge.control = lambda *args: {'document': {'document':'document','application':'word'}, 'identity':'identity'}
    context = SimpleNamespace(host_access_policy=HostAccessPolicy.portable_root(tmp_path),
        session_id='conversation', cancellation=CancellationToken())
    source = tmp_path/'original.png'
    source.write_bytes(image_bytes())
    args = WordImageRegisterArguments(session='word',path=str(source))
    assert bridge.resource_policy(contract,args,context).resource == source
    with pytest.raises(CapabilityExecutionError):
        bridge.resource_policy(contract,args.model_copy(update={'path':str(ROOT/'pyproject.toml')}),context)
    bridge.bind_picture_sources('another-conversation',None,())
    with pytest.raises(CapabilityExecutionError):
        bridge.picture_source('attachment:att-'+'0'*32,'conversation')


def test_asset_count_chunk_order_and_total_media_bounds():
    assets = WordAssets()
    data = base64.b64encode(image_bytes()).decode()
    with pytest.raises(OfficeConflict, match='sequence'):
        assets.chunk('s','first',1,data,True)
    for number in range(8):
        assets.chunk('s','asset'+str(number),0,data,True)
    with pytest.raises(OfficeConflict, match='eight'):
        assets.chunk('s','ninth',0,data,True)
    assets = WordAssets()
    assets.pending = {'other': ('s',b'x'*(1024*1024))}
    with pytest.raises(OfficeConflict, match='media'):
        assets.chunk('s','first',0,data,True)


def test_repeated_picture_placements_count_toward_total_media_before_compilation():
    from random import Random
    stream = BytesIO()
    Image.frombytes('RGB', (300, 220), Random(0).randbytes(300 * 220 * 3)).save(stream, format='PNG')
    data = stream.getvalue()
    assert 1024 * 1024 / 6 < len(data) < MAX_IMAGE_BYTES
    assets = WordAssets()
    for offset in range(0, len(data), 24000):
        assets.chunk('s', 'first', offset, base64.b64encode(data[offset:offset+24000]).decode(),
            offset + 24000 >= len(data))
    picture = {'kind':'image','asset':'first','width_mm':70,'alt_text':'Repeated original diagram'}
    def plan(count):
        return WordComposeArguments.model_validate({'session':'s','snapshot':'r','blocks':[picture] * count})
    assert assets.resolve(plan(4))['first'][0] == data
    with pytest.raises(OfficeConflict, match='one-MiB'):
        assets.resolve(plan(6))


def test_render_deadline_is_bounded_without_changing_ordinary_reads_or_explicit_overrides():
    from app.mcp.office_connection import OfficeConnection
    from app.mcp.office_contracts import ReadArguments
    from tests.test_office_mcp_connection import ROOT
    read = next(t for t in OFFICE_TOOLS if t.name == 'office.read')
    bridge = OfficeConnection(ROOT, backend=lambda:'cloud')
    assert bridge.tool_timeout(read,ReadArguments(session='s',target='authoring')) == 10
    assert bridge.tool_timeout(read,ReadArguments(session='s',target='render:1:3')) == 30
    bridge.close()
    bridge = OfficeConnection(ROOT, backend=lambda:'cloud',call_timeout=.2)
    assert bridge.tool_timeout(read,ReadArguments(session='s',target='render:1:3')) == .2
    bridge.close()


def test_one_column_layout_does_not_publish_word_undefined_spacing():
    from types import SimpleNamespace
    from app.mcp.office_word_render import layout_view
    setup = SimpleNamespace(PageWidth=595,PageHeight=842,
        TextColumns=SimpleNamespace(Count=1,Spacing=9999999))
    document = SimpleNamespace(Repaginate=lambda:None,Range=lambda *args:SimpleNamespace(Information=lambda _:1),
        Sections=SimpleNamespace(Count=1,Item=lambda _:SimpleNamespace(PageSetup=setup)),
        Tables=SimpleNamespace(Count=0),InlineShapes=SimpleNamespace(Count=0))
    assert layout_view(document)['sections'] == [{'columns':1,'column_spacing_mm':0}]


def test_paged_paragraph_reads_bound_capture_and_refuse_foreign_changes():
    from types import SimpleNamespace
    from app.mcp.office_word import WordEdits
    from app.mcp.office_contracts import ReadArguments
    document = SimpleNamespace(revision='first')
    captures = []
    class Backend:
        def word_read_guard(self, doc):
            return doc.revision
        def word_read_anchor_valid(self, descriptor):
            return True
        def plan(self, kind, doc, target):
            return [('word',doc,i,i+1) for i in range(12)]
        def capture_word(self, descriptor):
            captures.append(descriptor[2])
            return {'start':descriptor[2],'end':descriptor[3],'text':'native'}
        def piece(self, descriptor, offset, count):
            return {'label':'Native paragraph','text':'native'}, None
    edits = WordEdits(SimpleNamespace(backend=Backend(),documents={'document':('word',document)}))
    binding = {'identity':'identity','document':{'document':'document','application':'word'}}
    first = edits.read(ReadArguments(session='s',target='document',max_chars=8192),binding)
    assert len(first['items']) == 4 and captures == [0,1,2,3] and first['cursor']
    second = edits.read(ReadArguments(session='s',target='document',cursor=first['cursor'],max_chars=8192),binding)
    assert len(second['items']) == 4 and captures == list(range(8)) and second['cursor']
    document.revision = 'foreign'
    with pytest.raises(OfficeConflict,match='changed'):
        edits.read(ReadArguments(session='s',target='document',cursor=second['cursor']),binding)
    assert captures == list(range(8))


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in isolated real Word gate")
def test_native_pictures_sections_capture_restore_and_reopen(tmp_path):
    import gc
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    from app.mcp.office_com import WindowsOffice
    from app.mcp.office_word_document import capture_document, compile_packet, write_document, verify_document, restore_document, same_document
    from app.mcp.office_word_render import render_document_pages
    pythoncom.CoInitializeEx(2)
    application = document = backend = owned = None
    failure = None
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = True
        application.DisplayAlerts = 0
        document = application.Documents.Add()
        owned = psutil.Process(win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1])
        path = tmp_path / "native-illustrated.docx"
        document.SaveAs2(str(path), 12)
        backend = WindowsOffice()
        existing_path = tmp_path / 'preexisting.png'
        existing_path.write_bytes(image_bytes())
        existing = document.InlineShapes.AddPicture(str(existing_path), False, True, document.Range(0, 0))
        existing.AlternativeText = 'Existing original test picture'
        existing.Width = 70 * 72 / 25.4
        existing = None
        document.PageSetup.TextColumns.SetCount(2)
        document.PageSetup.TextColumns.Spacing = 8 * 72 / 25.4
        document.Sections.Item(1).Headers.Item(1).Range.Text = 'Existing running identification'
        end = int(document.Content.End) - 1
        document.Range(end, end).InsertBreak(3)  # Native continuous section.
        document.Sections.Item(2).PageSetup.TextColumns.SetCount(1)
        assert bool(document.Sections.Item(2).Headers.Item(1).LinkToPrevious)
        document.Save()
        before = capture_document(backend, document)
        assert [s['columns'] for s in before['view']['sections']] == [2, 1]
        media = {"first": (image_bytes(), inspect_image(image_bytes())),
            "second": (image_bytes("JPEG", "#C4663C"), inspect_image(image_bytes("JPEG", "#C4663C")))}
        plan = WordComposeArguments.model_validate(section_plan())
        packet = compile_packet(document, plan, before, media)
        write_document(backend, document, packet, plan)
        verify_document(document, plan, {k: sha256(v[0]).hexdigest() for k, v in media.items()})
        captured = capture_document(backend, document)
        assert len(captured["view"]["sections"]) == 3 and len(captured["view"]["pictures"]) == 2
        shorter = WordComposeArguments.model_validate({"session": "s", "snapshot": "r", "blocks": [{"text": "Short owned replacement"}]})
        write_document(backend, document, compile_packet(document, shorter, captured), shorter)
        verify_document(document, shorter)
        restore_document(backend, document, captured)
        assert same_document(capture_document(backend, document), captured)
        restore_document(backend, document, before)
        assert same_document(capture_document(backend, document), before)
        restore_document(backend, document, captured)
        assert same_document(capture_document(backend, document), captured)
        document.Save()
        document.Close(False)
        document = application.Documents.Open(str(path))
        verify_document(document, plan)
        assert same_document(capture_document(backend, document), captured)
        count = int(document.Range(0, 0).Information(4))
        assert count >= 3
        for start in range(1, count + 1, 3):
            for number, pixels, _, text in render_document_pages(document, start, min(start + 2, count)):
                assert plan.header in " ".join(text.split())
                (tmp_path / f"page-{number}.png").write_bytes(pixels)
    except Exception as error:
        trace, lines = error.__traceback__, []
        while trace:
            if Path(trace.tb_frame.f_code.co_filename).name in {"office_word_document.py", "office_word_assets.py", "test_office_word_pictures_columns.py"}:
                lines.append(trace.tb_lineno)
            trace = trace.tb_next
        failure = (type(error).__name__, lines)
        print("native_section_boundaries", [(i, int(document.Sections.Item(i).Range.Start), int(document.Sections.Item(i).Range.End))
            for i in range(1, int(document.Sections.Count) + 1)])
        print("paragraph_boundaries", [(len(str(document.Paragraphs.Item(i).Range.Text)),
            [ord(c) for c in str(document.Paragraphs.Item(i).Range.Text)[-2:] if ord(c) < 32 or ord(c) == 65532])
            for i in range(1, int(document.Paragraphs.Count) + 1) if not bool(document.Paragraphs.Item(i).Range.Information(12))])
        if 'captured' in locals():
            from app.mcp.office_word_document import package_state, signature
            from unittest.mock import patch
            states = []
            def observe(root):
                state = package_state(root)
                states.append(dict(state))
                return state
            with patch('app.mcp.office_word_document.package_state', side_effect=observe):
                signature(captured['xml'])
                signature(capture_document(backend, document)['xml'])
            left, right = states[0], states[-1]
            def category(name):
                return next((v for v in ('document', 'header', 'footer', 'styles', 'settings', 'media') if v in name), 'other')
            print('different_package_categories', [category(k) for k in left.keys() | right.keys() if left.get(k) != right.get(k)])
            def differences(a, b, trail=()):
                if a == b:
                    return []
                if isinstance(a, list) and isinstance(b, list):
                    if len(a) != len(b):
                        return [(trail, 'length', len(a), len(b))]
                    return [v for i, (x, y) in enumerate(zip(a,b)) for v in differences(x,y,trail+(i,))][:12]
                if isinstance(a, dict) and isinstance(b, dict):
                    return [(trail, 'attribute', k.rsplit('}',1)[-1], (a.get(k), b.get(k)) if k.rsplit('}',1)[-1] == 'linePitch' else None) for k in a.keys()|b.keys() if a.get(k)!=b.get(k)][:12]
                return [(trail, 'scalar', type(a).__name__, type(b).__name__)]
            print('semantic_differences', [(category(k),differences(left.get(k),right.get(k))) for k in left.keys() & right.keys() if left[k]!=right[k]])
            for kind in ('header','footer'):
                old = [v for k,v in left.items() if k.startswith(kind+':')]
                new = [v for k,v in right.items() if k.startswith(kind+':')]
                if old and new:
                    print(kind+'_content_differences', [differences(a,b) for a in old for b in new][:8])
    finally:
        if document is not None:
            document.Close(False)
        document = None
        gc.collect()
        if application is not None:
            application.Quit(False)
        application = None
        gc.collect()
        if owned is not None:
            owned.wait(10)
        if backend is not None:
            backend.close()
        backend = None
        pythoncom.CoUninitialize()
    assert failure is None, failure


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Opt-in isolated production Word bridge gate")
def test_native_bridge_assets_approval_substitution_noop_and_foreign_recovery(tmp_path):
    import gc
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    from uuid import uuid4
    from zipfile import ZipFile
    from app.mcp.office_connection import OfficeConnection
    from app.security.write_policy import HostWritePolicy
    from app.conversation.attachments import AttachmentStore
    from app.capabilities.contracts import CapabilityExecutionError
    from tests.test_office_mcp_capabilities import runtime_for, prepare, authorize
    from tests.test_office_mcp_connection import ROOT
    from tests.test_office_mcp_live import execute
    pythoncom.CoInitializeEx(2)
    application = document = owned = None
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20)
    runtime = runtime_for(bridge, tmp_path / "runtime", policy=bridge.resource_policy)
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = True
        application.DisplayAlerts = 0
        document = application.Documents.Add()
        document.SaveAs2(str(tmp_path / ("bridge-" + uuid4().hex + ".docx")), 12)
        owned = psutil.Process(win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1])
        bridge.connect()
        selected = next(d for d in bridge.list_documents() if d["application"] == "word" and d["title"] == str(document.Name))
        bridge.select_document(selected["document"])
        session = execute(runtime, "attach", {"application": "word", "document": selected["document"]}, "attach").output["session"]
        (tmp_path / "application").mkdir()
        for name in ("office.word_compose", "office.word_edit", "office.save", "office.revert"):
            runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "application")
        source = tmp_path / "source.png"
        original = image_bytes()
        source.write_bytes(original)
        registered = execute(runtime, "image_register", {"session": session, "path": str(source)}, "register-local")
        assert registered.success, registered.error
        store = AttachmentStore(tmp_path / "attachments")
        reference = store.import_bytes(image_bytes("JPEG", "#C4663C"), name="original.jpg")
        bridge.bind_picture_sources("session1", store, (reference,))
        discovery = execute(runtime, "read", {"session": session, "target": "assets"}, "discover-assets")
        assert discovery.success and len(discovery.output["items"]) == 1
        second = execute(runtime, "image_register", {"session": session, "path": "attachment:" + reference.id}, "register-attachment")
        assert second.success, second.error
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.image_register", {"session": session, "path": "attachment:att-" + "0" * 32}, "unknown-attachment")
        def read():
            result = execute(runtime, "read", {"session": session, "target": "authoring", "max_chars": 8192}, "read-" + uuid4().hex)
            assert result.success, result.error
            value = result.output
            while value["cursor"]:
                result = execute(runtime, "read", {"session": session, "target": "authoring", "cursor": value["cursor"], "max_chars": 8192}, "cursor-" + uuid4().hex)
                assert result.success, result.error
                value = result.output
            return value
        args = section_plan(session, read()["snapshot"], (registered.output["asset"], second.output["asset"]))
        prepared = prepare(runtime, "office.word_compose", args, "compose")
        authorization = authorize(runtime, prepared)
        source.write_bytes(image_bytes(color="red"))
        applied = runtime.executor.execute(prepared, authorization)
        assert applied.success and applied.output["outcome"] == "applied", applied.error
        assert int(document.InlineShapes.Count) == 2 and int(document.Sections.Count) == 3
        # Ordinary paragraph reads must stay usable after native pictures and
        # sections, without eagerly exporting every paragraph's dependencies.
        body = execute(runtime, "read", {"session": session, "target": "document"}, "body-read")
        assert body.success, body.error
        while body.output["cursor"]:
            body = execute(runtime, "read", {"session": session, "target": "document", "cursor": body.output["cursor"]}, "body-cursor-"+uuid4().hex)
            assert body.success, body.error
        same_args = section_plan(session, read()["snapshot"], (registered.output["asset"], second.output["asset"]))
        # Current workflow requires inspected defects before another composition.
        # Keep the native gate aligned with that existing authority contract.
        with pytest.raises(CapabilityExecutionError, match="page inspection"):
            execute(runtime, "word_compose", same_args, "identical-compose")
        page_count = int(document.Range(0,0).Information(4))
        for first_page in range(1,page_count+1,3):
            rendered = execute(runtime, "read", {"session":session,
                "target":f"render:{first_page}:{min(first_page+2,page_count)}"}, "inspect-"+str(first_page))
            assert rendered.success, rendered.error
            bridge.render_images(rendered.output)
        review = execute(runtime, "word_review", {"session":session,
            "revision":rendered.output["word_workflow"]["revision"],
            "findings":[{"location":"document body", "defect":"The recovery fixture still contains the long report",
                "requirement":"Replace the fixture with one paragraph before testing owned restoration"}],
            "requirements_checked":["Disposable recovery fixture body"], "requirements_met":False}, "review-shorter")
        assert review.success, review.error
        shorter = execute(runtime, "word_compose", {"session": session, "snapshot": read()["snapshot"],
            "blocks": [{"text": "Owned short replacement"}]}, "shorter")
        if not shorter.success:
            print('shorter_native_diagnostic', json.dumps(bridge.diagnostics))
        assert shorter.success, (shorter.error, bridge.diagnostics)
        restored = execute(runtime, "revert", {"session": session, "snapshot": read()["snapshot"],
            "recovery": shorter.output["recovery"]}, "restore")
        assert restored.success, restored.error
        document.Paragraphs.Item(1).Range.InsertBefore("Foreign change ")
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.revert", {"session": session, "snapshot": read()["snapshot"],
                "recovery": applied.output["recovery"]}, "foreign-refusal")
        destination = tmp_path / "bridge-qualified.docx"
        saved = execute(runtime, "save", {"session": session, "path": str(destination)}, "save")
        assert saved.success, saved.error
        with ZipFile(destination) as package:
            assert original in [package.read(n) for n in package.namelist() if n.startswith("word/media/")]
    finally:
        runtime.shutdown()
        if document is not None:
            document.Close(False)
        document = None
        gc.collect()
        if application is not None:
            application.Quit(False)
        application = None
        gc.collect()
        if owned is not None:
            owned.wait(10)
        pythoncom.CoUninitialize()
    assert not bridge.diagnostics["worker_alive"]
