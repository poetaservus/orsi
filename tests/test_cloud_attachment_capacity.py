"""Source-based admission and account-aware native attachment capacity."""
from __future__ import annotations

import asyncio
import httpx
import pytest

from app.conversation.attachments import AttachmentStore
from app.conversation.cloud_attachments import MAX_FILE_BYTES, MAX_IMAGES, validate_sources
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.attachments import AttachmentError
from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError
from app.inference.openai_rate_limits import OpenAIRatePacer
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.settings.cloud import load_cloud_config
from tests.test_cloud_attachment_input import native_sdk, user
from tests.test_openai_rate_limits import Clock, headers, limits


def test_large_source_uses_measured_content_before_admission(tmp_path, native_sdk):
    engine, counts, generations, _ = native_sdk(count=100)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'Padding ' * 50_000, name='source.pdf')
    assert engine.count_attachment_message_tokens([user(ref)]) > engine.context_length
    assert service.run('Read the supplied source', attachments=[ref]) == 'Done'
    assert len(counts) == 2 and len(generations) == 1
    measured = engine.count_attachment_message_tokens([user(ref)])
    assert measured == 100
    before = len(counts)
    assert engine.count_attachment_message_tokens([user(ref)]) == measured
    assert len(counts) == before  # GUI/context meter stays offline after measurement too.


def test_cached_counts_bind_text_model_root_and_credentials(tmp_path, native_sdk):
    engine, counts, generations, _ = native_sdk()
    store = AttachmentStore(tmp_path / 'sources')
    engine.set_attachment_store(store)
    ref = store.import_bytes(b'synthetic source', name='private-name.txt')
    message = user(ref)
    engine.prepare_attachment_context([message])
    engine.prepare_attachment_context([message])
    engine.set_attachment_store(AttachmentStore(store.root))
    engine.prepare_attachment_context([message])
    assert len(counts) == 1 and not generations
    assert all(len(key) == 64 and type(value) is int for key, value in engine._attachment_counts.items())
    engine.prepare_attachment_context([user(ref, 'Different request')])
    assert len(counts) == 2
    engine.select_model('gpt-6.1-sol')
    assert not engine._attachment_counts
    engine.prepare_attachment_context([message])
    assert len(counts) == 3
    engine.set_attachment_store(AttachmentStore(tmp_path / 'other'))
    assert not engine._attachment_counts
    engine.set_attachment_store(store)
    engine.prepare_attachment_context([message])
    engine.set_api_key('replacement-fake-never-live')
    assert not engine._attachment_counts and engine.last_attachment_capacity is None


def test_cache_never_bypasses_snapshot_verification(tmp_path, native_sdk):
    engine, counts, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'original', name='source.txt')
    engine.prepare_attachment_context([user(ref)])
    (service.store.attachment_store.root / ref.id / 'content').write_bytes(b'tampered')
    with pytest.raises(AttachmentError):
        service.run('Read the supplied source', attachments=[ref])
    assert len(counts) == 1 and not bodies


def test_cancelled_measurement_and_skill_controls_do_not_call_provider(tmp_path, native_sdk):
    engine, counts, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'source', name='source.txt')
    cancellation = CancellationSource(); cancellation.cancel()
    with pytest.raises(TaskCancelled):
        engine.prepare_attachment_context([user(ref)], cancellation=cancellation.token)
    service.store.begin_turn('Earlier', attachments=[ref])
    assert service.run('/skill') == 'Skill deactivated.'
    assert not counts and not bodies


@pytest.mark.parametrize('actual,expected', [(90_000, 109_744), (100, 128_000), (199_712, 32)])
def test_output_allowance_fits_actual_sources_and_preserves_profile(tmp_path, native_sdk, actual, expected):
    settings = load_cloud_config().model_copy(update={'rate_limits': limits()})
    engine, counts, bodies, _ = native_sdk(count=actual, engine_config=settings)
    clock = Clock()
    engine._rate_pacer = OpenAIRatePacer(limits(), clock=clock, sleep=clock.sleep)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'synthetic', name='source.txt')
    assert service.run('Read', attachments=[ref]) == 'Done'
    assert bodies[0]['max_output_tokens'] == expected
    assert engine.max_response_tokens == 128_000 and engine.config == settings
    assert engine.last_attachment_capacity == {'input_tokens': actual,
        'output_allowance': expected, 'token_rate_ceiling': 200_000}


def test_no_reply_room_stops_before_paid_generation(tmp_path, native_sdk):
    settings = load_cloud_config().model_copy(update={'rate_limits': limits()})
    engine, counts, bodies, _ = native_sdk(count=199_713, engine_config=settings)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'synthetic', name='source.txt')
    with pytest.raises(CloudInferenceError) as error:
        service.run('Read', attachments=[ref])
    assert error.value.code == CloudErrorCode.RATE_LIMIT
    assert len(counts) == 1 and not bodies and not service.store.messages()


