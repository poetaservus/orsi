"""Context recovery stops retain work and diagnose only fixed, content-free categories."""
import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.context_diagnostics import ContextRecoveryFailure
from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.agent.runtime import _RecoveryUsage
from app.inference.attachments import AttachmentError
from app.inference.completion import CompletionText
from app.inference.protocol import ModelResponse
from app.vault.logging import ProfileLogHandler
from tests.test_agent_runtime import build_runtime, capability_call, run
from tests.test_bounded_edit_recovery import make_service, read, edit


PRIVATE = 'PRIVATE sk-proj-PRIVATE C:/private/source.ts'


@pytest.mark.parametrize('stage,exception,category', [
    ('schema_reserve', TypeError, 'type_error'),
    ('budget', AttachmentError, 'attachment_error'),
    ('projection', ValueError, 'value_error'),
    ('compaction', AttributeError, 'attribute_error'),
    ('compaction', RuntimeError, 'other'),
])
def test_recovery_failure_reports_fixed_stage_without_exception_contents(tmp_path, monkeypatch, stage, exception, category):
    runtime, _, _, _, _ = build_runtime(tmp_path, [])
    runtime.context_recovery_enabled = True
    transcript = [{'role': 'user', 'content': 'Keep the current request intact.'}]
    events = tmp_path / 'events.json'
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: events, register=lambda **_: None))
    logger = logging.getLogger('app.agent.context_diagnostics')
    logger.addHandler(handler)
    def fail_reserve(*args, **kwargs):
        raise exception(PRIVATE)
    def fail_recovery(*args, stage_observer, **kwargs):
        stage_observer(stage)
        raise exception(PRIVATE)
    if stage == 'schema_reserve':
        monkeypatch.setattr('app.conversation.context.capability_schema_reserve', fail_reserve)
    else:
        monkeypatch.setattr('app.conversation.recovery.recover_context_request', fail_recovery)
    usage = _RecoveryUsage()
    try:
        assert runtime._recover_transcript(transcript, (), usage) is False
        assert usage.context_recovery_failure == ContextRecoveryFailure(stage=stage, exception_category=category)
        assert transcript == [{'role': 'user', 'content': 'Keep the current request intact.'}]
        recorded = json.loads(events.read_text())
        assert recorded == [{'event': 'context_recovery', 'stage': stage, 'reason': 'unexpected_exception',
                             'exception_category': category, 'level': 'error'}]
        assert PRIVATE not in events.read_text()
    finally:
        logger.removeHandler(handler)
        handler.close()
        runtime.shutdown()


def test_failed_compaction_keeps_settled_edit_and_unverified_proposal_in_service_and_store(tmp_path, monkeypatch, make_service):
    from app.agent.task_completion import REVIEW_PREFIX
    from app.conversation.store import ConversationStore
    import app.conversation.recovery as recovery
    original = recovery.recover_context_request
    def fail_review_recovery(inference, messages, **kwargs):
        if messages[-1].get('content', '').startswith(REVIEW_PREFIX):
            kwargs['stage_observer']('compaction')
            raise AttributeError(PRIVATE)
        return original(inference, messages, **kwargs)
    monkeypatch.setattr(recovery, 'recover_context_request', fail_review_recovery)
    path = tmp_path / 'source.txt'
    path.write_text('old')
    candidate = 'Saved the requested change; completion remains to be reviewed.'
    service, model, approvals = make_service([read(1, path), edit(2, path, 'old', 'new'),
        ModelResponse.text(candidate)], auto_review=False)
    service.agent_runtime.context_recovery_enabled = True
    answer = service.run('Change old to new; skip tests.')
    outcome = service._turn_result

    assert isinstance(answer, CompletionText) and answer.completion.incomplete
    assert answer.completion.finish_reason == 'agent_context_recovery_failed'
    assert answer.status_message == outcome.message
    assert 'Proposed answer retained from before the stop (completion is unverified):' in answer
    assert candidate in answer and PRIVATE not in answer
    assert outcome.status == AgentRunStatus.INTERNAL_FAILURE and outcome.assistant_text is None
    assert outcome.context_recovery_failure.stage == 'compaction'
    assert outcome.context_recovery_failure.exception_category == 'attribute_error'
    assert outcome.proposed_answer == candidate and outcome.completion_review is None
    assert path.read_text() == 'new' and len(approvals) == 1 and len(model.requests) == 3
    assert len(outcome.settled_calls) == 2 and all(item.result.success for item in outcome.settled_calls)
    restored = ConversationStore(service.store.path).turns()[0]
    assert restored.outcome == outcome.model_copy(update={'settled_calls': ()})
    assert restored.outcome.proposed_answer == candidate and restored.goal.state == 'stopped'
    assert tuple(restored.settled_calls) == outcome.settled_calls
    assert PRIVATE not in service.store.path.read_text()


def test_forged_diagnostics_drop_raw_payload_and_do_not_format_exception(tmp_path):
    events = tmp_path / 'events.json'
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: events, register=lambda **_: None))
    record = logging.LogRecord('app.agent.context_diagnostics', logging.ERROR, PRIVATE, 1,
        PRIVATE, (PRIVATE,), (RuntimeError, RuntimeError(PRIVATE), None))
    record.orsi_context_recovery_diagnostic = {'stage': [PRIVATE], 'reason': {PRIVATE: True},
        'exception_category': PRIVATE, 'traceback': PRIVATE, 'arguments': PRIVATE}
    try:
        handler.emit(record)
        assert json.loads(events.read_text()) == [{'event': 'context_recovery', 'stage': 'unknown',
            'reason': 'unknown', 'exception_category': 'unknown', 'level': 'error'}]
        assert PRIVATE not in events.read_text()
    finally:
        handler.close()


def test_recovery_failure_metadata_is_optional_for_old_outcomes_and_rejects_private_fields():
    outcome = AgentRunResult(status=AgentRunStatus.INTERNAL_FAILURE, message='Stopped safely.',
        steps=0, capability_calls=0, protocol_failures=0)
    data = json.loads(outcome.model_dump_json())
    data.pop('context_recovery_failure')
    assert AgentRunResult.model_validate_json(json.dumps(data)).context_recovery_failure is None
    for forged in ({'stage': PRIVATE, 'exception_category': 'other'},
                   {'stage': 'budget', 'exception_category': PRIVATE},
                   {'stage': 'budget', 'exception_category': 'other', 'message': PRIVATE}):
        with pytest.raises(ValidationError):
            ContextRecoveryFailure(**forged)


def test_unrelated_internal_failure_keeps_existing_noncompletion_shape(tmp_path):
    runtime, _, _, _, _ = build_runtime(tmp_path, [capability_call(1), RuntimeError('model failure')])
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.INTERNAL_FAILURE
        assert outcome.context_recovery_failure is None
        assert outcome.partial_text is None and not outcome.completion.incomplete
        assert len(outcome.settled_calls) == 1
    finally:
        runtime.shutdown()
