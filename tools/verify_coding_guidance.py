"""Opt-in Phase 3 cloud gate: finite requested changes and honest verification."""
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
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config
from tests.fixtures.source_reads import python_source_fixture
from tools.verify_routing_intent import screenshot


def verification_disclosure(answer):
    """English qualification report check; not a production response rewriter."""
    unrun, claimed_execution = False, False
    for clause in re.split(r"[.!?;\n]+", str(answer).casefold()):
        checks = re.search(r"\b(?:python|imports?|gui|tests?|execution|runtime)\b", clause)
        negation = re.search(r"\b(?:not|no|unrun|unavailable|cannot|can't|didn't|didn’t|haven't|haven’t|couldn't|couldn’t|wasn't|wasn’t)\b", clause)
        if checks and negation:
            unrun = True
        positive = re.search(
            r"\b(?:ran|executed|tested|passed)\b.{0,100}\b(?:python|imports?|gui|tests?|app)\b|"
            r"\b(?:python|imports?|gui|tests?|app)\b.{0,100}\b(?:ran|executed|tested|passed)\b", clause)
        if positive and not negation:
            claimed_execution = True
    return unrun, claimed_execution


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
    skill_digest = sha256((skill_source / "SKILL.md").read_bytes()).hexdigest() if skill_source else None
    config = load_cloud_config()
    report = {"passed": False, "cloud_model": config.default_model, "skill_identity": skill_digest,
        "cases": [], "python_execution_by_agent": False, "gui_execution": False}

    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    for skill in (False, True):
        for copy in (False, True):
            cell = {"skill": skill, "workflow": "requested_copies" if copy else "existing_fixes", "status": "failed"}
            report["cases"].append(cell)
            if skill and skill_source is None:
                cell.update(status="skipped", error_category="installed_skill_unavailable")
                save()
                continue
            folder = output / f"case-{len(report['cases'])}"
            folder.mkdir()
            portable = folder / "portable"
            portable.mkdir()
            originals = {folder / "main.py": python_source_fixture(),
                folder / "helpers.py": b"def item_count(values):\r\n    return len(values) - 1\r\n"}
            destinations = {path: path.with_name(path.stem + "_v2.py") if copy else path for path in originals}
            fixed = {destinations[path]: raw.replace(b"sum(values) - 1", b"sum(values)").replace(
                b"len(values) - 1", b"len(values)") for path, raw in originals.items()}
            for path, raw in originals.items():
                path.write_bytes(raw)
            registry = SkillRegistry(global_root=folder / "skills")
            if skill:
                shutil.copytree(skill_source, registry.global_root / "python-coder")
                registry.discover()
            engine = OpenAIResponsesInferenceEngine(config, api_key=key, selection_path=folder / "cloud-selection.json")
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
                allowed = (record.capability in ({"filesystem.copy", "filesystem.write_text", "filesystem.edit_text"} if copy else {"filesystem.edit_text"})
                    and record.resource is not None and Path(record.resource).resolve() in fixed)
                approved.append(allowed)
                service.resolve_approval(record.approval_id, allowed)

            service.set_approval_requester(approve)
            try:
                main, helpers = originals
                prompt = (f'Create a new copy of "{main}" at "{destinations[main]}" and of "{helpers}" at "{destinations[helpers]}". '
                    'Implement the fixes only in those copies and preserve both original files. ' if copy else
                    f'Fix "{main}" and "{helpers}" in place. Do not create another version of either file. ')
                prompt += ('The attached screenshot shows draw_overlay([2, 3]) returning 4 instead of 5. '
                    'Make draw_overlay return the sum of its values. Also fix item_count([2, 3]), '
                    'which returns 1 instead of 2: make item_count return the number of values. '
                    'Complete both requested fixes, preserving unrelated source and line endings. '
                    'Read current source before changing it and verify the saved text with available tools. '
                    'Report which versions contain the changes and which checks you actually performed or could not run.')
                reference = service.store.attachment_store.import_bytes(screenshot(), name="bug.png")
                kwargs = {"skill_name": "python-coder"} if skill else {}
                decision = service.image_route_decision(prompt, attachments=(reference,), **kwargs)
                answer = service.run(prompt, attachments=(reference,), **kwargs)
                turn = service.store.turns()[-1]
                unrun, claimed_execution = verification_disclosure(answer)
                mutations = [c for c in turn.settled_calls if c.call.capability in {
                    "filesystem.edit_text", "filesystem.write_text", "filesystem.copy"} and c.result.success]
                cell.update(route=decision.route, catalog_size=len(runtime.registry.model_definitions()),
                    terminal_status=turn.outcome.status.value, calls=len(turn.settled_calls),
                    model_requests=turn.outcome.model_requests, semantic_corrections=turn.outcome.semantic_corrections,
                    failed_calls=sum(not c.result.success for c in turn.settled_calls),
                    mutations=len(mutations), approved=sum(approved), denied=len(approved) - sum(approved),
                    generated_images=len(answer.generated_images), unrun_checks_disclosed=unrun,
                    claimed_unavailable_execution=claimed_execution)
                assert decision.route == "agent" and not answer.generated_images
                assert turn.outcome.status.value == "completed"
                assert all(path.read_bytes() == expected for path, expected in fixed.items())
                assert all(path.name in str(answer) for path in fixed)
                assert unrun and not claimed_execution
                assert 2 <= len(mutations) <= (4 if copy else 2)
                assert len(approved) == sum(approved) == len(mutations)
                reads = {}
                for call in turn.settled_calls:
                    if call.call.capability == "filesystem.read_text" and call.result.success:
                        out = call.result.output
                        if out.get("path") and isinstance(out.get("text"), str):
                            reads[Path(out["path"])] = out
                    if call.call.capability == "filesystem.edit_text" and call.result.success:
                        out = reads.get(Path(call.call.arguments["path"]))
                        assert out and call.call.arguments["old_text"] in out["text"]
                        if call.call.arguments.get("expected_sha256") is not None:
                            assert call.call.arguments["expected_sha256"] == out["sha256"]
                if copy:
                    assert all(path.read_bytes() == raw for path, raw in originals.items())
                assert set(folder.glob("*.py")) == set(originals) | set(fixed)
                cell.update(status="passed", bytes_verified=True, originals_preserved=copy,
                    completed_requested_changes=2, grounded_edits=True)
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
    report["skill_source_preserved"] = skill_digest is None or sha256((skill_source / "SKILL.md").read_bytes()).hexdigest() == skill_digest
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
