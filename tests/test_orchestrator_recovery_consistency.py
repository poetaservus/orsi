"""The inspection/read/edit/completion sequence must work as one bounded workflow."""
import json
from pathlib import Path
import sys

import pytest

from app.agent.contracts import AgentRunStatus
from app.agent.feedback import call_fingerprint
from app.agent.prerequisite_retries import PrerequisiteRetries, repetition_fingerprint
from app.agent.project_progress import ProjectProgressTracker
from app.agent.repair_loop import RepairLoopTracker
from app.capabilities.contracts import CapabilityErrorCode, CapabilityFailure, CapabilityResult
from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.capabilities.project_verification import ProjectInspectCapability
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call, read, edit
from tests.test_filesystem_read_text import context
from tests.test_repair_loop import diagnosis, failed


def request(name, **args):
    return ModelCapabilityCall(provider_call_id='probe', capability=name, arguments=args)


def source(path, identity='source', **args):
    tool = request('filesystem.read_text', path=str(path), **args)
    result = FilesystemReadTextCapability().invoke(tool.arguments, context(path.parent))
    assert result.success
    return tool, result.model_copy(update={'call_id': identity})


def rejected(tool, identity='rejected', reason='inspection_diagnosis', code=CapabilityErrorCode.INVALID_ARGUMENTS):
    return CapabilityResult(call_id=identity, capability=tool.capability, success=False, duration_ms=0,
        error=CapabilityFailure(code=code, message='No mutation executed.'), metadata={'edit_recovery': reason})


def check(project, identity, *, passed=False, target='#hero', value='systems'):
    step = dict(action='text', target=target, value=value)
    tool = request('project.inspect', project_path=str(project), kind='browser', steps=[step])
    result = failed(project).model_copy(update={'call_id': identity, 'output': dict(
        project_path=str(project), inspection_complete=True, passed=passed,
        checks=[dict(action='text', target=target, passed=passed,
            **({} if passed else {'failure_kind': 'interaction_assertion_failed'}))], problems=[])})
    return tool, result


def test_repeated_defect_keeps_the_receipt_and_read_boundary_whose_allowance_was_granted(tmp_path):
    path = tmp_path/'App.tsx'; path.write_text('old')
    tracker, repeated = ProjectProgressTracker(), {}
    reader, result = source(path)
    tracker.observe(reader, result, repeated, step=1)
    fingerprint = call_fingerprint(reader); repeated[fingerprint] = 2
    inspection, failure = check(tmp_path, 'failure-1')
    tracker.observe(inspection, failure, repeated, step=2)
    assert fingerprint not in repeated
    tracker.observe(reader, result.model_copy(update={'call_id': 'fresh'}), repeated, step=3)
    repeated[fingerprint] = 2
    inspection = inspection.model_copy(update={'arguments': {**inspection.arguments, 'timeout_seconds': 31}})
    feedback = tracker.observe(inspection, failure.model_copy(update={'call_id': 'failure-2'}), repeated, step=4)
    assert repeated[fingerprint] == 2 and 'failure-1' in feedback
    mutation = request('filesystem.edit_text', path=str(path), old_text='old', new_text='new',
        repair_diagnosis=diagnosis('failure-1'))
    assert tracker.repair_loop.before(mutation, step=5) is None
    assert tracker.repair_loop.before(mutation.model_copy(update={'arguments': {**mutation.arguments,
        'repair_diagnosis': diagnosis('failure-2')}}), step=5) is None
    assert tracker.repair_loop.before(mutation.model_copy(update={'arguments': {**mutation.arguments,
        'repair_diagnosis': diagnosis('unrelated-receipt')}}), step=5) is not None


def test_narrow_pass_cannot_erase_an_older_unresolved_scope_or_another_expected_value(tmp_path):
    tracker = RepairLoopTracker()
    a, failure_a = check(tmp_path, 'failure-a', target='#hero')
    b, failure_b = check(tmp_path, 'failure-b', target='#menu')
    tracker.observe(a, failure_a, step=1)
    tracker.observe(b, failure_b, step=2)
    b_pass, success = check(tmp_path, 'pass-b', passed=True, target='#menu')
    tracker.observe(b_pass, success, step=3)
    mutation = request('filesystem.edit_text', path=str(tmp_path/'App.tsx'))
    assert tracker.before(mutation, step=4) is not None
    wrong, success = check(tmp_path, 'wrong-value', passed=True, target='#hero', value='radial')
    tracker.observe(wrong, success, step=5)
    assert tracker.before(mutation, step=6) is not None
    a_pass, success = check(tmp_path, 'pass-a', passed=True, target='#hero')
    tracker.observe(a_pass, success, step=7)
    assert tracker.before(mutation, step=8) is None


