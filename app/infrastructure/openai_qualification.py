"""Revision-bound OpenAI acceptance evidence, independent of legacy pool gates."""
from __future__ import annotations

import json
from pathlib import Path

from app.infrastructure import qualification as q
from app.settings.openai_cloud import OpenAICloudConfig

FILESYSTEM_CASES = ("listing", "reading", "multiline-writing", "searching", "copying",
                    "moving", "folder-creation", "trashing")
WORKFLOWS = (*q.WORKFLOWS, "restart", "mode_round_trip", *FILESYSTEM_CASES)
TERMINALS = {**q.TERMINALS, "restart": ["completed", "completed"],
             "mode_round_trip": ["completed"] * 3,
             **{name: ["completed"] for name in FILESYSTEM_CASES}}


def profiles(root: Path) -> list[dict]:
    config = OpenAICloudConfig.model_validate(json.loads((root / "config/cloud.json").read_text()))
    return [{key: value for key, value in profile.model_dump().items() if key != "qualified"}
            for profile in config.profiles]


def identity(root: Path) -> dict:
    import importlib.metadata
    result = q.identity(root)
    result.update(cloud_manifest_sha256=q.digest((root / "config/cloud.json").read_bytes()),
                  packaging_manifest_sha256=q.digest((root / "pyproject.toml").read_bytes()),
                  sdk_version=importlib.metadata.version("openai"))
    result["suite_sha256"] = q.digest(json.dumps({"prompts": q.PROMPTS, "workflows": WORKFLOWS,
        "filesystem_prompt_source": q.digest((root / "tests/test_cloud_live_model.py").read_bytes().replace(b"\r\n", b"\n"))},
        sort_keys=True).encode())
    return result


def qualification_errors(report: dict, current: dict, expected_profiles: list[dict]) -> list[str]:
    errors = []
    if report.get("schema_version") != 1 or report.get("measurement_kind") != "live_openai":
        errors.append("A versioned live OpenAI report is required.")
    if not current.get("clean") or report.get("identity", {}).get("clean") is not True:
        errors.append("The measured candidate must be committed and clean.")
    for key in ("revision", "source_sha256", "suite_sha256", "cloud_manifest_sha256",
                "model_manifest_sha256", "packaging_manifest_sha256", "runtime_sha256",
                "effective_flags", "python_version", "sdk_version"):
        if not current.get(key) or report.get("identity", {}).get(key) != current[key]:
            errors.append(f"Evidence does not match {key}.")
    if report.get("finished") is not True or report.get("all_owned_resources_released") is not True:
        errors.append("Every owned client, worker and local server must be released.")
    regression = report.get("regression", {})
    if (type(regression.get("passed")) is not int or regression["passed"] <= 0
            or regression.get("failed") != 0 or regression.get("errors") != 0
            or regression.get("exit_code") != 0):
        errors.append("A successful full regression run is required.")
    if not all(report.get("packaging", {}).get(key) is True for key in
               ("passed", "sdk_transport_fixture_passed", "cloud_native_tools_startup", "ui_startup_passed")):
        errors.append("Isolated portable dependency and startup verification is required.")
    expected = {(p["id"], w, n) for p in expected_profiles for w in WORKFLOWS for n in range(q.REPETITIONS)}
    cells = report.get("cells", [])
    observed = [(c.get("model_id"), c.get("workflow"), c.get("repetition")) for c in cells]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        errors.append("Every configured profile/workflow/repetition must occur exactly once.")
    by_id = {p["id"]: p for p in expected_profiles}
    for cell in cells:
        if cell.get("status") != "passed" or cell.get("terminal_verified") is not True:
            errors.append("All live cells must pass; blocked, failed and skipped cells cannot qualify.")
        consents = cell.get("cloud_privacy_acceptances")
        if type(consents) is not int or consents < (2 if cell.get("workflow") == "restart" else 1):
            errors.append("Cloud workflows require their actual fixture-consent dialog acceptance.")
        if cell.get("profile") != by_id.get(cell.get("model_id")) or cell.get("limits_verified") is not True:
            errors.append("Actual selection, application limits and request settings must match the profile.")
        terminal = cell.get("terminal_outcomes", [])
        if ([t.get("status") for t in terminal] != TERMINALS.get(cell.get("workflow"))
                or not all(t.get("ended") is True for t in terminal)):
            errors.append("Complete durable terminal sequences are required.")
        if cell.get("workflow") != "cancel_then_task":
            cost = cell.get("request_cost", {})
            count = cost.get("generation_requests")
            if (type(count) is not int or count <= 0 or cost.get("usage_coverage") != count
                    or type(cost.get("observed_total_tokens")) is not int):
                errors.append("Non-cancelled workflows require complete request usage.")
        if cell.get("workflow") in {"read_edit_clarify_followup", *FILESYSTEM_CASES} and cell.get("bytes_verified") is not True:
            errors.append("Filesystem cells require verified fixture effects and approvals.")
        if cell.get("workflow") == "cancel_then_task" and cell.get("ui_released") is not True:
            errors.append("Cancellation must release controls before the next task.")
        if cell.get("workflow") in {"restart", "model_round_trip", "mode_round_trip"} and cell.get("session_preserved") is not True:
            errors.append("Restart and switching must preserve the session.")
        if cell.get("workflow") == "mode_round_trip" and cell.get("previous_servers_exited") is not True:
            errors.append("Mode switching must release the replaced owned local server.")
    if current.get("effective_flags", {}).get("context_recovery_enabled") is True:
        errors.append("Enabled recovery still requires its separately matched live acceptance gate.")
    return list(dict.fromkeys(errors))
