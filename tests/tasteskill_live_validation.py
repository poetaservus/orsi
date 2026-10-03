"""Explicit Phase 5.1 audit; failed qualification is reported, never repaired here."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from app.agent.bootstrap import build_agent_runtime
from app.conversation.context import calculate_context_budget
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.runtime.skills import SkillInstaller, SkillRegistry, SkillCandidate, select_skill, with_active_skill
from app.runtime.skills.selection import SELECTOR_SYSTEM_PROMPT
from app.security.host_access import HostReadScope
from app.settings.agent import AgentFeatureConfig
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from tests.fixtures.tasteskill_cases import (
    FRONTEND_TASKS, UNRELATED_TASKS, TOOL_TASK, ACCEPTABLE_FRONTEND_SKILLS,
)


FIXTURE = Path(__file__).parent / "fixtures" / "tasteskill"


def run_validation(root: Path) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # The live HTTPS import is separately recorded. This reproducible model audit
    # installs the same byte-exact pinned files through the local transaction.
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(FIXTURE / "skills")
    registry = installer.registry
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=root / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration("Qwen314BQ4KM.gguf"))
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    summary = {"schema_version": 1, "upstream_revision": manifest["revision"],
               "comparison_scope": "stat_only_style_and_routing",
               "model_id": "Qwen314BQ4KM.gguf", "qualification_passed": False,
               "skills": [], "routing": [], "comparisons": [], "tool_probes": [],
               "physical_requests": []}
    artifact = root / "live-summary.json"
    active = None
    services = []
    process = None
    actual = backend._request_completion

    def save():
        artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def audit(payload):
        completion = actual(payload)
        usage = completion.get("usage", {})
        summary["physical_requests"].append({
            "kind": "selector" if payload["messages"][0]["content"] == SELECTOR_SYSTEM_PROMPT else "answer",
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "skill_sections": payload["messages"][0]["content"].count("\nACTIVE SKILL\n"),
            "tool_count": len(payload.get("tools", [])),
            "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
            "finish_reason": completion.get("choices", [{}])[0].get("finish_reason"),
        })
        save()
        return completion

    backend._request_completion = audit
    try:
        backend.prepare()
        process = backend._process
        summary.update(effective_context=backend.context_length,
                       effective_output_reserve=backend.max_response_tokens)
        candidates = tuple(SkillCandidate(s.name, s.description) for s in registry.list())
        for item in manifest["records"]:
            skill = registry.get(item["name"])
            file_text = skill.source_path.read_bytes().decode("utf-8")
            tokens = backend._live_token_count(skill.instructions)
            file_tokens = backend._live_token_count(file_text)
            if tokens is None or file_tokens is None:
                raise RuntimeError("Native tokenizer measurement unavailable.")
            summary["skills"].append({"name": skill.name, "file_bytes": item["file_bytes"],
                                       "body_bytes": item["body_bytes"], "file_tokens": file_tokens,
                                       "body_tokens": tokens, "sha256": item["sha256"]})
        save()
        print(json.dumps({"stage": "tokenized", "skills": len(summary["skills"]),
                          "effective_context": backend.context_length,
                          "effective_output_reserve": backend.max_response_tokens}), flush=True)
        for case_id, request in (*FRONTEND_TASKS, *UNRELATED_TASKS):
            selection = select_skill(backend, candidates=candidates, request=request)
            expected = ACCEPTABLE_FRONTEND_SKILLS.get(case_id)
            record = {"case_id": case_id, "selected": selection.name,
                      "acceptable": selection.name in expected if expected is not None else selection.name is None,
                      "selection": asdict(selection)}
            summary["routing"].append(record)
            save()
            print(json.dumps({"stage": "routing", **record}), flush=True)

        def service_for(case_id, mode):
            scope = root / "runs" / f"{case_id}-{mode}"
            scope.mkdir(parents=True, exist_ok=True)
            # Both modes start from identical synthetic input, isolated from the
            # user's application and conversations. No writes/launches are enabled.
            (scope / "index.html").write_text(
                '<!doctype html><html><head><title>Generic page</title></head><body>'
                '<h1>Welcome</h1><p>Build better with AI.</p><button>Get started</button>'
                '<div>Feature one</div><div>Feature two</div><div>Feature three</div>'
                '</body></html>', encoding="utf-8")
            runtime = build_agent_runtime(backend, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                          portable_root=scope, state_directory=scope / "state")
            service = ConversationService(backend, ConversationStore(scope / "conversation.json"),
                agent_runtime=runtime, portable_root=scope, skill_registry=registry,
                automatic_skills_enabled=mode == "automatic")
            service.new_session()
            services.append(service)
            return service, runtime, scope

        def run_case(case_id, request, mode, explicit=None):
            nonlocal active
            service, runtime, scope = service_for(case_id, mode)
            active = service
            if explicit is not None:
                service.activate_skill(explicit)
            core = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, service.agent_capabilities)
            reserve = backend.count_capability_schema_tokens(runtime.registry.model_definitions())
            planned_skill = registry.get(explicit) if explicit is not None else None
            record = {"case_id": case_id, "mode": mode, "explicit": explicit,
                      "tool_catalog_count": len(runtime.registry.model_definitions()),
                      "schema_reserve": reserve,
                      "baseline_budget": asdict(calculate_context_budget(backend,
                          [{"role": "system", "content": core}, {"role": "user", "content": request}],
                          reserved_tokens=reserve))}
            if planned_skill is not None:
                record["skill_budget"] = asdict(calculate_context_budget(backend,
                    [{"role": "system", "content": with_active_skill(core, planned_skill)},
                     {"role": "user", "content": request}], reserved_tokens=reserve))
            begin = len(summary["physical_requests"])
            try:
                reply = service.run(request)
                record.update(outcome="completed", visible_chars=len(str(reply)),
                              visible_words=len(str(reply).split()),
                              completion_incomplete=bool(getattr(reply, "completion", None) and reply.completion.incomplete))
                # Synthetic answer artifacts are separate from content-free
                # diagnostics, retained only to support a manual qualitative review.
                (scope / "review-answer.txt").write_text(str(reply), encoding="utf-8")
            except Exception as error:
                record.update(outcome="blocked", error_type=type(error).__name__,
                              error_code=getattr(getattr(error, "code", None), "value", None))
            record["selection"] = asdict(service.skill_selection)
            record["physical_requests"] = deepcopy(summary["physical_requests"][begin:])
            result = service._turn_result
            record["run_status"] = result.status.value if result is not None else None
            record["capability_calls"] = result.capability_calls if result is not None else 0
            record["tool_successes"] = sum(bool(r.result_success) for r in runtime.executor.journal.records)
            record["active_skill"] = service.active_skill.name if service.active_skill is not None else None
            active = None
            print(json.dumps({"stage": "comparison", "case_id": case_id, "mode": mode,
                              "outcome": record["outcome"], "selection": record["selection"],
                              "run_status": record["run_status"]}), flush=True)
            return record

        for case_id, request in FRONTEND_TASKS:
            for mode in ("without", "automatic"):
                summary["comparisons"].append(run_case(case_id, request, mode))
                save()
        for mode, explicit in (("without", None), ("explicit-core", "design-taste-frontend"),
                               ("explicit-small", "minimalist-ui")):
            summary["tool_probes"].append(run_case("tool", TOOL_TASK, mode, explicit))
            save()
        # Core-only explicit admission makes oversize incompatibility unambiguous,
        # even when a full-bundle automatic task chooses a smaller specialist.
        summary["core_probe"] = run_case("core", FRONTEND_TASKS[0][1], "explicit-core",
                                          "design-taste-frontend")
        routing_ok = all(r["acceptable"] for r in summary["routing"])
        enabled = [r for r in summary["comparisons"] if r["mode"] == "automatic"]
        enabled_ok = all(r["outcome"] == "completed" and r["active_skill"] is not None
                         and not r.get("completion_incomplete", False) for r in enabled)
        tools_ok = all(r["tool_successes"] > 0 for r in summary["tool_probes"])
        summary.update(routing_passed=routing_ok, automatic_frontend_passed=enabled_ok,
                       tool_probes_passed=tools_ok,
                       qualification_passed=routing_ok and enabled_ok and tools_ok
                       and summary["core_probe"]["outcome"] == "completed",
                       audit_completed=True)
        save()
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
            raise RuntimeError("TasteSkill validation server did not stop.")
    return summary


def run_production_tool_validation(root: Path) -> dict:
    """Separate matched probe with all configured tools and unchanged model limits.

    Restrict host reads to the synthetic portable scope, and deny every write or
    launch approval. These fixture authority limits never alter user settings.
    """
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(FIXTURE / "skills")
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=root / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration("Qwen314BQ4KM.gguf"))
    production = load_agent_feature_config()
    fixture_config = production.model_copy(update={"full_local_read_enabled": False})
    summary = {"schema_version": 1, "qualification_passed": False, "probes": [],
               "production_catalog": True, "host_reads": "isolated_portable_root",
               "write_launch_approvals": "denied", "model_id": "Qwen314BQ4KM.gguf"}
    artifact = root / "production-tool-summary.json"
    services, physical = [], []
    process = None
    actual = backend._request_completion
    def audit(payload):
        result = actual(payload)
        usage = result.get("usage", {})
        physical.append({"tool_count": len(payload.get("tools", [])),
                         "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
                         "skill_sections": payload["messages"][0]["content"].count("\nACTIVE SKILL\n"),
                         "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")})
        return result
    backend._request_completion = audit
    try:
        backend.prepare()
        process = backend._process
        summary.update(effective_context=backend.context_length,
                       effective_output_reserve=backend.max_response_tokens)
        for mode, name in (("without", None), ("explicit-small", "minimalist-ui"),
                           ("explicit-core", "design-taste-frontend")):
            scope = root / mode
            scope.mkdir(exist_ok=True)
            (scope / "index.html").write_text("<!doctype html><title>Fixture</title>", encoding="utf-8")
            runtime = build_agent_runtime(backend, config=fixture_config, portable_root=scope,
                                          state_directory=scope / "state")
            service = ConversationService(backend, ConversationStore(scope / "conversation.json"),
                                          agent_runtime=runtime, portable_root=scope,
                                          skill_registry=installer.registry, automatic_skills_enabled=False)
            service.new_session()
            service.set_approval_requester(lambda record, owner=service: owner.resolve_approval(record.approval_id, False))
            services.append(service)
            if name is not None:
                service.activate_skill(name)
            reserve = backend.count_capability_schema_tokens(runtime.registry.model_definitions())
            core = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, service.agent_capabilities)
            record = {"mode": mode, "skill": name, "tool_count": len(service.agent_capabilities),
                      "schema_reserve": reserve,
                      "request_budget": asdict(calculate_context_budget(backend,
                          [{"role": "system", "content": with_active_skill(core, installer.registry.get(name) if name else None)},
                           {"role": "user", "content": TOOL_TASK}], reserved_tokens=reserve))}
            begin = len(physical)
            try:
                reply = service.run(TOOL_TASK)
                record.update(outcome="completed", visible_words=len(str(reply).split()))
                (scope / "review-answer.txt").write_text(str(reply), encoding="utf-8")
            except Exception as error:
                record.update(outcome="blocked", error_type=type(error).__name__,
                              error_code=getattr(getattr(error, "code", None), "value", None))
            result = service._turn_result
            record.update(run_status=result.status.value if result is not None else None,
                          capability_calls=result.capability_calls if result is not None else 0,
                          successful_stat_calls=sum(r.capability == "filesystem.stat" and bool(r.result_success)
                                                    for r in runtime.executor.journal.records),
                          physical_requests=deepcopy(physical[begin:]))
            summary["probes"].append(record)
            artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps({"stage": "production-tools", "mode": mode, "outcome": record["outcome"],
                              "tool_count": record["tool_count"], "run_status": record["run_status"],
                              "stat_successes": record["successful_stat_calls"]}), flush=True)
        hashes = {r["tools_sha256"] for r in physical}
        summary.update(tool_catalog_unchanged=len(hashes) <= 1,
                       smaller_skill_tool_probe_passed=all(r["successful_stat_calls"] > 0
                                                          for r in summary["probes"] if r["mode"] != "explicit-core"),
                       core_tool_probe_passed=summary["probes"][-1]["successful_stat_calls"] > 0,
                       audit_completed=True)
    finally:
        try:
            for service in services:
                service.shutdown()
        finally:
            backend.close()
        summary["owned_server_exited"] = process is None or process.poll() is not None
        artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if not summary["owned_server_exited"]:
            raise RuntimeError("Production tool audit server did not stop.")
    return summary


def print_summary(result):
    """Both audits share a content-free CLI summary, with mode-specific fields."""
    fields = ("qualification_passed", "routing_passed", "automatic_frontend_passed",
              "tool_probes_passed", "tool_catalog_unchanged", "smaller_skill_tool_probe_passed",
              "core_tool_probe_passed", "owned_server_exited")
    print(json.dumps({key: result[key] for key in fields if key in result}), flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit unchanged TasteSkill with isolated native Qwen state.")
    parser.add_argument("--production-tools", action="store_true")
    parser.add_argument("--report", type=Path, help="Summarize an existing content-free report without starting a model.")
    args = parser.parse_args()
    if args.report is not None:
        result = json.loads(args.report.read_text(encoding="utf-8"))
    elif args.production_tools:
        result = run_production_tool_validation(PATHS.state / "test-artifacts/skill-phase5-1/production-tool-audit")
    else:
        result = run_validation(PATHS.state / "test-artifacts/skill-phase5-1/model-audit")
    print_summary(result)
