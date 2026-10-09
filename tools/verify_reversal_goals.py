"""Opt-in live reassessment of a safely rejected synthetic reversal.

The first three model responses are controlled setup, not live model successes.
Only the subsequent reassessment uses the configured OpenAI model. Credentials
stay in memory; the summary contains counts/categories and receipt hashes only.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import PermissionClass
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config


class ReassessmentEngine(OpenAIResponsesInferenceEngine):
    def __init__(self, *args, target, **kwargs):
        super().__init__(*args, **kwargs)
        self.live_requests = 0
        calls = [("filesystem.read_text", {"path": str(target)}),
            ("filesystem.edit_text", {"path": str(target), "old_text": "VALUE = 'old'", "new_text": "VALUE = 'new'"}),
            ("filesystem.edit_text", {"path": str(target), "old_text": "VALUE = 'new'", "new_text": "VALUE = 'old'"})]
        self.setup = [ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"setup-{i}",
            capability=name, arguments=arguments),)) for i, (name, arguments) in enumerate(calls, 1)]

    def respond_with_capabilities(self, messages, capabilities):
        if self.setup:
            return self.setup.pop(0)
        self.live_requests += 1
        return super().respond_with_capabilities(messages, capabilities)


def verify(output: Path, key_file: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    with key_file.open(encoding="utf-8-sig") as stream:
        key = stream.readline().strip()
    if not key:
        return {"passed": False, "error_category": "credential_unavailable"}
    output.mkdir(parents=True, exist_ok=False)
    installed = SkillRegistry()
    installed.discover()
    definition = installed.get("python-coder")
    source = definition.source_path.parent if definition else None
    identity = sha256((source / "SKILL.md").read_bytes()).hexdigest() if source else None
    cloud = load_cloud_config()
    report = {"passed": False, "model": cloud.default_model, "cases": [],
        "setup_is_synthetic": True, "runtime_execution": False, "gui_validation": False}

    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for use_skill in (False, True):
        cell = {"skill": use_skill, "status": "failed", "synthetic_setup_responses": 3}
        report["cases"].append(cell)
        save()
        folder = output / f"case-{len(report['cases'])}"
        folder.mkdir()
        portable = folder / "portable"
        portable.mkdir()
        target = folder / "main.py"
        target.write_bytes(b"VALUE = 'old'\r\nKEEP = True\r\n")
        registry = SkillRegistry(global_root=folder / "skills")
        if use_skill:
            if source is None:
                cell.update(status="skipped", error_category="installed_skill_unavailable")
                save()
                continue
            shutil.copytree(source, registry.global_root / "python-coder")
            registry.discover()
        engine = ReassessmentEngine(cloud, api_key=key, target=target, selection_path=folder / "selection.json")
        policy = HostAccessPolicy.full_local(application_root=portable, user_home=folder, acknowledged=True)
        config = load_agent_feature_config()
        # This isolated qualification has a smaller ceiling; production limits stay unchanged.
        config = config.model_copy(update={"runtime_limits": config.runtime_limits.model_copy(update={
            "cloud_max_steps": 12, "cloud_max_model_requests": 12, "cloud_max_capability_calls": 20,
            "overall_timeout_seconds": 180.0})})
        runtime = build_agent_runtime(engine, config=config, portable_root=portable,
            state_directory=portable / "state", host_access_policy=policy)
        runtime.permission_gate = PermissionGate((*runtime.permission_gate.rules,
            PermissionRule("fixture-read-deny", PermissionDecision.DENY, permission=PermissionClass.READ),
            PermissionRule("fixture-read-allow", PermissionDecision.ALLOW, permission=PermissionClass.READ, resource_root=folder),
            PermissionRule("fixture-write-deny", PermissionDecision.DENY, permission=PermissionClass.WRITE),
            PermissionRule("fixture-write-ask", PermissionDecision.ASK, permission=PermissionClass.WRITE, resource_root=folder),
            PermissionRule("fixture-execute-deny", PermissionDecision.DENY, permission=PermissionClass.EXECUTE)))
        service = ConversationService(engine, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
            portable_root=portable, allowed_read_roots=(folder,), host_access_policy=policy, skill_registry=registry)
        approvals = []

        def approve(record):
            approvals.append(record)
            service.resolve_approval(record.approval_id, True)

        service.set_approval_requester(approve)
        try:
            kwargs = {"skill_name": "python-coder"} if use_skill else {}
            answer = service.run(f"In {target}, change VALUE from 'old' to 'new', preserve KEEP, "
                "and verify the saved source with available tools. Finish when this change is saved. "
                "Report remaining or unrun checks.", **kwargs)
            turn = service.store.turns()[-1]
            blocked = [item for item in turn.settled_calls if item.result.metadata.get("edit_recovery") == "revision_reversal"]
            saved = [item for item in turn.settled_calls if item.result.success and
                item.call.capability in {"filesystem.edit_text", "filesystem.write_text"}]
            goal = turn.goal
            cell.update(terminal_status=turn.outcome.status.value, live_requests=engine.live_requests,
                approved_mutations=len(approvals), successful_mutations=len(saved), blocked_reversals=len(blocked),
                failed_calls=sum(not item.result.success for item in turn.settled_calls),
                source_checked=bool(goal and goal.artifacts and goal.artifacts[0].source_check_call_id),
                goal_state=goal.state if goal else "missing", behaviour_verified=bool(goal and goal.behaviour_verified),
                goal_restored=ConversationStore(service.store.path).turns()[-1].goal == goal,
                final_sha256=sha256(target.read_bytes()).hexdigest(), catalog_size=len(runtime.registry.model_definitions()))
            assert target.read_bytes() == b"VALUE = 'new'\r\nKEEP = True\r\n"
            assert turn.outcome.status.value == "completed" and engine.live_requests > 0
            assert len(blocked) == len(saved) == len(approvals) == 1 and cell["failed_calls"] == 1
            assert cell["source_checked"] and cell["goal_restored"]
            assert goal.state == "reported_unverified" and not goal.behaviour_verified
            assert str(answer) == turn.outcome.assistant_text
            cell["status"] = "passed"
        except Exception as exc:
            cell["error_category"] = type(exc).__name__
        finally:
            runner = engine._runner
            service.shutdown()
            cell["transport_released"] = runner is None or runner._thread is None or not runner._thread.is_alive()
            save()
    del key
    report["skill_preserved"] = source is None or sha256((source / "SKILL.md").read_bytes()).hexdigest() == identity
    report["passed"] = all(cell["status"] == "passed" and cell["transport_released"] for cell in report["cases"]) and report["skill_preserved"]
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output.resolve(), args.key_file)
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
