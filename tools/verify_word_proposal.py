"""Opt-in real configured cloud/ConversationService/Office proposal acceptance.

Never seeds a model response or document plan. Only fixture writes are approved.
The prior contract option compares the exact tracked pre-fix advertisement;
prompts, sampling, context, routing and limits are identical in both runs.
Conversation/tool text remains in memory. Disk diagnostics are structural only.
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
import re
import shutil
import subprocess
import sys
import types
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityContext, CapabilityExecutionError, PermissionClass
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.word_plan_diagnostics import word_plan_shape
from app.mcp.office_connection import OfficeConnection
from app.runtime.skills import SkillRegistry
from app.runtime.cancellation import CancellationToken
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule, prepare_capability_call
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config


class MemoryConversationStore(ConversationStore):
    def _save_document(self, path, document):
        pass  # Preserve the real turn lifecycle, without storing proposal/chat text.


def read_call(runtime, name, arguments, operation, policy, output):
    context = CapabilityContext(call_id=operation, session_id="verification", turn_id="verification",
        portable_root=ROOT, allowed_read_roots=(output,), cancellation=CancellationToken(), host_access_policy=policy)
    capability = runtime.registry.resolve("office." + name)
    if capability.permission != PermissionClass.READ:
        raise ValueError("Independent verification only permits reads.")
    prepared = prepare_capability_call(capability, arguments, context)
    runtime.executor.journal.record_prepared(prepared)
    evaluation = runtime.permission_gate.evaluate(prepared)
    authorization = runtime.approval_manager.authorize(evaluation)
    runtime.executor.journal.record_authorization(prepared, authorization)
    result = runtime.executor.execute(prepared, authorization)
    if not result.success:
        raise CapabilityExecutionError(result.error.code, result.error.message)
    return result


def previous_definition(revision):
    source = subprocess.check_output(["git", "show", revision + ":app/mcp/office_contracts.py"], cwd=ROOT)
    module = types.ModuleType("_orsi_word_baseline_contracts")
    sys.modules[module.__name__] = module
    exec(compile(source, "<tracked baseline Office contracts>", "exec"), module.__dict__)
    return next(t.definition() for t in module.OFFICE_TOOLS if t.name == "office.word_compose")


def pricing_totals(cells):
    """Check monetary last-column line items, subtotal/tax/total independently."""
    from decimal import Decimal, InvalidOperation

    def amount(value):
        value = re.sub(r"(?:EUR|€|\s)", "", value, flags=re.I)
        if not re.fullmatch(r"[\d,.]+", value):
            return None
        if "," in value and "." in value:
            value = value.replace(",", "") if value.rfind(".") > value.rfind(",") else value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".") if len(value.rsplit(",", 1)[-1]) == 2 else value.replace(",", "")
        try:
            return Decimal(value)
        except InvalidOperation:
            return None

    line_items, subtotal, total, tax = [], None, None, Decimal(0)
    for row in cells[1:]:
        if not row:
            continue
        value = amount(row[-1])
        if value is None:
            continue
        label = " ".join(row[:-1]).lower()
        if "subtotal" in label or "sub-total" in label:
            subtotal = value
        elif "total" in label:
            total = value
        elif "vat" in label or "tax" in label:
            tax += value
        else:
            line_items.append(value)
    return bool(line_items and total is not None and sum(line_items) + tax == total
                and (subtotal is None or subtotal == sum(line_items)))


def verify(source, output, key_file, contract_revision=None):
    import pythoncom
    import psutil
    import win32com.client
    import win32process

    output.mkdir(parents=True, exist_ok=False)
    handler = logging.FileHandler(output / "word-structure.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    diagnostic_log = logging.getLogger("app.inference.word_plan_diagnostics")
    diagnostic_log.addHandler(handler)
    diagnostic_log.setLevel(logging.INFO)
    diagnostic_log.propagate = False
    # Never print keys, SDK errors, assistant prose, arguments or read results.
    report = {"passed": False, "contract": contract_revision or "current", "provider_requests": 0,
              "generated_plans": [], "calls": [], "approvals": [], "original_unchanged": False,
              "visual_inspection": "pending"}

    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    try:
        if key_file:
            with key_file.open(encoding="utf-8-sig") as stream:
                key = stream.readline().strip()
        else:
            key = os.environ.get("OPENAI_API_KEY", "").strip()
    except OSError:
        key = ""
        report["limitation"] = "credential_file_unavailable"
    if not key:
        report.setdefault("limitation", "credential_unavailable")
        save()
        diagnostic_log.removeHandler(handler)
        handler.close()
        return report
    config = load_cloud_config()
    report["model"] = config.default_model
    report["profile"] = config.profile(config.default_model).model_dump(mode="json")
    before = sha256(source.read_bytes()).digest()
    fixture = output / ("proposal-" + uuid4().hex[:8] + ".docx")
    shutil.copyfile(source, fixture)
    prompt_template = (ROOT / "tests/fixtures/word_proposal_prompt.txt").read_text(encoding="utf-8").strip()
    report["prompt_sha256"] = sha256(prompt_template.encode()).hexdigest()
    prior = previous_definition(contract_revision) if contract_revision else None
    cloud = OpenAIResponsesInferenceEngine(config, api_key=key, selection_path=output / "cloud-selection.json")
    key = None
    inference = HybridInferenceEngine(local=None, cloud=cloud, default_mode="cloud", fallback_to_local=config.fallback_to_local)
    actual = cloud.respond_with_capabilities
    generated = []

    def observe(messages, definitions):
        report["provider_requests"] += 1
        if prior is not None:
            definitions = tuple(prior if d.name == prior.name else d for d in definitions)
        response = actual(messages, definitions)
        for call in response.capability_calls:
            if call.capability == "office.word_compose":
                generated.append(deepcopy(call.arguments))
                report["generated_plans"].append(word_plan_shape(call.arguments))
        save()
        return response

    cloud.respond_with_capabilities = observe
    bridge = OfficeConnection(ROOT, backend=lambda: inference.mode, startup_timeout=20)
    policy = HostAccessPolicy.full_local(application_root=ROOT, user_home=Path.home(), acknowledged=True)
    def execute(runtime, name, arguments, operation):
        return read_call(runtime, name, arguments, operation, policy, output)
    runtime = build_agent_runtime(inference, config=load_agent_feature_config(), portable_root=ROOT,
        state_directory=output / "runtime", office_connection=bridge, office_resource_policy=bridge.resource_policy,
        host_access_policy=policy)
    # Preserve production ASK and approval binding; restrict the harness's
    # authority to the isolated fixture. No original or unrelated write passes.
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
        document = application.Documents.Open(str(fixture))
        owned = psutil.Process(win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1])
        bridge.connect()
        selected = next(d for d in bridge.list_documents() if d["application"] == "word" and d["title"] == str(document.Name))
        bridge.select_document(selected["document"])
        save()
        service.run(prompt_template.format(document=fixture))
        turn = service.store.turns()[-1]
        report["terminal_status"] = turn.outcome.status.value
        report["model_requests"] = turn.outcome.model_requests
        report["calls"] = [{"tool": c.call.capability, "success": c.result.success,
            "error": c.result.error.code.value if c.result.error else None} for c in turn.settled_calls]
        compositions = [c for c in turn.settled_calls if c.call.capability == "office.word_compose" and c.result.success]
        report["successful_compositions"] = len(compositions)
        if compositions:
            session = compositions[-1].call.arguments["session"]
            layout = execute(runtime, "read", {"session": session, "target": "layout"}, "verify-layout").output
            report["rendered_page_count"] = json.loads(layout["items"][0]["text"])["page_count"]
            pages = []
            for start in range(1, report["rendered_page_count"] + 1, 3):
                last_page = min(start + 2, report["rendered_page_count"])
                rendered = execute(runtime, "read", {"session": session, "target": f"render:{start}:{last_page}"}, "verify-render-" + str(start))
                for number, pixels in bridge.render_images(rendered.output):
                    (output / f"page-{number}.png").write_bytes(pixels)
                    pages.append(number)
            report["rendered_pages"] = pages
            report["native_tables"] = int(document.Tables.Count)
            report["native_shapes"] = int(document.Shapes.Count) + int(document.InlineShapes.Count)
            page = document.Sections.Item(1).PageSetup
            report["a4"] = abs(float(page.PageWidth) - 210 * 72 / 25.4) < .1 and abs(float(page.PageHeight) - 297 * 72 / 25.4) < .1
            from app.mcp.office_contracts import WordComposeArguments
            last = WordComposeArguments.model_validate(compositions[-1].call.arguments).model_dump(mode="json")
            tables = [b["cells"] for b in last["blocks"] if b.get("kind") == "table"]
            paragraphs = [b for b in last["blocks"] if b.get("kind", "paragraph") == "paragraph" and "text" in b]
            all_text = " ".join([b["text"] for b in paragraphs] + [v for rows in tables for row in rows for v in row]
                                + [last.get("header", ""), last.get("footer", "")]).lower()
            report["proposal_checks"] = {
                "title": "warehouse intelligence" in all_text and "operational analytics & automation proposal" in all_text,
                "identification": "northline systems" in all_text and "meridian logistics" in all_text,
                "executive_overview": "executive" in all_text and ("overview" in all_text or "summary" in all_text),
                "workstreams": "workstream" in all_text,
                "deliverables": "deliverable" in all_text,
                "eight_weeks": bool(re.search(r"eight.week|8.week|week.?8|weeks.?7\D+8", all_text)),
                "four_phases": len(re.findall(r"phase\s*[1-4]", all_text)) >= 4 or any(
                    "phase" in " ".join(rows[0]).lower() and len(rows) == 5 for rows in tables),
                "eur": "eur" in all_text or "€" in all_text,
                "payment_terms": bool(re.search(r"payment|invoice|deposit|payable", all_text)),
                "measurable_success": "success" in all_text and bool(re.search(r"\d+(?:\.\d+)?%", all_text)),
                "next_steps": "next steps" in all_text,
                "complete_body": len(paragraphs) >= 8 and len(all_text) >= 1500 and len(tables) >= 1,
                "native_heading_styles": sum(b.get("style", "Normal").startswith("Heading") for b in paragraphs) >= 3,
                "running_identification": bool(last.get("header")) and bool(last.get("footer")),
                "page_fields": last.get("page_numbers", "page_of_total") in {"page", "page_of_total"}
                    and int(document.Sections.Item(1).Footers.Item(1).Range.Fields.Count) ==
                        (1 if last.get("page_numbers") == "page" else 2)}
            report["pricing_totals_correct"] = any(pricing_totals(cells) for cells in tables)
            report["model_saved"] = any(c.call.capability == "office.save" and c.result.success for c in turn.settled_calls)
            report["passed"] = (turn.outcome.status.value == "completed" and report["rendered_page_count"] == 2
                and report["native_tables"] >= 1 and report["native_shapes"] == 0 and report["a4"]
                and report["pricing_totals_correct"] and report["model_saved"] and all(report["proposal_checks"].values()))
    except Exception as error:
        report["exception_type"] = type(error).__name__  # Exception text may contain private input.
        report["office_diagnostics"] = bridge.diagnostics
        # Read-only inspection of the isolated fixture after an uncertain write.
        # This never retries a mutation or marks that receipt successful.
        if document is not None and generated:
            from app.mcp.office_contracts import WordComposeArguments
            from app.mcp.office_word_document import verify_document
            try:
                verify_document(document, WordComposeArguments.model_validate(generated[-1]))
                report["independent_native_readback"] = True
            except Exception as mismatch:
                report["independent_native_readback"] = False
                report["readback_exception_type"] = type(mismatch).__name__
                trace = mismatch.__traceback__
                locations = []
                while trace is not None:
                    if Path(trace.tb_frame.f_code.co_filename).name == "office_word_document.py":
                        locations.append(trace.tb_lineno)
                    trace = trace.tb_next
                report["readback_code_lines"] = locations
            report["native_after_failure"] = {"tables": int(document.Tables.Count),
                "paragraphs": int(document.Paragraphs.Count), "text_chars": len(str(document.Content.Text)),
                "page_count": int(document.Range(0, 0).Information(4))}
        turns = service.store.turns()
        if turns:
            report["calls"] = [{"tool": c.call.capability, "success": c.result.success,
                "error": c.result.error.code.value if c.result.error else None} for c in turns[-1].settled_calls]
            if turns[-1].outcome is not None:
                report["terminal_status"] = turns[-1].outcome.status.value
        if isinstance(error, pythoncom.com_error):
            report["windows_hresult"] = error.hresult
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
        report["original_unchanged"] = sha256(source.read_bytes()).digest() == before
        save()
        diagnostic_log.removeHandler(handler)
        handler.close()
        pythoncom.CoUninitialize()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--contract-revision")
    args = parser.parse_args()
    result = verify(args.source.resolve(), args.output.resolve(), args.key_file, args.contract_revision)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
