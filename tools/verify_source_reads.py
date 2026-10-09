"""Opt-in Phase 2 cloud gate using synthetic source and content-free summaries."""
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
from app.inference.cloud_errors import CloudInferenceError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config
from tests.fixtures.source_reads import python_source_fixture
from tools.verify_routing_intent import screenshot


def verify(output: Path, key_file: Path, *, oversized_only=False):
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
    scenarios = [(skill, small, False) for skill in (False, True) for small in (False, True)]
    scenarios.append((False, True, True))
    if oversized_only:
        scenarios = [(False, True, True)]
    for skill, small, oversized in scenarios:
        cell = {"skill": skill, "default_first_read": small, "oversized": oversized, "status": "failed"}
        report["cases"].append(cell)
        if skill and skill_source is None:
            cell.update(status="skipped", error_category="installed_skill_unavailable")
            save()
            continue
        folder = output / f"case-{len(report['cases'])}"
        folder.mkdir()
        portable = folder / "portable"
        portable.mkdir()
        target = folder / "main.py"
        source = python_source_fixture()
        if oversized:
            # Target lies beyond both supported limits, with no private program content.
            source = b"# synthetic padding " + b"x" * 50 + b"\r\n"
            source = source * 1100 + b"def draw_overlay(values):\r\n    return sum(values) - 1\r\n"
        target.write_bytes(source)
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
            allowed = (not oversized and record.capability == "filesystem.edit_text"
                and record.resource is not None and Path(record.resource).resolve() == target.resolve())
            approved.append(allowed)
            service.resolve_approval(record.approval_id, allowed)

        service.set_approval_requester(approve)
        try:
            reference = service.store.attachment_store.import_bytes(screenshot(), name="bug.png")
            prompt = (f'Fix "{target}" in place. Do not create another version of the file. '
                'The attached screenshot shows draw_overlay([2, 3]) returning 4 instead of 5. '
                'Make draw_overlay return the sum of its values, preserving unrelated source and line endings. '
                'Read the current file before changing it. '
                'Report which file you changed and which checks you could actually run.')
            if small:
                prompt += ' Make the first source read with max_bytes=16384 and max_lines=200.'
            if oversized:
                prompt += ' If the available source reads cannot reach the method, stop and report the concrete read limitation.'
            kwargs = {"skill_name": "python-coder"} if skill else {}
            decision = service.image_route_decision(prompt, attachments=(reference,), **kwargs)
            answer = service.run(prompt, attachments=(reference,), **kwargs)
            turn = service.store.turns()[-1]
            reads = [c for c in turn.settled_calls if c.call.capability == "filesystem.read_text" and c.result.success]
            edits = [c for c in turn.settled_calls if c.call.capability == "filesystem.edit_text" and c.result.success]
            cell.update(route=decision.route, terminal_status=turn.outcome.status.value,
                calls=len(turn.settled_calls), model_requests=turn.outcome.model_requests,
                failed_calls=sum(not c.result.success for c in turn.settled_calls),
                reads=len(reads), edits=len(edits), approved=sum(approved), denied=len(approved) - sum(approved),
                generated_images=len(answer.generated_images), source_bytes=len(source), source_lines=len(source.splitlines()),
                first_read_truncated=bool(reads and not reads[0].result.output.get("source_complete", False)),
                complete_reads=sum(c.result.output.get("source_complete", False) for c in reads),
                read_outputs_limited=sum(c.result.metadata.get("output_limited", False) for c in reads))
            assert decision.route == "agent" and not answer.generated_images
            assert turn.outcome.status.value == "completed" and reads
            if small:
                assert reads[0].call.arguments.get("max_bytes", 16384) == 16384
                assert reads[0].call.arguments.get("max_lines", 200) == 200
                assert cell["first_read_truncated"]
            if oversized:
                assert not edits and not any(approved) and target.read_bytes() == source
                # The existing executor can replace an oversized JSON result with
                # a marked preview. It is incomplete evidence; its JSON digest is
                # not a file revision. The fixed read hint precedes source text.
                hints = [c.result.output.get("read_hint") or
                    c.result.output.get("_orsi_output_limited", {}).get("preview", "") for c in reads]
                assert any("Source is truncated at the supported" in hint for hint in hints)
                assert "limit" in str(answer).casefold() or "truncat" in str(answer).casefold()
                cell["limitation_reported"] = True
            else:
                assert len(edits) == 1 and target.read_bytes() == source.replace(b"sum(values) - 1", b"sum(values)")
                latest_read = None
                for call in turn.settled_calls:
                    if call.call.capability == "filesystem.read_text" and call.result.success:
                        latest_read = call.result.output
                    if call in edits:
                        assert latest_read and latest_read.get("source_complete", False)
                        assert call.call.arguments["old_text"] in latest_read["text"]
                        if call.call.arguments.get("expected_sha256") is not None:
                            assert call.call.arguments["expected_sha256"] == latest_read["sha256"]
                cell["grounded_edit"] = True
            assert sorted(p.name for p in folder.glob("*.py")) == ["main.py"]
            cell.update(status="passed", bytes_verified=True)
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
    parser.add_argument("--oversized-only", action="store_true")
    args = parser.parse_args()
    result = verify(args.output.resolve(), args.key_file, oversized_only=args.oversized_only)
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
