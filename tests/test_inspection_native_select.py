"""Native option selection and inspection-action errors, using disposable previews."""
from pathlib import Path
import sys

import pytest

from app.capabilities.project_verification import ProjectInspectCapability, ProjectInspectionArguments
from app.runtime.inspection_worker import _failure_kind
from tests.test_filesystem_read_text import context
from tests.test_project_verification import approved, free_port


@pytest.mark.parametrize('step', [
    dict(action='select_option', target='#family'),
    dict(action='select_option', value='systems'),
    dict(action='select_option', target=' ', value='systems'),
    dict(action='select_option', target='#family', value=['systems']),
    dict(action='select_option', target='#family', value='systems', option_label='Systems console'),
])
def test_native_option_arguments_require_exact_target_and_explicit_single_value(tmp_path, step):
    with pytest.raises(ValueError):
        ProjectInspectionArguments(project_path=str(tmp_path), kind='browser', url='http://localhost/', steps=[step])


def test_native_option_empty_value_is_explicit_and_desktop_use_is_rejected(tmp_path):
    step = dict(action='select_option', target='#family', value='')
    args = ProjectInspectionArguments(project_path=str(tmp_path), kind='browser', url='http://localhost/', steps=[step])
    assert args.steps[0].value == ''
    with pytest.raises(ValueError, match='browser-only'):
        ProjectInspectionArguments(project_path=str(tmp_path), kind='desktop', pid=42, steps=[step])


@pytest.mark.parametrize('message,action,expected', [
    ('Locator.fill: Element is not an <input>, <textarea> or [contenteditable] element', 'fill', 'action_incompatible'),
    ('Locator.fill: Input of type "checkbox" cannot be filled', 'fill', 'action_incompatible'),
    ('Locator.select_option: Element is not a <select> element', 'select_option', 'action_incompatible'),
    ('Expected text is absent.', 'text', 'interaction_assertion_failed'),
    ('Selected option did not remain at the requested value.', 'select_option', 'interaction_assertion_failed'),
    ('Application reported input of type unavailable', 'fill', 'interaction_assertion_failed'),
])
def test_action_failure_classification_remains_specific(message, action, expected):
    assert _failure_kind(message, '#family', action=action) == expected


def inspect(tmp_path, steps, *, reset=False, app_error=False):
    pytest.importorskip('playwright')
    state = Path(__file__).resolve().parents[1] / 'state'
    if not (state / 'playwright').is_dir():
        pytest.skip('Local Playwright browser is not installed.')
    (tmp_path / 'index.html').write_text('''<!doctype html><title>Disposable family selector</title>
        <select id="family"><option value="radial">Radial dial</option>
        <option value="systems">Systems console</option></select><input id="field">
        <p id="result">Radial dial</p><script>
        document.querySelector('#family').addEventListener('change', event => {
            document.querySelector('#result').textContent=event.target.selectedOptions[0].textContent;
            RESET
        });
        APP_ERROR
        </script>'''.replace('RESET', "event.target.value='radial';" if reset else '')
        .replace('APP_ERROR', "throw new Error('Disposable application runtime failure');" if app_error else ''), encoding='utf-8')
    port = free_port()
    tool = ProjectInspectCapability(state)
    args = dict(project_path=str(tmp_path), kind='browser', url=f'http://127.0.0.1:{port}/', steps=steps,
        server_executable=str(Path(sys.executable).resolve()),
        server_arguments=['-m', 'http.server', str(port), '--bind', '127.0.0.1'])
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output['inspection_complete'] and result.output['owned_processes_released'], result
    return result.output


def test_native_option_selection_checks_value_and_application_change_event(tmp_path):
    output = inspect(tmp_path, [dict(action='select_option', target='#family', value='systems'),
        dict(action='text', target='#result', value='Systems console')])
    assert output['passed'], output
    assert output['checks'][0]['selected_value'] == 'systems'
    assert output['checks'][0]['expected_value'] == 'systems'
    assert all(check['passed'] for check in output['checks'])


def test_native_select_fill_is_inspection_error_and_correct_action_can_proceed(tmp_path):
    output = inspect(tmp_path, [dict(action='fill', target='#family', value='systems'),
        dict(action='select_option', target='#family', value='systems'),
        dict(action='text', target='#result', value='Systems console')])
    assert not output['passed']
    assert output['checks'][0]['failure_kind'] == 'action_incompatible'
    assert not output['checks'][0]['passed']
    assert all(check['passed'] for check in output['checks'][1:])


def test_non_select_target_does_not_claim_option_selection(tmp_path):
    output = inspect(tmp_path, [dict(action='select_option', target='#field', value='systems')])
    assert not output['passed']
    assert output['checks'][0]['failure_kind'] == 'action_incompatible'


def test_option_selection_reverted_by_application_is_real_failed_assertion(tmp_path):
    output = inspect(tmp_path, [dict(action='select_option', target='#family', value='systems')], reset=True)
    assert not output['passed']
    assert output['checks'][0]['selected_value'] == 'radial'
    assert output['checks'][0]['failure_kind'] == 'interaction_assertion_failed'


def test_inspection_action_error_does_not_hide_application_runtime_failure(tmp_path):
    output = inspect(tmp_path, [dict(action='fill', target='#family', value='systems')], app_error=True)
    assert not output['passed']
    assert output['checks'][0]['failure_kind'] == 'action_incompatible'
    assert any(problem['kind'] == 'page_error' for problem in output['problems'])


def test_absent_option_cannot_pass_as_successful_selection(tmp_path):
    output = inspect(tmp_path, [dict(action='select_option', target='#family', value='absent', timeout_ms=100)])
    assert not output['passed']
    assert not output['checks'][0]['passed']