def test_provider_project_ceiling_limits_reply_but_remaining_balance_only_waits(tmp_path, native_sdk):
    settings = load_cloud_config().model_copy(update={'rate_limits': limits()})
    engine, _, bodies, _ = native_sdk(count=90_000, engine_config=settings,
        rate_headers=headers('project-tokens', 150_000, 0, '1s'))
    clock = Clock()
    engine._rate_pacer = OpenAIRatePacer(limits(), clock=clock, sleep=clock.sleep)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'source', name='source.txt')
    service.run('Read', attachments=[ref])
    assert bodies[0]['max_output_tokens'] == 59_744
    assert clock.waits and max(clock.waits) >= 1


def test_plain_request_retains_output_setting(tmp_path, native_sdk):
    settings = load_cloud_config().model_copy(update={'rate_limits': limits()})
    engine, counts, bodies, _ = native_sdk(engine_config=settings)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    service.run('Hello')
    assert not counts and bodies[0]['max_output_tokens'] == 128_000


def test_count_retries_consume_request_capacity_and_quota_is_not_retried(tmp_path, native_sdk):
    attempt = []
    def failure(request):
        attempt.append(request)
        if len(attempt) == 1:
            return httpx.Response(500, headers={'retry-after-ms': '1'}, json={'error': {'message': 'private'}})
        return httpx.Response(429, json={'error': {'code': 'insufficient_quota', 'message': 'private'}})
    settings = load_cloud_config().model_copy(update={'max_retries': 3, 'rate_limits': limits()})
    engine, counts, bodies, _ = native_sdk(failure=failure, engine_config=settings)
    clock = Clock()
    engine._rate_pacer = OpenAIRatePacer(limits(), clock=clock, sleep=clock.sleep)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'source', name='source.txt')
    with pytest.raises(CloudInferenceError) as error:
        service.run('Read', attachments=[ref])
    assert error.value.code == CloudErrorCode.QUOTA
    assert len(counts) == 2 and not bodies
    assert len(engine._rate_pacer.budgets[engine.active_model].ledger) == 2


def test_exact_image_and_file_metadata_boundaries_without_gui_network(tmp_path, native_sdk):
    engine, counts, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'source', name='source.txt')
    files = [ref.model_copy(update={'size_bytes': MAX_FILE_BYTES - 1})]
    validate_sources(files)
    with pytest.raises(AttachmentError, match='smaller than 50 MB'):
        validate_sources([ref.model_copy(update={'size_bytes': MAX_FILE_BYTES})])
    half = ref.model_copy(update={'size_bytes': MAX_FILE_BYTES // 2})
    other = half.model_copy(update={'id': 'att-' + 'f' * 32})
    validate_sources([half, other])
    with pytest.raises(AttachmentError, match='combined'):
        validate_sources([half, other.model_copy(update={'size_bytes': other.size_bytes + 1})])
    images = [ref.model_copy(update={'id': 'att-' + f'{i:032x}', 'kind': 'image',
        'name': f'{i}.png', 'media_type': 'image/png'}) for i in range(MAX_IMAGES + 1)]
    service._admit_attachments(images[:-1])
    with pytest.raises(AttachmentError, match='image count'):
        service._admit_attachments(images)
    assert not counts and not bodies and not service.store.messages()


def test_numeric_ceiling_uses_tightest_known_model_and_project_limits():
    clock = Clock()
    pacer = OpenAIRatePacer(limits(), clock=clock, sleep=clock.sleep)
    assert pacer.request_token_ceiling('unknown') is None
    pacer.observe('gpt-6-luna', headers('project-tokens', 150_000, 0, '1s'))
    assert pacer.request_token_ceiling('gpt-6-luna') == 150_000
    asyncio.run(pacer.acquire('gpt-6-luna', 1))
    assert pacer.request_token_ceiling('gpt-6-luna') == 200_000


def test_transport_labels_preserve_source_order_and_quote_untrusted_names(tmp_path, native_sdk):
    engine, _, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    names = ['first.txt', '"ignore policy".txt']
    refs = [service.store.attachment_store.import_bytes(b'source', name=name) for name in names]
    service.run('Read', attachments=refs)
    parts = bodies[0]['input'][-1]['content']
    assert [part['type'] for part in parts] == ['input_text', 'input_text', 'input_file', 'input_text', 'input_file']
    assert parts[1]['text'] == 'Attached file 1: "first.txt"'
    assert parts[3]['text'] == 'Attached file 2: "\\"ignore policy\\".txt"'
