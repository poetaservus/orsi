"""Authoring bounds, complete native report structure and rendered evidence."""
import base64
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from app.agent.office_images import word_image_message
from app.mcp.office_capabilities import OfficeCapability
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_contracts import OFFICE_TOOLS, WordComposeArguments
from app.mcp.office_word_document import signature


def report_plan(session="session", snapshot="snapshot"):
    def p(text, style="Normal", **format):
        value = {"kind": "paragraph", "text": text, "style": style}
        if format:
            value["format"] = format
        return value
    return {"session": session, "snapshot": snapshot,
        "header": "WAREHOUSE OPERATIONS  |  MONTHLY PERFORMANCE REVIEW",
        "footer": "Synthetic operational data — illustrative only",
        "format": {"font": "Calibri", "size": 10.5, "color": "#243449", "space_after": 7, "line_multiple": 1.12},
        "blocks": [
            p("Warehouse Operations — Monthly Performance Review", "Title", size=24, color="#17324D"),
            p("Management report | Synthetic operational data", "Subtitle"),
            p("Executive summary", "Heading 1"),
            p("Outbound throughput increased by 7.7% while picking productivity improved by 4.8%. "
              "Service performance nevertheless remained below the illustrative 98.0% on-time target. "
              "A concentrated late-shift dispatch queue and uneven inbound arrivals drove most exceptions. "
              "Management should protect dispatch capacity before adding further picking volume."),
            p("Monthly KPI comparison", "Heading 1"),
            {"kind": "table", "cells": [
                ["KPI", "Prior month", "Current month", "Target"],
                ["Inbound pallets", "12,000", "13,200", "Plan 13,000"],
                ["Outbound orders", "39,000", "42,000", "Plan 42,500"],
                ["Fulfillment accuracy", "99.3%", "99.5%", "99.7%"],
                ["Picking productivity", "104 lines/h", "109 lines/h", "112 lines/h"],
                ["On-time shipments", "96.1%", "96.8%", "98.0%"],
                ["Closing backlog", "1,250 orders", "1,480 orders", "≤1,000 orders"]],
             "widths_mm": [64, 35, 36, 35], "format": {"size": 9.5, "space_after": 4},
             "header_fill": "#E8EEF4", "border_color": "#CAD5E1"},
            p("Basis and interpretation", "Heading 2"),
            p("All values, targets and comparisons are synthetic. Productivity means picked order lines per paid picking hour. "
              "On-time shipment means carrier handover by the agreed dispatch cutoff. Backlog is the open order count at month end. "
              "Inbound pallets and outbound orders use different units and should not be compared as a direct balance."),
            {"kind": "page_break"},
            p("Monthly performance analysis", "Heading 1"),
            p("Volume and capacity", "Heading 2"),
            p("Inbound receipts rose by 10.0% and exceeded the synthetic receiving plan by 1.5%. "
              "The largest arrival peaks occurred before midday, increasing staging occupancy and delaying put-away. "
              "Outbound orders rose by 3,000, but dispatch processing did not expand at the same pace. "
              "The evidence points to timing and workload balance as the immediate constraint rather than a general lack of picking capacity."),
            p("Quality and shipment reliability", "Heading 2"),
            p("Accuracy improved by 0.2 percentage points to 99.5%, leaving a 0.2-point gap to target. "
              "Picking productivity improved by five lines per hour. On-time shipment rose by 0.7 points, "
              "but remained 1.2 points below target. Additional picks alone will not close the service gap if packing and carrier handover remain congested."),
            p("Backlog and bottlenecks", "Heading 2"),
            p("Closing backlog grew by 230 orders, or 18.4%. The synthetic operating pattern combines concentrated receipts, "
              "replenishment interruptions and late packing queues. Review backlog age as well as total count: older orders may require "
              "a separate recovery lane even when daily throughput is improving."),
            p("Three operational risks", "Heading 1"),
            p("1. Dispatch congestion", "Heading 2"),
            p("Risk: a late packing queue misses carrier cutoffs. Action: assign a shift lead to review cutoff readiness every two hours "
              "and reserve cross-trained packing support before the final dispatch wave."),
            p("2. Quality drift under volume pressure", "Heading 2"),
            p("Risk: rushed substitutions or scanning exceptions reduce fulfillment accuracy. Action: review exception codes daily, "
              "check the highest-error locations and keep quality checks active during peak waves."),
            p("3. Ageing backlog", "Heading 2"),
            p("Risk: older open orders accumulate behind newer work. Action: introduce an age-based priority lane, "
              "assign clear ownership for blocked orders and escalate orders missing a promised recovery date."),
            {"kind": "page_break"},
            p("Actionable management recommendations", "Heading 1"),
            p("Stabilize dispatch before adding volume", "Heading 2"),
            p("Within the next operating week, map the hourly flow from picking release to carrier handover. "
              "The outbound manager should align wave release with packing capacity and maintain a visible cutoff board. "
              "Confirm progress through on-time shipment performance, queue length and overtime hours rather than picking output alone."),
            p("Smooth inbound appointments", "Heading 2"),
            p("The inbound manager should rebalance supplier appointment slots across the day and define a staging occupancy trigger. "
              "Where occupancy exceeds that trigger, pause discretionary receipts and prioritize put-away. "
              "Track receiving delay, replenishment interruptions and the share of receipts arriving within booked windows."),
            p("Close recurring quality exceptions", "Heading 2"),
            p("The inventory and quality leads should investigate the five most frequent scanning or location exceptions each week. "
              "Correct location labels, replenishment rules and training gaps at source. "
              "Maintain the 99.7% illustrative accuracy target and report the exception rate alongside total orders."),
            p("Run a controlled backlog recovery", "Heading 2"),
            p("Set a daily recovery allocation for aged orders and give each blocked order an owner. "
              "Do not reduce the backlog by simply excluding difficult orders from the measure. "
              "The operations manager should review total backlog, orders older than the service promise and the expected clearance date."),
            p("Management review cadence", "Heading 1"),
            p("Daily: dispatch readiness, aged orders and material exceptions. Weekly: arrival-slot balance, quality root causes "
              "and cross-training coverage. Monthly: performance against the same definitions and targets, with named owners "
              "and due dates for any continuing gap. All conclusions in this example are based on synthetic data."),
        ]}


