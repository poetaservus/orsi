"""Current-request routing through the production catalog, SDK and durable sources."""
import base64

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.image_generation import image_request
from app.runtime.skills import SkillRegistry
from app.settings.agent import load_agent_feature_config
from tests.test_attachment_processing import image_data
from tests.test_cloud_attachment_input import native_sdk, inputs
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import response
from tests.test_image_generation_presentation import presentation_app
from tests.test_skill_activation import write_skill


CODING_REQUESTS = [
    'Traceback (most recent call last):\n  File "main.py", line 210\n    draw.rectangle(box)\nTypeError: invalid coordinates',
    'Fix this error:\n    draw.line(points)\nValueError: invalid points',
    '```python\ndraw.rectangle(box)\ndraw.line(points)\n```',
    'Do not generate images. Fix main.py.',
    "Don't generate images; fix main.py.",
    'I did not ask you to draw. Adjust the code.',
    'Change the sliders in main.py',
    'Remove the extra Tkinter button',
    'It still crashes. Adjust the code.',
    'Change this file',
    'Create a new copy of main.py and implement the fixes there',
    'Write a Python script that draws geometric overlays',
    'Create a Python program to draw an image',
    'Fix main.py. The error mentions draw.rectangle(...).',
    'The error says "Draw a picture". Fix main.py.',
    'Fix the program.\n> Generate an image of a cat',
    'Fix the program.\n```text\nGenerate a photograph of a forest\n```',
    'The log contains: Generate an image of a forest',
    'Make another version of this file',
    'Change the background color in main.py',
    'Change the image loading function in main.py',
    'Make image processing code for geometric overlays',
    'Remove the image preview button from main.py',
]


@pytest.mark.parametrize('prompt', CODING_REQUESTS)
@pytest.mark.parametrize('has_image', [False, True])
def test_diagnostics_and_coding_do_not_request_visual_output(prompt, has_image):
    assert not image_request(prompt, has_image=has_image)


def make_service(engine, tmp_path, *, skills=False):
    registry = SkillRegistry(global_root=tmp_path / 'skills')
    if skills:
        write_skill(registry.global_root, 'python-coder', 'Fix requested source; report unrun tests truthfully.')
        registry.discover()
    runtime = build_agent_runtime(engine, config=load_agent_feature_config().model_copy(update={'full_local_read_enabled': False}),
        portable_root=tmp_path, state_directory=tmp_path / 'runtime')
    return ConversationService(engine, ConversationStore(tmp_path / 'chat.json'),
        agent_runtime=runtime, portable_root=tmp_path, skill_registry=registry)


@pytest.mark.parametrize('prompt', CODING_REQUESTS)
@pytest.mark.parametrize('screenshot', [False, True])
def test_coding_service_preserves_sources_and_file_catalog(native_sdk, tmp_path, prompt, screenshot):
    engine, _, bodies, _ = native_sdk()
    service = make_service(engine, tmp_path)
    references = (service.store.attachment_store.import_bytes(image_data(), name='bug.png'),) if screenshot else ()
    try:
        decision = service.image_route_decision(prompt, attachments=references)
        assert decision.route == 'agent' and decision.references == references
        assert not service.will_generate_images(prompt, attachments=references)
        service.run(prompt, attachments=references)
        body = bodies[-1]
        assert body.get('tool_choice') != {'type': 'image_generation'}
        assert all(tool['type'] != 'image_generation' for tool in body['tools'])
        assert len(body['tools']) == len(service.agent_capabilities) == 12
        names = [tool['name'] for tool in body['tools']]
        assert any('read_text' in name for name in names)
        assert any('edit_text' in name for name in names)
        assert any('write_text' in name for name in names)
        assert service.store.visible_messages()[-2].attachments == references
        if screenshot:
            sent = inputs(body, 'input_image')
            assert len(sent) == 1
            assert base64.b64decode(sent[0]['image_url'].split(',', 1)[1]) == image_data()
    finally:
        service.shutdown()


@pytest.mark.parametrize('prompt', ['It still crashes. Adjust the code.', 'Change this file',
                                  'Make another version', 'Remove it', 'Analyze the image loading function in main.py'])
def test_historical_image_cannot_redirect_file_task(native_sdk, tmp_path, prompt):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), response('Done')])
    service = make_service(engine, tmp_path)
    try:
        original = service.run('Draw a blue circle').generated_images
        decision = service.image_route_decision(prompt)
        assert decision.route == 'agent' and not decision.references
        assert not service.will_generate_images(prompt)
        service.run(prompt)
        assert bodies[-1].get('tool_choice') != {'type': 'image_generation'}
        assert not service.store.visible_messages()[-2].attachments
        service.store.attachment_store.verify(original[0])
        assert service.store.visible_messages()[1].generated_images == original
    finally:
        service.shutdown()


def test_unrelated_task_ends_implicit_source_scope_but_explicit_selection_still_edits(native_sdk, tmp_path):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), response('Done'), response('Done'), image_payload()])
    service = make_service(engine, tmp_path)
    try:
        original = service.run('Draw a blue circle').generated_images
        service.run('Fix main.py')
        assert not service.will_generate_images('Make the background darker')
        assert not service.image_route_decision('Describe this image').references
        service.run('Make the background darker')
        assert not service.store.visible_messages()[-2].attachments
        assert service.will_generate_images('Make the background darker', attachments=original)
        service.run('Make the background darker', attachments=original)
        assert bodies[-1]['tool_choice'] == {'type': 'image_generation'}
        assert len(inputs(bodies[-1], 'input_image')) == 1
        assert service.store.visible_messages()[-2].attachments == original
    finally:
        service.shutdown()


