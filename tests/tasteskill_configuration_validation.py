"""Opt-in Phase 5.2 assessment of upstream conversational dials, not an engine.

This tests a concrete design plan with the unchanged, smaller upstream v1 skill.
It does not qualify generated websites or make the oversized v2 skill fit.
"""
from hashlib import sha256
import json
from pathlib import Path

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.runtime.skills import SkillInstaller, SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS


FIXTURE = Path(__file__).parent / "fixtures/tasteskill"
SKILL_NAME = "design-taste-frontend-v1"
# Frozen before the first inference. These are new assessment stimuli, not edits
# to Phase 5.1 or model acceptance prompts. Every case uses the same base task.
TASK = (
    "For a SaaS metrics page, choose a concrete design plan using the active skill. "
    "Return JSON only with exactly these keys: DESIGN_VARIANCE, MOTION_INTENSITY, "
    "VISUAL_DENSITY (integer effective dial values); layout (symmetric or asymmetric); "
    "motion (static or animated); density (airy, normal, or dense); "
    "implementation (one short sentence describing the actual grid, motion and metric spacing). "
    "Do not create files or use tools."
)
CASES = (
    ("default", "", (8, 6, 4), ("asymmetric", "animated", "normal")),
    ("one_override", "For this design use MOTION_INTENSITY: 1. ",
     (8, 1, 4), ("asymmetric", "static", "normal")),
    ("multiple_overrides", "For this design use DESIGN_VARIANCE: 2, MOTION_INTENSITY: 1, "
     "and VISUAL_DENSITY: 9. ", (2, 1, 9), ("symmetric", "static", "dense")),
    ("new_session_default", "", (8, 6, 4), ("asymmetric", "animated", "normal")),
)
DIAL_KEYS = ("DESIGN_VARIANCE", "MOTION_INTENSITY", "VISUAL_DENSITY")
PLAN_KEYS = ("layout", "motion", "density")


def assess_reply(reply, dials, plan):
    """Require applied choices as well as values; never accept an echoed prompt."""
    try:
        data = json.loads(reply)
    except (ValueError, TypeError):
        return {"json_valid": False, "passed": False}
    if not isinstance(data, dict):
        return {"json_valid": False, "passed": False}
    checks = {
        "json_valid": True,
        "exact_fields": set(data) == {*DIAL_KEYS, *PLAN_KEYS, "implementation"},
        "effective_values_match": all(type(data.get(key)) is int and data[key] == value
                                      for key, value in zip(DIAL_KEYS, dials)),
        "design_choices_match": all(data.get(key) == value for key, value in zip(PLAN_KEYS, plan)),
        "implementation_present": isinstance(data.get("implementation"), str)
                                  and bool(data["implementation"].strip()),
    }
    return {**checks, "passed": all(checks.values())}


def finalize_summary(summary):
    runs, physical = summary["runs"], summary["physical_requests"]
    expected = [case[0] for case in CASES]
    summary["assessment_passed"] = (
        [run["case_id"] for run in runs] == expected
        and all(run.get("assessment", {}).get("passed") is True
                and run.get("completed") is True and run.get("incomplete") is False
                and run.get("active_skill") == SKILL_NAME for run in runs)
        and len(physical) == len(CASES)
        and all(record["skill_body_exact"] is True and record["skill_sections"] == 1
                and record["tool_count"] == summary["production_tool_count"] for record in physical)
        and len({record["tools_sha256"] for record in physical}) == 1
        and summary.get("upstream_bytes_unchanged") is True
        and summary.get("model_profile_unchanged") is True
        and summary.get("owned_server_exited") is True
    )


