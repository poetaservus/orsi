"""Real cloud recovery from stopped/crashed attachment turns; synthetic sources."""
import json
import os
from pathlib import Path

import pytest

from app.agent.contracts import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.settings.cloud import load_cloud_config
from tests.test_attachment_processing import make_pdf
from tests.test_cloud_attachment_live import image_bytes


pytestmark = pytest.mark.skipif(os.environ.get('ORSI_RUN_ATTACHMENT_LIFECYCLE_LIVE') != '1',
    reason='Optional real cloud attachment lifecycle qualification with authorized credential')


def test_cloud_stopped_crashed_and_archived_sources_require_explicit_continuation(tmp_path):
    key_path = os.environ.get('ORSI_CLOUD_ATTACHMENT_KEY_FILE')
    assert key_path, 'Set the authorized existing credential file path.'
    with Path(key_path).open(encoding='utf-8-sig') as stream:
        key = stream.readline().strip()
    engine = OpenAIResponsesInferenceEngine(load_cloud_config(), api_key=key,
        rate_limits_path=Path('state/cloud_rate_limits_v1.json'))
    del key
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    records = []
    def record(service):
        usage = service.store.turns()[-1].outcome.completion.usage
        records.append({'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens})
    try:
        removed = service.store.attachment_store.import_bytes(b'Abandoned synthetic draft', name='removed.txt', draft=True)
        assert service.store.attachment_store.discard_draft(removed)
        ref = service.store.attachment_store.import_bytes(make_pdf(text='Recovery acceptance code: 731'),
            name='evidence.pdf', draft=True)
        answer = service.run('Read the supplied PDF and report its recovery acceptance code.', attachments=[ref],
            admission_observer=service.cancel_current_task)
        assert service.store.turns()[0].outcome.status == AgentRunStatus.CANCELLED
        assert not service.store.attachment_store.discard_draft(ref)
        service = ConversationService(engine, ConversationStore(service.store.path))
        answer = service.run('Read the PDF attached before the stopped turn. Report only its recovery acceptance code.')
        assert '731' in answer, 'Stopped-turn source recovery failed.'
        record(service)
        image = service.store.attachment_store.import_bytes(image_bytes('blue'), name='recovered.png', draft=True)
        # Persist an uncompleted turn as a process crash fixture. Reopening must
        # settle it without dispatching any model or tool operation automatically.
        service.store.begin_turn('Read this image.', attachments=[image])
        service = ConversationService(engine, ConversationStore(service.store.path))
        assert service.store.turns()[-1].outcome.status == AgentRunStatus.INTERNAL_FAILURE
        answer = service.run('Report the dominant color of the image attached in the interrupted turn and the original PDF recovery acceptance code. Keep it brief.')
        assert 'blue' in answer.lower() and '731' in answer, 'Crashed-turn source recovery failed.'
        record(service)
        service.new_session(preserve_history=True)
        archive = next((tmp_path / 'archives').glob('*.json'))
        service = ConversationService(engine, ConversationStore(archive))
        answer = service.run('Recall the attached image color and original PDF recovery acceptance code. Keep it brief.')
        assert 'blue' in answer.lower() and '731' in answer, 'Archived stopped-source recovery failed.'
        record(service)
        summary = {'passed': True, 'source_count': 2, 'abandoned_draft_removed': True,
            'stopped_turn_retained': True, 'crashed_turn_settled': True,
            'archive_recovered': True, 'turns': records}
        (tmp_path / 'live-summary.json').write_text(json.dumps(summary), encoding='utf-8')
        print(json.dumps(summary))
    finally:
        runner, client = engine._runner, engine._client
        engine.close()
        assert not engine.has_api_key
        assert runner is None or not runner._thread.is_alive()
        assert client is None or client.is_closed()
