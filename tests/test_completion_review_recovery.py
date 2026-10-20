"""Long settled work must not depend on the model transcribing a tool ledger."""
import json
import logging
from types import SimpleNamespace

import pytest

from app.agent.contracts import AgentRunStatus
from app.capabilities.project_verification import ProjectVerificationArguments
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from tests.test_agent_runtime import EchoCapability, ScriptedModel, build_runtime
from tests.test_bounded_edit_recovery import make_service, read, edit


class SettledCheck(EchoCapability):
    name = 'project.verify'
    arguments_model = ProjectVerificationArguments

    def execute(self, args, ctx):
        self.values.append(args.arguments)
        return {'project_path': args.project_path, 'kind': args.kind, 'passed': True, 'exit_code': 0}


def test_long_settled_history_accepts_semantic_review_without_model_ledger(tmp_path):
    count = 72
    responses = [ModelResponse.calls((ModelCapabilityCall(provider_call_id=f'check-{i}', capability='project.verify',
        arguments={'project_path': str(tmp_path), 'kind': 'test', 'executable': 'C:/synthetic/python.exe',
                   'arguments': [str(i)]}),)) for i in range(count)]
    assessment = ModelResponse.text('{"goal_id":"turn-1","status":"ready","remaining":[]}')
    model = ScriptedModel([*responses, ModelResponse.text('The selected checks passed; unrelated behavior remains unverified.'),
                           assessment, assessment], auto_review=False)
    model.context_length = 131072
    model.mode = 'cloud'
    runtime, _, tool, _, _ = build_runtime(tmp_path, [], capability=SettledCheck(), model=model)
    runtime.permission_gate = PermissionGate((PermissionRule('synthetic-check', PermissionDecision.ALLOW,
        permission=tool.permission, capability_pattern=tool.name),))
    try:
        result = runtime.run([{'role': 'user', 'content': 'Run selected checks and report limits.'}],
            session_id='session', turn_id='turn-1', portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            goal_request='Run selected checks and report limits.')
        assert result.status == AgentRunStatus.COMPLETED
        assert result.protocol_failures == 0 and len(model.requests) == count + 2
        assert len(tool.values) == len(result.settled_calls) == count
        assert len(result.completion_review.evidence) == count
        assert result.completion_review.evidence_origin == 'runtime'
    finally:
        runtime.shutdown()


def test_review_repair_keeps_settled_edit_and_records_safe_reason(tmp_path, make_service):
    from app.conversation.store import ConversationStore
    path = tmp_path / 'source.txt'
    path.write_text('old')
    service, model, approvals = make_service([read(1, path), edit(2, path, 'old', 'new'),
        ModelResponse.text('Saved the requested change; tests skipped.'),
        ModelResponse.text('{"goal_id":"turn-999","status":"ready","remaining":[]}'),
        ModelResponse.text('{"goal_id":"turn-1","status":"ready","remaining":[]}')], auto_review=False)
    service.run('Change old to new; skip tests.')
    result = service._turn_result
    assert result.status == AgentRunStatus.COMPLETED and path.read_text() == 'new'
    assert len(approvals) == 1 and len(result.settled_calls) == 2 and len(model.requests) == 5
    assert [failure.reason for failure in result.review_failures] == ['goal_mismatch']
    assert 'Assessment correction: Use the current goal_id' in model.requests[-1][-1]['content']
    assert ConversationStore(service.store.path).turns()[0].outcome.review_failures == result.review_failures


def test_exhausted_review_preserves_work_without_private_error_content(tmp_path, make_service):
    from app.inference.completion import IncompleteResponseError
    from app.vault.logging import ProfileLogHandler
    path = tmp_path / 'source.txt'
    path.write_text('old')
    private = 'PRIVATE sk-proj-PRIVATE C:/private/file'
    service, _, approvals = make_service([read(1, path), edit(2, path, 'old', 'new'),
        ModelResponse.text('Saved the requested change; tests skipped.'),
        ModelResponse.text(private), ModelResponse.text(private)], auto_review=False)
    events = tmp_path / 'events.json'
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: events, register=lambda **_: None))
    logger = logging.getLogger('app.agent.review_diagnostics')
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        with pytest.raises(IncompleteResponseError):
            service.run('Change old to new; skip tests.')
        result = service._turn_result
        assert result.status == AgentRunStatus.PROTOCOL_FAILURE_LIMIT
        assert path.read_text() == 'new' and len(approvals) == 1
        assert result.partial_text == 'Saved the requested change; tests skipped.'
        assert [failure.reason for failure in result.review_failures] == ['json_invalid', 'json_invalid']
        assert '(json_invalid)' in result.message
        records = json.loads(events.read_text())
        assert [entry['phase'] for entry in records] == ['rejected', 'exhausted']
        assert all(entry['reason'] == 'json_invalid' for entry in records)
        assert 'PRIVATE' not in events.read_text() and 'source.txt' not in events.read_text()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        handler.close()