def test_third_distinct_defect_has_explicit_bounded_stop_instead_of_an_impossible_read_requirement(tmp_path):
    tracker = RepairLoopTracker()
    for index in range(3):
        tool, result = check(tmp_path, f'failure-{index}', target=f'#target-{index}')
        feedback = tracker.observe(tool, result, step=index+1)
    assert 'further reads do not renew' in feedback
    mutation = request('filesystem.edit_text', path=str(tmp_path/'App.tsx'))
    assert tracker.before(mutation, step=4).reason == 'inspection_recovery_exhausted'


def test_action_incompatibility_alone_needs_inspection_correction_but_runtime_errors_still_require_repair(tmp_path):
    tracker = RepairLoopTracker()
    tool, result = check(tmp_path, 'setup')
    result.output['checks'][0]['failure_kind'] = 'action_incompatible'
    assert 'alone does not justify' in tracker.observe(tool, result, step=1)
    assert not tracker._failures
    result.output['problems'] = [{'kind': 'page_error'}]
    tracker.observe(tool, result.model_copy(update={'call_id': 'app-error'}), step=2)
    assert tracker.before(request('filesystem.edit_text', path=str(tmp_path/'App.tsx')), step=3) is not None


@pytest.mark.parametrize('mutation,args', [
    ('shell.run', {'action': 'run'}),
    ('filesystem.copy', {'destination_path': 'TARGET'}),
    ('filesystem.move', {'source_path': 'TARGET'}),
    ('filesystem.trash', {'path': 'TARGET'}),
    ('filesystem.write_text', {'path': 'TARGET'}),
])
def test_potential_mutation_invalidates_both_cached_repair_and_retry_reads(tmp_path, mutation, args):
    path = tmp_path/'App.tsx'; path.write_text('old')
    patch = request('filesystem.edit_text', path=str(path), old_text='old', new_text='new',
        repair_diagnosis=diagnosis('inspection'))
    retries, repair = PrerequisiteRetries(), RepairLoopTracker()
    inspection, failure = check(tmp_path, 'inspection')
    repair.observe(inspection, failure, step=1)
    retries.observe(patch, rejected(patch), step=2)
    reader, result = source(path)
    for tracker in (retries, repair): tracker.observe(reader, result, step=3)
    args = {key: str(path).upper() if value == 'TARGET' else value for key, value in args.items()}
    tool = request(mutation, **args)
    outcome = CapabilityResult(call_id='possible-mutation', capability=mutation, success=True, duration_ms=0, output={})
    for tracker in (retries, repair): tracker.observe(tool, outcome, step=4)
    assert repair.before(patch, step=5) is not None
    assert not retries.renew(patch, step=5, repair_rejection=None)


def test_exact_rejected_edit_gets_one_retry_after_complete_read_and_prose_cannot_renew_it(tmp_path):
    path = tmp_path/'App.tsx'; path.write_text('old')
    tool = request('filesystem.edit_text', path=str(path), old_text='old', new_text='new')
    tracker = PrerequisiteRetries()
    tracker.observe(tool, rejected(tool, 'rejected-1'), step=1)
    tracker.observe(tool, rejected(tool, 'rejected-2'), step=2)
    reader, result = source(path)
    tracker.observe(reader, result, step=3)
    assert not tracker.renew(tool, step=3, repair_rejection=None)
    assert not tracker.renew(tool, step=4, repair_rejection=object())
    assert tracker.renew(tool, step=4, repair_rejection=None)
    explained = tool.model_copy(update={'arguments': {**tool.arguments, 'repair_diagnosis': diagnosis()}})
    assert repetition_fingerprint(tool) == repetition_fingerprint(explained)
    tracker.observe(reader, result.model_copy(update={'call_id': 'reread'}), step=5)
    assert not tracker.renew(explained, step=6, repair_rejection=None)


