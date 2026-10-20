"""Recovery, original-byte evidence and receipt-bound completion regressions."""
from copy import deepcopy
import hashlib
import json

import pytest

from app.agent.completion_evidence import validate_review_evidence
from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.agent.goals import TaskGoal, observe_goal, replay_goal, verification_report
from app.agent.source_evidence import source_read_proof
from app.agent.task_completion import CompletionReview, completion_review_schema, completion_review_message
from app.capabilities.contracts import CapabilityResult
from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.capabilities.project_verification import ProjectInspectCapability
from app.capabilities.shell_run import ShellRunArguments
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.security.permissions import PermissionGate, PermissionRule, PermissionDecision
from tests.test_agent_runtime import build_runtime, run, capability_call, EchoCapability
from tests.test_filesystem_read_text import context
from tests.test_bounded_edit_recovery import make_service


def settled(name, args, output, identity='receipt-1', *, success=True):
    return SettledCall(provider_message_id='scope-' + identity,
        call=ModelCapabilityCall(provider_call_id='provider-' + identity, capability=name, arguments=args),
        result=CapabilityResult(call_id=identity, capability=name, success=success, output=output, duration_ms=0))


def test_repaired_errors_do_not_exhaust_an_unrelated_cumulative_budget(tmp_path):
    replies = []
    for index in range(5):
        replies.extend([capability_call(index * 2, arguments={'value': index}),
                        capability_call(index * 2 + 1, value=str(index))])
    runtime, _, echo, _, _ = build_runtime(tmp_path, [*replies, ModelResponse.text('Finished.')])
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.semantic_corrections == 5
        assert echo.values == ['0', '1', '2', '3', '4']
        assert len(outcome.settled_calls) == 10
    finally:
        runtime.shutdown()


def test_unchanged_recovery_stops_and_does_not_dispatch_later_batch_calls(tmp_path):
    replies = [capability_call(i, arguments={'value': i}) for i in range(3)]
    replies.append(ModelResponse.calls((capability_call(3, arguments={'value': 3}).capability_calls[0],
                                       capability_call(4, 'must not execute').capability_calls[0])))
    runtime, model, echo, _, _ = build_runtime(tmp_path, replies)
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT
        assert len(model.requests) == 4 and len(outcome.settled_calls) == 4 and not echo.values
        assert 'test.echo' in outcome.message
    finally:
        runtime.shutdown()


class PollCapability(EchoCapability):
    name = 'shell.run'
    arguments_model = ShellRunArguments

    def execute(self, args, ctx):
        self.values.append(args.session_id)
        done = len(self.values) == 5
        return {'session_id': args.session_id, 'running': not done, 'command_completed': done,
                'command_succeeded': done, 'exit_code': 0 if done else None, 'stop_reason': 'exited' if done else None}


