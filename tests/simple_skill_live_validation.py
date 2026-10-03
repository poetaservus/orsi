"""Opt-in audit of one unchanged Apache-2.0 skill; never adjusts the runtime."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re

from app.agent.bootstrap import build_agent_runtime
from app.conversation.context import calculate_context_budget
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.runtime.skills import SkillCandidate, SkillInstaller, SkillRegistry, select_skill, with_active_skill
from app.runtime.skills.selection import SELECTOR_SYSTEM_PROMPT
from app.security.host_access import HostReadScope
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from tests.fixtures.tasteskill_cases import UNRELATED_TASKS, TOOL_TASK


FIXTURE = Path(__file__).parent / "fixtures" / "brand_guidelines"
SKILL_NAME = "brand-guidelines"
# Fixed before any native inference. Identical stimuli in all three modes.
BRAND_TASKS = (
    ("css", "Using Anthropic's brand guidelines, reply with CSS only: define custom properties "
     "for all seven brand colors, set h1 font-family with its fallback, and set body font-family "
     "with its fallback. Do not create files or use tools."),
    ("fonts", "What are Anthropic's official heading and body fonts and their fallback fonts? "
     "Reply with just two short lines. Do not use tools."),
)
COLORS = frozenset({"#141413", "#faf9f5", "#b0aea5", "#e8e6dc", "#d97757", "#6a9bcc", "#788c5d"})


def assess_brand_reply(case_id, reply):
    text = reply.lower()
    fonts = all(name in text for name in ("poppins", "arial", "lora", "georgia"))
    if case_id == "fonts":
        return {"expected_fonts_present": fonts, "passed": fonts}
    color_values = set(re.findall(r"#[0-9a-f]{6}\b", text))
    heading = re.search(r"(?:^|[}\n])\s*h1\s*\{[^}]*font-family\s*:[^;}]*poppins[^;}]*arial", text)
    body = re.search(r"(?:^|[}\n])\s*body\s*\{[^}]*font-family\s*:[^;}]*lora[^;}]*georgia", text)
    properties = set(re.findall(r"--[\w-]+\s*:\s*(#[0-9a-f]{6})\b", text))
    checks = {"expected_fonts_present": fonts, "seven_colors_present": COLORS <= color_values,
              "seven_custom_properties_present": COLORS <= properties,
              "heading_and_body_font_rules": bool(heading and body)}
    return {**checks, "passed": all(checks.values())}


def finalize_summary(summary):
    answers = [r for r in summary["physical_requests"] if r["kind"] == "answer"]
    activated = [r for r in answers if r["skill_sections"]]
    brands = [r for r in summary["runs"] if r["case_id"] != "tool" and r["mode"] != "without"]
    tools = [r for r in summary["runs"] if r["case_id"] == "tool"]
    summary.update(audit_completed=len(summary["runs"]) == 8 and len(summary["routing"]) == 5,
        unrelated_routing_passed=len(summary["routing"]) == 5 and all(r["passed"] for r in summary["routing"]),
        tool_catalog_unchanged=(len({r["tools_sha256"] for r in answers}) == 1) if answers else None,
        branding_passed=len(brands) == 4 and all(r.get("assessment", {}).get("passed", False)
            and r["active_skill"] == SKILL_NAME and not r.get("completion_incomplete", True) for r in brands),
        tool_probes_passed=len(tools) == 2 and all(r["successful_stat_calls"] > 0 for r in tools),
        skill_injection_exact=(all(r["skill_sections"] == 1 and r["skill_body_exact"] is True
                                  for r in activated)) if activated else None)


def run_validation(root, model_id="Qwen314BQ4KM.gguf"):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(FIXTURE)
    assert len(installer.list()) == 1
    skill = installer.info(SKILL_NAME)
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    production = load_agent_feature_config()
    # Preserve all production tool flags; fixture reads are scoped and approvals denied.
    config = production.model_copy(update={"full_local_read_enabled": False})
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=root / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration(model_id))
    resolution = catalog._resolutions[model_id]
    summary = {"schema_version": 1, "upstream_revision": manifest["revision"],
               "skill_name": skill.name, "skill_bytes": manifest["records"][0]["file_bytes"],
               "model_id": model_id, "catalog_size": 1,
               "profile_resolution": {key: resolution[key] for key in
                   ("target", "effective", "selection_reason", "gpu_before_load_mib")},
               "installed_exact_bytes": skill.source_path.read_bytes() == (FIXTURE / "SKILL.md").read_bytes(),
               "install_idempotent": installer.install(FIXTURE).already_installed == (SKILL_NAME,),
               "production_catalog": True, "host_reads": "isolated_portable_root",
               "write_launch_approvals": "denied", "routing": [], "runs": [], "physical_requests": []}
    artifact = root / "live-summary.json"
    services = []
    active = None
    process = None
    actual = backend._request_completion

    def save():
        artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def audit(payload):
        result = actual(payload)
        system = payload["messages"][0]["content"]
        count = system.count("\nACTIVE SKILL\n")
        exact = None
        if count == 1:
            encoded = system.split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0]
            exact = json.loads(encoded) == {"name": skill.name, "instructions": skill.instructions}
        usage = result.get("usage", {})
        summary["physical_requests"].append({
            "kind": "selector" if system == SELECTOR_SYSTEM_PROMPT else "answer",
            "skill_sections": count, "skill_body_exact": exact,
            "tool_count": len(payload.get("tools", [])),
            "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "finish_reason": result.get("choices", [{}])[0].get("finish_reason"),
        })
        save()
        return result

    backend._request_completion = audit
    try:
        backend.prepare()
        process = backend._process
        summary.update(effective_context=backend.context_length, effective_output_reserve=backend.max_response_tokens,
                       body_tokens=backend._live_token_count(skill.instructions),
                       file_tokens=backend._live_token_count((FIXTURE / "SKILL.md").read_text(encoding="utf-8")))
        print(json.dumps({"stage": "prepared", "effective_context": backend.context_length,
                          "body_tokens": summary["body_tokens"]}), flush=True)
        candidates = (SkillCandidate(skill.name, skill.description),)
        for case_id, request in UNRELATED_TASKS:
            selection = select_skill(backend, candidates=candidates, request=request)
            summary["routing"].append({"case_id": case_id, "selection": asdict(selection),
                                       "passed": selection.name is None and selection.reason == "no_match"})
            save()
            print(json.dumps({"stage": "unrelated-routing", "case_id": case_id,
                              "selection": asdict(selection)}), flush=True)

        for case_id, request in (*BRAND_TASKS, ("tool", TOOL_TASK)):
            modes = ("without", "explicit", "automatic") if case_id != "tool" else ("without", "explicit")
            for mode in modes:
                scope = root / "runs" / f"{case_id}-{mode}"
                scope.mkdir(parents=True, exist_ok=True)
                (scope / "index.html").write_text("<!doctype html><title>Fixture</title>", encoding="utf-8")
                runtime = build_agent_runtime(backend, config=config, portable_root=scope, state_directory=scope / "state")
                service = ConversationService(backend, ConversationStore(scope / "conversation.json"),
                    agent_runtime=runtime, portable_root=scope, skill_registry=installer.registry,
                    automatic_skills_enabled=mode == "automatic")
                service.new_session()
                service.set_approval_requester(lambda record, owner=service: owner.resolve_approval(record.approval_id, False))
                services.append(service)
                active = service
                if mode == "explicit":
                    service.activate_skill(SKILL_NAME)
                definitions = runtime.registry.model_definitions()
                reserve = backend.count_capability_schema_tokens(definitions)
                core = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, service.agent_capabilities)
                record = {"case_id": case_id, "mode": mode, "tool_catalog_count": len(definitions),
                          "schema_reserve": reserve}
                for label, selected in (("baseline_budget", None), ("with_skill_budget", skill)):
                    record[label] = asdict(calculate_context_budget(backend,
                        [{"role": "system", "content": with_active_skill(core, selected)},
                         {"role": "user", "content": request}], reserved_tokens=reserve))
                start = len(summary["physical_requests"])
                try:
                    reply = service.run(request)
                    text = str(reply)
                    record.update(outcome="completed", completion_incomplete=bool(reply.completion.incomplete))
                    (scope / "review-answer.txt").write_text(text, encoding="utf-8")
                    if case_id != "tool":
                        record["assessment"] = assess_brand_reply(case_id, text)
                except Exception as error:
                    record.update(outcome="blocked", error_type=type(error).__name__,
                                  error_code=getattr(getattr(error, "code", None), "value", None))
                turn = service._turn_result
                record.update(selection=asdict(service.skill_selection),
                    active_skill=service.active_skill.name if service.active_skill else None,
                    run_status=turn.status.value if turn else None,
                    successful_stat_calls=sum(r.capability == "filesystem.stat" and bool(r.result_success)
                                              for r in runtime.executor.journal.records),
                    physical_requests=deepcopy(summary["physical_requests"][start:]))
                summary["runs"].append(record)
                save()
                active = None
                print(json.dumps({"stage": "run", "case_id": case_id, "mode": mode,
                                  "outcome": record["outcome"], "assessment": record.get("assessment"),
                                  "stat_successes": record["successful_stat_calls"]}), flush=True)
        finalize_summary(summary)
    finally:
        if active is not None:
            active.cancel_current_task()
        try:
            for service in services:
                service.shutdown()
        finally:
            backend.close()
        summary["owned_server_exited"] = process is None or process.poll() is not None
        save()
        if not summary["owned_server_exited"]:
            raise RuntimeError("Simple skill audit server did not stop.")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen314BQ4KM.gguf")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--report", type=Path, help="Refresh derived fields of an existing audit without starting a model.")
    args = parser.parse_args()
    if args.report is not None:
        result = json.loads(args.report.read_text(encoding="utf-8"))
        finalize_summary(result)
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        result = run_validation(args.root or PATHS.state / "test-artifacts/simple-skill/model-audit", args.model_id)
    print(json.dumps({key: value for key, value in result.items() if key.endswith("passed")
                     or key in ("owned_server_exited", "tool_catalog_unchanged", "skill_injection_exact")}), flush=True)
