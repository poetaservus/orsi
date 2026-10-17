"""One opt-in configured-model/ConversationService/Office illustrated acceptance.

The frozen request is never rewritten. No model responses or plans are seeded.
Only numeric/fixed-category diagnostics persist; intended DOCX/PNG outputs are
separate artifacts. Existing credentials stay in memory. No local model runs.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gc
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_word_proposal import MemoryConversationStore, read_call
from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import PermissionClass
from app.conversation.orchestrator import ConversationService
from app.inference.hybrid import HybridInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.word_plan_diagnostics import word_plan_shape
from app.mcp.office_connection import OfficeConnection
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config


def illustrations(output):
    """Original, explicitly synthetic diagrams with no third-party image rights."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
    font = ImageFont.truetype(str(font_path), 24)
    small = ImageFont.truetype(str(font_path), 19)
    paths = []
    for number in (1, 2):
        image = Image.new("RGB", (960, 540), "#F4F7F8")
        draw = ImageDraw.Draw(image)
        draw.text((35, 25), "ORIGINAL TEST ILLUSTRATION | SYNTHETIC", font=small, fill="#47616D")
        if number == 1:
            draw.text((35, 70), "Rainfall to retention: a conceptual catchment", font=font, fill="#183846")
            labels = ("Street runoff", "Rain garden", "Retention basin")
            for i, label in enumerate(labels):
                x = 35 + i * 310
                draw.rounded_rectangle((x, 190, x + 265, 350), radius=18, fill=("#B9D8E3", "#A9C7AC", "#6C9EAF")[i])
                draw.text((x + 18, 255), label, font=font, fill="#183846")
                if i < 2:
                    draw.line((x + 270, 270, x + 300, 270), fill="#183846", width=5)
                    draw.polygon(((x + 300, 270), (x + 290, 260), (x + 290, 280)), fill="#183846")
            draw.text((35, 435), "Conceptual flow only; no site measurements", font=small, fill="#47616D")
        else:
            draw.text((35, 70), "Illustrative storage allocation (arbitrary units)", font=font, fill="#183846")
            for i, (label, value) in enumerate((("Rain gardens", 30), ("Permeable paving", 45), ("Retention basins", 75))):
                y = 170 + i * 85
                draw.text((35, y + 10), label, font=small, fill="#183846")
                draw.rectangle((280, y, 280 + value * 7, y + 48), fill="#28778C")
                draw.text((295 + value * 7, y + 10), str(value), font=small, fill="#183846")
            draw.text((35, 450), "Synthetic values demonstrate a chart, not real performance", font=small, fill="#47616D")
        path = output / f"original-illustration-{number}.png"
        image.save(path)
        paths.append(path)
    return paths