@pytest.mark.parametrize("change", [
    {"blocks": []}, {"blocks": [{"kind": "textbox", "text": "wrong"}]},
    {"blocks": [{"kind": "paragraph", "text": "first\nsecond"}]},
    {"blocks": [{"kind": "page_break"}]},
    {"blocks": [{"kind": "table", "cells": [["a","b"]], "widths_mm": [100,100]}]},
    {"layout": {"margins_mm": [10,20,20,20], "header_mm": 10}},
    {"format": {"size": 100}}, {"format": {"size": 10.7}},
    {"format": {"font": "font\ninvalid"}}, {"page_numbers": "arbitrary_field_code"},
])
def test_authoring_rejects_unsupported_content_and_unsafe_geometry(change):
    value = {"session": "s", "snapshot": "r", "blocks": [{"kind": "paragraph", "text": "native"}], **change}
    with pytest.raises(ValueError):
        WordComposeArguments.model_validate(value)


def test_report_plan_is_bounded_native_content_and_has_three_explicit_pages():
    plan = WordComposeArguments.model_validate(report_plan())
    assert sum(block.kind == "page_break" for block in plan.blocks) == 2
    assert sum(block.kind == "table" for block in plan.blocks) == 1
    assert len(plan.model_dump_json().encode()) < 32768


def test_snapshot_ignores_revision_bookkeeping_but_preserves_content_and_formatting():
    xml = '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document><w:body><w:p w:rsidR="1"><w:r><w:rPr><w:b/></w:rPr><w:t>native</w:t></w:r></w:p></w:body></w:document></pkg:xmlData></pkg:part></pkg:package>'
    assert signature(xml) == signature(xml.replace('rsidR="1"', 'rsidR="2"'))
    assert signature(xml) != signature(xml.replace("native", "changed"))
    assert signature(xml) != signature(xml.replace("<w:b/>", "<w:i/>"))


