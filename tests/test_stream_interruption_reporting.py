"""Report the interrupted request's phase without inventing an Excel write."""
import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionMetadata, IncompleteResponseError
from app.inference.protocol import ModelResponse, ModelProtocolFailureCode
from tests.test_agent_runtime import build_runtime, run
from tests.test_openai_phase1 import response
from tests.test_openai_streaming import Stream, events, make_engine, streaming_response
from tests.test_openai_tools import function


@pytest.mark.parametrize('function_seen', [False, True])
def test_actual_sdk_interruption_reports_observed_function_only(make_engine, tmp_path, function_seen):
    requests, streams = [], []
    engine = make_engine(lambda request: handle(request), max_retries=3)
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    payload = (response(output=[function(definition, {'value': 'never-execute'})])
               if function_seen else response('Partial explanation.'))

    def handle(request):
        requests.append(request)
        stream = Stream(events(payload, terminal=False))
        streams.append(stream)
        return streaming_response(stream)

    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE
        assert result.completion.request_phase == 'reply'
        assert result.completion.observed_function_call is function_seen
        assert ('incomplete tool generation was not executed' in result.message) is function_seen
        assert ('reply was interrupted' in result.message) is (not function_seen)
        assert len(requests) == 1 and all(stream.closed.is_set() for stream in streams)
        assert capability.values == [] and journal.records == () and result.settled_calls == ()
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('function_seen', [False, True])
def test_sdk_failed_review_retains_proposed_answer_and_phase_through_reload(make_engine, tmp_path, function_seen):
    payloads, requests, streams = [], [], []

    def handle(request):
        requests.append(json.loads(request.content))
        stream = Stream(payloads.pop(0))
        streams.append(stream)
        return streaming_response(stream)

    engine = make_engine(handle, max_retries=3)
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    candidate = 'The workbook helper formulas were explained; no changes were requested.'
    second = (response(output=[function(definition, {'value': 'forbidden-review-call'})])
              if function_seen else response('{"goal_id":"turn-1",'))
    payloads.extend([events(response(candidate)), events(second, terminal=False)])
    store = ConversationStore(tmp_path / 'conversation.json')
    objective = 'Explain the selected workbook helper formulas.'
    turn_id = store.begin_turn(objective)
    store.start_goal(turn_id)
    try:
        result = runtime.run([{'role': 'user', 'content': objective}], session_id=store.session_id,
            turn_id=turn_id, portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request=objective)
        assert result.status == AgentRunStatus.INCOMPLETE
        assert result.partial_text == result.proposed_answer == candidate
        assert result.completion.request_phase == 'completion_review'
        assert result.completion.observed_function_call is function_seen
        assert 'completion review was interrupted' in result.message
        assert 'tool generation' not in result.message and 'reply was interrupted' not in result.message
        assert result.completion_review is None and result.goal.state == 'stopped'
        assert requests[1]['tool_choice'] == 'none' and len(requests) == 2
        assert capability.values == [] and journal.records == () and result.settled_calls == ()
        assert all(stream.closed.is_set() for stream in streams)
        store.finish_turn(turn_id, result, result.partial_text)
        restored = ConversationStore(store.path).turns()[0]
        assert restored.outcome.completion == result.completion
        assert restored.outcome.partial_text == restored.outcome.proposed_answer == candidate
        assert restored.outcome.status == AgentRunStatus.INCOMPLETE
    finally:
        runtime.shutdown()


def test_continued_work_interruption_is_not_mislabeled_as_earlier_review(tmp_path):
    interruption = ModelResponse.failure(ModelProtocolFailureCode.STREAM_INTERRUPTED, 'Interrupted.').model_copy(
        update={'completion': CompletionMetadata(finish_reason='error', interrupted=True,
                failure_reason='stream_ended', observed_function_call=False)})
    runtime, model, _, _, _ = build_runtime(tmp_path, [ModelResponse.text('Initial proposal.'),
        ModelResponse.text('{"goal_id":"turn-1","status":"continue","remaining":["Read current data"]}'),
        interruption])
    model.auto_review = False
    try:
        result = runtime.run([{'role': 'user', 'content': 'Explain current data.'}], session_id='session',
            turn_id='turn-1', portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request='Explain current data.')
        assert result.status == AgentRunStatus.INCOMPLETE
        assert 'reply was interrupted' in result.message and 'completion review was interrupted' not in result.message
        assert 'tool generation' not in result.message
    finally:
        runtime.shutdown()