def verify(output, key_file=None):
    output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "fixture": "word_illustrated_prompt_v1", "provider_requests": 0,
        "generated_plans": [], "calls": [], "approvals": [], "visual_inspection": "pending"}
    template = (ROOT / "tests/fixtures/word_illustrated_prompt.txt").read_text(encoding="utf-8").strip()
    report["fixture_sha256"] = sha256(template.encode()).hexdigest()
    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        key = key_file.read_text(encoding="utf-8-sig").splitlines()[0].strip() if key_file else os.environ.get("OPENAI_API_KEY", "").strip()
    except (OSError, IndexError):
        key = ""
    if not key:
        report["limitation"] = "existing_authorized_credential_unavailable"
        report["live_model_gate"] = "unverified_no_provider_request"
        save()
        return report
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    images = illustrations(output)
    fixture = output / "urban-water-resilience.docx"
    original = Path.home() / "Desktop/report.docx"
    original_digest = sha256(original.read_bytes()).digest() if original.is_file() else None
    handler = logging.FileHandler(output / "word-structure.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    diagnostic_log = logging.getLogger("app.inference.word_plan_diagnostics")
    diagnostic_log.addHandler(handler)
    diagnostic_log.setLevel(logging.INFO)
    diagnostic_log.propagate = False
    config = load_cloud_config()
    report["model"] = config.default_model
    cloud = OpenAIResponsesInferenceEngine(config, api_key=key, selection_path=output / "cloud-selection.json")
    key = None
    inference = HybridInferenceEngine(local=None, cloud=cloud, default_mode="cloud", fallback_to_local=config.fallback_to_local)
    respond = cloud.respond_with_capabilities
    def observe(messages, definitions):
        report["provider_requests"] += 1
        response = respond(messages, definitions)
        for call in response.capability_calls:
            if call.capability == "office.read":
                from app.mcp.office_read_diagnostics import read_shape
                report.setdefault("read_requests", []).append(read_shape(call.arguments))
            if call.capability == "office.word_compose":
                report["generated_plans"].append(word_plan_shape(call.arguments))
        save()
        return response
    cloud.respond_with_capabilities = observe
    bridge = OfficeConnection(ROOT, backend=lambda: inference.mode, startup_timeout=20)
    policy = HostAccessPolicy.full_local(application_root=ROOT, user_home=Path.home(), acknowledged=True)
    runtime = build_agent_runtime(inference, config=load_agent_feature_config(), portable_root=ROOT,
        state_directory=output / "runtime", office_connection=bridge, office_resource_policy=bridge.resource_policy,
        host_access_policy=policy)
    runtime.permission_gate = PermissionGate((*runtime.permission_gate.rules,
        PermissionRule("acceptance-write-deny", PermissionDecision.DENY, permission=PermissionClass.WRITE),
        *(PermissionRule("acceptance-" + name.rsplit(".", 1)[-1], PermissionDecision.ASK,
            permission=PermissionClass.WRITE, capability_pattern=name, resource_root=output)
          for name in ("office.word_compose", "office.word_edit", "office.save", "office.revert")),
        PermissionRule("acceptance-execute-deny", PermissionDecision.DENY, permission=PermissionClass.EXECUTE)))
    registry = SkillRegistry()
    registry.discover()
    service = ConversationService(inference, MemoryConversationStore(output / "not-persisted.json"),
        agent_runtime=runtime, portable_root=ROOT, allowed_read_roots=(output,), host_access_policy=policy,
        skill_registry=registry, automatic_skills_enabled=False)
    def approve(record):
        allowed = (record.capability in {"office.word_compose", "office.word_edit", "office.save", "office.revert"}
            and record.resource is not None and Path(record.resource).resolve() == fixture.resolve())
        report["approvals"].append({"tool": record.capability, "approved": allowed})
        service.resolve_approval(record.approval_id, allowed)
    service.set_approval_requester(approve)
    application = document = owned = None
    pythoncom.CoInitializeEx(2)
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = True
        application.DisplayAlerts = 0
        document = application.Documents.Add()
        document.SaveAs2(str(fixture), 12)
        owned = psutil.Process(win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1])
        bridge.connect()
        selected = next(d for d in bridge.list_documents() if d["application"] == "word" and d["title"] == str(document.Name))
        bridge.select_document(selected["document"])
        service.run(template.format(document=fixture, image1=images[0], image2=images[1]))
        turn = service.store.turns()[-1]
        report["terminal_status"] = turn.outcome.status.value
        report["calls"] = [{"tool": c.call.capability, "success": c.result.success,
            "error": c.result.error.code.value if c.result.error else None} for c in turn.settled_calls]
        compositions = [c for c in turn.settled_calls if c.call.capability == "office.word_compose" and c.result.success]
        report["successful_compositions"] = len(compositions)
        if compositions:
            from app.mcp.office_contracts import WordComposeArguments
            from app.mcp.office_word_document import verify_document
            plan = WordComposeArguments.model_validate(compositions[-1].call.arguments)
            verify_document(document, plan)
            report["sections"] = [int(document.Sections.Item(i).PageSetup.TextColumns.Count)
                for i in range(1, int(document.Sections.Count) + 1)]
            report["pictures"] = int(document.InlineShapes.Count)
            report["tables"] = int(document.Tables.Count)
            report["pages"] = int(document.Range(0, 0).Information(4))
            report["words"] = int(document.ComputeStatistics(0))
            report["native_readback"] = True
            session = plan.session
            for start in range(1, report["pages"] + 1, 3):
                rendered = read_call(runtime, "read", {"session": session, "target": f"render:{start}:{min(start + 2, report['pages'])}"},
                    "verify-render-" + str(start), policy, output)
                for number, pixels in bridge.render_images(rendered.output):
                    (output / f"page-{number}.png").write_bytes(pixels)
            report["model_saved"] = any(c.call.capability == "office.save" and c.result.success for c in turn.settled_calls)
            report["passed"] = (turn.outcome.status.value == "completed" and report["model_saved"]
                and report["pictures"] >= 2 and report["tables"] >= 1 and report["pages"] >= 3
                and 1300 <= report["words"] <= 1600
                and report["sections"][0] == report["sections"][-1] == 1 and 2 in report["sections"])
            if report["model_saved"]:
                document.Close(False)
                document = application.Documents.Open(str(fixture))
                verify_document(document, plan)
                report["saved_reopen_verified"] = True
    except Exception as error:
        report["exception_type"] = type(error).__name__
        report["office_diagnostics"] = bridge.diagnostics
        turns = service.store.turns()
        if turns:
            report["calls"] = [{"tool": c.call.capability, "success": c.result.success,
                "error": c.result.error.code.value if c.result.error else None} for c in turns[-1].settled_calls]
            report["successful_compositions"] = sum(c.call.capability == "office.word_compose" and c.result.success
                for c in turns[-1].settled_calls)
            report["model_saved"] = any(c.call.capability == "office.save" and c.result.success for c in turns[-1].settled_calls)
        report["passed"] = False
    finally:
        runtime.shutdown()
        inference.close()
        if document is not None:
            document.Close(False)
        document = None
        gc.collect()
        if application is not None:
            application.Quit(False)
        application = None
        gc.collect()
        if owned is not None:
            try:
                owned.wait(10)
                report["owned_word_released"] = True
            except psutil.TimeoutExpired:
                report["owned_word_released"] = False
        report["bridge_released"] = not bridge.diagnostics["worker_alive"]
        report["original_unchanged"] = original_digest is None or sha256(original.read_bytes()).digest() == original_digest
        save()
        diagnostic_log.removeHandler(handler)
        handler.close()
        pythoncom.CoUninitialize()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    result = verify(args.output.resolve(), args.key_file)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
