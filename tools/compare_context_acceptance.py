"""Content-free comparison and conservative rollout decision for fixed A/B arms."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


BASELINE_FINGERPRINT = "e12c827243a6341ce09a06e0ac8135b6425467503d54f93a8f026ce48ea91350"


def compare(baseline: dict, candidate: dict) -> dict:
    matches = all(baseline.get(k) == candidate.get(k) and baseline.get(k) is not None for k in
        ("measurement_kind", "acceptance_suite_sha256", "prompt_source_sha256", "model_id", "model_sha256",
         "profiles_sha256", "effective_model", "effective_agent_limits", "authority", "running_limits"))
    flags = [dict(arm.get("effective_flags", {})) for arm in (baseline, candidate)]
    baseline_enabled = flags[0].pop("context_recovery_enabled", False)
    candidate_enabled = flags[1].pop("context_recovery_enabled", False)
    matches = matches and flags[0] == flags[1] and not baseline_enabled and candidate_enabled
    matches = matches and baseline.get("source_fingerprint") == BASELINE_FINGERPRINT
    workloads = {}
    for workload in ("accepted_small", "continuous_pressure"):
        values = []
        for arm in (baseline, candidate):
            sessions = [s for s in arm.get("sessions", []) if s["workload"] == workload]
            turns = [t for s in sessions for t in s["turns"]]
            values.append({"sessions": len(sessions), "turns": len(turns),
                "passed_turns": sum(t["passed"] for t in turns),
                "continuous_successes": sum(s["continuous_success"] for s in sessions),
                "generation_requests": sum(s["generation_requests"] for s in sessions),
                "estimated_input_tokens": sum(s["estimated_input_tokens"] for s in sessions),
                "observed_total_tokens": (sum(s["observed_total_tokens"] for s in sessions)
                    if sessions and all(s.get("observed_total_tokens") is not None for s in sessions) else None),
                "usage_coverage": sum(s["usage_coverage"] for s in sessions)})
        workloads[workload] = {"baseline": values[0], "candidate": values[1]}
    small, pressure = workloads["accepted_small"], workloads["continuous_pressure"]
    sufficient = all(v["sessions"] >= 2 and v["turns"] > 0 for w in workloads.values() for v in w.values())
    paired = all(w["baseline"]["sessions"] == w["candidate"]["sessions"]
        and w["baseline"]["turns"] == w["candidate"]["turns"] for w in workloads.values())
    success = sufficient and paired and all(w["candidate"]["passed_turns"] == w["candidate"]["turns"]
        and w["candidate"]["continuous_successes"] == w["candidate"]["sessions"] for w in workloads.values())
    success = success and pressure["candidate"]["continuous_successes"] >= pressure["baseline"]["continuous_successes"]
    request_ratio = small["candidate"]["generation_requests"] / max(1, small["baseline"]["generation_requests"])
    token_ratio = small["candidate"]["estimated_input_tokens"] / max(1, small["baseline"]["estimated_input_tokens"])
    observed_ratio = (small["candidate"]["observed_total_tokens"] / max(1, small["baseline"]["observed_total_tokens"])
        if small["candidate"]["observed_total_tokens"] is not None and small["baseline"]["observed_total_tokens"] is not None else None)
    # Cost controls are explicit and fixed; failure savings are never called an improvement.
    cost = request_ratio <= 1.25 and token_ratio <= 1.25 and (observed_ratio is None or observed_ratio <= 1.25)
    closed = all(a.get("finished") and a.get("all_owned_servers_exited") for a in (baseline, candidate))
    live = baseline.get("measurement_kind") == candidate.get("measurement_kind") == "live"
    usage_complete = all(v["generation_requests"] > 0 and v["usage_coverage"] == v["generation_requests"]
        and v["observed_total_tokens"] is not None for w in workloads.values() for v in w.values())
    accepted_limits = all(a.get("effective_model", {}).get("context_length") == 16384
        and a.get("effective_model", {}).get("max_response_tokens") == 4096
        and a.get("running_limits", {}).get("context_length") == 16384
        and a.get("running_limits", {}).get("max_response_tokens") == 4096 for a in (baseline, candidate))
    return {"schema_version": 1, "baseline_revision": "651567b19fab4e8dbe7808aa3644bb54297dbe00",
        "measurement_kind": baseline.get("measurement_kind"), "comparable": bool(matches and paired),
        "workloads": workloads, "routine_request_ratio": round(request_ratio, 4),
        "routine_estimated_input_ratio": round(token_ratio, 4),
        "routine_observed_total_ratio": round(observed_ratio, 4) if observed_ratio is not None else None,
        "routine_cost_ceiling_ratio": 1.25, "success_gate_passed": bool(success), "cost_gate_passed": cost,
        "live_usage_coverage_complete": bool(live and usage_complete), "live_measurement_performed": live,
        "rollout_qualified": bool(matches and paired and success and cost and closed and live and usage_complete and accepted_limits)}


def compare_experiment(baseline: dict, candidate: dict) -> dict:
    """Measure recovery on/off on one candidate source; never certify promotion.

    The accepted-baseline comparison above remains unchanged. This isolates only
    recovery, after separately staged prompt/estimate changes, instead of treating
    a different prompt as evidence for the recovery feature.
    """
    reference = baseline.get("source_fingerprint")
    same_source = reference is not None and reference == candidate.get("source_fingerprint")
    result = compare({**baseline, "source_fingerprint": BASELINE_FINGERPRINT}, candidate)
    experiment_passed = same_source and result["rollout_qualified"]
    result.update(baseline_revision=None, reference_source_fingerprint=reference,
                  comparable=same_source and result["comparable"],
                  experiment_passed=bool(experiment_passed),
                  accepted_baseline_comparison=False, rollout_qualified=False)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--experiment-only", action="store_true",
                        help="Compare recovery off/on on identical candidate source; cannot qualify rollout.")
    args = parser.parse_args()
    comparator = compare_experiment if args.experiment_only else compare
    result = comparator(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