@pytest.mark.parametrize('observation', ['failed', 'partial'])
def test_failed_or_partial_later_read_cannot_reuse_an_older_complete_read(tmp_path, observation):
    path = tmp_path/'App.tsx'; path.write_text('old source\n'*100)
    patch = request('filesystem.edit_text',path=str(path),old_text='old',new_text='new',
        repair_diagnosis=diagnosis('inspection'))
    repair, retries = RepairLoopTracker(), PrerequisiteRetries()
    inspection, result = check(tmp_path,'inspection')
    repair.observe(inspection,result,step=1)
    retries.observe(patch,rejected(patch),step=2)
    reader, result = source(path)
    for tracker in (repair,retries): tracker.observe(reader,result,step=3)
    if observation == 'partial':
        reader,result = source(path,'partial',max_bytes=64,max_lines=2)
    else:
        result = CapabilityResult(call_id='failed-read',capability=reader.capability,success=False,duration_ms=0,
            error=CapabilityFailure(code=CapabilityErrorCode.NOT_FOUND,message='Source unavailable.'))
    for tracker in (repair,retries): tracker.observe(reader,result,step=4)
    assert repair.before(patch,step=5) is not None
    assert not retries.renew(patch,step=5,repair_rejection=None)


@pytest.mark.parametrize('code', [CapabilityErrorCode.PERMISSION_DENIED, CapabilityErrorCode.OUTCOME_UNKNOWN])
def test_unknown_or_denied_mutation_never_earns_retry_renewal(tmp_path, code):
    path = tmp_path/'App.tsx'; path.write_text('old')
    tool = request('filesystem.edit_text', path=str(path), old_text='old', new_text='new')
    tracker = PrerequisiteRetries()
    tracker.observe(tool, rejected(tool), step=1)
    tracker.observe(tool, rejected(tool, 'blocked', reason=None, code=code), step=2)
    reader, result = source(path)
    tracker.observe(reader, result, step=3)
    assert not tracker.renew(tool, step=4, repair_rejection=None)


@pytest.fixture
def recovery_runtime(tmp_path):
    from app.agent.bootstrap import build_agent_runtime
    from app.settings.agent import AgentFeatureConfig
    from app.security.host_access import HostAccessPolicy
    portable = tmp_path/'portable'; portable.mkdir()
    model = RoomyScriptedModel([], auto_review=False)
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True, project_inspect_enabled=True,
        full_local_read_enabled=True), portable_root=portable, state_directory=portable/'state', host_access_policy=policy)
    runtime.set_tool_approval_required(False)
    def run():
        return runtime.run([{'role': 'user', 'content': 'Implement and inspect the Systems console family.'}],
            session_id='session', turn_id='turn-1', portable_root=portable, allowed_read_roots=(tmp_path,),
            host_access_policy=policy, goal_request='Implement and inspect the Systems console family.')
    run.inspector = runtime.registry.resolve('project.inspect')
    yield model, run
    runtime.shutdown()


def assessment(status, remaining=()):
    return ModelResponse.text(json.dumps(dict(goal_id='turn-1', status=status, remaining=list(remaining))))


