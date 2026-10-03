"""Prevent the opt-in 5.2 assessment from reporting missing evidence as a pass."""
from copy import deepcopy
import json

import pytest

from tests.tasteskill_configuration_validation import (
    CASES, SKILL_NAME, assess_reply, finalize_summary,
)


def valid_reply():
    return {"DESIGN_VARIANCE": 8, "MOTION_INTENSITY": 6, "VISUAL_DENSITY": 4,
            "layout": "asymmetric", "motion": "animated", "density": "normal",
            "implementation": "Use an offset grid, transform transitions, and regular metric spacing."}


@pytest.mark.parametrize("change", [
    {"MOTION_INTENSITY": 1}, {"VISUAL_DENSITY": True}, {"DESIGN_VARIANCE": "8"},
    {"motion": "static"}, {"implementation": " "}, {"unknown_setting": 7},
])
def test_plan_assessment_rejects_wrong_values_choices_types_and_unknown_fields(change):
    reply = valid_reply() | change
    assert assess_reply(json.dumps(reply), (8, 6, 4), ("asymmetric", "animated", "normal"))["passed"] is False


@pytest.mark.parametrize("reply", ["prompt echo", "[]", "null", "```json\n{}\n```"])
def test_plan_assessment_does_not_count_unstructured_or_empty_replies(reply):
    assert assess_reply(reply, (8, 6, 4), ("asymmetric", "animated", "normal"))["passed"] is False


def passing_summary():
    return {"production_tool_count": 12,
            "runs": [{"case_id": case[0], "assessment": {"passed": True},
                      "completed": True, "incomplete": False, "active_skill": SKILL_NAME}
                     for case in CASES],
            "physical_requests": [{"skill_body_exact": True, "skill_sections": 1,
                                   "tool_count": 12, "tools_sha256": "same"} for _ in CASES],
            "upstream_bytes_unchanged": True, "model_profile_unchanged": True,
            "owned_server_exited": True}


def test_complete_matching_evidence_passes():
    reply = json.dumps(valid_reply())
    assert assess_reply(reply, (8, 6, 4), ("asymmetric", "animated", "normal"))["passed"] is True
    summary = passing_summary()
    finalize_summary(summary)
    assert summary["assessment_passed"] is True


@pytest.mark.parametrize("failure", [
    "missing_case", "duplicate_case", "missing_request", "incomplete", "wrong_skill",
    "changed_tools", "changed_body", "extra_section", "server_alive", "changed_profile",
])
def test_missing_or_changed_native_evidence_cannot_pass(failure):
    summary = deepcopy(passing_summary())
    if failure == "missing_case":
        summary["runs"].pop()
    elif failure == "duplicate_case":
        summary["runs"][-1]["case_id"] = "default"
    elif failure == "missing_request":
        summary["physical_requests"].pop()
    elif failure == "incomplete":
        summary["runs"][0]["incomplete"] = True
    elif failure == "wrong_skill":
        summary["runs"][0]["active_skill"] = None
    elif failure == "changed_tools":
        summary["physical_requests"][0]["tools_sha256"] = "different"
    elif failure == "changed_body":
        summary["physical_requests"][0]["skill_body_exact"] = False
    elif failure == "extra_section":
        summary["physical_requests"][0]["skill_sections"] = 2
    elif failure == "server_alive":
        summary["owned_server_exited"] = False
    elif failure == "changed_profile":
        summary["model_profile_unchanged"] = False
    finalize_summary(summary)
    assert summary["assessment_passed"] is False
