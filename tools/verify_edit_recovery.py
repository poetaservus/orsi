"""Opt-in cloud recovery gate: seeded native rejections, frozen Phase 2 requests."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import PermissionClass
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_errors import CloudInferenceError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config
from tests.fixtures.source_reads import python_source_fixture
from tools.verify_coding_guidance import verification_disclosure
from tools.verify_routing_intent import screenshot


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
    skill_source = definition.source_path.parent if definition else None
    identity = sha256((skill_source / "SKILL.md").read_bytes()).hexdigest() if skill_source else None
    config = load_cloud_config()
    report = {"passed": False, "cloud_model": config.default_model, "skill_identity": identity,
        "cases": [], "python_execution_by_agent": False, "gui_execution": False}

    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for skill in (False, True):
        for rejection in ("missing_match", "stale_digest", "no_change"):
            cell = {"skill": skill, "seeded_rejection": rejection, "status": "failed"}
            report["cases"].append(cell)
            save()
            if skill and skill_source is None:
                cell.update(status="skipped", error_category="installed_skill_unavailable")
                continue
            folder = output / f"case-{len(report['cases'])}"
            portable = folder / "portable"
            portable.mkdir(parents=True)
            target = folder / "main.py"
            original = python_source_fixture()
            expected = original.replace(b"sum(values) - 1", b"sum(values)")
            source = expected if rejection == "no_change" else original
            target.write_bytes(source)
            registry = SkillRegistry(global_root=folder / "skills")
            if skill:
                shutil.copytree(skill_source, registry.global_root / "python-coder")
                registry.discover()
            engine = OpenAIResponsesInferenceEngine(config, api_key=key, selection_path=folder / "cloud-selection.json")
            actual_respond = engine.respond_with_capabilities
            seeded = False

            def respond(messages, capabilities):
                nonlocal seeded
                if not seeded:
                    seeded = True
                    args = {"path": str(target), "old_text": "return sum(values) - 1",
                        "new_text": "return sum(values)"}
                    if rejection == "missing_match":
                        args["old_text"] = "return sum(values) - 999"
                    elif rejection == "stale_digest":
                        args["expected_sha256"] = "0" * 64
                    else:
                        args["old_text"] = args["new_text"]
                    return ModelResponse.calls((ModelCapabilityCall(provider_call_id="seeded-rejection",
                        capability="filesystem.edit_text", arguments=args),))
                return actual_respond(messages, capabilities)

            engine.respond_with_capabilities = respond
            policy = HostAccessPolicy.full_local(application_root=portable, user_home=folder, acknowledged=True)
            runtime = build_agent_runtime(engine, config=load_agent_feature_config(), portable_root=portable,
                state_directory=portable / "state", host_access_policy=policy)
            runtime.permission_gate = PermissionGate((*runtime.permission_gate.rules,
                PermissionRule("fixture-read-deny", PermissionDecision.DENY, permission=PermissionClass.READ),
                PermissionRule("fixture-read-allow", PermissionDecision.ALLOW, permission=PermissionClass.READ, resource_root=folder),
                PermissionRule("fixture-write-deny", PermissionDecision.DENY, permission=PermissionClass.WRITE),
                PermissionRule("fixture-write-ask", PermissionDecision.ASK, permission=PermissionClass.WRITE, resource_root=folder),
                PermissionRule("fixture-execute-deny", PermissionDecision.DENY, permission=PermissionClass.EXECUTE)))
            service = ConversationService(engine, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
                portable_root=portable, allowed_read_roots=(folder,), host_access_policy=policy, skill_registry=registry)
            approved = []

            def approve(record):
                allowed = (rejection != "no_change" and record.capability == "filesystem.edit_text"
                    and record.resource is not None and Path(record.resource).resolve() == target.resolve())
                approved.append(allowed)
                service.resolve_approval(record.approval_id, allowed)

            service.set_approval_requester(approve)
            try:
                # Keep the existing Phase 2 natural request verbatim, apart from fixture path.
                prompt = (f'Fix "{target}" in place. Do not create another version of the file. '
                    'The attached screenshot shows draw_overlay([2, 3]) returning 4 instead of 5. '
                    'Make draw_overlay return the sum of its values, preserving unrelated source and line endings. '
                    'Read the current file before changing it. '
                    'Report which file you changed and which checks you could actually run.')
                reference = service.store.attachment_store.import_bytes(screenshot(), name="bug.png")
                kwargs = {"skill_name": "python-coder"} if skill else {}
                decision = service.image_route_decision(prompt, attachments=(reference,), **kwargs)
                answer = service.run(prompt, attachments=(reference,), **kwargs)
                turn = service.store.turns()[-1]
                calls = turn.settled_calls
                edits = [c for c in calls if c.call.capability == "filesystem.edit_text" and c.result.success]
                unrun, claimed = verification_disclosure(answer)
                cell.update(route=decision.route, catalog_size=len(runtime.registry.model_definitions()),
                    terminal_status=turn.outcome.status.value, calls=len(calls), model_requests=turn.outcome.model_requests,
                    semantic_corrections=turn.outcome.semantic_corrections, failed_calls=sum(not c.result.success for c in calls),
                    approved=sum(approved), denied=len(approved)-sum(approved), successful_edits=len(edits),
                    generated_images=len(answer.generated_images), unrun_checks_disclosed=unrun,
                    claimed_unavailable_execution=claimed)
                assert decision.route == "agent" and not answer.generated_images and turn.outcome.status.value == "completed"
                assert calls and not calls[0].result.success and calls[0].result.error.code.value == "invalid_arguments"
                assert target.read_bytes() == expected and sorted(p.name for p in folder.glob("*.py")) == ["main.py"]
                assert unrun and not claimed and target.name in answer
                assert len(edits) == sum(approved) == (0 if rejection == "no_change" else 1) and not cell["denied"]
                latest = None
                for item in calls[1:]:
                    if item.call.capability == "filesystem.read_text" and item.result.success:
                        if item.result.output.get("path") == str(target):
                            latest = item.result.output
                    if item in edits:
                        assert latest and item.call.arguments["old_text"] in latest.get("text", "")
                        if item.call.arguments.get("expected_sha256") is not None:
                            assert item.call.arguments["expected_sha256"] == latest.get("sha256")
                assert latest and latest.get("source_complete") is True
                if rejection == "no_change":
                    assert re.search(r"\balready\b|\bno\b.{0,30}\b(?:changes?|edits?|modifications?)\b|\bunchanged\b", str(answer).casefold())
                cell.update(status="passed", bytes_verified=True, fresh_sufficient_read=True,
                    no_change_remained_failed=calls[0].result.success is False)
            except CloudInferenceError as exc:
                cell["error_category"] = exc.code.value
            except Exception as exc:
                cell["error_category"] = type(exc).__name__
            finally:
                if service.store.turns():
                    turn = service.store.turns()[-1]
                    if turn.outcome:
                        cell.setdefault("terminal_status", turn.outcome.status.value)
                        cell.setdefault("calls", len(turn.settled_calls))
                        cell["tool_errors"] = [c.result.error.code.value for c in turn.settled_calls if c.result.error]
                runner = engine._runner
                service.shutdown()
                cell["transport_released"] = runner is None or runner._thread is None or not runner._thread.is_alive()
                save()
    del key
    report["skill_source_preserved"] = identity is None or sha256((skill_source / "SKILL.md").read_bytes()).hexdigest() == identity
    report["passed"] = all(c["status"] == "passed" and c["transport_released"] for c in report["cases"]) and report["skill_source_preserved"]
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
