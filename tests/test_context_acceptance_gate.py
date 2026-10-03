from copy import deepcopy

import pytest

from tools.compare_context_acceptance import BASELINE_FINGERPRINT, compare, compare_experiment


def arm(kind="live", enabled=False):
    result = {"measurement_kind": kind, "acceptance_suite_sha256": "fixed-suite", "prompt_source_sha256": "fixed-prompt",
        "model_id": "accepted-model", "model_sha256": "fixed-model", "profiles_sha256": "fixed-profiles",
        "effective_model": {"context_length": 16384, "max_response_tokens": 4096}, "effective_agent_limits": {},
        "authority": "synthetic_portable_workspace", "running_limits": {"context_length": 16384, "max_response_tokens": 4096},
        "effective_flags": {"filesystem_stat_enabled": True, "context_recovery_enabled": enabled},
        "source_fingerprint": BASELINE_FINGERPRINT if not enabled else "candidate-source", "finished": True,
        "all_owned_servers_exited": True, "sessions": []}
    for repetition in range(2):
        for workload, count in (("accepted_small", 3), ("continuous_pressure", 8)):
            result["sessions"].append({"workload": workload, "turns": [{"passed": True} for _ in range(count)],
                "continuous_success": True, "generation_requests": count, "estimated_input_tokens": 100 * count,
                "observed_total_tokens": 120 * count, "usage_coverage": count})
    return result


def test_only_matched_complete_live_success_and_bounded_cost_can_qualify():
    result = compare(arm(), arm(enabled=True))
    assert result["comparable"] and result["rollout_qualified"]
    assert result["routine_observed_total_ratio"] == 1


@pytest.mark.parametrize("change", ["deterministic", "input_cost", "output_cost", "partial_usage", "memory_downgrade",
    "prompt_change", "permission_change", "unfinished_session", "wrong_baseline", "insufficient_repeats", "failed_turn",
    "unknown_total_usage", "both_downgraded"])
def test_acceptance_gate_rejects_regressions_and_unmatched_or_unmeasured_work(change):
    baseline, candidate = arm(), arm(enabled=True)
    if change == "deterministic":
        baseline["measurement_kind"] = candidate["measurement_kind"] = "deterministic"
    elif change == "input_cost":
        candidate["sessions"][0]["estimated_input_tokens"] *= 6
    elif change == "output_cost":
        candidate["sessions"][0]["observed_total_tokens"] *= 6
    elif change == "partial_usage":
        candidate["sessions"][0]["usage_coverage"] -= 1
        candidate["sessions"][0]["observed_total_tokens"] = None
    elif change == "memory_downgrade":
        candidate["effective_model"]["context_length"] = 4096
    elif change == "prompt_change":
        candidate["prompt_source_sha256"] = "changed"
    elif change == "permission_change":
        candidate["effective_flags"]["filesystem_stat_enabled"] = False
    elif change == "unfinished_session":
        candidate["sessions"][1]["continuous_success"] = False
    elif change == "wrong_baseline":
        baseline["source_fingerprint"] = "unaccepted"
    elif change == "insufficient_repeats":
        baseline["sessions"] = baseline["sessions"][:2]
        candidate["sessions"] = candidate["sessions"][:2]
    elif change == "failed_turn":
        candidate["sessions"][1]["turns"][0]["passed"] = False
    elif change == "unknown_total_usage":
        candidate["sessions"][0]["observed_total_tokens"] = None
    elif change == "both_downgraded":
        for value in (baseline, candidate):
            value["effective_model"]["context_length"] = 4096
            value["running_limits"]["context_length"] = 4096
    assert compare(baseline, candidate)["rollout_qualified"] is False


def test_matched_candidate_experiment_cannot_promote_an_unaccepted_build():
    baseline, candidate = arm(), arm(enabled=True)
    baseline["source_fingerprint"] = candidate["source_fingerprint"] = "same-candidate-source"
    result = compare_experiment(baseline, candidate)
    assert result["comparable"] and result["experiment_passed"]
    assert result["rollout_qualified"] is False and result["accepted_baseline_comparison"] is False
    candidate["source_fingerprint"] = "another-source"
    assert compare_experiment(baseline, candidate)["experiment_passed"] is False
    candidate["source_fingerprint"] = baseline["source_fingerprint"]
    candidate["prompt_source_sha256"] = "changed-prompt"
    assert compare_experiment(baseline, candidate)["experiment_passed"] is False
