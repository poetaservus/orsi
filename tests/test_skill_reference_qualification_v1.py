from copy import deepcopy
from hashlib import sha256
import json

import pytest

from tools.skill_reference_code_check import check_source
from tools.skill_reference_qualification import (FIXTURE, REPETITIONS, WORKFLOWS,
    qualification_errors, validate_answer, case_passes, scope_is_clean)


FUNCTION = '''def clamp(value, lower, upper):
    if lower > upper:
        raise ValueError("lower exceeds upper")
    return min(max(value, lower), upper)
'''
CHECKS = '''assert clamp(-2, 0, 3) == 0
assert clamp(2, 0, 3) == 2
assert clamp(5, 0, 3) == 3
assert clamp(8, 4, 4) == 4
try:
    clamp(2, 3, 0)
except ValueError as error:
    assert str(error) == "lower exceeds upper"
else:
    assert False, "expected ValueError"
'''


@pytest.mark.parametrize("source,kind", [(FUNCTION, "function"), (CHECKS, "assertions"),
    (CHECKS.replace('    clamp(2, 3, 0)', '    clamp(2, 3, 0)\n    assert False, "expected ValueError"')
        .replace('else:\n    assert False, "expected ValueError"\n', ''), "assertions")])
def test_correct_synthetic_code_passes_in_restricted_worker(source, kind):
    assert check_source(source, kind) is None
    assert validate_answer(kind, "```python\n" + source + "```")


@pytest.mark.parametrize("source,kind", [
    ('import os\n' + FUNCTION, "function"),
    (FUNCTION.replace('return min(max(value, lower), upper)', 'return __import__("os").system("echo bad")'), "function"),
    (FUNCTION.replace('return min(max(value, lower), upper)', 'while True: pass'), "function"),
    (FUNCTION.replace('return min(max(value, lower), upper)', 'return clamp(value, lower, upper)'), "function"),
    (FUNCTION.replace('lower exceeds upper', 'wrong'), "function"),
    (FUNCTION.replace('return min(max(value, lower), upper)', 'return value'), "function"),
    (FUNCTION.replace('raise ValueError("lower exceeds upper")', 'return lower'), "function"),
    (CHECKS.replace('assert clamp(5, 0, 3) == 3\n', ''), "assertions"),
    (CHECKS.replace('assert str(error) == "lower exceeds upper"', 'assert True'), "assertions"),
    (CHECKS.replace('assert False, "expected ValueError"', 'assert True'), "assertions"),
    (CHECKS + '\nprint("unwanted output")', "assertions"),
])
def test_bad_behavior_and_unsafe_execution_never_pass(source, kind):
    assert check_source(source, kind) is not None


@pytest.mark.parametrize("case,answer,passed", [
    ("unrelated", "12", True), ("unrelated", "13", False),
    ("follow-up", 'It raises ValueError("lower exceeds upper").', True),
    ("follow-up", 'Swap the bounds.', False),
    ("unavailable", "The required behavior reference is unavailable. Please provide its content.", True),
    ("unavailable", "I can\u2019t write the function without the required behavior reference. Please provide references/behavior.md.", True),
    ("unavailable", "Here is a function without the reference.\n" + FUNCTION, False),
])
def test_semantic_acceptance_checks(case, answer, passed):
    assert validate_answer(case, answer) is passed


def complete_report():
    current = {"clean": True, **{k: "fixed" for k in (
        "source_sha256", "model_manifest_sha256", "effective_flags", "runtime_sha256", "python_version")}}
    models = [("local", "small"), ("cloud", "cloud")]
    report = {"schema_version": 1, "measurement_kind": "live_skill_references", "identity": deepcopy(current),
        "acceptance_sha256": sha256((FIXTURE / "acceptance.json").read_bytes()).hexdigest(),
        "finished": True, "all_owned_resources_released": True, "blockers": [], "settings_preserved": True,
        "models": [{"kind": kind, "model_id": model, "ready": True, "resources_released": True} for kind, model in models],
        "cells": [{"model_id": model, "workflow": workflow, "repetition": rep,
                   "status": "passed", "terminal_verified": True}
                  for _, model in models for workflow in WORKFLOWS for rep in range(REPETITIONS)]}
    return report, current, models


def test_complete_content_free_matrix_is_accepted():
    report, current, models = complete_report()
    assert not qualification_errors(report, current, models)


@pytest.mark.parametrize("failure", ["scripted", "partial", "duplicate", "skipped", "terminal", "dirty",
    "source", "prompts", "resources", "model", "unfinished", "blocker", "settings"])
def test_missing_or_failed_evidence_blocks_qualification(failure):
    report, current, models = complete_report()
    if failure == "scripted": report["measurement_kind"] = "deterministic"
    elif failure == "partial": report["cells"].pop()
    elif failure == "duplicate": report["cells"][-1] = report["cells"][0]
    elif failure == "skipped": report["cells"][0]["status"] = "skipped"
    elif failure == "terminal": report["cells"][0]["terminal_verified"] = False
    elif failure == "dirty": current["clean"] = False
    elif failure == "source": current["source_sha256"] = "changed"
    elif failure == "prompts": report["acceptance_sha256"] = "changed"
    elif failure == "resources": report["all_owned_resources_released"] = False
    elif failure == "model": report["models"].pop()
    elif failure == "unfinished": report["finished"] = False
    elif failure == "blocker": report["blockers"].append("profile_unavailable")
    elif failure == "settings": report["settings_preserved"] = False
    assert qualification_errors(report, current, models)


def test_followup_needs_real_same_scope_read_even_with_correct_answer(tmp_path):
    from types import SimpleNamespace
    from app.agent.contracts import AgentRunResult, AgentRunStatus
    from app.conversation.store import SkillReferenceScope
    outcome = AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="done", steps=1,
                             capability_calls=0, protocol_failures=0)
    turn = SimpleNamespace(outcome=outcome, settled_calls=[], reference_scope=SkillReferenceScope(
        package_id="1" * 64, version="2" * 64))
    answer = 'ValueError("lower exceeds upper")'
    assert not case_passes("follow-up", answer, turn)
    assert not case_passes("follow-up", answer, turn, previous=turn)


def test_fixed_prompts_remain_byte_identical_to_phase_one():
    from pathlib import Path
    import subprocess
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(["git", "show", "b6021fc:tests/fixtures/skill_package_v1/acceptance.json"], cwd=root)
    assert json.loads(original) == json.loads((FIXTURE / "acceptance.json").read_bytes())


def test_scope_gate_allows_visible_history_but_rejects_reference_bodies_and_opaque_replay():
    from app.inference.openai_replay import REPLAY_KEY
    visible = [{"role": "assistant", "content": 'raise ValueError("lower exceeds upper")'}]
    assert scope_is_clean([visible])
    assert not scope_is_clean([visible + [{"role": "capability", "result": {"capability": "skill.read_reference"}}]])
    assert not scope_is_clean([[{**visible[0], REPLAY_KEY: {"opaque": True}}]])
