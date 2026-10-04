"""Real Responses/UI matrix using unchanged local and cloud acceptance prompts.

All fixtures and mutable selections are isolated. Reports retain numeric evidence
and fixed labels only; synthetic conversations stay in separate ignored fixtures.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
import traceback
import xml.etree.ElementTree as ET

from app.infrastructure import openai_qualification as gate
from app.infrastructure import qualification as q
from app.state.storage import JsonStore
from tools.live_qualification import asks_for_color, code_is_complete, completed_stat


def prepare_fixture(folder: Path):
    from tests.fixtures.context_reliability import large_css_fixture
    portable = folder / "portable"
    portable.mkdir()
    target = folder / "styles.css"
    original = large_css_fixture().encode()
    target.write_bytes(original)
    note = folder / "acceptance-note.txt"
    note.write_bytes(b"A" * 83)
    return portable, target, note, original


def fixture_approval_allowed(record, folder: Path, portable: Path) -> bool:
    if record.capability not in {"filesystem.edit_text", "filesystem.write_text", "filesystem.copy",
            "filesystem.move", "filesystem.mkdir", "filesystem.trash"} or not isinstance(record.resource, str):
        return False
    try:
        path = Path(record.resource).resolve()
        return path.is_relative_to(folder.resolve()) and not path.is_relative_to(portable.resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def accept_fixture_cloud_notice(window, app):
    """Click only this harness window's known consent dialog for synthetic data."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox
    window._qualification_cloud_consents = 0
    timer = QTimer(window)
    def accept():
        dialog = app.activeModalWidget()
        if (isinstance(dialog, QMessageBox) and dialog.parent() is window
                and dialog.windowTitle() == "Use cloud model?"):
            window._qualification_cloud_consents += 1
            dialog.button(QMessageBox.StandardButton.Yes).click()
    timer.timeout.connect(accept)
    timer.start(10)
    return timer


