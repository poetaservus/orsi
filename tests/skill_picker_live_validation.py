"""Opt-in native 14B UI handoff audit with isolated state and two fixed prompts."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hashlib import sha256
import json
from pathlib import Path
from time import monotonic

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
from app.ui.main_window import MainWindow
from tests.simple_skill_live_validation import BRAND_TASKS, FIXTURE, assess_brand_reply
from tests.fixtures.tasteskill_cases import UNRELATED_TASKS


def run_validation(root):
    app = QApplication.instance() or QApplication([])
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    profile = PATHS.config / "model.json"
    profile_before = profile.read_bytes()
    catalog = LocalModelCatalog(PATHS.models, profile, load_model_config(), selection_path=root / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration("Qwen314BQ4KM.gguf"))
    installer = SkillInstaller(SkillRegistry(global_root=root / "skills"))
    installer.install(FIXTURE)
    scope = root / "portable"
    scope.mkdir(exist_ok=True)
    flags = load_agent_feature_config()
    policy = HostAccessPolicy.full_local(application_root=scope, user_home=scope, acknowledged=True)
    runtime = build_agent_runtime(backend, config=flags, portable_root=scope,
        state_directory=scope / "state", host_access_policy=policy)
    service = ConversationService(backend, ConversationStore(scope / "conversation.json"),
        agent_runtime=runtime, portable_root=scope, host_access_policy=policy,
        skill_registry=installer.registry, automatic_skills_enabled=False)
    service.set_approval_requester(lambda record: service.resolve_approval(record.approval_id, False))
    # Automatic routing is disabled only in this fixture to isolate explicit
    # attachment expiry. Production routing/configuration remains unchanged.
    ui = MainWindow(service, "TEST")
    summary = {"schema_version": 1, "model_id": "Qwen314BQ4KM.gguf", "passed": False,
        "fixture_automatic_selection": False, "write_launch_approvals": "denied", "physical_requests": []}
    actual = backend._request_completion
    def audit(payload):
        result = actual(payload)
        system = payload["messages"][0]["content"]
        usage = result.get("usage", {})
        summary["physical_requests"].append({
            "skill_sections": system.count("\nACTIVE SKILL\n"),
            "tool_count": len(payload.get("tools", [])),
            "tools_sha256": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest(),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "finish_reason": result.get("choices", [{}])[0].get("finish_reason"),
        })
        return result
    backend._request_completion = audit
    process = None
    def wait_turn():
        deadline = monotonic() + 180
        while ui.thread is not None and monotonic() < deadline:
            app.processEvents()
            QTest.qWait(20)
        if ui.thread is not None:
            raise RuntimeError("Native UI turn exceeded the audit deadline.")
    try:
        ui.show()
        app.processEvents()
        ui.input.setFocus()
        QTest.keyClicks(ui.input, "/skill brand")
        app.processEvents()
        assert ui.skill_picker.popup.isVisible() and ui.skill_picker.items.count() == 1
        ui.grab().save(str(root / "picker.png"))
        QTest.keyClick(ui.input, Qt.Key.Key_Return)
        assert ui.skill_picker.selected_name == "brand-guidelines"
        request = BRAND_TASKS[1][1]
        ui.input.setPlainText(request)
        app.processEvents()
        ui.grab().save(str(root / "chip.png"))
        backend.prepare()
        process = backend._process
        summary.update(effective_context=backend.context_length, output_reserve=backend.max_response_tokens)
        ui.send.click()
        wait_turn()
        first = ui.chat._messages[-1]
        (root / "fonts-review.txt").write_text(first.label.plain_text(), encoding="utf-8")
        summary.update(fonts_passed=assess_brand_reply("fonts", first.label.plain_text())["passed"],
            message_skill_expired=service.active_skill is None,
            chip_cleared=ui.skill_picker.selected_name is None,
            controls_released=ui.input.isEnabled() and ui.send.isEnabled())
        greeting = next(text for case_id, text in UNRELATED_TASKS if case_id == "greeting")
        ui.input.setPlainText(greeting)
        ui.send.click()
        wait_turn()
        summary["next_message_completed"] = service._turn_result.status.value == "completed"
        physical = summary["physical_requests"]
        summary["passed"] = (all(summary[key] is True for key in
            ("fonts_passed", "message_skill_expired", "chip_cleared", "controls_released", "next_message_completed"))
            and len(physical) == 2 and [r["skill_sections"] for r in physical] == [1, 0]
            and all(r["tool_count"] == 12 and r["finish_reason"] == "stop" for r in physical)
            and len({r["tools_sha256"] for r in physical}) == 1)
    finally:
        if ui.thread is not None:
            service.cancel_current_task()
        backend.close()
        if ui.thread is not None:
            wait_turn()
        ui.close()
        summary.update(owned_server_exited=process is None or process.poll() is not None,
                       model_profile_unchanged=profile.read_bytes() == profile_before)
        summary["passed"] = summary["passed"] and summary["owned_server_exited"] and summary["model_profile_unchanged"]
        (root / "live-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PATHS.state / "test-artifacts/skill-picker/native-ui")
    report = run_validation(parser.parse_args().root)
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if report["passed"] else 1)
