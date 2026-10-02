"""Fail-closed qualification of a source revision, never inferred from pytest skips."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPETITIONS = 2
WORKFLOWS = ("ordinary", "long_code", "read_edit_clarify_followup", "cancel_then_task", "model_round_trip")
TERMINALS = {"ordinary": ["completed"], "long_code": ["completed"],
    "read_edit_clarify_followup": ["completed"] * 4, "cancel_then_task": ["cancelled", "completed"],
    "model_round_trip": ["completed"] * 3}
LONG_CODE = ("Provide a complete Python pygame top-down shooter with Player, Bullet, Enemy and Game classes. "
             "Return only the complete executable Python code block.")
ORDINARY = "This is ordinary conversation number 0. Reply exactly with chat-0; do not use a tool."
READ = 'Read "{target}" using filesystem.read_text with max_bytes=1024 and max_lines=1, and report its color.'
EDIT = ('Edit "{target}": change only the color of .phase0-component-001 from '
        '#123456 to #ffffff. First use filesystem.read_text with max_bytes=1024 and '
        'max_lines=1, then filesystem.edit_text with a unique short exact excerpt. '
        'Preserve all other bytes. Do not return or replace the entire file.')
CLARIFY = 'Edit "{target}" to change its color. Ask which color before changing any bytes.'
FOLLOWUP = 'Use #abcdef for .phase0-component-001 only. Preserve all other bytes.'
CANCEL = "Write a detailed 1200-word essay for the UI cancellation test. Do not use a tool."
AFTER_CANCEL = "Use filesystem.stat exactly once to inspect acceptance-note.txt, then report its size in bytes."
ROUNDTRIP = "Reply with OK only."
PROMPTS = (LONG_CODE, ORDINARY, READ, EDIT, CLARIFY, FOLLOWUP, CANCEL, AFTER_CANCEL, ROUNDTRIP)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def identity(root: Path) -> dict:
    from app.settings.agent import load_agent_feature_config
    # Include tests, packaging and the gate itself: changing a validator invalidates evidence.
    entries = []
    for name in sorted(git(root, "ls-files").splitlines()):
        if name.startswith(("app/", "config/", "tests/", "tools/", "packaging/", "requirements")):
            entries.append([name, digest((root / name).read_bytes().replace(b"\r\n", b"\n"))])
    return {"revision": git(root, "rev-parse", "HEAD"),
        "source_sha256": digest(json.dumps(entries, separators=(",", ":")).encode()),
        "suite_sha256": digest(json.dumps(PROMPTS).encode()),
        "model_manifest_sha256": digest((root / "config/model.json").read_bytes()),
        "effective_flags": load_agent_feature_config().model_dump(),
        "runtime_sha256": digest(json.dumps({name: digest((root / name).read_bytes())
            if (root / name).is_file() else None for name in
            ("runtime/python/python.exe", "runtime/llama-server/llama-server.exe")}, sort_keys=True).encode()),
        "python_version": sys.version.split()[0],
        "clean": not bool(git(root, "status", "--porcelain"))}


def required_profiles(root: Path) -> list[dict]:
    manifest = json.loads((root / "config/model.json").read_text())
    # Accepted, load-tested and experimental shipped profiles all remain required.
    return [{"model_id": p["model_id"], "sha256": p["sha256"],
             "context_length": p["configuration"]["context_length"],
             "max_response_tokens": p["configuration"]["max_tokens"],
             "sampling": {key: p["configuration"][key] for key in
                 ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "presence_penalty", "cache_type", "gpu_layers")}}
            for p in manifest["profiles"]]


def qualification_errors(report: dict, current: dict, profiles: list[dict]) -> list[str]:
    errors = []
    if report.get("schema_version") != 1 or report.get("measurement_kind") != "live":
        errors.append("A versioned live report is required.")
    if not current.get("clean"):
        errors.append("The candidate must be committed and clean.")
    for key in ("revision", "source_sha256", "suite_sha256", "model_manifest_sha256", "effective_flags", "runtime_sha256", "python_version"):
        if not current.get(key) or report.get("identity", {}).get(key) != current[key]:
            errors.append(f"Candidate evidence does not match {key}.")
    if report.get("finished") is not True or report.get("all_owned_servers_exited") is not True:
        errors.append("The run must finish and release every owned server.")
    suite = report.get("regression", {})
    if (suite.get("passed", 0) <= 0 or suite.get("failed") != 0 or suite.get("errors") != 0
            or suite.get("exit_code") != 0):
        errors.append("A successful full regression run is required.")
    cells = report.get("cells", [])
    expected = {(p["model_id"], workflow, repeat) for p in profiles for workflow in WORKFLOWS for repeat in range(REPETITIONS)}
    observed = [(c.get("model_id"), c.get("workflow"), c.get("repetition")) for c in cells]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        errors.append("Every profile/workflow/repetition must occur exactly once; skipped or missing cells block promotion.")
    by_id = {p["model_id"]: p for p in profiles}
    for cell in cells:
        profile = by_id.get(cell.get("model_id"))
        if not profile:
            errors.append("Unexpected profile evidence.")
            continue
        if cell.get("status") != "passed" or cell.get("terminal_verified") is not True:
            errors.append("Every live workflow must pass with verified terminal outcomes.")
        terminal = cell.get("terminal_outcomes", [])
        if ([t.get("status") for t in terminal] != TERMINALS.get(cell.get("workflow"))
                or not all(t.get("ended") is True for t in terminal)):
            errors.append("Durable terminal outcomes must match the full workflow sequence.")
        if cell.get("profile") != profile:
            errors.append("Actual loaded identity, limits and sampling must match the versioned profile.")
        if cell.get("workflow") in {"read_edit_clarify_followup", "cancel_then_task"} and cell.get("bytes_verified") is not True:
            errors.append("Actual fixture bytes must be verified.")
        if cell.get("workflow") == "cancel_then_task" and cell.get("ui_released") is not True:
            errors.append("Cancellation must release UI controls before the next task.")
        if cell.get("workflow") == "model_round_trip" and (cell.get("previous_servers_exited") is not True
                or cell.get("session_preserved") is not True):
            errors.append("Model round trips must preserve the session and release replaced servers.")
    if current.get("effective_flags", {}).get("context_recovery_enabled") is True and report.get("feature_acceptance_qualified") is not True:
        errors.append("Enabled gated features require their separate measured acceptance.")
    return list(dict.fromkeys(errors))
