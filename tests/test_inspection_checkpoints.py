"""Real-browser forward/return evidence and its bounded transport contract."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.agent.inspection_images import inspection_image_message
from app.capabilities.project_verification import ProjectInspectCapability, ProjectInspectionArguments
from tests.test_filesystem_read_text import context
from tests.test_project_verification import approved, free_port


def inspection(tmp_path, steps, *, hidden_parent=False):
    pytest.importorskip('playwright')
    state = Path(__file__).resolve().parents[1] / 'state'
    if not (state/'playwright').is_dir():
        pytest.skip('Playwright Chromium unavailable')
    (tmp_path/'index.html').write_text('''<style>
        body{margin:0} #runway{height:2400px} #hero{position:sticky;top:0;height:800px;background:red}
        #next{height:1000px;background:green}</style><div id=runway><div id=hero>Hero</div></div><div id=next>Next</div>
        <script>addEventListener('scroll',()=>document.querySelector('#hero').style.setProperty('--progress',scrollY/1600));
        document.querySelector('#hero').style.setProperty('--progress',0);</script>'''
        + ('<style>#runway{opacity:0}</style>' if hidden_parent else ''), encoding='utf-8')
    port = free_port()
    args = dict(project_path=str(tmp_path), kind='browser', url=f'http://127.0.0.1:{port}/', steps=steps,
        server_executable=str(Path(sys.executable).resolve()),
        server_arguments=['-m','http.server',str(port),'--bind','127.0.0.1'])
    tool = ProjectInspectCapability(state)
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output['owned_processes_released'], result.error
    return tool, result


def checkpoint(label, **kwargs):
    return dict(action='checkpoint', label=label, target='#hero', **{'properties':['--progress','opacity','transform'], **kwargs})


def test_attached_checkpoint_timeout_is_capture_failure_not_missing_target_or_defect():
    from app.runtime.inspection_worker import _failure_kind
    message = 'Locator.evaluate: Timeout 2000ms exceeded; locator resolved to visible SVG'
    assert _failure_kind(message,'#hero',True) == 'observation_unavailable'
    assert _failure_kind('Locator.element_handle: Timeout 2000ms exceeded','#absent') == 'target_not_found'
    assert _failure_kind('Checkpoint interaction assertion failed','#hero',True) == 'interaction_assertion_failed'


def test_one_session_delivers_initial_partial_complete_and_return_pixels(tmp_path):
    tool, result = inspection(tmp_path, [checkpoint('initial'), {'action':'scroll_to','amount':600},
        checkpoint('partial', expectation='visible'), {'action':'scroll_to','amount':1600},
        checkpoint('complete'), {'action':'scroll_to','amount':600},
        checkpoint('return', reference='partial', expectation='same_state')])
    output = result.output
    assert output['passed'], output
    checkpoints = output['checkpoints']
    assert [c['scroll']['y'] for c in checkpoints] == [0,600,1600,600]
    assert checkpoints[1]['bounds']['y'] == 0
    assert checkpoints[1]['properties']['--progress'] == checkpoints[3]['properties']['--progress']
    assert len({c['screenshot_path'] for c in checkpoints}) == 4
    assert all(len(c['screenshot_sha256']) == 64 for c in checkpoints)
    message = inspection_image_message(tool, result, SimpleNamespace(supports_local_image_inputs=True))
    assert sum(part['type']=='image_url' for part in message['content']) == 5
    # One tampered intermediate frame invalidates the whole supplement.
    Path(checkpoints[1]['screenshot_path']).write_bytes(b'tampered')
    assert inspection_image_message(tool, result, SimpleNamespace(supports_local_image_inputs=True))['role'] == 'system'


def test_interaction_failure_is_distinct_from_selector_failure(tmp_path):
    _, result = inspection(tmp_path, [checkpoint('before'), {'action':'scroll_to','amount':600},
        checkpoint('wrong_return', reference='before', expectation='same_state'),
        {'action':'visible','target':'[invalid!'}])
    assert not result.output['passed']
    assert result.output['checks'][2]['failure_kind'] == 'interaction_assertion_failed'
    assert result.output['checks'][3]['failure_kind'] == 'selector_error'


def test_ambiguous_locator_is_selector_failure_for_actions_and_checkpoints(tmp_path):
    _,result = inspection(tmp_path,[dict(action='visible',target='#hero,#next'),
        dict(action='checkpoint',target='#hero,#next',label='ambiguous')])
    assert [c['failure_kind'] for c in result.output['checks']] == ['selector_error','selector_error']


def test_failed_reference_checkpoint_requires_inspection_correction(tmp_path):
    missing = checkpoint('missing');missing['target']='#absent';missing['timeout_ms']=1
    _, result = inspection(tmp_path,[missing,checkpoint('return',reference='missing',expectation='same_state')])
    assert result.output['checks'][0]['failure_kind'] == 'target_not_found'
    assert result.output['checks'][1]['failure_kind'] == 'checkpoint_reference_unavailable'


def test_visibility_assertion_checks_ancestors_even_with_custom_properties_only(tmp_path):
    _, result = inspection(tmp_path,[checkpoint('hidden',expectation='visible',properties=['--progress'])],hidden_parent=True)
    assert result.output['checkpoints'][0]['in_viewport']
    assert not result.output['checkpoints'][0]['rendered']
    assert not result.output['checks'][0]['passed']


@pytest.mark.parametrize('action', ['key','touch'])
def test_native_navigation_and_bounded_frame_timing(tmp_path, action):
    _, result = inspection(tmp_path, [checkpoint('before'),
        {'action':action, **({'value':'PageDown'} if action=='key' else {'amount':350})},
        checkpoint('after', reference='before', expectation='scroll_down'),
        {'action':'frame_timing', 'timeout_ms':300,'amount':100,'target':'#hero','properties':['--progress']}])
    assert result.output['passed'], result.output
    timing = result.output['checks'][-1]['frame_timing']
    assert 1 <= len(timing['samples']) <= 120
    assert '--progress' in timing['first_state'] and '--progress' in timing['last_state']
    assert all(isinstance(frame['state_changed'],bool) for frame in timing['samples'])
    assert 'not proof' in timing['scope']


@pytest.mark.parametrize('steps', [
    [checkpoint('same'),checkpoint('same')], [checkpoint('later',reference='missing',expectation='same_state')],
    [checkpoint(str(i)) for i in range(5)], [checkpoint('unsafe',properties=['innerHTML'])],
    [dict(action='key',value='Control+L')], [dict(action='frame_timing',timeout_ms=2001)],
    [dict(action='frame_timing'),dict(action='frame_timing')], [dict(action='checkpoint',target='#hero')],
])
def test_observation_and_navigation_arguments_remain_bounded(tmp_path, steps):
    with pytest.raises(ValueError):
        ProjectInspectionArguments(project_path=str(tmp_path),kind='browser',url='http://localhost/',steps=steps)


def test_old_cloud_inspection_evidence_keeps_original_bytes(tmp_path):
    from app.inference.openai_tools import responses_input
    from app.inference.protocol import ModelCapabilityCall, ModelCapabilityDefinition
    from tests.test_openai_tools import function
    from tests.test_openai_replay import evidence, history_for
    definition = ModelCapabilityDefinition(name='project.inspect', description='Inspect',
        input_schema=ProjectInspectionArguments.model_json_schema())
    arguments = ProjectInspectionArguments(project_path=str(tmp_path),kind='browser',url='http://localhost/',
        steps=[dict(action='scroll',amount=300)]).model_dump(mode='json')
    for key in ('label','properties','reference','expectation'):
        arguments['steps'][0].pop(key)
    call = ModelCapabilityCall(provider_call_id='call_exact_1',capability='project.inspect',arguments=arguments)
    raw = function(definition, arguments)
    assert responses_input(history_for(evidence([raw]), (call,)), (definition,))[0] == raw


@pytest.mark.parametrize('bad', ['path','count','combined_bytes','viewport'])
def test_checkpoint_output_cannot_bypass_integrity_or_transport_limits(tmp_path, monkeypatch, bad):
    import json
    import app.capabilities.project_verification as module
    from tests.test_attachment_processing import image_data
    from PIL import Image
    tool = ProjectInspectCapability(tmp_path/'state')
    data = image_data()
    if bad == 'combined_bytes':
        monkeypatch.setattr(module, 'MAX_INSPECTION_IMAGE_BYTES', len(data)*2+1)
    def worker(command, **kwargs):
        spec = json.loads(Path(command[-1]).read_text())
        folder = Path(spec['screenshot']).parent
        values = []
        for index in range(5 if bad=='count' else 2):
            path = folder/f'checkpoint-{index}.png'
            path.write_bytes(data)
            values.append(dict(label=str(index), target='#hero',screenshot_path=str(path)))
        Path(spec['screenshot']).write_bytes(data)
        if bad == 'path':
            values[0]['screenshot_path'] = str(tmp_path/'outside.png')
        if bad == 'viewport':
            Image.new('RGB',(1921,1)).save(values[0]['screenshot_path'])
        return dict(exit_code=0,stop_reason=None,output=json.dumps(dict(passed=True,
            checkpoints=values,screenshot_path=spec['screenshot'])))
    monkeypatch.setattr(module,'run_worker',worker)
    args = dict(project_path=str(tmp_path),kind='browser',url='http://localhost/',steps=[checkpoint('0'),checkpoint('1')])
    result = tool.invoke(args, approved(tool,args,context(tmp_path)))
    assert not result.success and result.error.code.value == 'invalid_output'
