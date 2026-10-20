"""Office completion claims remain narrow, current and history compatible."""
import json

import pytest

from app.agent.completion_evidence import compile_review_evidence, evidence_catalog, validate_review_evidence
from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.agent.goals import TaskGoal, replay_goal
from app.agent.task_completion import CompletionReview, completion_review_message, completion_review_schema
from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityFailure, CapabilityResult
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall


def office(name, identity, args=None, output=None, *, error=None):
    default = {} if name in {'office.documents', 'office.attach', 'shell.run'} else {'session': 'session-a'}
    args = {**default, **(args or {})}
    result = CapabilityResult(call_id=identity, capability=name, duration_ms=0,
        success=error is None, output=output,
        error=CapabilityFailure(code=error, message='Synthetic failure') if error else None)
    return SettledCall(provider_message_id='scope-' + identity,
        call=ModelCapabilityCall(provider_call_id='provider-' + identity, capability=name, arguments=args), result=result)


def attach(identity='attach', *, session='session-a', document='document-a'):
    return office('office.attach', identity, {'application': 'excel', 'document': document},
        {'session': session, 'document': {'document': document, 'application': 'excel', 'dirty': False,
                                        'title': 'Synthetic', 'has_path': True, 'read_only': False}})


def read(identity='read', *, session='session-a', cursor=None):
    return office('office.read', identity, {'session': session, 'target': 'Sheet1!A1:B2'},
        {'session': session, 'application': 'excel', 'snapshot': 'snapshot-' + identity,
         'items': [], 'cursor': cursor})


def applied(identity='edit', *, session='session-a', **output):
    return office('office.excel_edit', identity, {'session': session, 'snapshot': 'synthetic',
        'changes': [{'sheet': 'Sheet1', 'range': 'A1', 'values': [[1]]}]},
        {'session': session, 'operation': identity, 'outcome': 'applied', 'affected_items': 1, **output})


def save(identity='save', *, session='session-a', **output):
    return office('office.save', identity, {'session': session},
        {'session': session, 'operation': identity, 'saved': True, **output})


def goal(calls):
    return replay_goal(TaskGoal(goal_id='turn-1', objective='Build and save the Excel dashboard.', evidence_version=2), calls)


def compiled(calls, *, version=2):
    return compile_review_evidence(goal(calls), calls, ledger_version=version)


def review(calls, *, version=2, **kwargs):
    return CompletionReview(goal_id='turn-1', status='ready', remaining=(), ledger_version=version,
        evidence_origin='runtime', evidence=compiled(calls, version=version), **kwargs)


def test_office_ledger_accounts_for_metadata_read_edit_save_and_failure_without_project_pass_claims():
    calls = [office('office.documents', 'documents', {}, {'documents': []}), attach(), read(), applied(),
             read('readback'), save(), office('office.read', 'failed', error=Code.PERMISSION_DENIED)]
    assert [item.claim for item in compiled(calls)] == [
        'observed', 'observed', 'unverified', 'applied', 'observed', 'saved', 'failed']
    catalog = evidence_catalog(calls, goal(calls), ledger_version=2)
    assert catalog[2]['stale'] and catalog[4]['scope'] == 'read_page'
    assert catalog[4]['target'] == 'Sheet1!A1:B2' and catalog[4]['more_pages'] is False
    assert catalog[5]['scope'] == 'document_save'
    assert not any(item['observed'] == 'passed' for item in catalog)
    validate_review_evidence(review(calls), goal(calls), calls)


def test_later_edits_invalidate_saved_and_read_revision_but_preserve_historical_applied_edit():
    calls = [attach(), read(), applied(), save(), read('after-save'), applied('next-edit')]
    assert [item.claim for item in compiled(calls)] == [
        'observed', 'unverified', 'applied', 'unverified', 'unverified', 'applied']
    calls += [save('new-save')]
    assert compiled(calls)[-1].claim == 'saved'
    assert compiled(calls)[3].claim == 'unverified'


def test_same_document_alias_invalidates_reads_and_saves_but_other_workbook_does_not():
    original = [attach(), read(), save()]
    other = [*original, attach('other', session='session-b', document='document-b'), applied('edit-b', session='session-b')]
    assert compiled(other)[1].claim == 'observed' and compiled(other)[2].claim == 'saved'
    alias = [*original, attach('alias', session='session-b'), applied('edit-alias', session='session-b')]
    assert compiled(alias)[1].claim == compiled(alias)[2].claim == 'unverified'


@pytest.mark.parametrize('error', [Code.OUTCOME_UNKNOWN, Code.TIMED_OUT, Code.CANCELLED, Code.INVALID_OUTPUT])
def test_uncertain_mutation_preserves_failure_and_invalidates_earlier_read_save_evidence(error):
    calls = [attach(), read(), save(), office('office.excel_edit', 'uncertain', error=error)]
    assert [item.claim for item in compiled(calls)][1:] == ['unverified', 'unverified', 'failed']
    assert evidence_catalog(calls, ledger_version=2)[-1]['outcome_uncertain']


@pytest.mark.parametrize('error', [Code.PERMISSION_DENIED, Code.INVALID_ARGUMENTS])
def test_rejected_mutation_does_not_erase_confirmed_read_or_save(error):
    calls = [read(), save(), office('office.excel_edit', 'rejected', error=error)]
    assert [item.claim for item in compiled(calls)] == ['observed', 'saved', 'failed']


@pytest.mark.parametrize('receipt', [applied(operation='another-call'), applied(session='session-b'),
                                    save(operation='another-call'), save(saved=False)])
