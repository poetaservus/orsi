from types import SimpleNamespace
import json
import pytest
from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.inference.completion import AgentStoppedError, CompletionMetadata, IncompleteResponseError
from tests.test_bounded_edit_recovery import make_service, read
from tools.verify_word_illustrated import retain_terminal
from tests.test_completion_state import qt_app


def test_local_repeat_retains_status_through_conversation_and_exception_report(tmp_path, make_service):
    path = tmp_path / 'private-name.txt'
    path.write_text('private document content')
    service, model, _ = make_service([read(i, path) for i in range(1, 4)])
    with pytest.raises(AgentStoppedError) as caught:
        service.run('Inspect the supplied file')
    error = caught.value
    assert not isinstance(error, IncompleteResponseError)
    assert error.status == AgentRunStatus.REPEATED_CALL
    assert error.completion.finish_reason == 'agent_recovery_stop'
    turn = service.store.turns()[-1]
    report = {}
    retain_terminal(report, turn)
    assert report['terminal_status'] == 'repeated_call'
    assert report['stop_category'] == 'local_recovery'
    assert report['model_requests'] == 3 and report['settled_calls'] == 2
    assert not report['task_completed'] and not report['model_saved']
    assert 'private' not in json.dumps(report) and str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize('reason', ['output_limit', 'stream_connection', 'provider_incomplete'])
def test_provider_incompleteness_keeps_distinct_reporting(reason):
    completion = CompletionMetadata(finish_reason='length', failure_reason=reason, interrupted=True)
    result = AgentRunResult(status=AgentRunStatus.INCOMPLETE, message='Provider response incomplete',
        completion=completion, steps=1, capability_calls=0, protocol_failures=0)
    report = {}
    retain_terminal(report, SimpleNamespace(outcome=result, settled_calls=()))
    assert report['stop_category'] == 'provider_incomplete'
    assert report['failure_reason'] == reason and report['finish_reason'] == 'length'


def test_local_stop_worker_and_restored_presentation(qt_app):
    from app.ui.worker import ConversationWorker
    from app.ui.chat import ChatView
    from app.inference.completion import CompletionText
    result = AgentRunResult(status=AgentRunStatus.REPEATED_CALL, message='Repeated inspection; not dispatched.',
        partial_text='Task remains unverified.', completion=CompletionMetadata(finish_reason='agent_recovery_stop', interrupted=True),
        steps=3, capability_calls=3, protocol_failures=0)
    class Service:
        def run(self, *args):
            raise AgentStoppedError(result)
    worker = ConversationWorker(Service(), 'test')
    failed = []
    worker.failed.connect(failed.append)
    worker.run()
    assert failed[0].status_message == result.message
    chat = ChatView()
    try:
        chat.add_message('Agent', CompletionText(str(failed[0]), result.completion))
        label = chat._messages[-1].completion_label.text()
        assert 'stopped locally' in label and 'Incomplete response' not in label
    finally:
        chat.close()


@pytest.mark.parametrize('reason', ['output_limit', 'stream_connection', 'provider_incomplete'])
def test_provider_incomplete_through_conversation(tmp_path, make_service, reason):
    from app.inference.protocol import ModelResponse
    completion = CompletionMetadata(finish_reason='length', failure_reason=reason, interrupted=True)
    response = ModelResponse.text('Partial provider output').model_copy(update={'completion': completion})
    service, _, _ = make_service([response], auto_review=False)
    answer = service.run('Answer this request')
    assert answer.completion.incomplete
    turn = service.store.turns()[-1]
    assert turn.outcome.status == AgentRunStatus.INCOMPLETE
    assert turn.outcome.completion.failure_reason == reason
    report = {}
    retain_terminal(report, turn)
    assert report['stop_category'] == 'provider_incomplete'


def test_helper_keeps_save_and_unchanged_receipts_without_claiming_completion():
    from app.agent.contracts import SettledCall
    from tests.test_office_read_recovery import call, result
    calls = []
    for name, output in [('office.word_compose', {'outcome': 'unchanged', 'affected_items': 0}),
                         ('office.word_edit', {'outcome': 'applied', 'affected_items': 1}),
                         ('office.save', {'saved': True})]:
        request = call(name)
        calls.append(SettledCall(provider_message_id='message', call=request, result=result(request, **output)))
    outcome = AgentRunResult(status=AgentRunStatus.REPEATED_CALL, message='private text must not persist',
        steps=4, capability_calls=4, protocol_failures=0, settled_calls=tuple(calls),
        completion=CompletionMetadata(finish_reason='agent_recovery_stop', interrupted=True))
    report = {}
    retain_terminal(report, SimpleNamespace(outcome=outcome, settled_calls=tuple(calls)))
    assert report['model_saved'] and report['successful_compositions'] == 1
    assert not report['task_completed']
    assert [c['outcome'] for c in report['calls']] == ['unchanged', 'applied', None]
    assert [c['affected_items'] for c in report['calls']] == [0, 1, None]
    assert 'private' not in json.dumps(report)


def test_read_renewal_epochs_require_an_actual_matching_edit():
    from app.agent.office_read_repetition import OfficeReadRepetition
    from app.agent.feedback import call_fingerprint
    from tests.test_office_read_recovery import call, result
    tracker = OfficeReadRepetition()
    inspection = call(target='layout')
    fingerprint = call_fingerprint(inspection)
    counts = {fingerprint: 2}
    tracker.observe(inspection, result(inspection), counts)
    edit = call('office.word_edit')
    tracker.observe(edit, result(edit, operation='operation', outcome='applied', affected_items=1), counts)
    assert fingerprint not in counts
    counts[fingerprint] = 2
    tracker.observe(inspection, result(inspection), counts)
    for request, output in [(call('office.save'), {'saved': True}),
                            (edit, {'outcome': 'unchanged', 'affected_items': 0})]:
        tracker.observe(request, result(request, operation='operation', **output), counts)
        assert counts[fingerprint] == 2
    tracker.observe(edit, result(edit, success=False), counts)
    assert counts[fingerprint] == 2
