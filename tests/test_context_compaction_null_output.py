"""A rejected call followed by successful work must survive real compaction."""
from copy import deepcopy
import json

import pytest

from app.agent.contracts import AgentRunStatus
from app.capabilities.contracts import CapabilityErrorCode
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelResponse, native_chat_messages
from tests.test_bounded_edit_recovery import RoomyScriptedModel, read, edit
from tests.test_context_recovery import CharacterModel, exchange


def pressured_history(*, null_output=True, protected_size=0):
    messages = [{'role':'system','content':'Exact policy'},
        {'role':'user','content':'Preserve every requirement. ' + 'P'*protected_size}]
    rejected = exchange('rejected', 'unused')
    result = rejected[-1]['result']
    result.update(success=False, output=None, error=dict(code='invalid_arguments',message='Rejected exact edit.'))
    if not null_output:
        result.pop('output')
    messages.extend(rejected)
    for index in range(6):
        messages.extend(exchange(f'later-{index}', 'source evidence '*2200,index=index+1))
    return messages


@pytest.mark.parametrize('null_output', [True,False])
@pytest.mark.parametrize('openai_context', [False,True])
def test_natural_deep_compaction_preserves_null_or_omitted_failed_output(null_output,openai_context):
    messages = pressured_history(null_output=null_output)
    original = deepcopy(messages)
    model = CharacterModel(); model.context_length=12_000
    model.supports_openai_context=openai_context
    model.count_context_message_tokens=lambda values: len(json.dumps(values,separators=(',',':')))
    stages=[]
    recovered = recover_context_request(model,messages,stage_observer=stages.append)
    assert recovered.compacted and recovered.budget.fits
    assert messages == original
    assert recovered.messages[3] == original[3]
    assert [m for m in recovered.messages if 'capability_calls' in m] == [m for m in original if 'capability_calls' in m]
    assert len(recovered.messages) == len(original)
    assert stages[0]=='projection' and stages[-1]=='budget' and 'compaction' in stages
    assert [m for m in recovered.messages if m.get('role') in {'system','user'}] == original[:2]


def test_unfit_protected_context_returns_nonfit_budget_without_crashing_on_failed_receipt():
    messages=pressured_history(protected_size=30_000)
    model=CharacterModel(); model.context_length=20_000
    recovered=recover_context_request(model,messages)
    assert not recovered.budget.fits
    assert recovered.messages[:4] == messages[:4]


class PressureModel(RoomyScriptedModel):
    context_length=24_000
    max_response_tokens=512

    @staticmethod
    def count_message_tokens(messages):
        return sum(len(message['content']) for message in messages)


@pytest.fixture
def pressure_runtime(tmp_path):
    from app.agent.bootstrap import build_agent_runtime
    from app.settings.agent import AgentFeatureConfig
    from app.security.host_access import HostAccessPolicy
    portable=tmp_path/'portable'; portable.mkdir()
    model=PressureModel([],auto_review=False)
    policy=HostAccessPolicy.full_local(application_root=portable,user_home=tmp_path,acknowledged=True)
    runtime=build_agent_runtime(model,config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True,filesystem_edit_text_enabled=True,full_local_read_enabled=True,
        context_recovery_enabled=True), portable_root=portable,state_directory=portable/'state',host_access_policy=policy)
    runtime.set_tool_approval_required(False)
    def run(objective):
        return runtime.run([{'role':'user','content':objective}],session_id='session',turn_id='turn-1',
            portable_root=portable,allowed_read_roots=(tmp_path,),host_access_policy=policy,goal_request=objective)
    yield runtime,model,run
    runtime.shutdown()


def test_real_rejected_edit_then_success_deep_compaction_and_completion_keep_original_receipts(tmp_path,pressure_runtime):
    runtime,model,run=pressure_runtime
    path=tmp_path/'flag.txt'; path.write_text('enabled=false\n')
    evidence=[]
    for index in range(4):
        target=tmp_path/f'evidence-{index}.txt'; target.write_text(f'Evidence {index}\n'+'independent source '*1800)
        evidence.append(target)
    responses=[edit(1,path,'missing target','enabled=true'), read(2,path,max_bytes=65536,max_lines=1000),
        edit(3,path,'enabled=false','enabled=true'),read(4,path,max_bytes=65536,max_lines=1000),
        *[read(index+5,target,max_bytes=65536,max_lines=1000) for index,target in enumerate(evidence)],
        ModelResponse.text('Changed the flag and read the requested evidence.'),
        ModelResponse.text(json.dumps(dict(goal_id='turn-1',status='ready',remaining=[])))]
    model.responses=list(responses)
    objective='Change enabled=false to enabled=true in flag.txt, read the evidence files, and report completion.'
    outcome=run(objective)
    mutations=[item for item in outcome.settled_calls if item.call.capability=='filesystem.edit_text']
    assert outcome.status==AgentRunStatus.COMPLETED,(outcome.status,outcome.context_compactions,
        [(item.call.capability,item.result.success,item.result.error.message if item.result.error else None)
            for item in outcome.settled_calls])
    assert outcome.context_compactions>0
    assert 'enabled=true' in path.read_text() and 'enabled=false' not in path.read_text()
    assert [item.result.success for item in mutations]==[False,True]
    assert mutations[0].result.output is None
    assert mutations[0].result.error.code==CapabilityErrorCode.INVALID_ARGUMENTS
    assert len(outcome.settled_calls)==8 and len(model.requests)==10 and not model.responses
    assert outcome.completion_review.status=='ready' and outcome.completion_review_current
    for request in model.requests:
        native_chat_messages(request,runtime.registry.model_definitions())
    retained=[m for m in model.requests[-2] if m.get('role')=='capability']
    failed=next(m for m in retained if m['result']['call_id']==mutations[0].result.call_id)
    assert failed['result']==mutations[0].result.model_dump(mode='json')
    assert any(m['result'].get('metadata',{}).get('context_projection') for m in retained)
    # Durable results keep full original source; projection modifies request copies only.
    last_read=outcome.settled_calls[-1].result
    assert len(last_read.output['text'])>30_000 and 'context_projection' not in last_read.metadata
    store=ConversationStore(tmp_path/'completed.json'); turn=store.begin_turn(objective)
    store.finish_turn(turn,outcome)
    restored=ConversationStore(store.path).turns()[0]
    assert restored.settled_calls==list(outcome.settled_calls)
    assert restored.outcome.status==AgentRunStatus.COMPLETED
    assert restored.outcome.completion_review==outcome.completion_review


def test_genuinely_unfit_request_stops_as_context_limit(tmp_path,pressure_runtime):
    runtime,model,run=pressure_runtime
    # Protected user requirements cannot be trimmed for admission.
    model.responses=[ModelResponse.text('Must not be sent')]
    outcome=run('Exact user requirement: '+'R'*40_000)
    assert outcome.status==AgentRunStatus.CONTEXT_LIMIT,outcome
    assert outcome.capability_calls==0 and len(model.requests)==0
    assert getattr(outcome,'context_recovery_failure',None) is None