def test_quiet_owned_session_can_be_polled_through_completion(tmp_path):
    calls = [ModelResponse.calls((ModelCapabilityCall(provider_call_id=f'poll-{i}', capability='shell.run',
        arguments={'action': 'status', 'session_id': 'shell-' + 'a' * 32}),)) for i in range(5)]
    runtime, _, tool, _, _ = build_runtime(tmp_path, [*calls, ModelResponse.text('Completed.')], capability=PollCapability())
    runtime.permission_gate = PermissionGate((PermissionRule('poll', PermissionDecision.ALLOW,
        permission=tool.permission, capability_pattern='shell.run'),))
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.COMPLETED and len(tool.values) == 5
        assert outcome.settled_calls[-1].result.output['command_completed']
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('action', ['status', 'list'])
def test_observation_preserves_current_checks_but_old_history_keeps_its_projection(action):
    check = settled('project.verify', {'kind': 'build', 'project_path': 'C:/project'},
                    {'passed': True, 'project_path': 'C:/project'})
    poll = settled('shell.run', {'action': action}, {}, 'poll')
    for version in (1, 2):
        goal = replay_goal(TaskGoal(goal_id='turn-1', objective='Build', evidence_version=version), [check, poll])
        assert goal.verification[0].stale is (version == 1)


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16'])
def test_paged_original_bytes_verify_saved_digest_and_restore(tmp_path, encoding):
    path = tmp_path / 'large.txt'
    raw = ('Hello Ω\r\n' * 9000).encode(encoding)
    path.write_bytes(raw)
    mutation = settled('filesystem.write_text', {'path': str(path)},
        {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'operation': 'created'}, 'write')
    calls = [mutation]
    tool = FilesystemReadTextCapability()
    args = {'path': str(path), 'encoding': encoding, 'max_bytes': 16000, 'max_lines': 1000}
    while args:
        result = tool.invoke(args, context(tmp_path))
        assert result.success
        calls.append(SettledCall(provider_message_id=f'scope-{len(calls)}',
            call=ModelCapabilityCall(provider_call_id=f'page-{len(calls)}', capability=tool.name, arguments=args),
            result=result.model_copy(update={'call_id': f'page-{len(calls)}'})))
        args = result.output['next_read']
    assert len(calls) > 2 and all(not item.result.output['source_complete'] for item in calls[1:])
    proof = source_read_proof(calls[-1], calls[:-1])
    assert proof.sha256 == hashlib.sha256(raw).hexdigest()
    assert source_read_proof(calls[-1], [calls[0], *calls[2:-1]]) is None
    altered = deepcopy(calls)
    altered[1] = altered[1].model_copy(update={'result': altered[1].result.model_copy(update={
        'output': {**altered[1].result.output, 'revision': 'f' * 64}})})
    assert source_read_proof(altered[-1], altered[:-1]) is None
    from app.agent.repair_loop import RepairLoopTracker
    from tests.test_repair_loop import request, failed, diagnosis
    tracker = RepairLoopTracker()
    tracker.observe(request('project.inspect', project_path=str(tmp_path)), failed(tmp_path), step=1)
    for index, item in enumerate(calls[1:], 2):
        tracker.observe(item.call, item.result, step=index)
    assert tracker.before(request('filesystem.edit_text', path=str(path), old_text='Hello', new_text='Hi',
        repair_diagnosis=diagnosis()), step=len(calls) + 1) is None
    store = ConversationStore(tmp_path / 'chat.json')
    turn = store.begin_turn('Save and read the large file')
    store.start_goal(turn)
    for item in calls:
        store.record_settled(turn, item)
    goal = store.turns()[0].goal
    assert goal.artifacts[0].source_check_call_ids == proof.call_ids
    store.finish_turn(turn, AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text='Saved and read.',
        steps=len(calls), capability_calls=len(calls), protocol_failures=0, goal=goal))
    assert ConversationStore(store.path).turns()[0].goal.artifacts == goal.artifacts


def review(*evidence, status='ready'):
    return CompletionReview.model_validate({'goal_id': 'turn-1', 'status': status,
        'remaining': () if status == 'ready' else ('Work remains',), 'evidence': tuple(evidence)})


def test_claims_require_current_outcomes_and_delivered_pixels():
    inspection = settled('project.inspect', {'kind': 'browser', 'project_path': 'C:/project'},
        {'project_path': 'C:/project', 'passed': True, 'screenshot_sha256': 'a' * 64})
    goal = replay_goal(TaskGoal(goal_id='turn-1', objective='Inspect', evidence_version=2), [inspection])
    with pytest.raises(ValueError, match='Account for'):
        validate_review_evidence(review(), goal, [inspection])
    claim = {'call_id': 'receipt-1', 'claim': 'passed', 'visual_sha256': ('a' * 64,)}
    with pytest.raises(ValueError, match='exact screenshot'):
        validate_review_evidence(review(claim), goal, [inspection])
    validate_review_evidence(review(claim), goal, [inspection], ['a' * 64])
    stale = observe_goal(goal, settled('shell.run', {'command': 'work'}, {}, 'shell'))
    with pytest.raises(ValueError, match='current passing'):
        validate_review_evidence(review(claim), stale, [inspection], ['a' * 64])
    with pytest.raises(ValueError, match='unknown'):
        validate_review_evidence(review({'call_id': 'absent', 'claim': 'passed'}), goal, [inspection])


