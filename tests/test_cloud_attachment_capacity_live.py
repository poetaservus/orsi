"""Opt-in capacity gates using synthetic inputs and numeric-only diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.conversation.cloud_attachments import MAX_FILE_BYTES, MAX_IMAGES
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.settings.cloud import load_cloud_config
from tests.test_attachment_processing import make_pdf
from tests.test_cloud_attachment_live import image_bytes


pytestmark = pytest.mark.skipif(os.environ.get('ORSI_RUN_CLOUD_ATTACHMENT_CAPACITY_LIVE') != '1',
    reason='Optional paid cloud capacity qualification; requires authorized existing credential')


@pytest.fixture
def live_service(tmp_path):
    key_path = os.environ.get('ORSI_CLOUD_ATTACHMENT_KEY_FILE')
    assert key_path, 'Set the authorized existing credential file path.'
    with Path(key_path).open(encoding='utf-8-sig') as stream:
        key = stream.readline().strip()
    assert key, 'The authorized credential file is empty.'
    engine = OpenAIResponsesInferenceEngine(load_cloud_config(), api_key=key,
        rate_limits_path=Path('state/cloud_rate_limits_v1.json'))
    del key
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    try:
        yield service
    finally:
        engine.close()
        assert engine._runner is None and not engine.has_api_key


def record(service, tmp_path, **numbers):
    completion = service.store.turns()[-1].outcome.completion
    result = {'passed': True, **numbers, **service.inference.last_attachment_capacity,
        'input_tokens_used': completion.usage.input_tokens,
        'output_tokens_used': completion.usage.output_tokens,
        'profile_output_allowance': service.inference.max_response_tokens}
    (tmp_path / 'live-summary.json').write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps(result))


def test_maximum_image_count_with_account_fitted_reply(live_service, tmp_path):
    service = live_service
    colors = {0: 'red', 750: 'green', 1499: 'blue'}
    images = {color: image_bytes(color) for color in ('red', 'green', 'blue')}
    refs = [service.store.attachment_store.import_bytes(images[colors.get(i, 'red')],
        name=f'capacity-{i:04d}-' + 'x' * 150 + '.png') for i in range(MAX_IMAGES)]
    answer = service.run('Report only the dominant colors of attached images number 1, 751 and 1500, in that order.', attachments=refs)
    assert all(color in answer.lower() for color in ('red', 'green', 'blue')), 'Boundary source recognition failed.'
    assert service.inference.last_attachment_capacity['output_allowance'] < 128_000
    record(service, tmp_path, image_count=len(refs))


def test_file_just_below_document_byte_ceiling(live_service, tmp_path):
    service = live_service
    raw = make_pdf(text='PDF capacity acceptance code: 731')
    index = raw.rfind(b'\nstartxref')
    assert index > 0
    # A legal large comment leaves page content and xref offsets unchanged.
    data = raw[:index] + b'\n%' + b' ' * (MAX_FILE_BYTES - 1 - len(raw) - 3) + b'\n' + raw[index:]
    assert len(data) == MAX_FILE_BYTES - 1
    ref = service.store.attachment_store.import_bytes(data, name='capacity.pdf')
    answer = service.run('Report only the PDF capacity acceptance code from the supplied file.', attachments=[ref])
    assert '731' in answer, 'Near-ceiling PDF source recognition failed.'
    record(service, tmp_path, file_count=1, file_bytes=ref.size_bytes)


def test_many_files_have_no_arbitrary_count_cap(live_service, tmp_path):
    service = live_service
    refs = [service.store.attachment_store.import_bytes(f'Capacity acceptance code: {i:04d}'.encode(),
        name=f'capacity-{i:04d}.txt') for i in range(256)]
    answer = service.run('Report only the capacity acceptance codes from the first and last attached files, in order.', attachments=refs)
    assert '0000' in answer and '0255' in answer, 'Many-file boundary source recognition failed.'
    record(service, tmp_path, file_count=len(refs), file_bytes=sum(ref.size_bytes for ref in refs))
