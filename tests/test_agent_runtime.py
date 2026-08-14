from __future__ import annotations

from copy import deepcopy
import json
from itertools import count
from pathlib import Path
from threading import Event, Timer

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent_runtime import (
    AgentRunStatus,
    AgentRuntime,
    AgentRuntimeLimits,
)
from app.capabilities.contracts import (
    Capability,
    ExecutionIsolation,
    PermissionClass,
)
from app.capabilities.crash_journal import (
    CallLifecycleState,
    CapabilityCrashJournal,
    JournaledCapabilityExecutor,
)
from app.capabilities.executor import CapabilityExecutor
from app.capabilities.permissions import (
    ApprovalManager,
    ApprovalStatus,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
)
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.inference.engine import InferenceEngine
from app.inference.protocol import (
    ModelCapabilityCall,
    ModelProtocolFailureCode,
    ModelResponse,
)
from app.runtime.cancellation import CancellationSource


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


class EchoCapability(Capability[EchoArguments]):
    name = "test.echo"
    description = "Echo one bounded test value."
    arguments_model = EchoArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def __init__(self):
        self.values: list[str] = []

    def execute(self, arguments, context):
        context.cancellation.raise_if_cancelled()
        self.values.append(arguments.value)
        return {"echo": arguments.value}


class BlockingCapability(EchoCapability):
    def __init__(self):
        super().__init__()
        self.started = Event()

    def execute(self, arguments, context):
        self.started.set()
        while True:
            context.cancellation.raise_if_cancelled()
            context.cancellation.wait(0.005)


class LargeOutputCapability(EchoCapability):
    def execute(self, arguments, context):
        context.cancellation.raise_if_cancelled()
        self.values.append(arguments.value)
        return {"content": "x" * 2_000}


class ScriptedModel(InferenceEngine):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[dict]] = []
        self.definitions = []
        self.before_request = {}

    def respond(self, messages):
        raise AssertionError("AgentRuntime must use the structured model boundary.")

    def respond_with_capabilities(self, messages, capabilities):
        index = len(self.requests)
        callback = self.before_request.get(index)
        if callback is not None:
            callback(messages, capabilities)
        self.requests.append(deepcopy(messages))
        self.definitions.append(tuple(capabilities))
        if not self.responses:
            raise AssertionError("The fake model response script was exhausted.")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class BlockingModel(InferenceEngine):
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.cancelled = Event()

    def respond(self, messages):
        raise AssertionError("AgentRuntime must use the structured model boundary.")

    def respond_with_capabilities(self, messages, capabilities):
        self.started.set()
        self.release.wait(2.0)
        return ModelResponse.text("late model response")

    def cancel_current_request(self):
        self.cancelled.set()


def capability_call(index: int, value: str = "hello", *, arguments=None):
    return ModelResponse.calls(
        (
            ModelCapabilityCall(
                provider_call_id=f"provider-call-{index}",
                capability="test.echo",
                arguments={"value": value} if arguments is None else arguments,
            ),
        )
    )


def build_runtime(
    tmp_path: Path,
    responses,
    *,
    capability=None,
    decision: PermissionDecision = PermissionDecision.ALLOW,
    limits: AgentRuntimeLimits | None = None,
    approval_requester_factory=None,
    model=None,
):
    implementation = capability or EchoCapability()
    scripted = model or ScriptedModel(responses)
    registry = CapabilityRegistry(
        (
            CapabilityRegistration(
                implementation,
                enabled=True,
                model_visible=True,
            ),
        )
    )
    gate = PermissionGate(
        (
            PermissionRule(
                "runtime-test-rule",
                decision,
                permission=PermissionClass.READ,
                capability_pattern="test.echo",
            ),
        )
    )
    manager_ids = count(1)
    manager = ApprovalManager(
        id_factory=lambda: f"approval-{next(manager_ids)}"
    )
    journal = CapabilityCrashJournal(tmp_path / "agent-journal.json")
    executor = JournaledCapabilityExecutor(CapabilityExecutor(), journal)
    requester = (
        approval_requester_factory(manager)
        if approval_requester_factory is not None
        else None
    )
    call_ids = count(1)
    runtime = AgentRuntime(
        model=scripted,
        registry=registry,
        permission_gate=gate,
        approval_manager=manager,
        executor=executor,
        limits=limits,
        call_id_factory=lambda: f"internal-call-{next(call_ids)}",
        approval_requester=requester,
    )
    return runtime, scripted, implementation, journal, manager


