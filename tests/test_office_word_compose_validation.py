"""Provider-shaped report calls and safe, actionable composition refusals."""
from copy import deepcopy
import json
from types import SimpleNamespace

import jsonschema
import pytest

from app.capabilities.contracts import CapabilityArgumentError, CapabilityResult
from app.inference.completion import CompletionMetadata
from app.inference.openai_tools import (
    _arguments, normalize_responses_calls, responses_function_tools, responses_input,
)
from app.inference.protocol import model_capability_calls_message, model_capability_result_message
from app.mcp.office_capabilities import OfficeCapability
from app.mcp.office_contracts import OFFICE_TOOLS, WordComposeArguments, canonical_json
from tests.test_filesystem_read_text import context
from tests.test_office_word_authoring import report_plan


CONTRACT = next(tool for tool in OFFICE_TOOLS if tool.name == "office.word_compose")


def tool():
    # Any attempted bridge/resource/permission access fails: invalid arguments
    # must be refused before native Word or approval preparation is reached.
    return OfficeCapability(CONTRACT, None, None, None, None)


def wire_call(plan, call_id="call_report"):
    definition = CONTRACT.definition()
    schema = definition.input_schema
    wire = _arguments(schema, plan, schema, from_wire=False)
    native = responses_function_tools((definition,))[0]
    response = normalize_responses_calls([{
        "call_id": call_id, "name": native["name"], "arguments": canonical_json(wire),
    }], (definition,), CompletionMetadata())
    assert response.protocol_failure is None
    return wire, response.capability_calls[0]


def test_complete_three_page_report_round_trips_the_strict_provider_boundary():
    before = deepcopy(CONTRACT.definition().input_schema)
    wire, call = wire_call(report_plan())
    jsonschema.validate(wire, responses_function_tools((CONTRACT.definition(),))[0]["parameters"])
    plan = tool().validate_arguments(call.arguments)
    assert plan == WordComposeArguments.model_validate(report_plan())
    assert sum(block.kind == "page_break" for block in plan.blocks) == 2
    assert sum(block.kind == "table" for block in plan.blocks) == 1
    assert len(canonical_json(wire).encode()) < 32768
    assert CONTRACT.definition().input_schema == before


def redundant_breaks(plan):
    value = deepcopy(plan)
    blocks = [{"kind": "page_break"}, {"kind": "page_break"}]
    for block in value["blocks"]:
        blocks.append(block)
        if block["kind"] == "page_break":
            blocks.append({"kind": "page_break"})
    value["blocks"] = blocks + [{"kind": "page_break"}, {"kind": "page_break"}]
    return value


def test_redundant_report_breaks_normalize_before_dispatch_without_changing_wire_history():
    original = redundant_breaks(report_plan())
    before = deepcopy(original)
    wire, call = wire_call(original)
    effective = tool().validate_arguments(call.arguments)
    assert effective == WordComposeArguments.model_validate(report_plan())
    assert original == before
    assert WordComposeArguments.model_validate(effective.model_dump(mode="json")) == effective
    transcript = [model_capability_calls_message((call,), provider_message_id="response_report"),
                  model_capability_result_message(call, CapabilityResult(
                      call_id=call.provider_call_id, capability=call.capability, success=True,
                      output={"synthetic_dispatch": True}, duration_ms=0).model_dump(mode="json"),
                      provider_message_id="response_report")]
    replay = responses_input(transcript, (CONTRACT.definition(),))
    assert json.loads(replay[0]["arguments"]) == wire
    assert sum(block["kind"] == "page_break" for block in call.arguments["blocks"]) == 8
    assert sum(block.kind == "page_break" for block in effective.blocks) == 2


@pytest.mark.parametrize("blocks,expected", [
    ([{"kind": "page_break"}, {"kind": "paragraph", "text": "body"}], ["paragraph"]),
    ([{"kind": "paragraph", "text": "body"}, {"kind": "page_break"}], ["paragraph"]),
    ([{"kind": "paragraph", "text": "first"}, {"kind": "page_break"},
      {"kind": "page_break"}, {"kind": "paragraph", "text": "second"}],
     ["paragraph", "page_break", "paragraph"]),
    ([{"kind": "page_break"}, {"kind": "table", "cells": [["body"]], "widths_mm": [100]},
      {"kind": "page_break"}], ["table"]),
    ([{"kind": "paragraph", "text": "first"}, {"kind": "page_break"},
      {"kind": "paragraph", "text": ""}, {"kind": "page_break"},
      {"kind": "paragraph", "text": "third"}],
     ["paragraph", "page_break", "paragraph", "page_break", "paragraph"]),
])
def test_report_breaks_delimit_content_without_creating_empty_pages(blocks, expected):
    plan = WordComposeArguments.model_validate({**report_plan(), "blocks": blocks})
    assert [block.kind for block in plan.blocks] == expected