def test_interruption_metadata_preserves_old_history_and_rejects_private_fields():
    legacy = CompletionMetadata.model_validate_json('{"finish_reason":"error","interrupted":true}')
    assert legacy.request_phase is None and legacy.observed_function_call is None
    assert CompletionMetadata.model_validate_json(legacy.model_dump_json()) == legacy
    for fields in ({'request_phase': 'PRIVATE-DOCUMENT'}, {'observed_function_call': 'true'}):
        with pytest.raises(ValidationError):
            CompletionMetadata(**fields)


@pytest.mark.parametrize('status', ['completed', 'incomplete'])
def test_terminal_only_unfinished_function_is_observed_but_never_dispatched(make_engine, tmp_path, status):
    engine = make_engine(lambda request: streaming_response(stream))
    runtime, _, capability, journal, _ = build_runtime(tmp_path, [], model=engine)
    definition = runtime.registry.model_definitions()[0]
    item = function(definition, {'value': 'never-execute'})
    item['status'] = 'incomplete'
    payload = response(output=[item], status=status)
    if status == 'incomplete':
        payload['incomplete_details'] = {'reason': 'max_output_tokens'}
    values = events(payload)
    stream = Stream([{**values[0], 'sequence_number': 0}, {**values[-1], 'sequence_number': 1}])
    try:
        result = run(runtime, tmp_path)
        assert result.status == AgentRunStatus.INCOMPLETE
        assert result.completion.observed_function_call is True
        assert 'incomplete tool generation was not executed' in result.message
        assert capability.values == [] and journal.records == () and result.settled_calls == ()
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('phase', ['reply', 'completion_review', 'fallback_review'])
def test_real_service_correlates_route_model_thread_stream_and_terminal(make_engine, tmp_path, monkeypatch, phase):
    from app.runtime.skills import SkillRegistry
    from app.runtime.diagnostic_context import current_turn_id, current_request_phase
    from app.vault.logging import ProfileLogHandler
    from tests.test_phase8_filesystem_stat import build_service

    requests, streams = [], []
    candidate = 'The data explanation is prepared; checks remain unverified.'
    first = candidate if phase != 'fallback_review' else json.dumps({'tool': None, 'arguments': {}, 'response': candidate})
    values = [] if phase == 'reply' else [events(response(first))]
    values.append([events()[0], {'type': 'response.unreviewed_public_event', 'sequence_number': 1}])

    def handle(request):
        requests.append(request)
        stream = Stream(values.pop(0))
        streams.append(stream)
        return streaming_response(stream)

    engine = make_engine(handle, max_retries=3)
    service, runtime, store, _ = build_service(tmp_path, engine)
    journal = runtime.executor.journal
    service.skill_registry = SkillRegistry(global_root=tmp_path / 'skills')
    if phase == 'fallback_review':
        monkeypatch.setattr(engine, 'respond_with_capabilities', lambda *args:
            ModelResponse.failure(ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS, 'Synthetic fallback.'))
    path = tmp_path / 'safe-events.json'
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: path, register=lambda **_: None))
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        if phase == 'reply':
            with pytest.raises(IncompleteResponseError):
                service.run('Explain the current data.')
        else:
            answer = service.run('Explain the current data.')
            assert answer.completion.incomplete and candidate in answer
        recorded = json.loads(path.read_text())
        route = [row for row in recorded if row['event'] == 'route_decision']
        stream = [row for row in recorded if row['event'] == 'openai_stream_failure']
        terminal = [row for row in recorded if row['event'] == 'agent_turn']
        assert len(route) == len(terminal) == 1 and stream
        assert route[0]['turn_id'] is not None
        assert {row['turn_id'] for row in (*route, *stream, *terminal)} == {route[0]['turn_id']}
        expected = 'reply' if phase == 'reply' else 'completion_review'
        assert {row['request_phase'] for row in (*stream, *terminal)} == {expected}
        assert len({row['request_id'] for row in stream}) == 1
        assert stream[0]['request_id'] is not None and stream[0]['event_fingerprint'] is not None
        assert len(requests) == (1 if phase == 'reply' else 2)
        assert service._turn_result.capability_calls == 0 and journal.records == ()
        assert all(item.closed.is_set() for item in streams)
        restored = ConversationStore(store.path).turns()[0].outcome
        assert restored.completion.request_phase == expected
        if phase != 'reply':
            assert restored.partial_text == restored.proposed_answer == candidate
            assert 'completion review was interrupted' in restored.message
        assert current_turn_id() is None and current_request_phase() == 'reply'
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        handler.close()
        service.shutdown()