def run(runtime, tmp_path: Path, *, cancellation=None):
    return runtime.run(
        [{"role": "user", "content": "Run the bounded scenario."}],
        session_id="session-1",
        turn_id="turn-1",
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
        cancellation=cancellation,
    )


@pytest.mark.parametrize("call_count", [0, 1, 2, 5])
def test_zero_one_two_and_five_call_scenarios_complete_sequentially(
    tmp_path: Path,
    call_count: int,
):
    responses = [
        capability_call(index + 1, f"value-{index + 1}")
        for index in range(call_count)
    ]
    responses.append(ModelResponse.text(f"completed {call_count}"))
    runtime, model, capability, journal, _ = build_runtime(tmp_path, responses)

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert result.assistant_text == f"completed {call_count}"
    assert result.steps == call_count + 1
    assert result.capability_calls == call_count
    assert capability.values == [f"value-{index + 1}" for index in range(call_count)]
    assert len(model.requests) == call_count + 1
    assert len(journal.records) == call_count
    assert all(record.state == CallLifecycleState.COMPLETED for record in journal.records)


def test_structured_result_is_persisted_and_appended_before_model_continuation(
    tmp_path: Path,
):
    runtime, model, _, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1), ModelResponse.text("done")],
    )

    def verify_before_second_request(messages, definitions):
        del definitions
        assert journal.get("internal-call-1").state == CallLifecycleState.COMPLETED
        assert messages[-2]["role"] == "assistant"
        assert messages[-2]["capability_calls"][0]["provider_call_id"] == (
            "provider-call-1"
        )
        assert messages[-1]["role"] == "capability"
        assert messages[-1]["provider_call_id"] == "provider-call-1"
        assert messages[-1]["result"]["call_id"] == "internal-call-1"
        assert messages[-1]["result"]["output"] == {"echo": "hello"}

    model.before_request[1] = verify_before_second_request

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED


def test_invalid_arguments_return_to_model_without_execution_or_journaling(
    tmp_path: Path,
):
    runtime, model, capability, journal, _ = build_runtime(
        tmp_path,
        [
            capability_call(1, arguments={"wrong": "private-marker"}),
            ModelResponse.text("The arguments were invalid."),
        ],
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert capability.values == []
    assert journal.records == ()
    failure = model.requests[1][-1]["result"]
    assert failure["error"]["code"] == "invalid_arguments"
    assert "private-marker" not in json_text(failure)


def test_denied_call_is_journaled_and_returned_to_model_without_execution(
    tmp_path: Path,
):
    runtime, model, capability, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1), ModelResponse.text("Permission was denied.")],
        decision=PermissionDecision.DENY,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert capability.values == []
    assert journal.records[0].state == CallLifecycleState.DENIED
    assert model.requests[1][-1]["result"]["error"]["code"] == "permission_denied"


def test_ask_without_an_approval_surface_stops_in_durable_waiting_state(
    tmp_path: Path,
):
    runtime, _, capability, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1)],
        decision=PermissionDecision.ASK,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.APPROVAL_REQUIRED
    assert capability.values == []
    assert journal.records[0].state == CallLifecycleState.AWAITING_APPROVAL


