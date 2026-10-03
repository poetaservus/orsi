"""Opt-in native default-model regression with isolated state and real switching."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.runtime.skills import SkillInstaller, SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import detect_nvidia_memory_mib, load_model_config
from app.settings.paths import PATHS
from tests.simple_skill_live_validation import BRAND_TASKS, FIXTURE, assess_brand_reply
from tests.fixtures.tasteskill_cases import TOOL_TASK


MODEL_ID = "Qwen314BQ4KM.gguf"


def run_validation(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    profile_before = (PATHS.config / "model.json").read_bytes()
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=root / "selection.json")
    initial = catalog.configuration(MODEL_ID)
    catalog.current_config = initial
    local = LazyInferenceEngine(lambda: LlamaServerInferenceEngine(catalog.configuration(MODEL_ID)),
        context_length=initial.context_length, max_response_tokens=initial.max_tokens)
    physical = []
    processes = []
    summary = {"schema_version": 1, "default_model_id": catalog.profiles.default_model_id,
               "scope": "default_14b_context_fix", "runs": [], "switches": [],
               "production_catalog": True, "full_local_read_enabled": True,
               "write_launch_approvals": "denied", "physical_requests": physical}
    artifact = root / "live-summary.json"

    def save():
        artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def factory(config):
        backend = LlamaServerInferenceEngine(config)
        actual = backend._request_completion
        def audit(payload):
            result = actual(payload)
            usage = result.get("usage", {})
            physical.append({"model_id": Path(config.model_path).name,
                "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                "tool_count": len(payload.get("tools", [])),
                "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
                "skill_sections": payload["messages"][0]["content"].count("\nACTIVE SKILL\n"),
                "finish_reason": result.get("choices", [{}])[0].get("finish_reason")})
            save()
            return result
        backend._request_completion = audit
        return backend

    local._factory = lambda: factory(catalog.configuration(MODEL_ID))
    inference = HybridInferenceEngine(local=local, cloud=None, model_catalog=catalog, local_factory=factory)
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(FIXTURE)
    scope = root / "portable"
    scope.mkdir(exist_ok=True)
    (scope / "index.html").write_text("<!doctype html><title>Fixture</title>", encoding="utf-8")
    flags = load_agent_feature_config()
    # Full-local relative paths resolve under user_home. Give the synthetic
    # session its own home so the unchanged stat request addresses its fixture.
    policy = HostAccessPolicy.full_local(application_root=scope, user_home=scope, acknowledged=True)
    runtime = build_agent_runtime(inference, config=flags, portable_root=scope, state_directory=scope / "state",
                                  host_access_policy=policy)
    service = ConversationService(inference, ConversationStore(scope / "conversation.json"),
        agent_runtime=runtime, portable_root=scope, host_access_policy=policy,
        skill_registry=installer.registry, automatic_skills_enabled=False)
    service.set_approval_requester(lambda record: service.resolve_approval(record.approval_id, False))

    def record_server():
        backend = inference.local._get_engine()
        backend.prepare()
        url, key, process = backend._ensure_started()
        if process not in processes:
            processes.append(process)
        request = Request(url + "/props", headers={"Authorization": "Bearer " + key})
        with urlopen(request, timeout=10) as response:
            props = json.load(response)
        context = props["default_generation_settings"]["n_ctx"]
        assert context == backend.context_length == inference.context_length
        if catalog.current_id == MODEL_ID:
            assert context == 16384
        resolution = catalog._resolutions[catalog.current_id]
        memory = detect_nvidia_memory_mib()
        allocation = resolution["gpu_before_load_mib"]["free"] - memory[1] if memory and resolution["gpu_before_load_mib"] else None
        if backend.config.gpu_layers != 0:
            assert memory and memory[1] >= memory[0] * 0.2
            assert allocation <= resolution["estimated_allocation_mib"]
        summary["switches"].append({"model_id": catalog.current_id, "server_context": context,
            "effective_output_reserve": backend.max_response_tokens, "gpu_layers": backend.config.gpu_layers,
            "cache_type": backend.config.cache_type, "model_sha256": resolution["sha256"],
            "gpu_after_load_mib": memory, "observed_gpu_allocation_mib": allocation,
            "estimated_gpu_allocation_mib": resolution["estimated_allocation_mib"],
            "sampling": backend.config.sampling_parameters(), "selection_reason": resolution["selection_reason"],
            "profile_target": resolution["target"], "gpu_before_load_mib": resolution["gpu_before_load_mib"]})
        save()
        print(json.dumps({"stage": "server", **summary["switches"][-1]}), flush=True)

    def run_case(case_id, request, skill=None):
        service.new_session()
        if skill:
            service.activate_skill(skill)
        start = len(physical)
        journal_start = len(runtime.executor.journal.records)
        reply = service.run(request)
        record = {"case_id": case_id, "model_id": catalog.current_id,
            "status": service._turn_result.status.value, "nonempty_reply": bool(str(reply).strip()),
            "incomplete": bool(reply.completion.incomplete), "context_budget": asdict(service.context_budget()),
            "physical_request_count": len(physical) - start,
            "successful_stat_calls": sum(r.capability == "filesystem.stat" and bool(r.result_success)
                                           for r in runtime.executor.journal.records[journal_start:]),
            "active_skill": service.active_skill.name if service.active_skill else None}
        if case_id == "css-explicit":
            record["assessment"] = assess_brand_reply("css", str(reply))
        summary["runs"].append(record)
        save()
        print(json.dumps({"stage": "run", **record}), flush=True)
        assert record["status"] == "completed" and record["nonempty_reply"] and not record["incomplete"]
        assert record["context_budget"]["remaining_tokens"] > 0
        return record

    try:
        record_server()
        run_case("hey-before", "hey")
        assert run_case("stat", TOOL_TASK)["successful_stat_calls"] > 0
        assert run_case("css-explicit", BRAND_TASKS[0][1], "brand-guidelines")["assessment"]["passed"]
        for model_id in ("model.gguf", MODEL_ID):
            previous = processes[-1]
            service.select_local_model(model_id)
            assert previous.poll() is not None
            record_server()
            run_case("small-switch" if model_id != MODEL_ID else "hey-after", "Reply with OK only." if model_id != MODEL_ID else "hey")
        assert catalog.selected_id() == MODEL_ID
        assert summary["switches"][0]["sampling"] == summary["switches"][-1]["sampling"]
        assert (PATHS.config / "model.json").read_bytes() == profile_before
        hashes = {r["tools_sha256"] for r in physical if r["tool_count"]}
        assert len(hashes) == 1 and all(r["tool_count"] == 12 for r in physical if r["tool_count"])
        summary["passed"] = True
    finally:
        service.shutdown()
        inference.close()
        summary["owned_servers_exited"] = all(p.poll() is not None for p in processes)
        save()
        assert summary["owned_servers_exited"]
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PATHS.state / "test-artifacts/default14b-fix/native")
    args = parser.parse_args()
    result = run_validation(args.root)
    print(json.dumps({"passed": result["passed"], "owned_servers_exited": result["owned_servers_exited"]}), flush=True)