def run(root: Path, workspace: Path, report_path: Path, *, api_key: str, local_models: Path,
        packaging: dict | None = None, regression: bool = True) -> dict:
    from PySide6.QtWidgets import QApplication
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
    from app.inference.openai_backend import OpenAIResponsesInferenceEngine
    from app.inference.cloud_errors import CloudInferenceError
    from app.inference.llama_server_backend import LlamaServerInferenceEngine
    from app.settings.cloud import load_cloud_config
    from app.settings.agent import load_agent_feature_config
    from app.settings.local_models import LocalModelCatalog
    from app.settings.model import load_model_config
    from app.security.host_access import HostAccessPolicy
    from app.ui.main_window import MainWindow
    from tests.test_cloud_live_model import _prepare_capability_case, _verify_capability_case
    from pytest import MonkeyPatch

    workspace.mkdir(parents=True, exist_ok=False)
    expected = gate.profiles(root)
    report = {"schema_version": 1, "measurement_kind": "live_openai", "identity": gate.identity(root),
        "cells": [], "preflight": [], "finished": False, "qualified": False, "regression": {},
        "packaging": packaging or {}, "all_owned_resources_released": False}
    save = lambda: JsonStore(report_path).save(report)
    save()
    if not report["identity"]["clean"] or not api_key.strip() or os.name != "nt":
        report.update(finished=True, all_owned_resources_released=True, blockers=["live_preflight_unavailable"])
        save()
        return report
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    config = load_cloud_config()
    flags = load_agent_feature_config()
    resources = []
    catalog = LocalModelCatalog(local_models, root / "config/model.json", load_model_config(),
                                selection_path=workspace / "local-selection.json")

    class ObservedCloud(OpenAIResponsesInferenceEngine):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.requests = []

        def _request(self, inputs, *, tools=None):
            requested_model = self.active_model
            try:
                result = super()._request(inputs, tools=tools)
                self.requests.append({"model_id": result.requested_model,
                    "profile": self.config.profile(result.requested_model).model_dump(exclude={"qualified"}),
                    "metrics": result.request_metrics.model_dump(),
                    "encrypted_items": sum(item.get("type") == "reasoning" and bool(item.get("encrypted_content"))
                                           for item in result.get("output", []))})
                return result
            except CloudInferenceError as exc:
                self.requests.append({"model_id": requested_model, "error_code": exc.code,
                    "profile": self.config.profile(requested_model).model_dump(exclude={"qualified"}),
                    "metrics": self.last_request_metrics.model_dump() if self.last_request_metrics else None})
                raise
            finally:
                if self._runner is not None and self._runner not in resources:
                    resources.append(self._runner)

    def wait(window, limit=240):
        until = monotonic() + limit
        while window.thread is not None and monotonic() < until:
            app.processEvents()
            sleep(.01)
        app.processEvents()
        if window.thread is not None:
            window.cancel_current_task()
            until = monotonic() + 20
            while window.thread is not None and monotonic() < until:
                app.processEvents()
                sleep(.01)
            raise TimeoutError("Live UI deadline exceeded.")
        assert window.input.isEnabled() and window.send.isEnabled() and not window.stop.isEnabled()

    def submit(window, service, prompt, status="completed"):
        before = len(service.store.turns())
        window.input.setPlainText(prompt)
        window.submit()
        wait(window)
        turns = service.store.turns()
        assert len(turns) == before + 1 and turns[-1].ended_at is not None
        assert turns[-1].outcome is not None and turns[-1].outcome.status.value == status
        assert ConversationStore(service.store.path).turns()[-1].outcome == turns[-1].outcome
        return turns[-1], window.chat._messages[-1]._content

    try:
        for profile in expected:
            probe = ObservedCloud(config, api_key=api_key)
            probe.select_model(profile["id"])
            try:
                text = probe.respond([{"role": "user", "content": q.ROUNDTRIP}])
                assert text.strip() == "OK" and not text.completion.incomplete
                access = None
                report["preflight"].append({"model_id": profile["id"], "status": "passed"})
            except CloudInferenceError as exc:
                access = exc.code
                report["preflight"].append({"model_id": profile["id"], "status": "blocked", "error_code": access})
            except Exception:
                access = "preflight_failed"
                report["preflight"].append({"model_id": profile["id"], "status": "failed"})
            finally:
                probe.close()
            save()
            for repetition in range(q.REPETITIONS):
                for workflow in gate.WORKFLOWS:
                    cell = {"model_id": profile["id"], "workflow": workflow, "repetition": repetition,
                            "profile": profile, "status": "failed", "terminal_verified": False}
                    report["cells"].append(cell)
                    if access:
                        cell.update(status="blocked", error_code=access)
                        save()
                        continue
                    folder = workspace / f"profile-{expected.index(profile)}-repeat-{repetition}" / workflow
                    folder.mkdir(parents=True)
                    portable, target, note, original = prepare_fixture(folder)
                    cloud = ObservedCloud(config, api_key=api_key, selection_path=folder / "cloud-selection.json")
                    cloud.select_model(profile["id"])
                    local_config = catalog.configuration(catalog.current_id)
                    def local_factory():
                        engine = LlamaServerInferenceEngine(local_config)
                        try:
                            engine.prepare()
                            _, _, process = engine._ensure_started()
                        except Exception:
                            engine.close()
                            raise
                        resources.append(process)
                        return engine
                    inference = HybridInferenceEngine(local=LazyInferenceEngine(local_factory,
                        context_length=local_config.context_length, max_response_tokens=local_config.max_tokens),
                        cloud=cloud, default_mode="cloud", fallback_to_local=config.fallback_to_local)
                    policy = HostAccessPolicy.full_local(application_root=portable, user_home=folder, acknowledged=True)
                    runtime = build_agent_runtime(inference, config=flags, portable_root=portable,
                                                   state_directory=portable / "state", host_access_policy=policy)
                    store = ConversationStore(portable / "state/history.json", start_fresh=True)
                    service = ConversationService(inference, store, agent_runtime=runtime, portable_root=portable,
                                                  host_access_policy=policy)
                    window = MainWindow(service, "qualification", inference=inference)
                    window.show()
                    app.processEvents()
                    consent_timer = accept_fixture_cloud_notice(window, app)
                    prior_consents = 0
                    approvals = []
                    def approve(record):
                        # Only this synthetic workspace may receive write authority.
                        allowed = fixture_approval_allowed(record, folder, portable)
                        approvals.append((record.capability, allowed))
                        service.resolve_approval(record.approval_id, allowed)
                    service.set_approval_requester(approve)
                    patch = MonkeyPatch()
                    try:
                        assert inference.mode == "cloud" and inference.context_length == profile["context_length"]
                        assert inference.max_response_tokens == profile["max_output_tokens"]
                        cell["limits_verified"] = True
                        if workflow == "ordinary":
                            turn, answer = submit(window, service, q.ORDINARY)
                            assert answer.strip() == "chat-0" and not turn.settled_calls
                        elif workflow == "long_code":
                            from app.inference.completion import CompletionText
                            turn, answer = submit(window, service, q.LONG_CODE)
                            assert code_is_complete(CompletionText(answer, turn.outcome.completion)) and not turn.settled_calls
                        elif workflow == "read_edit_clarify_followup":
                            submit(window, service, q.READ.format(target=target))
                            assert target.read_bytes() == original
                            assert any(c.call.capability == "filesystem.read_text" and c.result.success for c in service.store.turns()[-1].settled_calls)
                            submit(window, service, q.EDIT.format(target=target))
                            changed = original.replace(b"#123456", b"#ffffff", 1)
                            assert target.read_bytes() == changed
                            turn, answer = submit(window, service, q.CLARIFY.format(target=target))
                            assert asks_for_color(answer) and target.read_bytes() == changed
                            assert not any(c.call.capability == "filesystem.edit_text" for c in turn.settled_calls)
                            submit(window, service, q.FOLLOWUP)
                            assert target.read_bytes() == changed.replace(b"#ffffff", b"#abcdef", 1)
                            assert approvals == [("filesystem.edit_text", True)] * 2
                            cell["bytes_verified"] = True
                        elif workflow == "cancel_then_task":
                            window.input.setPlainText(q.CANCEL)
                            window.submit()
                            until = monotonic() + 10
                            while monotonic() < until and not (cloud._runner is not None and cloud._runner._active is not None):
                                app.processEvents()
                                sleep(.01)
                            assert cloud._runner is not None and cloud._runner._active is not None
                            window.cancel_current_task()
                            wait(window, 20)
                            cancelled = service.store.turns()[-1]
                            assert cancelled.outcome.status.value == "cancelled"
                            assert ConversationStore(service.store.path).turns()[-1].outcome == cancelled.outcome
                            turn, answer = submit(window, service, q.AFTER_CANCEL)
                            assert completed_stat(turn) and "83" in answer and note.read_bytes() == b"A" * 83
                            cell.update(ui_released=True, bytes_verified=True)
                        elif workflow == "model_round_trip":
                            submit(window, service, q.ROUNDTRIP)
                            session = store.session_id
                            away = next(p for p in expected if p["id"] != profile["id"])
                            cloud.select_model(away["id"])
                            inference.set_mode("cloud")
                            away_failure = None
                            try:
                                submit(window, service, q.ROUNDTRIP)
                            except Exception as exc:
                                away_failure = exc
                            finally:
                                cloud.select_model(profile["id"])
                                inference.set_mode("cloud")
                            _, answer = submit(window, service, q.ROUNDTRIP)
                            assert answer.strip() == "OK" and store.session_id == session
                            cell["session_preserved"] = True
                            cell["returned_to_original_model"] = cloud.active_model == profile["id"]
                            if away_failure is not None:
                                raise away_failure
                        elif workflow == "mode_round_trip":
                            accepted = catalog.profiles.get(catalog.current_id).configuration
                            assert local_config.context_length == accepted.context_length and local_config.max_tokens == accepted.max_tokens
                            assert local_config.gpu_layers != 0
                            submit(window, service, q.ROUNDTRIP)
                            session = store.session_id
                            inference.set_mode("local")
                            _, answer = submit(window, service, q.ROUNDTRIP)
                            assert answer.strip() == "OK"
                            local = inference.local._get_engine()
                            url, local_key, process = local._ensure_started()
                            from urllib.request import Request, urlopen
                            with urlopen(Request(url + "/props", headers={"Authorization": "Bearer " + local_key}), timeout=10) as response:
                                actual_context = json.load(response)["default_generation_settings"]["n_ctx"]
                            cell["local_limits"] = {"context_length": actual_context, "max_output_tokens": local.max_response_tokens}
                            assert actual_context == local_config.context_length and local.max_response_tokens == local_config.max_tokens
                            inference.set_mode("cloud")
                            assert process.poll() is not None
                            _, answer = submit(window, service, q.ROUNDTRIP)
                            assert answer.strip() == "OK" and store.session_id == session
                            cell.update(session_preserved=True, previous_servers_exited=True)
                        elif workflow == "restart":
                            turn, _ = submit(window, service, q.AFTER_CANCEL)
                            assert completed_stat(turn) and turn.provider_responses
                            session = store.session_id
                            prior_consents = window._qualification_cloud_consents
                            consent_timer.stop()
                            window.close()
                            service.shutdown()
                            # New client/runtime/process objects, same isolated durable conversation.
                            cloud = ObservedCloud(config, api_key=api_key, selection_path=folder / "cloud-selection.json")
                            inference = HybridInferenceEngine(local=None, cloud=cloud, default_mode="cloud", fallback_to_local=False)
                            runtime = build_agent_runtime(inference, config=flags, portable_root=portable,
                                state_directory=portable / "state", host_access_policy=policy)
                            store = ConversationStore(store.path)
                            service = ConversationService(inference, store, agent_runtime=runtime,
                                portable_root=portable, host_access_policy=policy)
                            service.set_approval_requester(approve)
                            window = MainWindow(service, "qualification", inference=inference)
                            window.show()
                            consent_timer = accept_fixture_cloud_notice(window, app)
                            turn, answer = submit(window, service, "Reply exactly with pool-chat-ok and do not use a tool.")
                            assert "pool-chat-ok" in answer.casefold() and not turn.settled_calls and store.session_id == session
                            cell["session_preserved"] = True
                        else:
                            prompt, expected_effect = _prepare_capability_case(workflow, folder, patch)
                            patch.undo()  # Real Recycle Bin adapter; no substituted tool execution.
                            turn, answer = submit(window, service, prompt)
                            assert len(turn.settled_calls) == 1 and turn.settled_calls[0].result.success
                            capability = {"listing": "list", "reading": "read_text", "multiline-writing": "write_text",
                                "searching": "search", "copying": "copy", "moving": "move", "folder-creation": "mkdir", "trashing": "trash"}[workflow]
                            assert turn.settled_calls[0].call.capability == "filesystem." + capability
                            if workflow == "trashing":
                                assert not expected_effect["target"].exists()
                            else:
                                _verify_capability_case(workflow, expected_effect, answer)
                            assert approvals == ([] if workflow in {"listing", "reading", "searching"} else [("filesystem." + capability, True)])
                            cell["bytes_verified"] = True
                        # Profile settings are captured only after a successful actual SDK request.
                        assert any(r["profile"] == profile for r in cloud.requests)
                        cell.update(status="passed", terminal_verified=True)
                    except Exception as exc:
                        cell["error_type"] = type(exc).__name__
                        sites = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == __file__]
                        cell["error_check_line"] = sites[-1].lineno if sites else None
                    finally:
                        patch.undo()
                        if window.thread is not None:
                            window.cancel_current_task()
                            wait(window, 20)
                        turns = service.store.turns()
                        cell["terminal_outcomes"] = [{"status": t.outcome.status.value if t.outcome else "unsettled",
                            "ended": t.ended_at is not None, "finish_reason": t.outcome.completion.finish_reason if t.outcome else None}
                            for t in turns]
                        cell["request_cost"] = q.request_cost([t.outcome for t in turns])
                        cell["capability_results"] = [{"capability": c.call.capability, "success": c.result.success,
                            "failure_code": c.result.error.code if c.result.error else None} for t in turns for c in t.settled_calls]
                        cell["approvals"] = {"allowed": sum(allowed for _, allowed in approvals),
                                            "denied": sum(not allowed for _, allowed in approvals)}
                        cell["requests"] = [{k: v for k, v in r.items() if k != "profile"} for r in cloud.requests]
                        cell["cloud_privacy_acceptances"] = prior_consents + window._qualification_cloud_consents
                        consent_timer.stop()
                        window.close()
                        service.shutdown()
                        inference.close()
                        app.processEvents()
                        save()
                        print(profile["id"], repetition, workflow, cell["status"], flush=True)
    finally:
        report["all_owned_resources_released"] = all(
            ((resource._thread is None or not resource._thread.is_alive()) and (resource.client is None or resource.client.is_closed()))
            if hasattr(resource, "_thread") else resource.poll() is not None for resource in resources)
        save()
    if regression:
        junit = workspace / "regression.xml"
        # The development worktree isolates its SDK; a real package imports its installed SDK.
        bootstrap = "import sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); sys.path.append(str(Path.cwd()/'.testdeps')); import pytest; raise SystemExit(pytest.main(sys.argv[1:]))"
        command = [sys.executable, "-c", bootstrap, "--basetemp", ".pytest-tmp-c41r", "-o", "addopts=", "-q", f"--junitxml={junit}"]
        with (workspace / "regression.log").open("w") as log:
            completed = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        if junit.exists():
            suites = list(ET.parse(junit).getroot().iter("testsuite"))
            counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
            report["regression"] = {"exit_code": completed.returncode,
                "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
                "failed": counts["failures"], "errors": counts["errors"], "skipped": counts["skipped"],
                "junit_sha256": q.digest(junit.read_bytes())}
        else:
            report["regression"] = {"exit_code": completed.returncode}
    report["finished"] = True
    report["qualification_errors"] = gate.qualification_errors(report, gate.identity(root), expected)
    report["qualified"] = not report["qualification_errors"]
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--local-models", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--packaging-report", type=Path)
    args = parser.parse_args()
    key = args.key_file.read_text(encoding="utf-8-sig").strip() if args.key_file else os.environ.get("OPENAI_API_KEY", "")
    packaging = json.loads(args.packaging_report.read_text()) if args.packaging_report else None
    result = run(Path.cwd(), args.workspace.resolve(), args.report.resolve(), api_key=key,
                 local_models=args.local_models.resolve(), packaging=packaging)
    print("OpenAI qualification:", "passed" if result["qualified"] else "BLOCKED/FAILED")
    raise SystemExit(0 if result["qualified"] else 1)