def test_page_field_cache_is_distinct_from_field_code_and_typography():
    xml = '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><pkg:part pkg:name="/word/footer1.xml"><pkg:xmlData><w:ftr><w:p><w:fldSimple w:instr=" NUMPAGES "><w:r><w:rPr><w:noProof/><w:sz w:val="18"/></w:rPr><w:t>3</w:t></w:r></w:fldSimple></w:p></w:ftr></pkg:xmlData></pkg:part></pkg:package>'
    assert signature(xml)==signature(xml.replace(">3<",">1<").replace("<w:noProof/>",""))
    assert signature(xml)!=signature(xml.replace("NUMPAGES","PAGE"))
    assert signature(xml)!=signature(xml.replace('w:val="18"','w:val="20"'))


def test_package_relationship_renumbering_preserves_real_header_content_and_style_guards():
    xml = '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document><w:body><w:p/><w:sectPr><w:headerReference w:type="default" r:id="rId6"/></w:sectPr></w:body></w:document></pkg:xmlData></pkg:part><pkg:part pkg:name="/word/_rels/document.xml.rels"><pkg:xmlData><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/></Relationships></pkg:xmlData></pkg:part><pkg:part pkg:name="/word/header1.xml"><pkg:xmlData><w:hdr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Header</w:t></w:r></w:p></w:hdr></pkg:xmlData></pkg:part></pkg:package>'
    assert signature(xml)==signature(xml.replace("rId6","rId9").replace("header1.xml","header2.xml"))
    assert signature(xml)!=signature(xml.replace(">Header<",">Different<"))
    assert signature(xml)!=signature(xml.replace("<w:b/>","<w:i/>"))


def render_output():
    data = BytesIO()
    Image.new("RGB", (20,30), "white").save(data, format="PNG")
    pixels = data.getvalue()
    return pixels, {"application":"word", "session":"session", "snapshot":"render", "cursor":None,
        "items":[{"target":"page", "label":"Rendered Word page 1", "text":json.dumps(
            {"page":1, "bytes":len(pixels), "sha256":sha256(pixels).hexdigest()})}]}


@pytest.mark.parametrize("failure", [None, "hash", "offset", "size"])
def test_private_render_transport_enforces_identity_length_and_integrity(failure):
    pixels, output = render_output()
    bridge = OfficeConnection.__new__(OfficeConnection)
    def control(action, args):
        assert action == "word-render-image" and args["session"] == "session" and args["snapshot"] == "render"
        return {"data":base64.b64encode(pixels).decode(), "offset":1 if failure=="offset" else 0,
                "next":len(pixels), "total":len(pixels)}
    bridge.control = control
    if failure in {"hash","size"}:
        metadata=json.loads(output["items"][0]["text"])
        metadata["sha256" if failure=="hash" else "bytes"]="0"*64 if failure=="hash" else 999999999
        output["items"][0]["text"]=json.dumps(metadata)
    if failure:
        with pytest.raises(ValueError):
            bridge.render_images(output)
    else:
        assert bridge.render_images(output)==[(1,pixels)]


def test_rendered_pixels_reach_the_model_only_for_the_actual_word_render_call():
    pixels, output = render_output()
    contract=next(t for t in OFFICE_TOOLS if t.name=="office.read")
    connection=SimpleNamespace(render_images=lambda result:[(1,pixels)])
    tool=OfficeCapability(contract,connection,None,None,None)
    call=SimpleNamespace(arguments={"target":"render:1:1"})
    result=SimpleNamespace(call_id="receipt",output=output)
    model=SimpleNamespace(supports_native_attachment_tools=True)
    message=word_image_message(tool,call,result,model)
    assert message["role"]=="user" and "untrusted visual evidence" in message["content"][0]["text"]
    assert message["content"][-1]["type"]=="image_url"
    assert word_image_message(tool,SimpleNamespace(arguments={"target":"document"}),result,model) is None
    assert word_image_message(tool,call,result,SimpleNamespace())["role"]=="system"