@pytest.mark.parametrize("blocks", [
    [{"kind": "page_break"}, {"kind": "page_break"}],
    [{"kind": "page_break", "private": "must-not-be-dropped"}, {"kind": "paragraph", "text": "body"}],
    [{"kind": "paragraph", "text": "body"}] + [{"kind": "page_break"}] * 96,
])
def test_normalization_retains_empty_report_unknown_field_and_block_count_refusals(blocks):
    with pytest.raises(ValueError):
        WordComposeArguments.model_validate({**report_plan(), "blocks": blocks})


@pytest.mark.parametrize("change,expected", [
    ({"blocks": [{"kind": "paragraph", "text": "private\nparagraph"}]}, "blocks.0.text"),
    ({"blocks": [{"kind": "table", "cells": [["private\tcell"]], "widths_mm": [100]}]}, "blocks.0.cells.0.0"),
    ({"header": "private\nheader"}, "header"),
    ({"footer": "private\tfooter"}, "footer"),
    ({"header": "p" * 513}, "header"),
    ({"blocks": [{"kind": "table", "cells": [["a", "b"]], "widths_mm": [4, 100]}]}, "blocks.0.widths_mm.0"),
    ({"blocks": [{"kind": "table", "cells": [["a", "b"]], "widths_mm": [100]}]}, "one column width per column"),
    ({"blocks": [{"kind": "table", "cells": [["a", "b"]], "widths_mm": [100, 100]}]}, "printable body width"),
    ({"blocks": [{"kind": "table", "cells": [["a"], ["b", "c"]], "widths_mm": [100]}]}, "rectangular"),
    ({"layout": {"margins_mm": [4, 20, 20, 20]}}, "layout.margins_mm.0"),
    ({"layout": {"margins_mm": [10, 20, 20, 20], "header_mm": 10}}, "header/footer distances inside the margins"),
    ({"format": {"size": 10.7}}, "format.size"),
    ({"blocks": [{"kind": "page_break"}]}, "no paragraphs or tables"),
])
def test_refusal_explains_the_actual_field_without_dispatch_or_input_echo(tmp_path, change, expected):
    args = {**report_plan(), **change}
    value = tool().invoke(args, context(tmp_path))
    assert not value.success and value.error.code.value == "invalid_arguments"
    assert expected in value.error.message
    assert "No Word write was dispatched" in value.error.message
    assert "private" not in value.error.message and "p" * 513 not in value.error.message
    assert "function-after" not in value.error.message
    assert len(value.error.message) <= 500


def test_table_union_refusal_does_not_suggest_missing_paragraph_text():
    args = {**report_plan(), "blocks": [{"kind": "table", "widths_mm": [100]}]}
    with pytest.raises(CapabilityArgumentError) as error:
        tool().validate_arguments(args)
    assert "blocks.0.cells: required field is missing" in error.value.failure.message
    assert "text: required field is missing" not in error.value.failure.message
    assert len(error.value.failure.details) == 1


@pytest.mark.parametrize("blocks,breaks,empty", [
    ([{}], 0, 1),
    ([{"kind": "page_break"}], 1, 0),
    ([{}, {"kind": "page_break"}, {}], 1, 2),
])
def test_empty_plan_explains_full_replacement_and_retains_content_free_shape(blocks, breaks, empty):
    with pytest.raises(CapabilityArgumentError) as error:
        tool().validate_arguments({**report_plan(), "blocks": blocks})
    failure = error.value.failure
    assert "no paragraphs or tables" in failure.message
    assert "COMPLETE document body" in failure.message
    assert "page_break_before" in failure.message
    assert "No Word write was dispatched" in failure.message
    assert len(failure.message) <= 500
    assert failure.details[-1] == {"word_plan_shape": {
        "paragraphs": 0, "tables": 0, "page_breaks": breaks, "empty_blocks": empty}}


