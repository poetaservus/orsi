"""Live tiny-pack matrix. Reports are content-free; runtime settings stay unchanged."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
from threading import Timer
from time import monotonic
from urllib.request import Request, urlopen

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.infrastructure.qualification import identity, request_cost
from app.inference.completion import CompletionText
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.inference.openai_replay import REPLAY_KEY
from app.runtime.skills import SkillRegistry, SkillInstaller
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.state.storage import JsonStore
from tools.skill_reference_code_check import source_text


FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/skill_package_v1"
CASES = json.loads((FIXTURE / "acceptance.json").read_text())["cases"]
CASE_BY_ID = {c["id"]: c for c in CASES}
REPETITIONS = 2
WORKFLOWS = ("function", "follow-up", "assertions", "unrelated", "unavailable",
             "automatic-function", "automatic-unrelated", "legacy", "stale", "switch")


def validate_answer(case_id, answer):
    text = str(answer).strip()
    if case_id in {"function", "assertions"}:
        try:
            result = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("skill_reference_code_check.py"))],
                input=json.dumps({"source": source_text(text), "kind": case_id}), text=True,
                capture_output=True, timeout=3, check=True)
            return json.loads(result.stdout)["passed"] is True
        except Exception:
            return False
    if case_id == "unrelated":
        return bool(re.search(r"(?<!\d)12(?!\d)", text)) and not re.search(r"(?<!\d)(?:11|13)(?!\d)", text)
    if case_id == "follow-up":
        return "ValueError" in text and "lower exceeds upper" in text
    if case_id == "unavailable":
        lowered = " ".join(text.casefold().split())
        return (not re.search(r"\bdef\s+clamp\b", text) and "reference" in lowered
            and bool(re.search(r"unavailable|disabled|cannot|can't|not available|don't have|do not have", lowered))
            and bool(re.search(r"provide|paste|share|supply|send", lowered)))
    raise ValueError("Unknown acceptance case.")


def reference_reads(turn):
    return [s for s in turn.settled_calls if s.call.capability == "skill.read_reference"]


def case_passes(case_id, answer, turn, *, previous=None):
    case = CASE_BY_ID[case_id]
    reads = reference_reads(turn)
    paths = {s.call.arguments.get("path") for s in reads if s.result.success}
    if (turn.outcome is None or turn.outcome.status.value != "completed" or turn.outcome.completion.incomplete
            or any(s.call.capability != "skill.read_reference" or not s.result.success for s in turn.settled_calls)
            or not set(case["required_reads"]) <= paths or set(case["unneeded_reads"]) & paths):
        return False
    if case_id == "follow-up":
        if previous is None or previous.reference_scope != turn.reference_scope:
            return False
        cached = {s.call.arguments.get("path") for s in reference_reads(previous) if s.result.success}
        if "references/behavior.md" not in paths | cached:
            return False
    return validate_answer(case_id, answer)


def resources_released(processes, runners):
    return (all(p.poll() is not None for p in processes)
            and all(r._thread is None or not r._thread.is_alive() for r in runners))


def scope_is_clean(inputs):
    # Visible prior answers are permitted history, including quoted rules.
    # Raw reader results and opaque replay must expire with their authority.
    return all(REPLAY_KEY not in message and not (message.get("role") == "capability"
        and message.get("result", {}).get("capability") == "skill.read_reference")
        for messages in inputs for message in messages)


def settings_identity(root):
    return {name: sha256((root / name).read_bytes()).hexdigest() if (root / name).is_file() else None
            for name in ("config/model.json", "config/cloud.json", "config/agent.json",
                         "state/local_model_selection_v1.json", "state/cloud_model_selection_v1.json")}


def qualification_errors(report, current, expected_models):
    errors = []
    if report.get("schema_version") != 1 or report.get("measurement_kind") != "live_skill_references":
        errors.append("invalid_report")
    if not current.get("clean") or not report.get("identity", {}).get("clean"):
        errors.append("candidate_not_clean")
    # Documentation-only commits do not change the measured application, test
    # harness, profiles or pinned runtimes. The measured revision remains named.
    for key in ("source_sha256", "model_manifest_sha256", "effective_flags", "runtime_sha256", "python_version"):
        if not current.get(key) or report.get("identity", {}).get(key) != current[key]:
            errors.append("identity_mismatch_" + key)
    if report.get("acceptance_sha256") != sha256((FIXTURE / "acceptance.json").read_bytes()).hexdigest():
        errors.append("acceptance_changed")
    if report.get("finished") is not True or report.get("all_owned_resources_released") is not True:
        errors.append("unfinished_or_owned_resources_remain")
    if report.get("blockers"):
        errors.append("preflight_blocked")
    if report.get("settings_preserved") is not True:
        errors.append("user_settings_changed")
    required = {(model, workflow, rep) for _, model in expected_models for workflow in WORKFLOWS for rep in range(REPETITIONS)}
    cells = report.get("cells", [])
    observed = [(c.get("model_id"), c.get("workflow"), c.get("repetition")) for c in cells]
    if len(observed) != len(required) or set(observed) != required:
        errors.append("missing_or_duplicate_cells")
    if any(c.get("status") != "passed" or c.get("terminal_verified") is not True for c in cells):
        errors.append("live_cases_failed_or_blocked")
    models = report.get("models", [])
    if ({(m.get("kind"), m.get("model_id")) for m in models} != set(expected_models)
            or len(models) != len(expected_models) or any(m.get("ready") is not True
            or m.get("resources_released") is not True for m in models)):
        errors.append("model_unavailable_or_cleanup_failed")
    return errors


class Observation:
    """Observe existing requests without changing payloads or retaining their text."""
    def __init__(self, backend):
        self.backend = backend
        self.requests = []
        self.inputs = []  # Synthetic per-turn inputs, used only for scope checks.
        self.processes, self.runners = [], []
        for method in ("respond", "respond_with_capabilities"):
            original = getattr(backend, method)
            def observe(messages, *args, _original=original, **kwargs):
                self.inputs.append(deepcopy(messages))
                return _original(messages, *args, **kwargs)
            setattr(backend, method, observe)
        method = "_request_completion" if isinstance(backend, LlamaServerInferenceEngine) else "_request"
        original = getattr(backend, method)
        def physical(*args, **kwargs):
            started = monotonic()
            item = {"status": "failed"}
            try:
                response = original(*args, **kwargs)
                usage = response.get("usage", {})
                item.update(status="completed", input_tokens=usage.get("prompt_tokens", usage.get("input_tokens")),
                    output_tokens=usage.get("completion_tokens", usage.get("output_tokens")),
                    total_tokens=usage.get("total_tokens"))
                return response
            except Exception as error:
                item["error_type"] = type(error).__name__
                item["error_code"] = getattr(getattr(error, "code", None), "value", None)
                raise
            finally:
                item["elapsed_seconds"] = round(monotonic() - started, 3)
                self.requests.append(item)
                process, runner = getattr(backend, "_process", None), getattr(backend, "_runner", None)
                if process is not None and process not in self.processes: self.processes.append(process)
                if runner is not None and runner not in self.runners: self.runners.append(runner)
        setattr(backend, method, physical)


def run(root, workspace, report_path, *, api_key, model_ids=None, repetitions=REPETITIONS):
    workspace.mkdir(parents=True, exist_ok=False)
    current = identity(root)
    catalog = LocalModelCatalog(root / "models", root / "config/model.json", load_model_config(),
                                selection_path=workspace / "local-selection.json")
    cloud_config = load_cloud_config()
    expected_models = [("local", p.model_id) for p in catalog.profiles.profiles]
    expected_models += [("cloud", p.id) for p in cloud_config.profiles]
    selected = [m for m in expected_models if model_ids is None or m[1] in model_ids]
    flags = load_agent_feature_config().model_copy(update={"full_local_read_enabled": False})
    report = {"schema_version": 1, "measurement_kind": "live_skill_references", "identity": current,
        "acceptance_sha256": sha256((FIXTURE / "acceptance.json").read_bytes()).hexdigest(),
        "fixture_sha256": sha256(b"".join(p.read_bytes() for p in sorted((FIXTURE / "python-clamp").rglob("*.md")))).hexdigest(),
        "cloud_profiles_sha256": sha256((root / "config/cloud.json").read_bytes()).hexdigest(),
        "fixture_flags": flags.model_dump(), "models": [], "cells": [], "finished": False,
        "all_owned_resources_released": False, "qualified": False, "blockers": [],
        "settings_before": settings_identity(root), "settings_preserved": False}
    save = lambda: JsonStore(report_path).save(report)
    save()
    if not current["clean"] or set(selected) != set(expected_models) or repetitions != REPETITIONS:
        report["blockers"].append("candidate_dirty_or_partial_matrix")
    processes, runners = [], []
    for kind, model_id in selected:
        folder = workspace / model_id.replace(".", "-")
        folder.mkdir()
        model_record = {"kind": kind, "model_id": model_id, "ready": False, "resources_released": False}
        report["models"].append(model_record)
        backend = service = observer = None
        try:
            if kind == "local":
                config = catalog.configuration(model_id)
                profile = catalog.profiles.get(model_id)
                model_record["resolution"] = catalog._resolutions[model_id]
                if config.context_length != profile.configuration.context_length or config.max_tokens != profile.configuration.max_tokens:
                    raise RuntimeError("accepted_profile_unavailable")
                backend = LlamaServerInferenceEngine(config)
                backend.prepare()
                url, token, process = backend._ensure_started()
                processes.append(process)
                with urlopen(Request(url + "/props", headers={"Authorization": "Bearer " + token}), timeout=10) as response:
                    actual_context = json.load(response)["default_generation_settings"]["n_ctx"]
                if actual_context != config.context_length: raise RuntimeError("actual_context_mismatch")
                model_record.update(effective_context=actual_context, effective_output=backend.max_response_tokens)
            else:
                backend = OpenAIResponsesInferenceEngine(cloud_config, api_key=api_key,
                                                        selection_path=folder / "cloud-selection.json")
                backend.select_model(model_id)
                model_record.update(effective_context=backend.context_length, effective_output=backend.max_response_tokens,
                                    profile=cloud_config.profile(model_id).model_dump())
            observer = Observation(backend)
            registry = SkillRegistry(global_root=folder / "skills")
            SkillInstaller(registry).install(FIXTURE / "python-clamp")
            authored = folder / "authored"
            authored.mkdir()
            (authored / "SKILL.md").write_text('---\nname: arithmetic\ndescription: Answer simple arithmetic questions.\n---\nAnswer arithmetic briefly.\n')
            legacy_registry = SkillRegistry(global_root=folder / "legacy-skills")
            SkillInstaller(legacy_registry).install(authored)
            portable = folder / "portable"
            portable.mkdir()
            runtime = build_agent_runtime(backend, config=flags, portable_root=portable, state_directory=portable / "state")
            service = ConversationService(backend, ConversationStore(folder / "history.json"), agent_runtime=runtime,
                portable_root=portable, skill_registry=registry, automatic_skills_enabled=False)
            service.set_approval_requester(lambda approval: service.resolve_approval(approval.approval_id, False))
            model_record.update(ready=True, baseline_tool_count=len(service.agent_capabilities))
            failed_provider = False
            for repetition in range(repetitions):
                prior = None
                for workflow in WORKFLOWS:
                    cell = {"model_id": model_id, "kind": kind, "workflow": workflow, "repetition": repetition,
                            "status": "failed", "terminal_verified": False}
                    report["cells"].append(cell)
                    if failed_provider:
                        cell.update(status="blocked", reason="provider_unavailable")
                        save()
                        continue
                    if workflow not in {"follow-up", "stale", "switch"}: service.new_session()
                    service.skill_registry = legacy_registry if workflow == "legacy" else registry
                    service.automatic_skills_enabled = workflow.startswith("automatic-")
                    service._references.enabled = workflow != "unavailable"
                    if workflow.startswith("automatic-"):
                        case_id = workflow.removeprefix("automatic-")
                    else:
                        case_id = "unrelated" if workflow == "legacy" else "follow-up" if workflow in {"stale", "switch"} else workflow
                    if not workflow.startswith("automatic-"):
                        service.activate_skill("arithmetic" if workflow == "legacy" else "python-clamp")
                    begin = len(observer.requests)
                    observer.inputs.clear()
                    deadline = Timer(180, service.cancel_current_task)
                    started = monotonic()
                    deadline.start()
                    # The stale/switch cases establish fresh evidence first. Their
                    # acceptance prompt is still the frozen follow-up prompt.
                    changed = original = None
                    setup = None
                    try:
                        if workflow in {"stale", "switch"}:
                            service.new_session()
                            service.activate_skill("python-clamp")
                            service.run(CASE_BY_ID["function"]["prompt"])
                            setup = service.store.turns()[-1]
                            cell["setup_verified"] = any(s.result.success and s.call.arguments.get("path") == "references/behavior.md"
                                                         for s in reference_reads(setup))
                            if workflow == "stale":
                                changed = registry.get("python-clamp").root_path / "references/behavior.md"
                                original = changed.read_bytes()
                                changed.write_bytes(original + b"\n")
                            else:
                                service.skill_registry = legacy_registry
                                service.activate_skill("arithmetic")
                            observer.inputs.clear()
                        answer = service.run(CASE_BY_ID[case_id]["prompt"])
                        turn = service.store.turns()[-1]
                        restored = ConversationStore(service.store.path).turns()[-1]
                        cell["terminal_verified"] = turn.outcome == restored.outcome and turn.ended_at is not None
                        if workflow in {"stale", "switch"}:
                            passed = (cell["setup_verified"] and turn.outcome.status.value == "completed"
                                and not turn.settled_calls and scope_is_clean(observer.inputs))
                            if workflow == "stale":
                                passed = passed and any('"available": false' in m[0]["content"] for m in observer.inputs)
                        else:
                            passed = case_passes(case_id, answer, turn, previous=prior if workflow == "follow-up" else None)
                            if workflow == "automatic-function": passed = passed and service.skill_selection.name == "python-clamp"
                            if workflow == "automatic-unrelated": passed = passed and service.skill_selection.name is None
                            if workflow == "legacy": passed = passed and not reference_reads(turn)
                        cell.update(status="passed" if passed and cell["terminal_verified"] else "failed",
                            run_status=turn.outcome.status.value, selection=service.skill_selection.name,
                            reads=[{"path": s.call.arguments.get("path"), "success": s.result.success,
                                    "complete_document": bool(s.result.output and s.result.output.get("complete_document"))}
                                   for s in reference_reads(turn)], cost=request_cost(
                                       [setup.outcome, turn.outcome] if setup is not None else [turn.outcome]))
                        if workflow == "function": prior = turn
                    except Exception as error:
                        cell.update(error_type=type(error).__name__, run_status=service._turn_result.status.value if service._turn_result else None)
                    finally:
                        deadline.cancel()
                        deadline.join()
                        if changed is not None: changed.write_bytes(original)
                        cell["elapsed_seconds"] = round(monotonic() - started, 3)
                        cell["requests"] = observer.requests[begin:]
                        provider_errors = {r.get("error_code") for r in cell["requests"]}
                        if provider_errors & {"permission", "authentication", "quota"}:
                            failed_provider = True
                            cell.update(status="blocked", reason=next(r["error_code"] for r in cell["requests"] if r.get("error_code")))
                        save()
                        print(json.dumps({k: cell[k] for k in ("model_id", "workflow", "repetition", "status")}), flush=True)
        except Exception as error:
            model_record["error_type"] = type(error).__name__
        finally:
            try:
                if service is not None: service.shutdown()
                elif backend is not None: backend.close()
            except Exception as error:
                model_record["cleanup_error_type"] = type(error).__name__
            if observer is not None:
                processes.extend(p for p in observer.processes if p not in processes)
                runners.extend(r for r in observer.runners if r not in runners)
                model_record["resources_released"] = resources_released(observer.processes, observer.runners)
            else:
                model_record["resources_released"] = backend is None or not getattr(backend, "is_running", False)
            save()
    report["finished"] = True
    report["all_owned_resources_released"] = resources_released(processes, runners)
    report["settings_preserved"] = settings_identity(root) == report["settings_before"]
    report["qualification_errors"] = qualification_errors(report, identity(root), expected_models)
    report["qualified"] = not report["qualification_errors"]
    save()
    print(json.dumps({"finished": True, "qualified": report["qualified"], "cells": len(report["cells"]),
                      "all_owned_resources_released": report["all_owned_resources_released"]}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--models", nargs="*")
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    args = parser.parse_args()
    # Only the existing adapters may emit diagnostics; suppress third-party
    # warnings/tracebacks here so provider payloads never enter harness output.
    logging.disable(logging.CRITICAL)
    try:
        key = args.key_file.read_text(encoding="utf-8-sig").strip()
        if not key.startswith("sk-"):
            raise ValueError("invalid_key_format")
    except Exception:
        print('{"finished":false,"qualified":false,"reason":"credential_file_unavailable"}')
        raise SystemExit(2)
    result = run(Path.cwd(), args.workspace.resolve(), args.report.resolve(), api_key=key,
                 model_ids=args.models, repetitions=args.repetitions)
    raise SystemExit(0 if result["qualified"] else 1)
