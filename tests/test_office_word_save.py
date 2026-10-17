"""Word-only save projection and completion through the production owned bridge."""
from copy import deepcopy
import json
from types import SimpleNamespace

import jsonschema
import pytest

from app.capabilities.contracts import CapabilityArgumentError
from app.capabilities.registry import CapabilityRegistry
from app.inference.completion import CompletionMetadata
from app.inference.openai_tools import _arguments, normalize_responses_calls, responses_function_tools, responses_input
from app.mcp.office_capabilities import OfficeCapability, OfficeCapabilityRegistry
from app.mcp.office_contracts import OFFICE_TOOLS, OfficeExposure, SaveArguments, office_catalog
from app.mcp.office_word_save import word_save_definition


SAVE = next(t for t in OFFICE_TOOLS if t.name == "office.save")


def registry(application, applications=("excel", "word")):
    bridge = SimpleNamespace(live=False, selected_application=application,
        exposure=OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1,
            applications=applications))
    return OfficeCapabilityRegistry(CapabilityRegistry([]), bridge, SimpleNamespace(mode="cloud"),
        resource_policy=lambda *args: None, write_policy=None)


@pytest.mark.parametrize("application", ["word", "excel", None])
def test_only_selected_word_receives_narrower_save_choices(application):
    instance = registry(application)
    definitions = instance.model_definitions()
    baseline = office_catalog(instance.connection.exposure).model_definitions()
    for actual, original in zip(definitions, baseline, strict=True):
        if original.name == "office.save" and application == "word":
            assert actual == word_save_definition()
        else:
            assert actual == original
    assert instance.resolve("office.save").arguments_model is SaveArguments


def test_word_only_connection_is_guided_before_attachment_and_definitions_are_fresh():
    instance = registry(None, ("word",))
    definition = next(t for t in instance.model_definitions() if t.name == "office.save")
    definition.input_schema["properties"]["overwrite"]["const"] = True
    assert next(t for t in instance.model_definitions() if t.name == "office.save") == word_save_definition()


@pytest.mark.parametrize("path,overwrite", [(None, None), (None, False), ("C:/new.docx", False)])
def test_strict_provider_save_roundtrip_validates_at_host(path, overwrite):
    definition = word_save_definition()
    wire = {"session": "attached-session", "path": path, "overwrite": overwrite}
    native = responses_function_tools((definition,))[0]
    jsonschema.validate(wire, native["parameters"])
    response = normalize_responses_calls([{"call_id": "save-call", "name": native["name"],
        "arguments": json.dumps(wire)}], (definition,), CompletionMetadata())
    assert response.protocol_failure is None
    actual = SaveArguments.model_validate(response.capability_calls[0].arguments)
    assert actual.path == path and actual.overwrite is False


@pytest.mark.parametrize("path", [None, "C:/new.docx"])
def test_word_strict_schema_cannot_offer_unsupported_overwrite(path):
    schema = responses_function_tools((word_save_definition(),))[0]["parameters"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"session": "s", "path": path, "overwrite": True}, schema)
    # Excel's original contract and explicit Save As choices are untouched.
    assert SaveArguments(session="s", path="C:/new.xlsx", overwrite=True).overwrite


@pytest.mark.parametrize("native_evidence", [False, True])
def test_previous_save_attempts_remain_replayable_under_narrower_word_schema(native_evidence):
    from tests.test_openai_replay import evidence, history_for
    from tests.test_openai_tools import function
    legacy = SAVE.definition()
    schema = legacy.input_schema
    wire = _arguments(schema, {"session": "s", "overwrite": True}, schema, from_wire=False)
    output = [function(legacy, wire)]
    response = normalize_responses_calls(output, (legacy,), CompletionMetadata())
    assert response.protocol_failure is None
    history = [{"role": "user", "content": "Synthetic historical save"},
        *history_for(evidence(output), response.capability_calls)]
    if not native_evidence:
        history[1].pop("openai_response")
    projected = responses_input(history, (word_save_definition(),))
    if native_evidence:
        assert projected[1] == output[0]
    else:
        assert json.loads(projected[1]["arguments"]) == wire
    # Historical evidence grants no new execution or live decoding allowance.
    assert normalize_responses_calls(output, (word_save_definition(),), CompletionMetadata()).protocol_failure is not None