@pytest.mark.parametrize('scope', ['message', 'session'])
@pytest.mark.parametrize('prompt', ['Do not generate images. Fix main.py.',
                                  'Generate a photograph of a forest', '/image a blue circle',
                                  'Make it darker', 'Make this image darker'])
def test_effective_skill_scope_agrees_without_vetoing_explicit_images(native_sdk, tmp_path, scope, prompt):
    visual = prompt.startswith(('Generate', '/image', 'Make this image'))
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), image_payload() if visual else response('Done')])
    service = make_service(engine, tmp_path, skills=True)
    try:
        original = service.run('Draw a blue circle').generated_images
        if scope == 'session':
            service.activate_skill('python-coder')
        kwargs = {'skill_name': 'python-coder'} if scope == 'message' else {}
        decision = service.image_route_decision(prompt, **kwargs)
        assert decision.skill_name == 'python-coder'
        assert service.will_generate_images(prompt, **kwargs) == visual
        service.run(prompt, **kwargs)
        assert (bodies[-1].get('tool_choice') == {'type': 'image_generation'}) == visual
        assert (service.active_skill is not None) == (scope == 'session')
        if prompt == 'Make this image darker':
            assert service.store.visible_messages()[-2].attachments == original
    finally:
        service.shutdown()


@pytest.mark.parametrize('prompt', ['Describe this image', 'Please describe this image',
                                  'Can you please analyze this image', 'Show this image'])
def test_image_inspection_after_explicit_selection_uses_selected_original(native_sdk, tmp_path, prompt):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(count=2), response('Done'), response('A blue circle')])
    service = make_service(engine, tmp_path)
    try:
        originals = service.run('Generate two images of a blue circle').generated_images
        service.run('Describe this image', attachments=(originals[0],))
        decision = service.image_route_decision(prompt)
        assert decision.route == 'agent' and decision.references == (originals[0],)
        service.run(prompt)
        assert bodies[-1].get('tool_choice') != {'type': 'image_generation'}
        assert service.store.visible_messages()[-2].attachments == (originals[0],)
    finally:
        service.shutdown()


@pytest.mark.parametrize('prompt', ['Edit this screenshot to remove the extra button',
    'Remove the extra button from this image', 'Edit this image to show Python code',
    'Please generate a diagram of Python code', 'Could you please create a photograph of a forest'])
def test_explicit_visual_outputs_survive_mentions_of_code(native_sdk, tmp_path, prompt):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload()])
    service = make_service(engine, tmp_path)
    ref = service.store.attachment_store.import_bytes(image_data(), name='original.png')
    try:
        assert service.will_generate_images(prompt, attachments=(ref,))
        service.run(prompt, attachments=(ref,))
        assert bodies[-1]['tool_choice'] == {'type': 'image_generation'}
        assert service.store.visible_messages()[-2].attachments == (ref,)
    finally:
        service.shutdown()


@pytest.mark.parametrize('prompt', ["Do not create a new file. Generate a photograph of a forest.",
    "Don't generate a Python script. Draw a picture of a forest.",
    'Generate an image of a forest. Do not create a text report.'])
def test_negated_written_outputs_do_not_veto_visual_creation(prompt):
    assert image_request(prompt)


@pytest.mark.parametrize('prompt', ['Crop it', 'Resize it', 'Darken it', 'Make it red', 'Make it larger', 'Remove the hat'])
def test_concrete_visual_edit_preserves_current_original(native_sdk, tmp_path, prompt):
    engine, _, bodies, _ = native_sdk(payloads=[image_payload(), image_payload()])
    service = make_service(engine, tmp_path)
    try:
        original = service.run('Draw a blue circle').generated_images
        assert service.will_generate_images(prompt)
        service.run(prompt)
        assert bodies[-1]['tool_choice'] == {'type': 'image_generation'}
        assert service.store.visible_messages()[-2].attachments == original
    finally:
        service.shutdown()


def test_composer_coding_screenshot_has_no_generation_preview(presentation_app, native_sdk, tmp_path):
    from app.inference.hybrid import HybridInferenceEngine
    from app.ui.main_window import MainWindow
    from tests.test_message_images import wait_for

    engine, _, bodies, _ = native_sdk()
    hybrid = HybridInferenceEngine(local=None, cloud=engine, default_mode='cloud', fallback_to_local=False)
    service = make_service(hybrid, tmp_path)
    ref = service.store.attachment_store.import_bytes(image_data(), name='bug.png')
    window = MainWindow(service, 'ROUTING REGRESSION', inference=hybrid)
    window.show()
    try:
        window.attachment_tray.add_references((ref,))
        wait_for(lambda: window.attachment_tray.ready)
        window.input.setPlainText('Change the sliders in main.py')
        window.submit()
        assert not window._image_in_flight and window.chat.generation_frame is None
        wait_for(lambda: window.thread is None)
        assert bodies[-1].get('tool_choice') != {'type': 'image_generation'}
        assert service.store.visible_messages()[-2].attachments == (ref,)
    finally:
        window.close()
        service.shutdown()