def test_approved_ask_call_executes_once_and_completes(tmp_path: Path):
    def requester(manager):
        return lambda record: manager.resolve(
            record.approval_id,
            ApprovalStatus.APPROVED,
        )

    runtime, _, capability, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1), ModelResponse.text("Approved and complete.")],
        decision=PermissionDecision.ASK,
        approval_requester_factory=requester,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert capability.values == ["hello"]
    assert journal.records[0].state == CallLifecycleState.COMPLETED


def test_cancellation_covers_approval_waiting_and_persists_terminal_state(
    tmp_path: Path,
):
    runtime, _, capability, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1)],
        decision=PermissionDecision.ASK,
        approval_requester_factory=lambda manager: lambda record: None,
    )
    cancellation = CancellationSource()
    timer = Timer(0.03, cancellation.cancel)
    timer.daemon = True
    timer.start()

    result = run(runtime, tmp_path, cancellation=cancellation.token)
    timer.cancel()

    assert result.status == AgentRunStatus.CANCELLED
    assert capability.values == []
    assert journal.records[0].state == CallLifecycleState.CANCELLED


def test_repeated_identical_calls_stop_before_the_third_execution(tmp_path: Path):
    runtime, model, capability, journal, _ = build_runtime(
        tmp_path,
        [
            capability_call(1),
            capability_call(2),
            capability_call(3),
        ],
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.REPEATED_CALL
    assert result.steps == 3
    assert result.capability_calls == 3
    assert capability.values == ["hello", "hello"]
    assert len(model.requests) == 3
    assert len(journal.records) == 2


def test_duplicate_provider_call_id_is_a_bounded_protocol_failure(tmp_path: Path):
    duplicate = ModelResponse.calls(
        (
            ModelCapabilityCall(
                provider_call_id="provider-call-1",
                capability="test.echo",
                arguments={"value": "changed"},
            ),
        )
    )
    runtime, model, capability, _, _ = build_runtime(
        tmp_path,
        [capability_call(1), duplicate, ModelResponse.text("recovered")],
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert result.protocol_failures == 1
    assert capability.values == ["hello"]
    assert model.requests[2][-1]["role"] == "system"
    assert "duplicate_call_id" in model.requests[2][-1]["content"]


def test_protocol_failure_can_recover_but_repeated_failures_stop(tmp_path: Path):
    malformed = ModelResponse.failure(
        ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        "Malformed arguments.",
    )
    recovered, recovered_model, _, _, _ = build_runtime(
        tmp_path / "recovered",
        [malformed, ModelResponse.text("recovered")],
    )

    recovered_result = run(recovered, tmp_path / "recovered")

    assert recovered_result.status == AgentRunStatus.COMPLETED
    assert recovered_result.protocol_failures == 1
    assert "malformed_arguments" in recovered_model.requests[1][-1]["content"]

    stopped, _, _, _, _ = build_runtime(
        tmp_path / "stopped",
        [malformed, malformed],
    )
    stopped_result = run(stopped, tmp_path / "stopped")

    assert stopped_result.status == AgentRunStatus.PROTOCOL_FAILURE_LIMIT
    assert stopped_result.steps == 2


def test_multi_call_response_is_rejected_without_execution_and_can_recover(
    tmp_path: Path,
):
    multi_call = ModelResponse.calls(
        (
            ModelCapabilityCall(
                provider_call_id="provider-call-1",
                capability="test.echo",
                arguments={"value": "one"},
            ),
            ModelCapabilityCall(
                provider_call_id="provider-call-2",
                capability="test.echo",
                arguments={"value": "two"},
            ),
        )
    )
    runtime, model, capability, journal, _ = build_runtime(
        tmp_path,
        [multi_call, ModelResponse.text("recovered")],
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.COMPLETED
    assert result.protocol_failures == 1
    assert capability.values == []
    assert journal.records == ()
    assert "at most one" in model.requests[1][-1]["content"]


def test_maximum_step_limit_stops_before_another_model_request(tmp_path: Path):
    limits = AgentRuntimeLimits(max_steps=1)
    runtime, model, capability, _, _ = build_runtime(
        tmp_path,
        [capability_call(1)],
        limits=limits,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.STEP_LIMIT
    assert capability.values == ["hello"]
    assert len(model.requests) == 1


def test_accumulated_structured_transcript_has_a_hard_size_limit(tmp_path: Path):
    capability = LargeOutputCapability()
    limits = AgentRuntimeLimits(max_transcript_bytes=1_024)
    runtime, _, _, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1)],
        capability=capability,
        limits=limits,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.TRANSCRIPT_LIMIT
    assert capability.values == ["hello"]
    assert journal.records[0].state == CallLifecycleState.COMPLETED


def test_overall_timeout_stops_a_blocked_model_generation(tmp_path: Path):
    model = BlockingModel()
    limits = AgentRuntimeLimits(
        overall_timeout_seconds=0.03,
        poll_interval_seconds=0.005,
    )
    runtime, _, _, journal, _ = build_runtime(
        tmp_path,
        [],
        model=model,
        limits=limits,
    )

    result = run(runtime, tmp_path)
    model.release.set()

    assert result.status == AgentRunStatus.TIMED_OUT
    assert model.cancelled.is_set()
    assert journal.records == ()


def test_overall_timeout_cancels_blocked_capability_execution(tmp_path: Path):
    blocking = BlockingCapability()
    limits = AgentRuntimeLimits(
        overall_timeout_seconds=0.03,
        poll_interval_seconds=0.005,
    )
    runtime, _, _, journal, _ = build_runtime(
        tmp_path,
        [capability_call(1)],
        capability=blocking,
        limits=limits,
    )

    result = run(runtime, tmp_path)

    assert result.status == AgentRunStatus.TIMED_OUT
    assert blocking.started.is_set()
    assert journal.records[0].state == CallLifecycleState.CANCELLED


def test_cancellation_stops_blocked_generation_and_capability_execution(
    tmp_path: Path,
):
    model = BlockingModel()
    generation_runtime, _, _, _, _ = build_runtime(
        tmp_path / "generation",
        [],
        model=model,
    )
    generation_cancel = CancellationSource()
    generation_timer = Timer(0.03, generation_cancel.cancel)
    generation_timer.daemon = True
    generation_timer.start()

    generation_result = run(
        generation_runtime,
        tmp_path / "generation",
        cancellation=generation_cancel.token,
    )
    model.release.set()
    generation_timer.cancel()

    assert generation_result.status == AgentRunStatus.CANCELLED
    assert model.cancelled.is_set()

    capability_cancel = CancellationSource()
    blocking = BlockingCapability()
    capability_runtime, _, _, journal, _ = build_runtime(
        tmp_path / "capability",
        [capability_call(1)],
        capability=blocking,
    )
    capability_timer = Timer(0.03, capability_cancel.cancel)
    capability_timer.daemon = True
    capability_timer.start()

    capability_result = run(
        capability_runtime,
        tmp_path / "capability",
        cancellation=capability_cancel.token,
    )
    capability_timer.cancel()

    assert capability_result.status == AgentRunStatus.CANCELLED
    assert blocking.started.is_set()
    assert journal.records[0].state == CallLifecycleState.CANCELLED


def test_agent_runtime_is_connected_only_through_the_phase8_feature_gate():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config" / "agent.json").read_text(encoding="utf-8"))
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    service = (root / "app" / "conversation" / "service.py").read_text(
        encoding="utf-8"
    )

    assert config == {
        "filesystem_stat_enabled": False,
        "full_local_read_enabled": False,
    }
    assert "load_agent_feature_config" in main
    assert "agent_config.filesystem_stat_enabled" in main
    assert "agent_runtime: AgentRuntime | None = None" in service


def json_text(value) -> str:
    import json

    return json.dumps(value, sort_keys=True)