def test_later_presentation_failure_preserves_review_and_settled_work(tmp_path, make_service, monkeypatch):
    from app.conversation.store import ConversationStore
    path = tmp_path / 'source.txt'
    path.write_text('old')
    service, _, approvals = make_service([read(1, path), edit(2, path, 'old', 'new'),
        ModelResponse.text('Saved the requested change; tests skipped.'),
        ModelResponse.text('{"goal_id":"turn-999","status":"ready","remaining":[]}'),
        ModelResponse.text('{"goal_id":"turn-1","status":"ready","remaining":[]}')], auto_review=False)
    def fail_presentation(*args, **kwargs):
        raise RuntimeError('Synthetic presentation failure')
    monkeypatch.setattr('app.conversation.orchestrator.present_questions', fail_presentation)
    with pytest.raises(RuntimeError, match='Synthetic presentation failure'):
        service.run('Change old to new; skip tests.')
    restored = ConversationStore(service.store.path).turns()[0]
    assert restored.outcome.status == AgentRunStatus.INTERNAL_FAILURE
    assert restored.outcome.completion_review.status == 'ready'
    assert restored.outcome.completion_review.evidence_origin == 'runtime'
    assert [failure.reason for failure in restored.outcome.review_failures] == ['goal_mismatch']
    assert restored.goal.state == 'stopped' and len(restored.goal.artifacts) == 1
    assert path.read_text() == 'new' and len(approvals) == 1 and len(restored.settled_calls) == 2


def test_runtime_ledger_never_relabels_failed_stale_or_running_checks():
    from app.agent.completion_evidence import compile_review_evidence
    from app.agent.goals import TaskGoal, replay_goal
    from tests.test_orchestrator_completion_reliability import settled
    calls = [settled('project.verify', {'kind': 'build', 'project_path': 'C:/fixture'},
        {'project_path': 'C:/fixture', 'passed': True}, 'build'),
        settled('shell.run', {'command': 'synthetic', 'workdir': 'C:/fixture'},
        {'command_completed': True, 'command_succeeded': False}, 'failed'),
        settled('shell.run', {}, {'session_id': 'shell-' + 'a' * 32, 'running': True}, 'running')]
    goal = replay_goal(TaskGoal(goal_id='turn-1', objective='Report checks', evidence_version=2), calls)
    assert [entry.claim for entry in compile_review_evidence(goal, calls)] == ['unverified', 'failed', 'running']


@pytest.mark.parametrize(('payload', 'reason'), [
    ('PRIVATE not json', 'json_invalid'),
    ('{"goal_id":"turn-1","status":"PRIVATE","remaining":[]}', 'schema_invalid'),
    ('{"goal_id":"turn-1","status":"continue","remaining":[]}', 'remaining_invalid'),
    ('{"goal_id":"turn-1","status":"ready","remaining":["PRIVATE"]}', 'remaining_invalid'),
    ('{"goal_id":"turn-2","status":"ready","remaining":[]}', 'goal_mismatch'),
    ('{"goal_id":"turn-1","status":"ready","remaining":[],"evidence":"PRIVATE"}', 'schema_invalid'),
    ('PRIVATE' * 6000, 'size_limit'),
], ids=['json', 'schema', 'empty-remaining', 'ready-with-remaining', 'goal', 'extra-ledger', 'size'])
def test_review_errors_explain_correction_without_echoing_submitted_content(payload, reason):
    from app.agent.task_completion import ReviewValidationError, parse_completion_review
    with pytest.raises(ReviewValidationError) as caught:
        parse_completion_review(payload, 'turn-1')
    assert caught.value.reason == reason
    assert caught.value.feedback and 'PRIVATE' not in str(caught.value)


def test_forged_review_diagnostics_are_revalidated_without_formatting_private_values(tmp_path):
    from app.vault.logging import ProfileLogHandler
    events = tmp_path / 'events.json'
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: events, register=lambda **_: None))
    private = 'PRIVATE sk-proj-PRIVATE /private/file'
    record = logging.LogRecord('app.agent.review_diagnostics', logging.ERROR, private, 1, private, (private,), None)
    record.orsi_completion_review_diagnostic = {'phase': [private], 'reason': {private: True},
        'model_request': True, 'response_chars': private, 'receipt_count': 10**100, 'failure_count': -1,
        'response': private, 'message': private}
    handler.emit(record)
    value = json.loads(events.read_text())[0]
    assert value['phase'] == value['reason'] == 'unknown'
    assert all(value[key] is None for key in ('model_request', 'response_chars', 'receipt_count', 'failure_count'))
    assert 'PRIVATE' not in events.read_text() and 'response' not in value
