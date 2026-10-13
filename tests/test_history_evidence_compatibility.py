"""Read the frozen scroll-repair history format without importing its runtime changes."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.capabilities.contracts import CapabilityResult
from app.conversation.store import Conversation, ConversationStore, TurnHistoryError
from app.inference.protocol import ModelCapabilityCall


def saved_repair_history(*, interrupted=False, legacy=False):
    """Independent fixture matching 97a9648's persisted evidence, not today's projection."""
    root = "C:/synthetic-project"
    screenshot = root + "/inspection.png"
    digest = "a" * 64
    calls, verification = [], []
    for index, kind in enumerate(("build", "browser"), 1):
        capability = "project.verify" if kind == "build" else "project.inspect"
        output = {"project_path": root, "passed": True}
        item = {"call_id": f"receipt-{index}", "project_path": root, "kind": kind,
                "passed": True, "stale": False, "screenshot_path": None}
        if not legacy:
            output["evidence_version"] = 2
            item.update(command_passed=kind == "build" or None, interaction_assertions=[],
                        visual_observations=[], frame_timing_captured=False)
            if kind == "browser":
                output.update(screenshot_path=screenshot, screenshot_sha256=digest,
                    checks=[{"action": "text", "target": "#title", "label": "title", "passed": True},
                            {"action": "checkpoint", "target": "#model", "label": "behind text",
                             "expectation": "observe", "passed": True},
                            {"action": "scroll", "target": "#scene", "passed": True,
                             "frame_timing": {"samples": 2}}],
                    checkpoints=[{"label": "behind text", "screenshot_path": screenshot,
                                  "screenshot_sha256": digest}])
                item.update(screenshot_path=screenshot, frame_timing_captured=True,
                    interaction_assertions=[{"action": "text", "target": "#title", "label": "title", "passed": True},
                                            {"action": "scroll", "target": "#scene", "label": "", "passed": True}],
                    visual_observations=[{"label": label, "screenshot_path": screenshot,
                                          "screenshot_sha256": digest, "status": "requires_review"}
                                         for label in ("behind text", "final")])
        settled = SettledCall(provider_message_id=f"scope-{index}",
            call=ModelCapabilityCall(provider_call_id=f"call-{index}", capability=capability,
                                     arguments={"project_path": root, "kind": kind}),
            result=CapabilityResult(call_id=f"receipt-{index}", capability=capability,
                                    success=True, output=output, duration_ms=1))
        calls.append(settled.model_dump(mode="json"))
        verification.append(item)
    goal = {"goal_id": "turn-1", "objective": "Synthetic saved request", "artifacts": [],
            "verification": verification, "behaviour_verified": False, "unavailable_checks": [],
            "state": "active" if interrupted else "stopped"}
    outcome = AgentRunResult(status=AgentRunStatus.SEMANTIC_CORRECTION_LIMIT,
        message="Synthetic stopped task", steps=2, capability_calls=2, protocol_failures=0).model_dump(mode="json")
    outcome["goal"] = deepcopy(goal)
    payload = Conversation().model_dump(mode="json")
    payload["messages"] = [{"role": "user", "content": goal["objective"]}]
    if not interrupted:
        payload["messages"].append({"role": "assistant", "content": "Synthetic stopped task"})
    payload["turns"] = [{"turn_id": "turn-1", "user_index": 0,
        "assistant_index": None if interrupted else 1, "ended_at": None if interrupted else "2026-10-13T00:00:00Z",
        "goal": goal, "outcome": None if interrupted else outcome, "settled_calls": calls}]
    return payload


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("stale", [False, True])
def test_saved_history_restores_and_archives_without_replaying(tmp_path, legacy, interrupted, stale):
    payload = saved_repair_history(legacy=legacy, interrupted=interrupted)
    if stale:
        turn = payload["turns"][0]
        turn["settled_calls"].append(SettledCall(provider_message_id="scope-3",
            call=ModelCapabilityCall(provider_call_id="call-3", capability="shell.run", arguments={}),
            result=CapabilityResult(call_id="receipt-3", capability="shell.run", success=True,
                                    output={}, duration_ms=1)).model_dump(mode="json"))
        for item in turn["goal"]["verification"]:
            item["stale"] = True
        if turn["outcome"] is not None:
            turn["outcome"].update(goal=deepcopy(turn["goal"]), capability_calls=3)
    path = tmp_path / "conversation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    restored = ConversationStore(path)
    turn = restored.turns()[0]
    assert turn.goal == turn.outcome.goal and not turn.goal.behaviour_verified
    assert len(turn.settled_calls) == 2 + stale
    if interrupted:
        assert turn.outcome.status == AgentRunStatus.INTERNAL_FAILURE
    if not legacy:
        assert turn.goal.model_dump(mode="json")["verification"] == payload["turns"][0]["goal"]["verification"]
    restored.new_session(preserve_history=True)
    archives = list((tmp_path / "archives").glob("*.json"))
    assert len(archives) == 1 and restored.messages() == []
    archived = ConversationStore(archives[0])
    assert archived.turns()[0].goal == turn.goal
    assert archived.messages()[0]["content"] == payload["messages"][0]["content"]


@pytest.mark.parametrize("tamper", ["assertion", "visual", "timing", "command", "version", "unknown", "verified"])
def test_new_fields_still_require_matching_durable_receipts(tmp_path, tamper):
    payload = saved_repair_history()
    turn = payload["turns"][0]
    goal = turn["goal"]
    browser, build = goal["verification"][1], goal["verification"][0]
    if tamper == "assertion":
        browser["interaction_assertions"][0]["passed"] = False
    elif tamper == "visual":
        browser["visual_observations"][0]["screenshot_sha256"] = "b" * 64
    elif tamper == "timing":
        browser["frame_timing_captured"] = False
    elif tamper == "command":
        build["command_passed"] = False
    elif tamper == "version":
        turn["settled_calls"][1]["result"]["output"]["evidence_version"] = 1
    elif tamper == "unknown":
        browser["unknown_success_claim"] = True
    else:
        goal["behaviour_verified"] = True
    turn["outcome"]["goal"] = deepcopy(goal)
    path = tmp_path / "conversation.json"
    before = json.dumps(payload).encode()
    path.write_bytes(before)
    with pytest.raises(TurnHistoryError):
        ConversationStore(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("checks", None), ("checks", ["invalid"]),
                                        ("checkpoints", {}), ("checkpoints", [None])])
def test_malformed_versioned_receipts_fail_safely(tmp_path, field, value):
    payload = saved_repair_history()
    payload["turns"][0]["settled_calls"][1]["result"]["output"][field] = value
    path = tmp_path / "conversation.json"
    before = json.dumps(payload).encode()
    path.write_bytes(before)
    with pytest.raises(TurnHistoryError):
        ConversationStore(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["build", "browser"])
def test_failed_versioned_receipt_is_retained_as_failed(tmp_path, kind):
    payload = saved_repair_history()
    turn = payload["turns"][0]
    index = 0 if kind == "build" else 1
    result = turn["settled_calls"][index]["result"]
    result.update(success=False, error={"code": "timed_out", "message": "Synthetic timeout"})
    item = turn["goal"]["verification"][index]
    item["passed"] = False
    if kind == "build":
        item["command_passed"] = False
    turn["goal"]["unavailable_checks"] = ["runtime_execution" if kind == "build" else "gui_validation"]
    turn["outcome"]["goal"] = deepcopy(turn["goal"])
    path = tmp_path / "conversation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    restored = ConversationStore(path).turns()[0]
    assert not restored.goal.verification[index].passed
    assert not restored.goal.behaviour_verified


def test_encrypted_startup_restores_repair_history_and_composer_sends(monkeypatch, tmp_path):
    import app.startup as startup
    import app.vault.logging as profile_logging
    from PySide6.QtWidgets import QApplication
    from app.inference.engine import InferenceUnavailable
    from app.state.storage import JsonStore
    from app.ui.main_window import MainWindow
    from app.vault.engine import Vault
    from app.vault.session import ProfileSession
    from tests.test_openai_phase1 import config
    from tests.test_vault_application import Backend

    qt = QApplication.instance() or QApplication([])
    vault = Vault.create(tmp_path / "vault", b"synthetic history password")
    session = ProfileSession(vault)
    payload = saved_repair_history()
    path = session.path("state/conversation_v1/conversation.json")
    JsonStore(path).save(payload)
    monkeypatch.setattr(profile_logging, "configure_profile_logging", lambda _: None)
    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(root=tmp_path, state=tmp_path / "legacy",
        models=tmp_path / "models", config=tmp_path / "config"))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config(default_mode="cloud"))
    monkeypatch.setattr(startup, "load_model_config", lambda: (_ for _ in ()).throw(InferenceUnavailable("synthetic no local model")))
    monkeypatch.setattr(startup, "OpenAIResponsesInferenceEngine", lambda *args, **kwargs: Backend())
    window = None
    try:
        service, host, error, inference = startup.build_application(profile_session=session,
            agent_config_override=startup.AgentFeatureConfig())
        assert error is None and service is not None
        archives = [key for key in vault.list_paths() if "/archives/" in key]
        assert len(archives) == 1
        archived = JsonStore(session.path(archives[0])).load()
        assert [(item["role"], item["content"]) for item in archived["messages"]] == [
            (item["role"], item["content"]) for item in payload["messages"]]
        assert (Conversation.model_validate_json(json.dumps(archived)).turns[0].goal
                == Conversation.model_validate_json(json.dumps(payload)).turns[0].goal)
        assert service.store.messages() == []
        # Synthetic credentials stay in memory; the provider never contacts a network.
        inference.set_cloud_api_key("synthetic-history-key")
        window = MainWindow(service, host["hostname"], error, inference)
        window.bind_profile(session)
        window.show()
        window.input.setPlainText("Synthetic new message")
        assert window.send.isEnabled()
        window.send.click()
        deadline = monotonic() + 5
        while window.thread is not None and monotonic() < deadline:
            qt.processEvents()
            sleep(.01)  # Release the GIL for the Python conversation worker.
        assert window.thread is None
        assert service.store.messages() == [{"role": "user", "content": "Synthetic new message"},
                                          {"role": "assistant", "content": "synthetic reply"}]
        assert not (tmp_path / "legacy/conversation_v1").exists()
    finally:
        if window is not None:
            window.close()
            qt.processEvents()
        session.lock()