@pytest.mark.parametrize('mode', ['local', 'cloud', 'native'])
def test_combined_recovery_finishes_with_one_edit_and_updated_completion_review(tmp_path, monkeypatch, recovery_runtime, mode):
    native = mode == 'native'
    path = tmp_path/('index.html' if native else 'App.tsx')
    old, new = ('Systems pending', 'Systems console') if native else ('old', 'new')
    path.write_text('''<!doctype html><select id="family"><option value="radial">Radial dial</option>
        <option value="systems">Systems console</option></select><p id="hero">Radial dial</p><script>
        document.querySelector('#family').onchange=e=>document.querySelector('#hero').textContent=
        e.target.value==='systems'?'Systems pending':'Radial dial';</script>''' if native else old)
    model, run = recovery_runtime; model.mode = 'local' if native else mode
    attempts = []
    def inspect(self, args, ctx):
        attempts.append(args)
        if len(attempts) == 1:
            return dict(project_path=str(tmp_path), inspection_complete=False, passed=False, checks=[], problems=[])
        if len(attempts) < 4:
            return check(tmp_path, 'unused')[1].output
        return dict(project_path=str(tmp_path), inspection_complete=True, passed=True, checks=[
            dict(action='select_option', target='#family', passed=True, selected_value='systems'),
            dict(action='text', target='#hero', passed=True)], problems=[], evidence_version=2)
    if native:
        pytest.importorskip('playwright')
        from tests.test_project_verification import free_port
        state = Path(__file__).resolve().parents[1]/'state'
        if not (state/'playwright').is_dir(): pytest.skip('Local Playwright browser is not installed.')
        run.inspector.state_directory = state
        model.supports_local_image_inputs = True
        model.count_image_message_tokens = model.count_message_tokens
        original = ProjectInspectCapability.execute
        def native_inspect(self,args,ctx):
            attempts.append(args)
            return original(self,args,ctx)
        monkeypatch.setattr(ProjectInspectCapability,'execute',native_inspect)
    else:
        monkeypatch.setattr(ProjectInspectCapability, 'execute', inspect)
    args = dict(project_path=str(tmp_path), kind='browser', url='http://localhost/',
        steps=[dict(action='text', target='#hero', value='systems')])
    if native:
        port = free_port()
        args.update(url=f'http://127.0.0.1:{port}/', server_executable=str(Path(sys.executable).resolve()),
            server_arguments=['-m','http.server',str(port),'--bind','127.0.0.1'],
            steps=[dict(action='select_option',target='#family',value='systems'),
                dict(action='text',target='#hero',value='Systems console')])
    first_args = {key:value for key,value in args.items() if not native or key not in {'server_executable','server_arguments'}}
    final_steps = args['steps'] if native else [dict(action='select_option',target='#family',value='systems'),
        dict(action='text',target='#hero',value='systems')]
    model.responses = [read(1,path), read(2,path), call(3,'project.inspect',**first_args),
        ModelResponse.text('Implemented the family; preview has not responded.'),
        assessment('continue', ['Complete browser inspection; preview did not respond.']),
        call(6,'project.inspect',**args), edit(7,path,old,new), edit(8,path,old,new),
        read(9,path), call(10,'project.inspect',**{**args,'timeout_seconds':31}),
        edit(11,path,old,new), read(12,path),
        call(13,'project.inspect',**{**args,'steps':final_steps}),
        ModelResponse.text('Implemented and inspected Systems console.'), assessment('ready')]
    def explain(messages, definitions):
        receipt = [m['result']['call_id'] for m in messages if m.get('role') == 'capability'
            and m.get('capability') == 'project.inspect'][-1]
        for index, response in enumerate(model.responses):
            if response.capability_calls and response.capability_calls[0].capability == 'filesystem.edit_text':
                model.responses[index] = edit(f'grounded-{index}',path,old,new,repair_diagnosis=diagnosis(receipt))
    model.before_request[6] = explain
    if native:
        # The equivalent later inspection may be cited without demanding a new
        # read after every repeat of the same defect on the unchanged revision.
        model.before_request[10] = explain
    outcome = run()
    assert outcome.status == AgentRunStatus.COMPLETED, outcome
    assert new in path.read_text() and old not in path.read_text() and len(attempts) == 4
    edits = [item.result for item in outcome.settled_calls if item.call.capability == 'filesystem.edit_text']
    assert [item.success for item in edits] == [False, False, True]
    assert all(item.metadata['edit_recovery'] == 'inspection_diagnosis' for item in edits[:2])
    assert outcome.assistant_text == 'Implemented and inspected Systems console.'
    assert outcome.completion_review.status == 'ready' and outcome.completion_review_current
    assert outcome.completion_review_receipt_count == len(outcome.settled_calls)
    assert outcome.proposed_answer is None and not model.responses and len(model.requests) == 15
    assert len(outcome.goal.verification[-1].interaction_assertions) == 2
    if native:
        inspections = [item.result.output for item in outcome.settled_calls if item.call.capability == 'project.inspect']
        assert [item['passed'] for item in inspections] == [False,False,False,True]
        assert inspections[0]['inspection_complete'] is False
        assert all(item['owned_processes_released'] for item in inspections)
        assert inspections[-1]['screenshot_sha256'] in outcome.delivered_visuals