@pytest.mark.parametrize("payload,rule", [
    ({"session": "s", "overwrite": True}, "overwrite must be false"),
    ({"session": "s", "snapshot": "PRIVATE"}, "omit edit/snapshot fields"),
    ({"session": "PRIVATE/INVALID"}, "unchanged identifier"),
    ({"session": "s", "path": ""}, "nonempty text"),
    ({"session": "s", "PRIVATE": "PRIVATE"}, "only session, path and overwrite"),
])
def test_word_save_rejections_explain_exact_recovery_without_private_values(payload, rule):
    bridge = registry("word").connection
    capability = OfficeCapability(SAVE, bridge, None, None, None)
    before = deepcopy(payload)
    with pytest.raises(CapabilityArgumentError) as caught:
        capability.validate_arguments(payload)
    message = caught.value.failure.message
    assert rule in message and "No save was dispatched" in message
    assert "PRIVATE" not in message and len(message) <= 500
    assert payload == before
    with pytest.raises(CapabilityArgumentError) as original:
        OfficeCapability(SAVE, registry("excel").connection, None, None, None).validate_arguments(payload)
    assert original.value.failure.message == "The capability arguments did not match the required schema."


@pytest.mark.parametrize("recover_invalid_save", [False, True])
def test_four_word_edits_then_strict_save_finish_without_replaying_work(tmp_path, recover_invalid_save):
    from app.agent.contracts import AgentRunStatus
    from app.inference.protocol import ModelCapabilityCall, ModelResponse
    from tests.test_bounded_edit_recovery import RoomyScriptedModel
    from tests.test_office_mcp_capabilities import ROOT, runtime_for
    from tests.test_office_mcp_live import execute
    from tests.test_office_mcp_word import connection, patch
    from app.security.write_policy import HostWritePolicy

    bridge = connection()
    model = RoomyScriptedModel([], auto_review=False)
    model.mode = "cloud"
    (tmp_path / "application").mkdir()
    runtime = runtime_for(bridge, tmp_path / "runtime", model, policy=bridge.resource_policy)
    for name in ("office.word_edit", "office.save"):
        runtime.registry.resolve(name).write_policy = HostWritePolicy(tmp_path / "application")
    approvals = []
    def approve(record):
        approvals.append(record)
        runtime.resolve_approval(record.approval_id, True)
    runtime.set_approval_requester(approve)
    destination = tmp_path / "working.docx"
    destination.write_bytes(b"Original synthetic file")
    try:
        bridge.connect()
        bridge.control("fixture-document", {"path": str(destination)})
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        assert bridge.selected_application == "word"
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        def response(index, name, arguments):
            return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"provider-{index}",
                capability=name, arguments=arguments),))
        model.responses = [response(i, "office.read", {"session": session, "target": "document"}) for i in range(8)]
        model.responses.extend([response(8, "office.save", {"session": session}), ModelResponse.text("Synthetic Word task completed.")])
        if recover_invalid_save:
            model.responses.insert(8, response(80, "office.save", {"session": session, "overwrite": True}))
        def edit_at(index):
            def edit(messages, definitions):
                view = [m["result"]["output"] for m in messages if m.get("role") == "capability"][-1]
                model.responses[0] = response(index, "office.word_edit", patch(session, view, f"Revision {index}"))
            return edit
        def save(messages, definitions):
            if recover_invalid_save:
                failure = [m["result"] for m in messages if m.get("role") == "capability"][-1]
                assert "overwrite must be false" in failure["error"]["message"]
                assert "No save was dispatched" in failure["error"]["message"]
            definition = next(d for d in definitions if d.name == "office.save")
            assert definition == word_save_definition()
            schema = definition.input_schema
            wire = _arguments(schema, {"session": session}, schema, from_wire=False)
            native = responses_function_tools((definition,))[0]
            jsonschema.validate(wire, native["parameters"])
            model.responses[0] = normalize_responses_calls([{"call_id": "save-call", "name": native["name"],
                "arguments": json.dumps(wire)}], (definition,), CompletionMetadata())
        model.before_request = {i: edit_at(i) for i in (1, 3, 5, 7)}
        model.before_request[9 if recover_invalid_save else 8] = save
        outcome = runtime.run([{"role": "user", "content": "Synthetic Word save completion regression."}],
            session_id="test-session", turn_id="test-turn", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert outcome.status == AgentRunStatus.COMPLETED, (outcome.message,
            [(s.call.capability, s.result.error.model_dump() if s.result.error else None) for s in outcome.settled_calls])
        assert outcome.semantic_corrections == int(recover_invalid_save)
        assert sum(not item.result.success for item in outcome.settled_calls) == int(recover_invalid_save)
        names = [item.call.capability for item in outcome.settled_calls]
        assert names.count("office.word_edit") == 4 and names.count("office.save") == 1 + int(recover_invalid_save)
        assert len(approvals) == 5
        assert outcome.settled_calls[-1].result.output["saved"] is True
        assert destination.read_bytes() == b"Synthetic Word file"
    finally:
        runtime.shutdown()
    assert bridge.selected_application is None
    assert not bridge.diagnostics["worker_alive"] and bridge.diagnostics["temporary_released"]