def test_malformed_or_mismatched_success_never_proves_a_mutation_or_save(receipt):
    if receipt.result.output.get('session') == 'session-b':
        receipt = receipt.model_copy(update={'call': receipt.call.model_copy(update={'arguments': {'session': 'session-a'}})})
    assert compiled([receipt])[0].claim == 'unverified'


def test_malformed_successful_write_conservatively_stales_prior_current_read_and_save():
    calls = [read(), save(), applied('malformed', operation='another-call')]
    assert [item.claim for item in compiled(calls)] == ['unverified', 'unverified', 'unverified']
    assert evidence_catalog(calls, ledger_version=2)[-1]['outcome_uncertain']


@pytest.mark.parametrize('receipt', [applied(), save()])
def test_another_capabilitys_receipt_cannot_prove_this_edit_or_save(receipt):
    # The settled-call boundary already rejects this pair. The shared helper
    # also remains conservative when called directly by recovery accounting.
    from app.agent.office_receipts import office_receipt_event
    mismatched = receipt.result.model_copy(update={'capability': 'office.read'})
    event = office_receipt_event(receipt.call, mismatched)
    assert event['kind'] == 'unverified' and event['uncertain']


def test_read_pages_do_not_claim_complete_content_and_unbound_sessions_are_kept_separate():
    calls = [read(cursor='next-page'), save(), applied('other-edit', session='session-b')]
    assert [item.claim for item in compiled(calls)] == ['observed', 'saved', 'applied']
    assert evidence_catalog(calls, ledger_version=2)[0]['more_pages'] is True
    assert 'complete' not in evidence_catalog(calls, ledger_version=2)[0]['scope']


def test_unchanged_patch_does_not_invalidate_current_observations_or_save():
    calls = [read(), save(), applied('unchanged', outcome='unchanged', affected_items=0)]
    assert [item.claim for item in compiled(calls)] == ['observed', 'saved', 'unchanged']


@pytest.mark.parametrize(('action', 'claim'), [('run', 'unverified'), ('status', 'observed')])
def test_unscoped_mutating_shell_invalidates_office_observations_but_status_does_not(action, claim):
    calls = [read(), save(), office('shell.run', 'shell', {'action': action}, {})]
    assert compiled(calls)[0].claim == claim
    assert compiled(calls)[1].claim == ('saved' if action == 'status' else 'unverified')


def test_mismatched_attach_never_aliases_another_session_to_the_document():
    invalid = attach('invalid', session='session-b')
    invalid = invalid.model_copy(update={'call': invalid.call.model_copy(update={
        'arguments': {'application': 'excel', 'document': 'different-document'}})})
    calls = [attach(), read(), save(), invalid, applied('other-edit', session='session-b')]
    assert [item.claim for item in compiled(calls)][1:4] == ['observed', 'saved', 'unverified']


def test_office_claims_cannot_be_forged_or_promoted_to_project_passes():
    calls = [save(), applied()]
    stale = review(calls).model_copy(update={'evidence': (compiled(calls)[0].model_copy(update={'claim': 'saved'}), compiled(calls)[1])})
    with pytest.raises(ValueError, match='runtime ledger'):
        validate_review_evidence(stale, goal(calls), calls)
    model_claim = CompletionReview(goal_id='turn-1', status='ready', remaining=(), ledger_version=2,
        evidence=(compiled(calls)[0].model_copy(update={'claim': 'passed'}), compiled(calls)[1]))
    with pytest.raises(ValueError, match='current passing project'):
        validate_review_evidence(model_claim, goal(calls), calls)
    with pytest.raises(ValueError, match='current matching scoped'):
        validate_review_evidence(stale.model_copy(update={'evidence_origin': 'model'}), goal(calls), calls)


def test_legacy_review_ledger_excludes_office_receipts_and_retains_original_validation():
    calls = [read(), applied(), save()]
    assert compiled(calls, version=1) == ()
    old = CompletionReview.model_validate_json('{"goal_id":"turn-1","status":"ready","remaining":[],"evidence":[],"evidence_origin":"runtime"}')
    assert old.ledger_version == 1
    validate_review_evidence(old, goal(calls), calls)
    validate_review_evidence(review(calls), goal(calls), calls)


@pytest.mark.parametrize('version', [1, 2])
def test_office_reviews_round_trip_with_their_original_versioned_evidence(tmp_path, version):
    store = ConversationStore(tmp_path / 'chat.json')
    turn = store.begin_turn('Build and save the Excel dashboard.')
    store.start_goal(turn)
    calls = [attach(), read(), applied(), read('readback'), save()]
    for item in calls:
        store.record_settled(turn, item)
    store.finish_turn(turn, AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text='Saved; visuals unverified.',
        steps=len(calls), capability_calls=len(calls), protocol_failures=0, goal=store.turns()[0].goal,
        completion_review=review(calls, version=version), completion_review_current=True,
        completion_review_receipt_count=len(calls)))
    restored = ConversationStore(store.path).turns()[0].outcome.completion_review
    assert restored == review(calls, version=version)


def test_office_scope_names_supported_excel_checks_and_keeps_runtime_fields_out_of_model_schema():
    calls = [attach(), read(), save()]
    message = completion_review_message(goal(calls), None, ledger_version=2, settled_calls=calls)
    text = message['content']
    assert 'bounded values/formulas and native object metadata' in text
    assert 'Do not require project.inspect for an Office-only request' in text
    assert 'Excel visual inspection is not supplied' in text
    assert 'project process-ownership boundary' in text
    assert set(completion_review_schema([message])['properties']) == {'goal_id', 'status', 'remaining'}
    catalog = json.loads(text.split('Current completion receipts: ')[1].split('\n')[0])
    assert [item['observed'] for item in catalog] == ['observed', 'observed', 'saved']