def run_validation(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = FIXTURE / "skills/taste-skill-v1/SKILL.md"
    original = source.read_bytes()
    profile = PATHS.config / "model.json"
    profile_before = profile.read_bytes()
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(source.parent)
    skill = installer.info(SKILL_NAME)
    catalog = LocalModelCatalog(PATHS.models, profile, load_model_config(),
                                selection_path=root / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration("Qwen314BQ4KM.gguf"))
    scope = root / "portable"
    scope.mkdir(exist_ok=True)
    policy = HostAccessPolicy.full_local(application_root=scope, user_home=scope, acknowledged=True)
    runtime = build_agent_runtime(backend, config=load_agent_feature_config(), portable_root=scope,
                                  state_directory=scope / "state", host_access_policy=policy)
    service = ConversationService(backend, ConversationStore(scope / "conversation.json"),
        agent_runtime=runtime, portable_root=scope, host_access_policy=policy,
        skill_registry=installer.registry, automatic_skills_enabled=False)
    service.set_approval_requester(lambda record: service.resolve_approval(record.approval_id, False))
    summary = {"schema_version": 1, "scope": "phase_5_2_conversational_dial_assessment",
        "model_id": "Qwen314BQ4KM.gguf", "skill_name": SKILL_NAME,
        "upstream_revision": json.loads((FIXTURE / "manifest.json").read_text())["revision"],
        "upstream_sha256": sha256(original).hexdigest(),
        "production_tool_count": len(runtime.registry.model_definitions()),
        "host_reads": "isolated_synthetic_home", "write_launch_approvals": "denied",
        "persistent_override_engine_added": False, "assessment_passed": False,
        "runs": [], "physical_requests": []}
    artifact = root / "live-summary.json"

    def save():
        artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    actual = backend._request_completion

    def audit(payload):
        result = actual(payload)
        system = payload["messages"][0]["content"]
        sections = system.count("\nACTIVE SKILL\n")
        exact = False
        if sections == 1:
            encoded = system.split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0]
            exact = json.loads(encoded) == {"name": skill.name, "instructions": skill.instructions}
        usage = result.get("usage", {})
        summary["physical_requests"].append({
            "skill_sections": sections, "skill_body_exact": exact,
            "tool_count": len(payload.get("tools", [])),
            "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "finish_reason": result.get("choices", [{}])[0].get("finish_reason"),
        })
        save()
        return result

    backend._request_completion = audit
    process = None
    try:
        backend.prepare()
        process = backend._process
        summary.update(effective_context=backend.context_length,
                       effective_output_reserve=backend.max_response_tokens,
                       body_tokens=backend._live_token_count(skill.instructions))
        save()
        print(json.dumps({"stage": "prepared", "context": backend.context_length,
                          "output": backend.max_response_tokens}), flush=True)
        for case_id, prefix, dials, plan in CASES:
            # Same service, cleared history: proves overrides cannot leak into a
            # fresh conversation, while leaving installed bytes untouched.
            service.new_session()
            service.activate_skill(SKILL_NAME)
            record = {"case_id": case_id, "completed": False}
            summary["runs"].append(record)
            try:
                reply = service.run(prefix + TASK)
                record.update(completed=True, incomplete=bool(getattr(reply, "completion", None)
                              and reply.completion.incomplete), active_skill=service.active_skill.name,
                              assessment=assess_reply(str(reply), dials, plan),
                              capability_calls=service._turn_result.capability_calls)
                # Synthetic answers stay separate from the content-free summary.
                (root / (case_id + "-review.txt")).write_text(str(reply), encoding="utf-8")
            except Exception as error:
                record.update(error_type=type(error).__name__,
                              error_code=getattr(getattr(error, "code", None), "value", None))
            save()
            print(json.dumps({"stage": "case", **record}), flush=True)
    finally:
        try:
            service.shutdown()
        finally:
            backend.close()
        summary.update(owned_server_exited=process is None or process.poll() is not None,
                       upstream_bytes_unchanged=source.read_bytes() == original
                       and skill.source_path.read_bytes() == original,
                       model_profile_unchanged=profile.read_bytes() == profile_before)
        finalize_summary(summary)
        save()
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PATHS.state / "test-artifacts/skill-phase5-2")
    args = parser.parse_args()
    report = run_validation(args.root)
    print(json.dumps({key: report[key] for key in
                      ("assessment_passed", "owned_server_exited", "model_profile_unchanged",
                       "upstream_bytes_unchanged", "persistent_override_engine_added")}), flush=True)
    raise SystemExit(0 if report["assessment_passed"] else 1)
