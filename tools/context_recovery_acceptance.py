"""Run one fixed acceptance arm against current or frozen application source.

Only synthetic fixtures are used. The report contains counters, hashes and
booleans, never messages, tool arguments/results, model text or credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import monotonic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--installation-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--variant", choices=("baseline", "recovery"), required=True)
    parser.add_argument("--model-id", default="Qwen314BQ4KM.gguf")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--deterministic", action="store_true", help="Exercise source architecture with fixture responses; no model allocation or live qualification.")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 3:
        parser.error("Acceptance repetitions must be between one and three.")
    source, installation = args.source_root.resolve(), args.installation_root.resolve()
    sys.path.insert(0, str(source))
    # Both arms share the real installed runtime/model/config paths, but import
    # application implementation from their respective source snapshots.
    import app.settings.paths as paths
    paths.PATHS = paths.RuntimePaths(installation, installation / "config", installation / "models", installation / "state")
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.context import calculate_context_budget, capability_schema_reserve
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.engine import InferenceEngine
    from app.inference.protocol import ModelCapabilityCall, ModelResponse, native_chat_messages
    from app.inference.llama_server_backend import LlamaServerInferenceEngine
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import load_agent_feature_config
    from app.settings.local_models import LocalModelCatalog
    from app.settings.model import load_model_config, detect_nvidia_memory_mib
    from app.state.storage import JsonStore
    from tests.fixtures.context_reliability import large_css_fixture

    started = monotonic()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    flags = load_agent_feature_config()
    if args.variant == "recovery":
        flags = flags.model_copy(update={"context_recovery_enabled": True})
    catalog = LocalModelCatalog(installation / "models", installation / "config/model.json", load_model_config(),
        selection_path=workspace / "selection.json")
    configuration = catalog.configuration(args.model_id)
    profile = catalog._resolutions[args.model_id]
    if args.deterministic:
        target = next(p.configuration for p in catalog.profiles.profiles if p.model_id == args.model_id)
        report_effective = {**profile["effective"], "context_length": target.context_length,
                            "max_response_tokens": target.max_tokens, "gpu_layers": target.gpu_layers}
        class FixtureInference(InferenceEngine):
            context_length = target.context_length
            max_response_tokens = target.max_tokens

            @staticmethod
            def count_message_tokens(messages):
                from math import ceil
                return max(1, ceil(sum(len(m["content"]) for m in messages) / 4) + 4 * len(messages) + 3)

            def respond(self, messages):
                return "fixture response"

            def prepare(self):
                pass

            def close(self):
                pass

            def respond_with_capabilities(self, messages, definitions):
                native_chat_messages(messages, definitions)
                latest_user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
                if messages[-1].get("role") == "capability":
                    result = messages[-1]["result"]
                    if not result["success"]:
                        return ModelResponse.text("The requested operation failed.")
                    output = result["output"]
                    if result["capability"] == "filesystem.stat":
                        return ModelResponse.text(str(output["size_bytes"]))
                    if result["capability"] == "filesystem.read_text":
                        if "SESSION_MARKER=pressure-verified" in output.get("text", ""):
                            return ModelResponse.text("pressure-verified")
                        if "filesystem.search" in {d.name for d in definitions}:
                            return ModelResponse.calls((ModelCapabilityCall(provider_call_id="call_0", capability="filesystem.search",
                                arguments={"path": ".", "query": "SESSION_MARKER", "max_depth": 0, "max_files": 8,
                                           "max_file_bytes": 65536}),))
                        return ModelResponse.text("Marker unavailable from the bounded result.")
                    if result["capability"] == "filesystem.search":
                        found = any(m.get("relative_path") == "acceptance-large.txt" and "pressure-verified" in m.get("snippet", "") for m in output.get("matches", []))
                        return ModelResponse.text("pressure-verified" if found else "Marker unavailable.")
                    return ModelResponse.text("ready")
                if latest_user.startswith("For this session remember"):
                    return ModelResponse.text("remembered")
                if latest_user.startswith("Return only the exact session token"):
                    remembered = any("For this session remember the exact token SESSION_TOKEN=violet-731" in m.get("content", "") for m in messages if m.get("role") == "user")
                    return ModelResponse.text("SESSION_TOKEN=violet-731" if remembered else "Token unavailable.")
                if latest_user.startswith("This is ordinary conversation"):
                    return ModelResponse.text("chat-0")
                if "Make a second identical instance" in latest_user:
                    known_source = next(m["result"]["output"]["path"] for m in reversed(messages)
                        if m.get("role") == "capability" and m["result"].get("capability") == "filesystem.stat"
                        and m["result"].get("success") and Path(m["result"]["output"].get("path", "")).name == "acceptance-note.txt")
                    name, arguments = "filesystem.copy", {"source_path": known_source,
                        "destination_path": str(Path(known_source).with_name("replica.txt"))}
                elif "filesystem.read_text" in latest_user:
                    name, arguments = "filesystem.read_text", {"path": "acceptance-large.txt", "max_bytes": 65536, "max_lines": 1000}
                else:
                    name = "filesystem.stat"
                    arguments = {"path": "replica.txt" if "replica.txt" in latest_user else "acceptance-note.txt"}
                if name not in {d.name for d in definitions}:
                    return ModelResponse.text("The required capability is unavailable.")
                return ModelResponse.calls((ModelCapabilityCall(provider_call_id="call_0", capability=name, arguments=arguments),))
        backend = FixtureInference()
    else:
        report_effective = profile["effective"]
        target = next(p.configuration for p in catalog.profiles.profiles if p.model_id == args.model_id)
        if configuration.context_length != target.context_length or configuration.max_tokens != target.max_tokens or configuration.gpu_layers == 0:
            JsonStore(args.report).save({"schema_version": 1, "variant": args.variant, "measurement_kind": "live",
                "finished": False, "accepted_limits_available": False, "rollout_qualified": False,
                "model_id": args.model_id, "effective_model": report_effective,
                "gpu_before_load_mib": profile["gpu_before_load_mib"], "no_model_allocated": True})
            print("Accepted model limits unavailable under the current memory guard. No model was allocated.")
            return
        backend = LlamaServerInferenceEngine(configuration)

    class MeasuredInference(InferenceEngine):
        def __init__(self):
            self.requests = []

        @property
        def context_length(self):
            return backend.context_length

        @property
        def max_response_tokens(self):
            return backend.max_response_tokens

        def count_message_tokens(self, messages):
            return backend.count_message_tokens(messages)

        def _call(self, messages, definitions=None):
            budget = calculate_context_budget(self, messages,
                reserved_tokens=capability_schema_reserve(definitions or ()))
            entry = {"estimated_input_tokens": budget.system_message_tokens + budget.conversation_tokens
                + budget.structured_tool_history_tokens + budget.capability_schema_reserve,
                "input_tokens": None, "output_tokens": None, "total_tokens": None, "failed": False}
            self.requests.append(entry)
            try:
                response = backend.respond(messages) if definitions is None else backend.respond_with_capabilities(messages, definitions)
                completion = getattr(response, "completion", None)
                if completion is not None:
                    entry.update(completion.usage.model_dump())
                return response
            except Exception:
                entry["failed"] = True
                raise

        def respond(self, messages):
            return self._call(messages)

        def respond_with_capabilities(self, messages, capabilities):
            return self._call(messages, capabilities)

        def cancel_current_request(self):
            backend.cancel_current_request()

    measured = MeasuredInference()
    report = {"schema_version": 1, "variant": args.variant,
        "measurement_kind": "deterministic" if args.deterministic else "live",
        "authority": "synthetic_full_local_fixture",
        "source_fingerprint": hashlib.sha256(b"".join((source / name).read_bytes() for name in
            ("app/conversation/context.py", "app/conversation/orchestrator.py", "app/agent/runtime.py"))).hexdigest(),
        "acceptance_suite_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "prompt_source_sha256": hashlib.sha256((source / "app/conversation/prompt.py").read_bytes()).hexdigest(),
        "model_id": args.model_id, "model_sha256": profile["sha256"],
        "profiles_sha256": profile["profiles_sha256"], "effective_model": report_effective,
        "effective_flags": flags.model_dump(exclude={"runtime_limits"}),
        "effective_agent_limits": flags.runtime_limits.model_dump(), "sessions": []}
    services, processes = [], []

    def save():
        report["duration_seconds"] = round(monotonic() - started, 2)
        JsonStore(args.report).save(report)

    def service_for(folder):
        folder.mkdir()
        application = folder / "portable"
        application.mkdir()
        state = application / "state"
        policy = HostAccessPolicy.full_local(application_root=application, user_home=folder, acknowledged=True)
        runtime = build_agent_runtime(measured, config=flags, portable_root=application,
            state_directory=state, host_access_policy=policy)
        service = ConversationService(measured, ConversationStore(state / "conversation.json"),
            agent_runtime=runtime, portable_root=application, host_access_policy=policy)
        services.append(service)
        approval_ids = []
        def approve(record):
            # Authorization applies only to the exact synthetic copy in this fixture.
            allowed = record.capability == "filesystem.copy" and str((folder / "replica.txt").resolve()) in record.approval_preview
            approval_ids.append(record.approval_id)
            service.resolve_approval(record.approval_id, allowed)
        service.set_approval_requester(approve)
        return service, approval_ids, folder

    def turn(service, prompt, validator):
        before = len(measured.requests)
        error = None
        try:
            answer = service.run(prompt)
            passed = bool(validator(answer))
        except Exception as exc:
            passed, error = False, type(exc).__name__
        outcome = service.store.turns()[-1].outcome
        entry = {"passed": passed, "outcome": outcome.status.value if outcome else "unsettled",
            "error_type": error, "requests": len(measured.requests) - before,
            "call_count": len(service.store.turns()[-1].settled_calls)}
        if outcome:
            for name in ("context_projections", "context_compactions", "semantic_corrections", "protocol_failures"):
                entry[name] = getattr(outcome, name, 0)
        return entry

    try:
        backend.prepare()
        if not args.deterministic:
            _url, _key, process = backend._ensure_started()
            processes.append(process)
        report["running_limits"] = {"context_length": backend.context_length, "max_response_tokens": backend.max_response_tokens}
        report["gpu_after_load_mib"] = detect_nvidia_memory_mib()
        for repetition in range(args.repetitions):
            for workload in ("accepted_small", "continuous_pressure"):
                service, approvals, folder = service_for(workspace / f"{workload}-{repetition}")
                note = folder / "acceptance-note.txt"
                note.write_bytes(b"A" * 83)
                first_request = len(measured.requests)
                session = {"workload": workload, "repetition": repetition, "turns": []}
                report["sessions"].append(session)
                if workload == "accepted_small":
                    cases = [
                        ("Use filesystem.stat exactly once to inspect acceptance-note.txt, then report its size in bytes.", lambda a: "83" in a),
                        ("This is ordinary conversation number 0. Reply exactly with chat-0; do not use a tool.", lambda a: a.strip() == "chat-0"),
                        ("Use filesystem.stat exactly once to inspect acceptance-note.txt, then report its size in bytes.", lambda a: "83" in a),
                    ]
                else:
                    css = large_css_fixture()
                    # Place a literal requirement target in the middle, beyond the prefix excerpt.
                    lines = css.splitlines(keepends=True)
                    lines[97] = "/* SESSION_MARKER=pressure-verified */\n" + lines[97]
                    (folder / "acceptance-large.txt").write_text("".join(lines), encoding="utf-8")
                    cases = [
                        ("For this session remember the exact token SESSION_TOKEN=violet-731. When I later ask for the session token, return it exactly. Now reply only remembered; do not use a tool.", lambda a: a.strip() == "remembered"),
                        ("Use filesystem.stat exactly once to inspect acceptance-note.txt, then report its size in bytes.", lambda a: "83" in a),
                        ("Use filesystem.read_text exactly once to inspect acceptance-large.txt with max_bytes=65536 and max_lines=1000, then report only the value of SESSION_MARKER.", lambda a: "pressure-verified" in a),
                        ("Return only the exact session token I asked you to remember. Do not use any tool.", lambda a: "SESSION_TOKEN=violet-731" in a),
                        ("Use filesystem.read_text exactly once to inspect acceptance-large.txt with max_bytes=65536 and max_lines=1000, then report only the value of SESSION_MARKER.", lambda a: "pressure-verified" in a),
                        ("Make a second identical instance of acceptance-note.txt named replica.txt, and report when it is ready.", lambda a: (folder / "replica.txt").is_file() and (folder / "replica.txt").read_bytes() == note.read_bytes()),
                        ("Use filesystem.stat exactly once to inspect replica.txt, then report its size in bytes.", lambda a: "83" in a),
                        ("Return only the exact session token I asked you to remember. Do not use any tool.", lambda a: "SESSION_TOKEN=violet-731" in a),
                    ]
                for index, (prompt, validator) in enumerate(cases):
                    entry = turn(service, prompt, validator)
                    session["turns"].append(entry)
                    save()
                    print(args.variant, workload, repetition, "turn", index + 1,
                        "passed", entry["passed"], "status", entry["outcome"], "requests", entry["requests"], flush=True)
                observed = measured.requests[first_request:]
                session["continuous_success"] = all(t["passed"] and t["outcome"] == "completed" for t in session["turns"])
                session["generation_requests"] = len(observed)
                session["estimated_input_tokens"] = sum(r["estimated_input_tokens"] for r in observed)
                for name in ("input_tokens", "output_tokens", "total_tokens"):
                    session["observed_" + name] = (sum(r[name] for r in observed)
                        if all(r[name] is not None for r in observed) else None)
                session["usage_coverage"] = sum(r["input_tokens"] is not None and r["output_tokens"] is not None for r in observed)
                session["approval_count"] = len(approvals)
                session["turns_without_session_reset"] = len(session["turns"])
                service.store.close_session()
                save()
    finally:
        for service in services:
            service.shutdown()
        backend.close()
        report["all_owned_servers_exited"] = all(p.poll() is not None for p in processes)
        report["gpu_after_shutdown_mib"] = detect_nvidia_memory_mib()
        report["finished"] = True
        save()


if __name__ == "__main__":
    main()