def test_empty_block_is_no_longer_a_page_break_in_the_advertised_or_provider_schema():
    definition = CONTRACT.definition()
    schema = definition.input_schema
    args = {**report_plan(), "blocks": [{}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(args, schema)
    # Independent fixture for the old strict wire shape; do not generate this
    # through the current domain-to-wire adapter, which must reject it too.
    wire = _arguments(schema, report_plan(), schema, from_wire=False)
    wire["blocks"] = [{"kind": None}]
    native = responses_function_tools((definition,))[0]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(wire, native["parameters"])
    response = normalize_responses_calls([{
        "call_id": "call_empty_block", "name": native["name"], "arguments": canonical_json(wire),
    }], (definition,), CompletionMetadata())
    assert response.protocol_failure is not None and not response.capability_calls


def test_missing_optional_kinds_do_not_discard_paragraph_or_table_content():
    args = report_plan()
    for block in args["blocks"]:
        if block["kind"] != "page_break":
            del block["kind"]
    wire, call = wire_call(args)
    jsonschema.validate(wire, responses_function_tools((CONTRACT.definition(),))[0]["parameters"])
    effective = tool().validate_arguments(call.arguments)
    assert effective == WordComposeArguments.model_validate(report_plan())


@pytest.mark.parametrize("body", [False, True])
def test_pre_upgrade_null_page_break_evidence_replays_without_live_execution_authority(body):
    from app.inference.openai_replay import OpenAIReplay, REPLAY_KEY

    definition = CONTRACT.definition()
    old_schema = deepcopy(definition.input_schema)
    old_schema["$defs"]["WordPageBreak"].pop("required")
    old_definition = definition.model_copy(update={"input_schema": old_schema})
    blocks = [{"text": "first"}, {}, {"text": "second"}] if body else [{}]
    args = {**report_plan(), "blocks": blocks}
    old_wire = _arguments(old_schema, args, old_schema, from_wire=False)
    native = responses_function_tools((old_definition,))[0]
    item = {"type": "function_call", "id": "fc_old", "call_id": "call_old",
            "name": native["name"], "arguments": canonical_json(old_wire)}
    response = normalize_responses_calls([item], (old_definition,), CompletionMetadata())
    assert response.protocol_failure is None
    call = response.capability_calls[0]
    assert any(block == {} for block in call.arguments["blocks"])
    with pytest.raises(CapabilityArgumentError) as rejection:
        tool().validate_arguments(call.arguments)
    settled = CapabilityResult(call_id="receipt_old", capability=call.capability,
        success=body, error=None if body else rejection.value.failure,
        output={"synthetic_legacy_write": True} if body else None, duration_ms=0)
    replay = OpenAIReplay(model="synthetic-model", response_id="resp_old", items_json=json.dumps([item]))
    history = model_capability_calls_message((call,), provider_message_id="resp_old")
    history[REPLAY_KEY] = replay.model_dump()
    transcript = [history, model_capability_result_message(call, settled.model_dump(mode="json"),
                                                         provider_message_id="resp_old")]
    restored = responses_input(transcript, (definition,))
    assert restored[0] == item
    assert json.loads(restored[1]["output"])["success"] is body
    assert normalize_responses_calls([item], (definition,), CompletionMetadata()).protocol_failure is not None
    # Historical compatibility must not bless different original provider bytes.
    tampered = deepcopy(transcript)
    altered = deepcopy(item)
    altered_wire = deepcopy(old_wire)
    altered_wire["blocks"][1 if body else 0] = {"kind": "page_break"}
    altered["arguments"] = canonical_json(altered_wire)
    tampered[0][REPLAY_KEY] = OpenAIReplay(model="synthetic-model", response_id="resp_old",
        items_json=json.dumps([altered])).model_dump()
    with pytest.raises(ValueError, match="does not match"):
        responses_input(tampered, (definition,))


def test_unknown_keys_are_not_echoed_in_the_visible_error():
    with pytest.raises(CapabilityArgumentError) as error:
        tool().validate_arguments({**report_plan(), "private-document-content": "private-value"})
    assert "field: unexpected field" in error.value.failure.message
    assert "private" not in error.value.failure.message


def test_schema_advertises_control_width_margin_and_running_matter_bounds():
    schema = WordComposeArguments.model_json_schema()
    assert schema["properties"]["header"]["maxLength"] == 512
    assert schema["properties"]["footer"]["maxLength"] == 512
    assert schema["$defs"]["WordTable"]["properties"]["widths_mm"]["items"]["minimum"] == 5
    assert schema["$defs"]["WordPageLayout"]["properties"]["margins_mm"]["items"]["minimum"] == 5
    for change in ({"header": "one\ntwo"}, {"footer": "one\ttwo"},
                   {"blocks": [{"kind": "paragraph", "text": "one\ntwo"}]},
                   {"blocks": [{"kind": "table", "cells": [["one\ntwo"]], "widths_mm": [100]}]}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**report_plan(), **change}, schema)
    assert "default 170 mm" in CONTRACT.description
    assert "below top/bottom margins" in CONTRACT.description


def test_rejected_provider_call_and_corrected_report_can_be_replayed_without_changed_safeguards(tmp_path):
    bad = {**report_plan(), "blocks": [{"kind": "paragraph", "text": "one\ntwo"}]}
    wire, rejected_call = wire_call(bad, "call_bad_report")
    rejection = tool().invoke(rejected_call.arguments, context(tmp_path))
    assert not rejection.success and "blocks.0.text" in rejection.error.message
    transcript = [model_capability_calls_message((rejected_call,), provider_message_id="response_bad"),
                  model_capability_result_message(rejected_call, rejection.model_dump(mode="json"),
                                                  provider_message_id="response_bad")]
    replay = responses_input(transcript, (CONTRACT.definition(),))
    assert json.loads(replay[0]["arguments"]) == wire
    assert "blocks.0.text" in json.loads(replay[1]["output"])["error"]["message"]
    _, corrected = wire_call(report_plan(), "call_corrected_report")
    effective = tool().validate_arguments(corrected.arguments)
    assert effective.snapshot == "snapshot" and effective.session == "session"
    assert len(effective.blocks) == len(report_plan()["blocks"])


@pytest.mark.parametrize("corrected", [True, False])
def test_agent_can_correct_a_refusal_and_still_stops_identical_invalid_retries(tmp_path, corrected):
    from app.agent.contracts import AgentRunStatus
    from app.inference.protocol import ModelResponse
    from app.security.permissions import ApprovalStatus, PermissionClass, PermissionDecision, PermissionGate, PermissionRule
    from tests.test_agent_runtime import build_runtime, run
    from tests.test_bounded_edit_recovery import RoomyScriptedModel

    class RecordingOffice(OfficeCapability):
        def permission_resource(self, arguments, context):
            return None

        def approval_details(self, arguments, context):
            return None, None

        def execute(self, arguments, context):
            dispatched.append(arguments)
            return {"synthetic_dispatch": True}

    dispatched = []
    bad = {**report_plan(), "blocks": [{"kind": "paragraph", "text": "one\ntwo"}]}
    _, first = wire_call(bad, "call_bad_report")
    _, second = wire_call(redundant_breaks(report_plan()) if corrected else bad, "call_next_report")
    _, third = wire_call(bad, "call_repeated_report")
    responses = [ModelResponse.calls((first,)), ModelResponse.calls((second,)),
                 ModelResponse.text("Synthetic dispatch complete") if corrected else ModelResponse.calls((third,))]
    model = RoomyScriptedModel(responses)
    implementation = RecordingOffice(CONTRACT, SimpleNamespace(close=lambda: None), None, None, None)
    approvals = []
    def requester(manager):
        def approve(record):
            approvals.append(record)
            manager.resolve(record.approval_id, ApprovalStatus.APPROVED)
        return approve
    runtime, _, _, _, _ = build_runtime(tmp_path, responses, capability=implementation, model=model,
                                       approval_requester_factory=requester)
    runtime.permission_gate = PermissionGate((PermissionRule("synthetic-word", PermissionDecision.ASK,
        permission=PermissionClass.WRITE, capability_pattern="office.word_compose"),))
    try:
        result = run(runtime, tmp_path)
        assert result.status == (AgentRunStatus.COMPLETED if corrected else AgentRunStatus.REPEATED_CALL)
        assert len(dispatched) == (1 if corrected else 0), [
            (settled.result.error.code, settled.result.error.message) if settled.result.error else None
            for settled in result.settled_calls]
        assert len(approvals) == (1 if corrected else 0)
        failure = next(m["result"] for m in model.requests[1] if m.get("role") == "capability")
        assert failure["error"]["code"] == "invalid_arguments"
        assert "blocks.0.text" in failure["error"]["message"]
        if corrected:
            assert dispatched[0] == WordComposeArguments.model_validate(report_plan())
    finally:
        runtime.shutdown()