def test_running_jobs_cannot_be_claimed_completed_and_readiness_needs_matching_inspection():
    job = settled('shell.run', {}, {'workdir': 'C:/project', 'session_id': 'shell-' + 'b' * 32,
        'running': True}, 'job')
    goal = TaskGoal(goal_id='turn-1', objective='Start server', evidence_version=2)
    with pytest.raises(ValueError, match='recorded tool outcome'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'completed'}), goal, [job])
    with pytest.raises(ValueError, match='Server readiness'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'ready'}), goal, [job])
    inspection = settled('project.inspect', {'project_path': 'C:/project', 'kind': 'browser'},
        {'project_path': 'C:/project', 'inspection_complete': True, 'passed': True}, 'inspection')
    goal = observe_goal(goal, inspection)
    validate_review_evidence(review({'call_id': 'job', 'claim': 'ready', 'readiness_call_id': 'inspection'},
        {'call_id': 'inspection', 'claim': 'passed'}), goal, [job, inspection])
    temporary = inspection.model_copy(update={'call': inspection.call.model_copy(update={
        'arguments': {**inspection.call.arguments, 'server_executable': 'C:/python.exe'}})})
    with pytest.raises(ValueError, match='Server readiness'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'ready', 'readiness_call_id': 'inspection'},
            {'call_id': 'inspection', 'claim': 'passed'}), goal, [job, temporary])
    with pytest.raises(ValueError, match='Server readiness'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'ready', 'readiness_call_id': 'inspection'},
            {'call_id': 'inspection', 'claim': 'passed'}), goal, [inspection, job])
    stopped = settled('shell.run', {'action': 'status', 'session_id': job.result.output['session_id']},
        {'session_id': job.result.output['session_id'], 'running': False, 'command_completed': True,
         'command_succeeded': True}, 'stopped')
    with pytest.raises(ValueError, match='latest shell'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'ready', 'readiness_call_id': 'inspection'},
            {'call_id': 'inspection', 'claim': 'passed'}, {'call_id': 'stopped', 'claim': 'succeeded'}),
            goal, [job, inspection, stopped])


def test_failed_reports_can_finish_and_exact_scenario_success_resolves_history_only():
    args = {'project_path': 'C:/project', 'kind': 'browser', 'steps': [{'action': 'text', 'value': 'one'}]}
    failed = settled('project.inspect', args, {'project_path': 'C:/project', 'passed': False}, 'failed')
    changed = settled('project.inspect', {**args, 'steps': [{'action': 'text', 'value': 'two'}]},
        {'project_path': 'C:/project', 'passed': True}, 'changed')
    fixed = settled('project.inspect', args, {'project_path': 'C:/project', 'passed': True}, 'fixed')
    goal = replay_goal(TaskGoal(goal_id='turn-1', objective='Report failures', evidence_version=2), [failed, changed])
    assert not goal.superseded_verification
    validate_review_evidence(review({'call_id': 'failed', 'claim': 'failed'}, {'call_id': 'changed', 'claim': 'passed'}),
        goal, [failed, changed])
    goal = observe_goal(goal, fixed)
    assert goal.superseded_verification == {'failed': 'fixed'}
    assert 'historical failure' in verification_report(goal) and not goal.verification[0].passed


@pytest.mark.parametrize('step, message', [
    ({'action': 'scroll', 'label': 'bad'}, 'Checkpoint assertions require a checkpoint action'),
    ({'action': 'checkpoint', 'target': '#hero', 'label': 'return', 'expectation': 'same_state'}, 'earlier checkpoint reference'),
    ({'action': 'key', 'value': 'Enter'}, 'supported navigation key'),
    ({'action': 'frame_timing', 'timeout_ms': 3000}, 'bounded to 2000'),
    ({'action': 'checkpoint', 'properties': ['private-property']}, 'selected computed properties'),
])
def test_inspection_errors_name_the_actual_step_rule(tmp_path, step, message):
    tool = ProjectInspectCapability(tmp_path / 'state')
    result = tool.invoke({'project_path': str(tmp_path), 'kind': 'browser', 'url': 'http://localhost:8000',
                         'steps': [step]}, context(tmp_path))
    assert not result.success and message in result.error.message


def test_completion_schema_requires_evidence_fields_without_changing_old_history_parser():
    schema = completion_review_schema([completion_review_message(TaskGoal(goal_id='turn-1', objective='Report'), None)])
    assert 'evidence' in schema['required']
    assert set(schema['$defs']['ReviewEvidence']['required']) == {'call_id', 'claim', 'visual_sha256', 'readiness_call_id'}
    assert CompletionReview.model_validate_json('{"goal_id":"turn-1","status":"ready","remaining":[]}').evidence == ()


def test_completion_recovery_renews_after_real_edits(tmp_path, make_service):
    from tests.test_bounded_edit_recovery import read, edit
    from tests.test_current_task_completion import review as response_review
    path = tmp_path / 'stages.txt'
    path.write_text('stage=0')
    replies = [ModelResponse.text('I will perform the requested stages.')]
    for index in range(5):
        replies.extend([response_review('continue', [f'Perform stage {index + 1}']),
            read(index * 2 + 1, path), edit(index * 2 + 2, path, f'stage={index}', f'stage={index + 1}'),
            ModelResponse.text(f'Stage {index + 1} saved; tests unrun.')])
    replies.append(response_review())
    service, _, approvals = make_service(replies, auto_review=False)
    service.run('Complete five stages in stages.txt; skip tests.')
    assert service._turn_result.status == AgentRunStatus.COMPLETED
    assert service._turn_result.semantic_corrections == 5
    assert path.read_text() == 'stage=5' and len(approvals) == 5


