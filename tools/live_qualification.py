"""Mandatory live matrix. No scripted inference and no pytest skip-to-pass conversion."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from time import monotonic, sleep
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from app.infrastructure import qualification as q


def code_is_complete(answer) -> bool:
    if answer.completion.incomplete or answer.completion.finish_reason not in {"stop", "eos", "end_turn"}:
        return False
    match = re.fullmatch(r"\s*```(?:python|py)?\s*\n(.*?)\n```\s*", str(answer), re.DOTALL)
    if not match:
        return False
    try:
        tree = ast.parse(match[1])
        compile(tree, "qualification.py", "exec")  # Compile only; never run generated code.
    except (SyntaxError, ValueError):
        return False
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    return {"Player", "Bullet", "Enemy", "Game"} <= classes and "pygame" in imports


def asks_for_color(answer: str) -> bool:
    """Accept an actual request for a color without requiring question punctuation."""
    normalized = " ".join(answer.casefold().split())
    return bool(re.search(r"\b(?:which|what|specify|provide|choose|tell me|need|would you like)\b.{0,100}\bcolou?r\b"
                         r"|\bcolou?r\b.{0,80}\b(?:want|prefer|should|would you like)\b", normalized))


def completed_stat(turn) -> bool:
    # Persisted outcomes deliberately omit calls; the turn owns their durable evidence.
    return (turn.outcome is not None and turn.outcome.status.value == "completed"
        and len(turn.settled_calls) == 1 and turn.settled_calls[0].call.capability == "filesystem.stat"
        and turn.settled_calls[0].result.success)


def run(root: Path, workspace: Path, report_path: Path, *, regression=True) -> dict:
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
    from app.inference.llama_server_backend import LlamaServerInferenceEngine
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import load_agent_feature_config
    from app.settings.local_models import LocalModelCatalog
    from app.settings.model import load_model_config, detect_nvidia_memory_mib
    from app.settings.paths import PATHS
    from app.state.storage import JsonStore
    from tests.fixtures.context_reliability import large_css_fixture

    workspace.mkdir(parents=True, exist_ok=False)
    profiles = q.required_profiles(root)
    report = {"schema_version": 1, "measurement_kind": "live", "identity": q.identity(root),
        "cells": [], "finished": False, "all_owned_servers_exited": False,
        "feature_acceptance_required": load_agent_feature_config().context_recovery_enabled,
        "feature_acceptance_qualified": False, "regression": {}, "blockers": []}
    save = lambda: JsonStore(report_path).save(report)
    save()
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
        selection_path=workspace / "selection.json")
    if {m.id for m in catalog.models} != {p["model_id"] for p in profiles}:
        report["blockers"].append({"reason": "every_chooser_model_needs_a_versioned_profile"})
    # Resolve all profiles before allocating anything. A missing/unsafe profile cannot be omitted.
    for profile in profiles:
        try:
            config = catalog.configuration(profile["model_id"])
            if config.context_length != profile["context_length"] or config.max_tokens != profile["max_response_tokens"] or config.gpu_layers == 0:
                report["blockers"].append({"model_id": profile["model_id"], "reason": "accepted_limits_unavailable",
                    "effective_context": config.context_length, "effective_output": config.max_tokens})
        except Exception as exc:
            report["blockers"].append({"model_id": profile["model_id"], "reason": type(exc).__name__})
    if not report["identity"]["clean"]:
        report["blockers"].append({"reason": "candidate_not_committed_and_clean"})
    if os.name != "nt":
        report["blockers"].append({"reason": "windows_live_ui_required"})
    if report["blockers"]:
        report["finished"] = report["all_owned_servers_exited"] = True
        report["no_model_allocated"] = True
        report["qualified"] = False
        save()
        return report

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    processes = []

    def factory(config):
        expected = next(p for p in profiles if p["model_id"] == Path(config.model_path).name)
        if config.context_length != expected["context_length"] or config.max_tokens != expected["max_response_tokens"] or config.gpu_layers == 0:
            raise RuntimeError("The memory guard no longer permits the accepted profile.")
        return LlamaServerInferenceEngine(config)

    def observe(inference, profile):
        engine = inference.local._get_engine()
        engine.prepare()
        url, key, process = engine._ensure_started()
        if process not in processes:
            processes.append(process)
        with urlopen(Request(url + "/props", headers={"Authorization": "Bearer " + key}), timeout=10) as response:
            actual_context = json.load(response)["default_generation_settings"]["n_ctx"]
        actual = {"model_id": catalog.current_id, "sha256": catalog.identity(next(m for m in catalog.models if m.id == catalog.current_id))["sha256"],
            "context_length": actual_context, "max_response_tokens": engine.max_response_tokens,
            "sampling": {key: getattr(engine.config, key) for key in profile["sampling"]}}
        assert actual == profile, "Loaded profile does not match its versioned target."
        memory = detect_nvidia_memory_mib()
        assert memory and memory[1] >= memory[0] * 0.2, "Retain accepted GPU headroom after load."
        return actual, engine

    def wait(window, limit=240):
        until = monotonic() + limit
        while window.thread is not None and monotonic() < until:
            app.processEvents()
            sleep(0.01)
        app.processEvents()
        if window.thread is not None:
            window.cancel_current_task()
            until = monotonic() + 20
            while window.thread is not None and monotonic() < until:
                app.processEvents()
                sleep(0.01)
            raise TimeoutError("Live UI workflow deadline exceeded.")
        assert window.input.isEnabled() and window.send.isEnabled() and not window.stop.isEnabled()

    def submit(window, service, prompt, status="completed"):
        before = len(service.store.turns())
        window.input.setPlainText(prompt)
        window.submit()
        wait(window)
        turns = service.store.turns()
        assert len(turns) == before + 1
        outcome = turns[-1].outcome
        assert outcome is not None and outcome.status.value == status
        assert turns[-1].ended_at is not None
        # Verify persisted terminal outcome, independently of the UI's displayed text.
        restored = ConversationStore(service.store.path)
        assert restored.turns()[-1].outcome == outcome
        return outcome, window.chat._messages[-1]._content

    try:
        for profile in profiles:
            for repetition in range(q.REPETITIONS):
                folder = workspace / f"profile-{profiles.index(profile)}-repeat-{repetition}"
                folder.mkdir()
                portable = folder / "portable"
                portable.mkdir()
                note = folder / "acceptance-note.txt"
                note.write_bytes(b"A" * 83)
                target = folder / "styles.css"
                original = large_css_fixture().encode()
                target.write_bytes(original)
                config = catalog.configuration(profile["model_id"])
                catalog.current_config = config
                inference = HybridInferenceEngine(local=LazyInferenceEngine(lambda: factory(config),
                    context_length=config.context_length, max_response_tokens=config.max_tokens), cloud=None,
                    model_catalog=catalog, local_factory=factory)
                policy = HostAccessPolicy.full_local(application_root=portable, user_home=folder, acknowledged=True)
                runtime = build_agent_runtime(inference, config=load_agent_feature_config(), portable_root=portable,
                    state_directory=portable / "state", host_access_policy=policy)
                service = ConversationService(inference, ConversationStore(portable / "state/history.json"),
                    agent_runtime=runtime, portable_root=portable, host_access_policy=policy)
                window = MainWindow(service, "qualification", inference=inference)
                window.show()
                app.processEvents()
                approvals = []
                def approve(record):
                    allowed = record.capability == "filesystem.edit_text" and record.resource == str(target)
                    approvals.append(allowed)
                    service.resolve_approval(record.approval_id, allowed)
                service.set_approval_requester(approve)
                try:
                    for workflow in q.WORKFLOWS:
                        service.new_session()
                        cell = {"model_id": profile["model_id"], "workflow": workflow, "repetition": repetition,
                            "status": "failed", "terminal_verified": False}
                        report["cells"].append(cell)
                        try:
                            actual, engine = observe(inference, profile)
                            cell["profile"] = actual
                            if workflow == "ordinary":
                                outcome, answer = submit(window, service, q.ORDINARY)
                                assert answer.strip() == "chat-0" and not outcome.settled_calls
                            elif workflow == "long_code":
                                outcome, answer = submit(window, service, q.LONG_CODE)
                                from app.inference.completion import CompletionText
                                assert code_is_complete(CompletionText(answer, outcome.completion))
                                assert not outcome.settled_calls
                            elif workflow == "read_edit_clarify_followup":
                                start = len(approvals)
                                submit(window, service, q.READ.format(target=target))
                                assert target.read_bytes() == original
                                assert any(c.call.capability == "filesystem.read_text" and c.result.success for c in service.store.turns()[-1].settled_calls)
                                submit(window, service, q.EDIT.format(target=target))
                                changed = original.replace(b"#123456", b"#ffffff", 1)
                                assert target.read_bytes() == changed
                                _, answer = submit(window, service, q.CLARIFY.format(target=target))
                                assert target.read_bytes() == changed and asks_for_color(answer)
                                assert not any(c.call.capability == "filesystem.edit_text" for c in service.store.turns()[-1].settled_calls)
                                submit(window, service, q.FOLLOWUP)
                                assert target.read_bytes() == changed.replace(b"#ffffff", b"#abcdef", 1)
                                assert approvals[start:] == [True, True]
                                edits = [c for t in service.store.turns() for c in t.settled_calls if c.call.capability == "filesystem.edit_text"]
                                assert len(edits) == 2 and all(c.result.success for c in edits)
                                cell["bytes_verified"] = True
                            elif workflow == "cancel_then_task":
                                before = len(service.store.turns())
                                window.input.setPlainText(q.CANCEL)
                                window.submit()
                                until = monotonic() + 10
                                active = False
                                while monotonic() < until and not active:
                                    app.processEvents()
                                    active = engine.wait_for_active_request(0.05)
                                assert active
                                window.cancel_current_task()
                                wait(window, 20)
                                cancelled = service.store.turns()[-1]
                                assert len(service.store.turns()) == before + 1 and cancelled.outcome.status.value == "cancelled"
                                assert ConversationStore(service.store.path).turns()[-1].outcome == cancelled.outcome
                                outcome, answer = submit(window, service, q.AFTER_CANCEL)
                                assert "83" in answer and note.read_bytes() == b"A" * 83
                                assert completed_stat(service.store.turns()[-1])
                                cell.update(bytes_verified=True, ui_released=True)
                            else:
                                submit(window, service, q.ROUNDTRIP)
                                session = service.store.session_id
                                turns_before = len(service.store.turns())
                                away = next(p for p in profiles if p["model_id"] != profile["model_id"])
                                previous = engine._ensure_started()[2]
                                service.select_local_model(away["model_id"])
                                assert previous.poll() is not None
                                _, replacement = observe(inference, away)
                                submit(window, service, q.ROUNDTRIP)
                                previous = replacement._ensure_started()[2]
                                service.select_local_model(profile["model_id"])
                                assert previous.poll() is not None
                                observe(inference, profile)
                                _, answer = submit(window, service, q.ROUNDTRIP)
                                assert answer.strip() == "OK"
                                assert service.store.session_id == session and len(service.store.turns()) == turns_before + 2
                                cell.update(previous_servers_exited=True, session_preserved=True)
                            cell.update(status="passed", terminal_verified=True)
                        except Exception as exc:
                            cell["error_type"] = type(exc).__name__  # No exception text/private content.
                            sites = [frame for frame in traceback.extract_tb(exc.__traceback__) if frame.filename == __file__]
                            cell["error_check_line"] = sites[-1].lineno if sites else None
                        cell["terminal_outcomes"] = [{"status": t.outcome.status.value if t.outcome else "unsettled",
                            "ended": t.ended_at is not None,
                            "finish_reason": t.outcome.completion.finish_reason if t.outcome else None,
                            "usage": t.outcome.completion.usage.model_dump() if t.outcome else None,
                            "settled_calls": len(t.settled_calls)} for t in service.store.turns()]
                        cell["request_cost"] = q.request_cost([t.outcome for t in service.store.turns()])
                        if workflow in {"read_edit_clarify_followup", "cancel_then_task"}:
                            cell["fixture_sha256"] = q.digest((target if workflow == "read_edit_clarify_followup" else note).read_bytes())
                        # Synthetic content belongs in separate fixture artifacts, never diagnostics.
                        # Copy only while this UI turn is idle; no external reader races atomic writes.
                        (folder / f"{workflow}.history.json").write_bytes(service.store.path.read_bytes())
                        if workflow == "read_edit_clarify_followup":
                            (folder / "read_edit_clarify_followup.actual.css").write_bytes(target.read_bytes())
                        save()
                        print(profile["model_id"], repetition, workflow, cell["status"], flush=True)
                finally:
                    if window.thread is not None:
                        window.cancel_current_task()
                        wait(window, 20)
                    window.close()
                    app.processEvents()
                    service.shutdown()
                    inference.close()
    finally:
        report["all_owned_servers_exited"] = all(p.poll() is not None for p in processes)
        save()

    if regression:
        junit = workspace / "regression.xml"
        command = [sys.executable, "-m", "pytest", "--basetemp", str(workspace / "pytest"),
            "-p", "no:cacheprovider", "-o", "addopts=", "-q", f"--junitxml={junit}"]
        with (workspace / "regression.log").open("w") as log:
            result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        suites = list(ET.parse(junit).getroot().iter("testsuite"))
        counts = {name: sum(int(s.get(name, 0)) for s in suites) for name in ("tests", "failures", "errors", "skipped")}
        report["regression"] = {"exit_code": result.returncode, "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
            "failed": counts["failures"], "errors": counts["errors"], "skipped": counts["skipped"], "junit_sha256": q.digest(junit.read_bytes())}
    report["finished"] = True
    report["qualification_errors"] = q.qualification_errors(report, q.identity(root), profiles)
    report["qualified"] = not report["qualification_errors"]
    save()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run(Path.cwd(), args.workspace.resolve(), args.report.resolve())
    print("Live qualification:", "passed" if report.get("qualified") else "BLOCKED/FAILED")
    raise SystemExit(0 if report.get("qualified") else 1)


if __name__ == "__main__":
    main()
