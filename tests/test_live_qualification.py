"""Promotion policy tests are deterministic; they never certify a live workflow."""
from copy import deepcopy
from pathlib import Path

import pytest

from app.infrastructure import qualification as q
from app.inference.completion import CompletionMetadata, CompletionText
from tools.live_qualification import code_is_complete, asks_for_color, completed_stat
from tools.verify_live_qualification import verify


def evidence():
    profiles = [{"model_id": f"model-{n}", "sha256": f"sha-{n}", "context_length": 16384,
        "max_response_tokens": 4096, "sampling": {"temperature": 0.1}} for n in range(3)]
    current = {"revision": "fixed", "source_sha256": "source", "suite_sha256": "prompts",
        "model_manifest_sha256": "profiles", "effective_flags": {"context_recovery_enabled": False},
        "runtime_sha256": "binaries", "python_version": "3.12.10", "clean": True}
    report = {"schema_version": 1, "measurement_kind": "live", "identity": deepcopy(current),
        "finished": True, "all_owned_servers_exited": True,
        "regression": {"passed": 800, "failed": 0, "errors": 0, "skipped": 54, "exit_code": 0}, "cells": []}
    for profile in profiles:
        for workflow in q.WORKFLOWS:
            for repetition in range(q.REPETITIONS):
                report["cells"].append({"model_id": profile["model_id"], "workflow": workflow,
                    "repetition": repetition, "status": "passed", "profile": deepcopy(profile),
                    "terminal_verified": True, "bytes_verified": True, "ui_released": True,
                    "request_cost": {"generation_requests": 2, "usage_coverage": 2, "observed_total_tokens": 1000},
                    "previous_servers_exited": True, "session_preserved": True})
                report["cells"][-1]["terminal_outcomes"] = [{"status": status, "ended": True}
                    for status in q.TERMINALS[workflow]]
    return report, current, profiles


def test_complete_matched_live_matrix_allows_qualification_with_unrelated_legacy_skips():
    report, current, profiles = evidence()
    assert len(report["cells"]) == 30
    assert not q.qualification_errors(report, current, profiles)


@pytest.mark.parametrize("defect", ["deterministic", "no_live", "skip", "missing_model", "once", "duplicate",
    "failed", "unfinished", "process_leak", "wrong_revision", "wrong_source", "changed_prompt", "changed_flags",
    "changed_runtime", "changed_model", "downgraded", "sampling", "dirty", "no_regression", "regression_failure",
    "bytes", "terminal", "ui_stuck", "switch_leak", "session_lost", "gated_feature", "lost_cancelled_turn", "missing_usage"])
def test_required_live_evidence_cannot_be_replaced_by_green_deterministic_tests(defect):
    report, current, profiles = evidence()
    if defect == "deterministic": report["measurement_kind"] = "deterministic"
    elif defect == "no_live": report["cells"] = []
    elif defect == "skip": report["cells"][0]["status"] = "skipped"
    elif defect == "missing_model": report["cells"] = [c for c in report["cells"] if c["model_id"] != "model-2"]
    elif defect == "once": report["cells"] = [c for c in report["cells"] if c["repetition"] == 0]
    elif defect == "duplicate": report["cells"].append(deepcopy(report["cells"][0]))
    elif defect == "failed": report["cells"][0]["status"] = "failed"
    elif defect == "unfinished": report["finished"] = False
    elif defect == "process_leak": report["all_owned_servers_exited"] = False
    elif defect == "wrong_revision": current["revision"] = "later"
    elif defect == "wrong_source": current["source_sha256"] = "later"
    elif defect == "changed_prompt": current["suite_sha256"] = "easier"
    elif defect == "changed_flags": current["effective_flags"]["filesystem_read_text_enabled"] = False
    elif defect == "changed_runtime": current["runtime_sha256"] = "new"
    elif defect == "changed_model": report["cells"][0]["profile"]["sha256"] = "wrong"
    elif defect == "downgraded": report["cells"][0]["profile"]["context_length"] = 4096
    elif defect == "sampling": report["cells"][0]["profile"]["sampling"]["temperature"] = 0.9
    elif defect == "dirty": current["clean"] = False
    elif defect == "no_regression": report["regression"] = {}
    elif defect == "regression_failure": report["regression"]["failed"] = 1
    elif defect == "bytes": report["cells"][4]["bytes_verified"] = False
    elif defect == "terminal": report["cells"][0]["terminal_verified"] = False
    elif defect == "lost_cancelled_turn": report["cells"][6]["terminal_outcomes"].pop(0)
    elif defect == "missing_usage": report["cells"][0]["request_cost"]["usage_coverage"] = 1
    elif defect == "ui_stuck": report["cells"][6]["ui_released"] = False
    elif defect == "switch_leak": report["cells"][8]["previous_servers_exited"] = False
    elif defect == "session_lost": report["cells"][8]["session_preserved"] = False
    elif defect == "gated_feature":
        current["effective_flags"]["context_recovery_enabled"] = True
        report["identity"] = deepcopy(current)
        report["feature_acceptance_required"] = False  # Cannot bypass the effective flag.
    assert q.qualification_errors(report, current, profiles)