@pytest.mark.parametrize('complete', [False, True])
def test_only_complete_contiguous_paged_source_earns_the_retry(tmp_path, complete):
    path = tmp_path/'large.tsx'; path.write_text('original source line\n'*1000)
    patch = request('filesystem.edit_text',path=str(path),old_text='original',new_text='changed')
    tracker = PrerequisiteRetries()
    tracker.observe(patch,rejected(patch),step=1)
    args = dict(max_bytes=8192,max_lines=200)
    step = 2
    while args:
        reader,result = source(path,identity=f'page-{step}',**args)
        tracker.observe(reader,result,step=step)
        args = result.output['next_read']
        if args: args = {key:value for key,value in args.items() if key != 'path'}
        step += 1
        if not complete: break
    assert tracker.renew(patch,step=step,repair_rejection=None) is complete


@pytest.mark.parametrize('anchor,current,completed', [(None,False,False),(3,False,False),(1,True,False),
    (2,False,False),(1,False,True)])
def test_saved_review_rejects_missing_mismatched_or_completed_stale_anchor(tmp_path,anchor,current,completed):
    from app.agent.completion_evidence import compile_review_evidence
    from app.agent.contracts import AgentRunResult, SettledCall
    from app.agent.goals import TaskGoal, replay_goal, finish_goal
    from app.agent.task_completion import CompletionReview
    calls = tuple(SettledCall(provider_message_id=f'message-{index}',call=tool,result=result)
        for index,(tool,result) in enumerate([check(tmp_path,'first'),check(tmp_path,'second',passed=True)]))
    initial = TaskGoal(goal_id='turn-1',objective='Inspect',evidence_version=2)
    review = CompletionReview(goal_id='turn-1',status='ready' if completed else 'continue',
        remaining=() if completed else ('Inspect remaining behavior',),evidence_origin='runtime',
        evidence=compile_review_evidence(replay_goal(initial,calls[:1]),calls[:1]))
    goal = finish_goal(replay_goal(initial,calls),completed=completed)
    outcome = AgentRunResult(status=AgentRunStatus.COMPLETED if completed else AgentRunStatus.REPEATED_CALL,
        assistant_text='Done' if completed else None,message=None if completed else 'Repeated check stopped.',
        steps=2,capability_calls=2,protocol_failures=0,settled_calls=calls,goal=goal,completion_review=review,
        completion_review_receipt_count=anchor,completion_review_current=current)
    store = ConversationStore(tmp_path/'invalid.json'); turn = store.begin_turn('Inspect')
    with pytest.raises(ValueError,match='anchor|evidence prefix'):
        store.finish_turn(turn,outcome)


@pytest.mark.parametrize('unknown_visual', [False,True])
def test_stale_review_uses_only_prefix_pixels_and_still_rejects_unrecorded_delivery(tmp_path,unknown_visual):
    from app.agent.completion_evidence import compile_review_evidence
    from app.agent.contracts import AgentRunResult, SettledCall
    from app.agent.goals import TaskGoal, replay_goal, finish_goal
    from app.agent.task_completion import CompletionReview
    pairs = [check(tmp_path,'first'),check(tmp_path,'second',passed=True)]
    for index,(_,result) in enumerate(pairs): result.output['screenshot_sha256'] = ('a','b')[index]*64
    calls = tuple(SettledCall(provider_message_id=f'message-{index}',call=tool,result=result)
        for index,(tool,result) in enumerate(pairs))
    initial = TaskGoal(goal_id='turn-1',objective='Inspect',evidence_version=2)
    review = CompletionReview(goal_id='turn-1',status='continue',remaining=('Preview unavailable',),
        evidence_origin='runtime',evidence=compile_review_evidence(replay_goal(initial,calls[:1]),calls[:1]))
    outcome = AgentRunResult(status=AgentRunStatus.REPEATED_CALL,message='Repeated check stopped.',steps=2,
        capability_calls=2,protocol_failures=0,settled_calls=calls,
        goal=finish_goal(replay_goal(initial,calls),completed=False),completion_review=review,
        completion_review_receipt_count=1,completion_review_current=False,
        delivered_visuals=('a'*64,('c' if unknown_visual else 'b')*64))
    store = ConversationStore(tmp_path/'pixels.json'); turn = store.begin_turn('Inspect')
    if unknown_visual:
        with pytest.raises(ValueError,match='Visual delivery'): store.finish_turn(turn,outcome)
    else:
        store.finish_turn(turn,outcome)
        restored = ConversationStore(store.path).turns()[0].outcome
        assert restored.completion_review == review and not restored.completion_review_current


