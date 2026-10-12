from pathlib import Path

import pytest

from app.agent.repair_loop import RepairLoopTracker
from app.capabilities.contracts import CapabilityResult
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call, read, edit


def request(tool, **arguments):
    return ModelCapabilityCall(provider_call_id='probe',capability=tool,arguments=arguments)


def diagnosis(receipt='inspection-1'):
    return [receipt, 'Returning to the partial position changes opacity.',
        'The current source accumulates wheel delta separately from actual scroll.',
        'Compute progress from current geometry.',
        'The return checkpoint matches partial scroll, bounds and opacity.']


@pytest.mark.parametrize('value', [[], ['receipt']*4, ['receipt']*6,
    ['receipt','','cause','change','observation'], ['r'*129,'failure','cause','change','observation'],
    ['receipt','failure','cause','change',1]])
def test_compact_diagnosis_keeps_each_part_and_its_position_strict(value):
    from app.capabilities.repair_diagnosis import RepairDiagnosis
    with pytest.raises(ValueError):
        RepairDiagnosis.model_validate(value)


def test_native_cloud_wire_delivers_the_five_part_diagnosis_without_narration():
    from app.capabilities.filesystem_edit_text import FilesystemEditTextArguments
    from app.inference.openai_backend import normalize_tool_response
    from app.inference.protocol import ModelCapabilityDefinition, ModelResponseKind
    from tests.test_openai_phase1 import response
    from tests.test_openai_tools import function
    definition = ModelCapabilityDefinition(name='filesystem.edit_text',description='Edit',
        input_schema=FilesystemEditTextArguments.model_json_schema())
    wire = {key:None for key in definition.input_schema['properties']}
    wire.update(path='C:/project/App.tsx',old_text='old',new_text='new',repair_diagnosis=diagnosis())
    result = normalize_tool_response(response(output=[function(definition,wire)]),(definition,))
    assert result.kind == ModelResponseKind.CAPABILITY_CALLS
    parsed = FilesystemEditTextArguments.model_validate(result.capability_calls[0].arguments)
    assert parsed.repair_diagnosis.evidence_receipt == 'inspection-1'


def failed(project, **overrides):
    return CapabilityResult(call_id='inspection-1',capability='project.inspect',success=True,duration_ms=0,
        output=dict(project_path=str(project),inspection_complete=True,passed=False,
            checks=[dict(action='checkpoint',target='#hero',label='return',expectation='same_state',passed=False,
                failure_kind='interaction_assertion_failed')],problems=[],**overrides))


@pytest.mark.parametrize('problem', ['missing','stale_receipt','old_read','same_batch_read','truncated_read','valid'])
def test_repair_requires_a_complete_later_read_and_four_part_diagnosis(tmp_path, problem):
    tracker = RepairLoopTracker()
    tool = request('project.inspect',project_path=str(tmp_path))
    assert 'confirm or disprove' in tracker.observe(tool,failed(tmp_path),step=2)
    result = CapabilityResult(call_id='source',capability='filesystem.read_text',success=True,duration_ms=0,
        output=dict(path=str(tmp_path/'App.tsx'),source_complete=problem!='truncated_read'))
    tracker.observe(request('filesystem.read_text',path=str(tmp_path/'App.tsx')),result,
        step=1 if problem=='old_read' else 4 if problem=='same_batch_read' else 3)
    arguments = dict(path=str(tmp_path/'App.tsx'),old_text='old',new_text='new')
    if problem != 'missing':
        arguments['repair_diagnosis'] = diagnosis('stale' if problem=='stale_receipt' else 'inspection-1')
    assert (tracker.before(request('filesystem.edit_text',**arguments),step=4) is None) is (problem=='valid')
    assert tracker.before(request('filesystem.edit_text',path=str(tmp_path.parent/'other.tsx')),step=4) is None


def test_loading_only_pass_cannot_clear_an_unresolved_interaction(tmp_path):
    tracker = RepairLoopTracker()
    call = request('project.inspect',project_path=str(tmp_path))
    failure = failed(tmp_path)
    tracker.observe(call,failure,step=1)
    passing = failure.model_copy(update={'output':{**failure.output,'passed':True,'checks':[]}})
    tracker.observe(call,passing,step=2)
    mutation = request('filesystem.edit_text',path=str(tmp_path/'App.tsx'))
    assert tracker.before(mutation,step=3) is not None
    passing.output['checks'] = [{**failure.output['checks'][0],'passed':True}]
    tracker.observe(call,passing,step=4)
    assert tracker.before(mutation,step=5) is None


@pytest.mark.parametrize('kind', ['selector_error','target_not_found','checkpoint_reference_unavailable'])
def test_selector_correction_does_not_require_or_authorize_a_source_repair(tmp_path, kind):
    tracker = RepairLoopTracker()
    failure = failed(tmp_path)
    failure.output['checks'][0]['failure_kind'] = kind
    feedback = tracker.observe(request('project.inspect'),failure,step=1)
    assert 'selector' in feedback and 'alone does not justify' in feedback
    assert not tracker._failures


def test_native_tool_only_repair_rejection_then_diagnosis_recovers_in_same_turn(tmp_path, monkeypatch):
    from app.agent.bootstrap import build_agent_runtime
    from app.agent.contracts import AgentRunStatus
    from app.capabilities.project_verification import ProjectInspectCapability
    from app.settings.agent import AgentFeatureConfig
    from app.security.host_access import HostAccessPolicy
    from tests.test_agent_runtime import run
    path = tmp_path/'App.tsx'
    path.write_text('old')
    monkeypatch.setattr(ProjectInspectCapability,'execute',lambda self,args,ctx:
        failed(tmp_path).output)
    model = RoomyScriptedModel([call(1,'project.inspect',project_path=str(tmp_path),kind='browser',url='http://localhost/'),
        edit(2,path,'old','new'), read(3,path), edit(4,path,'old','new'), ModelResponse.text('Changed source; behavior remains unverified.')])
    def explain(messages, capabilities):
        receipt = next(m['result']['call_id'] for m in messages if m.get('role')=='capability'
            and m.get('capability')=='project.inspect')
        model.responses[0] = edit(4,path,'old','new',repair_diagnosis=diagnosis(receipt))
    model.before_request[3] = explain
    portable = tmp_path/'portable';portable.mkdir()
    policy = HostAccessPolicy.full_local(application_root=portable,user_home=tmp_path,acknowledged=True)
    runtime = build_agent_runtime(model,config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True,filesystem_edit_text_enabled=True,project_inspect_enabled=True,full_local_read_enabled=True),
        portable_root=portable,state_directory=portable/'state',host_access_policy=policy)
    runtime.set_tool_approval_required(False)
    result = run(runtime,tmp_path)
    assert result.status == AgentRunStatus.COMPLETED, result
    assert path.read_text() == 'new'