def test_completion_recovery_without_progress_stops_with_remaining_work(tmp_path):
    replies = []
    for index in range(4):
        replies.extend([ModelResponse.text(f'I plan to do the work, attempt {index}.'),
            ModelResponse.text(json.dumps({'goal_id': 'turn-1', 'status': 'continue', 'remaining': ['Perform the actual edit']}))])
    runtime, model, _, _, _ = build_runtime(tmp_path, replies)
    model.auto_review = False
    try:
        outcome = runtime.run([{'role': 'user', 'content': 'Perform the edit'}], session_id='session', turn_id='turn-1',
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request='Perform the edit')
        assert outcome.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT and len(model.requests) == 8
        assert 'Perform the actual edit' in outcome.partial_text
    finally:
        runtime.shutdown()


def test_native_status_wait_observes_a_quiet_job_completion(tmp_path):
    from app.capabilities.shell_run import ShellRunCapability
    from tests.test_shell_sessions import launch_args, invoke
    tool = ShellRunCapability()
    try:
        started = invoke(tool, tmp_path, launch_args(tmp_path, 'import time; time.sleep(0.6)', yield_time_ms=0))
        outcome = invoke(tool, tmp_path, {'action': 'status', 'session_id': started['session_id'], 'yield_time_ms': 3000})
        assert outcome['command_completed'] and outcome['command_succeeded']
        assert outcome['owned_processes_released']
    finally:
        tool.shutdown()


def test_review_cannot_turn_a_failed_command_into_success():
    job = settled('shell.run', {}, {'command_completed': True, 'command_succeeded': False, 'exit_code': 7}, 'job')
    goal = TaskGoal(goal_id='turn-1', objective='Report failure', evidence_version=2)
    with pytest.raises(ValueError, match='confirmed command success'):
        validate_review_evidence(review({'call_id': 'job', 'claim': 'succeeded'}), goal, [job])
    validate_review_evidence(review({'call_id': 'job', 'claim': 'completed'}), goal, [job])


def test_invalid_evidence_is_corrected_in_review_without_replaying_tools(tmp_path):
    from app.capabilities.project_verification import ProjectInspectionArguments
    from tests.test_agent_runtime import ScriptedModel
    class Inspect(EchoCapability):
        name = 'project.inspect'
        arguments_model = ProjectInspectionArguments

        def execute(self, args, ctx):
            self.values.append(args.project_path)
            return {'project_path': args.project_path, 'passed': True, 'inspection_complete': True}
    call = ModelResponse.calls((ModelCapabilityCall(provider_call_id='inspect', capability='project.inspect',
        arguments={'project_path': str(tmp_path), 'kind': 'browser', 'url': 'http://localhost/'}),))
    model = ScriptedModel([call, ModelResponse.text('The requested inspection passed.'),
        ModelResponse.text('{"goal_id":"turn-1","status":"ready","remaining":[]}'),
        ModelResponse.text(json.dumps({'goal_id': 'turn-1', 'status': 'ready', 'remaining': [], 'evidence': [
            {'call_id': 'internal-call-1', 'claim': 'passed'}]}))], auto_review=False)
    runtime, _, tool, _, _ = build_runtime(tmp_path, [], capability=Inspect(), model=model)
    runtime.permission_gate = PermissionGate((PermissionRule('inspect', PermissionDecision.ALLOW,
        permission=tool.permission, capability_pattern=tool.name),))
    try:
        outcome = runtime.run([{'role': 'user', 'content': 'Inspect this preview'}], session_id='session', turn_id='turn-1',
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request='Inspect this preview')
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.protocol_failures == 1
        assert len(tool.values) == len(outcome.settled_calls) == 1 and len(model.requests) == 4
        assert 'Evidence correction: Account for' in model.requests[-1][-1]['content']
        store = ConversationStore(tmp_path / 'review.json')
        turn = store.begin_turn('Inspect this preview')
        store.start_goal(turn)
        store.finish_turn(turn, outcome)
        assert ConversationStore(store.path).turns()[0].outcome.completion_review == outcome.completion_review
        payload = json.loads(store.path.read_text())
        payload['turns'][0]['outcome']['completion_review']['evidence'][0]['call_id'] = 'unknown'
        store.path.write_text(json.dumps(payload))
        from app.conversation.store import TurnHistoryError
        with pytest.raises(TurnHistoryError):
            ConversationStore(store.path)
    finally:
        runtime.shutdown()