def test_stop_preserves_answer_and_stale_review_through_save_reload_and_next_turn_context(tmp_path, monkeypatch, recovery_runtime):
    model, run = recovery_runtime
    attempts = []
    def inspect(self,args,ctx):
        attempts.append(args)
        return dict(project_path=str(tmp_path), inspection_complete=True, passed=len(attempts)>1, checks=[], problems=[])
    monkeypatch.setattr(ProjectInspectCapability,'execute',inspect)
    args = dict(project_path=str(tmp_path),kind='browser',url='http://localhost/')
    model.responses = [call(1,'project.inspect',**args), ModelResponse.text('Implemented; preview was unavailable.'),
        assessment('continue',['Preview unavailable; complete inspection.']),
        *[call(i,'project.inspect',**args) for i in range(4,7)]]
    outcome = run()
    assert outcome.status == AgentRunStatus.REPEATED_CALL and len(attempts) == 2
    assert outcome.blocked_attempt.capability == 'project.inspect' and outcome.blocked_attempt.repetition_count == 4
    assert outcome.proposed_answer == 'Implemented; preview was unavailable.'
    assert not outcome.completion_review_current and outcome.completion_review_receipt_count == 1
    assert 'Earlier completion assessment (predates later tool results' in outcome.partial_text
    assert 'Proposed answer retained' in outcome.partial_text
    store = ConversationStore(tmp_path/'stopped.json')
    turn = store.begin_turn('Implement and inspect the Systems console family.')
    store.finish_turn(turn,outcome)
    restored = ConversationStore(store.path)
    assert restored.turns()[0].outcome.completion_review == outcome.completion_review
    history = next(m['content'] for m in restored.agent_messages(preserve_unfinished=True)
        if m.get('content','').startswith('Unresolved historical work:'))
    retained = json.loads(history.split(': ',1)[1])
    assert retained['remaining'] == [] and retained['earlier_assessment'] == list(outcome.completion_review.remaining)
    assert 'requires reassessment' in retained['notice']
    assert restored.recall_turn(turn)['remaining'] == []
    assert len(restored.turns()[0].settled_calls) == 3
    # The undispatched fourth proposal is diagnostic evidence, never a settled call.
    assert all(item.result.call_id != outcome.blocked_attempt.fingerprint for item in restored.turns()[0].settled_calls)


def test_repeated_edit_without_changed_prerequisites_stops_before_dispatch_with_exact_reason(tmp_path,monkeypatch,recovery_runtime):
    path = tmp_path/'App.tsx'; path.write_text('old')
    model,run = recovery_runtime
    monkeypatch.setattr(ProjectInspectCapability,'execute',lambda self,args,ctx: check(tmp_path,'unused')[1].output)
    model.responses = [call(1,'project.inspect',project_path=str(tmp_path),kind='browser',url='http://localhost/'),
        *[edit(i,path,'old','new') for i in range(2,5)]]
    def ground(messages,definitions):
        receipt = next(m['result']['call_id'] for m in messages if m.get('role')=='capability')
        model.responses = [edit(i,path,'old','new',repair_diagnosis=diagnosis(receipt)) for i in range(2,5)]
    model.before_request[1] = ground
    outcome = run()
    assert outcome.status == AgentRunStatus.REPEATED_CALL and path.read_text() == 'old'
    assert len(outcome.settled_calls) == 3 and not model.responses
    assert outcome.blocked_attempt.capability == 'filesystem.edit_text'
    assert outcome.blocked_attempt.prerequisite_reason == 'source_read_required'
    assert outcome.blocked_attempt.evidence_receipt == outcome.settled_calls[0].result.call_id
    assert 'This call was not dispatched.' in outcome.partial_text