def test_fixed_prompts_preserve_existing_ordinary_and_long_code_requests():
    assert q.LONG_CODE == ("Provide a complete Python pygame top-down shooter with Player, Bullet, Enemy and Game classes. "
                           "Return only the complete executable Python code block.")
    assert q.ORDINARY == "This is ordinary conversation number 0. Reply exactly with chat-0; do not use a tool."
    assert q.EDIT.endswith("Preserve all other bytes. Do not return or replace the entire file.")


@pytest.mark.parametrize("defect", ["length", "fence", "syntax", "classes", "import", "unknown_finish"])
def test_long_code_requires_closed_fence_syntax_structure_and_known_completion(defect):
    source = "import pygame\n" + "\n".join(f"class {name}: pass" for name in ("Player", "Bullet", "Enemy", "Game"))
    answer = f"```python\n{source}\n```"
    finish = "stop"
    if defect == "length": finish = "length"
    elif defect == "fence": answer = answer[:-3]
    elif defect == "syntax": answer = answer.replace("class Player: pass", "class Player(")
    elif defect == "classes": answer = answer.replace("class Game", "class Other")
    elif defect == "import": answer = answer.replace("import pygame", "import math")
    elif defect == "unknown_finish": finish = None
    assert not code_is_complete(CompletionText(answer, CompletionMetadata(finish_reason=finish)))


def test_valid_code_is_compiled_but_never_executed():
    source = "import pygame\nraise RuntimeError('never run')\n" + "\n".join(
        f"class {name}: pass" for name in ("Player", "Bullet", "Enemy", "Game"))
    assert code_is_complete(CompletionText(f"```python\n{source}\n```", CompletionMetadata(finish_reason="stop")))


def test_missing_or_corrupt_report_blocks_before_git_or_build_mutation(tmp_path):
    assert verify(tmp_path, tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("not json")
    assert verify(tmp_path, broken)


def test_live_preflight_downgrade_blocks_without_allocating_a_model(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.settings import local_models
    from app.inference import llama_server_backend
    from tools.live_qualification import run
    report, current, profiles = evidence()
    monkeypatch.setattr(q, "identity", lambda root: current)
    monkeypatch.setattr(q, "required_profiles", lambda root: profiles)
    class GuardedCatalog:
        models = [SimpleNamespace(id=p["model_id"]) for p in profiles]
        def __init__(self, *args, **kwargs): pass
        def configuration(self, model_id):
            return SimpleNamespace(context_length=4096, max_tokens=1024, gpu_layers=0)
    monkeypatch.setattr(local_models, "LocalModelCatalog", GuardedCatalog)
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight allocated a model under downgraded limits")
    monkeypatch.setattr(llama_server_backend, "LlamaServerInferenceEngine", forbidden)
    result = run(tmp_path, tmp_path / "workspace", tmp_path / "report.json", regression=False)
    assert result["qualified"] is False and result["no_model_allocated"] is True
    assert result["cells"] == [] and len(result["blockers"]) == 3


@pytest.mark.parametrize("answer", ["Which color would you like?", "Please specify the desired color.",
                                   "Tell me the colour you prefer."])
def test_clarification_is_a_request_for_input_with_or_without_question_punctuation(answer):
    assert asks_for_color(answer)


@pytest.mark.parametrize("answer", ["Done.", "I changed the color to white.", "What file?"])
def test_acknowledgement_or_unrelated_question_is_not_color_clarification(answer):
    assert not asks_for_color(answer)


def test_stat_verifier_reads_durable_turn_calls_after_outcome_deduplication(tmp_path):
    from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
    from app.capabilities.contracts import CapabilityResult
    from app.conversation.store import ConversationStore
    from app.inference.protocol import ModelCapabilityCall
    store = ConversationStore(tmp_path / "conversation.json")
    turn_id = store.begin_turn(q.AFTER_CANCEL)
    call = ModelCapabilityCall(provider_call_id="call-0", capability="filesystem.stat", arguments={"path": "acceptance-note.txt"})
    result = CapabilityResult(call_id="settled-1", capability="filesystem.stat", success=True, output={"size_bytes":83}, duration_ms=1)
    settled = SettledCall(provider_message_id="message-1", call=call, result=result)
    store.record_settled(turn_id, settled)
    store.finish_turn(turn_id, AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="83", steps=2,
        capability_calls=1, protocol_failures=0, settled_calls=(settled,)))
    restored = ConversationStore(store.path).turns()[-1]
    assert restored.outcome.settled_calls == ()  # Accepted storage format, not missing work.
    assert completed_stat(restored)


def test_request_cost_counts_all_physical_steps_and_keeps_missing_usage_unknown():
    from app.agent.contracts import AgentRunResult, AgentRunStatus
    from app.inference.completion import TokenUsage
    first = CompletionMetadata(usage=TokenUsage(input_tokens=100, output_tokens=10))
    final = CompletionMetadata(usage=TokenUsage(total_tokens=250))
    outcome = AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="done", steps=2,
        capability_calls=0, protocol_failures=0, model_requests=2, inference_requests=2,
        completion=final, completion_history=(first, final))
    assert q.request_cost([outcome]) == {"generation_requests": 2, "usage_coverage": 2, "observed_total_tokens": 360}
    missing = outcome.model_copy(update={"completion_history": (first, CompletionMetadata())})
    assert q.request_cost([missing])["observed_total_tokens"] is None
