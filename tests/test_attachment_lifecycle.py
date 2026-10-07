"""Draft ownership, durable recovery and source-preserving context pressure."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
from copy import deepcopy
from threading import Event
import httpx

import pytest

from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.conversation.attachments import AttachmentStore
from app.conversation.attachment_processing import AttachmentProcessor
from app.conversation.local_documents import LocalDocumentCounter, LocalDocuments
from app.conversation.orchestrator import ConversationService
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore, TurnHistoryError
from app.inference.attachments import AttachmentError
from app.inference.cloud_errors import CloudErrorCode, CloudInferenceError
from app.inference.completion import IncompleteResponseError
from app.inference.hybrid import HybridInferenceEngine
from app.ui.worker import ConversationWorker
from tests.test_cloud_attachment_input import native_sdk, user
from tests.test_context_recovery import exchange
from tests.test_local_document_input import DocumentRecorder
from tests.test_cloud_attachment_live import word_document
from tests.test_openai_phase1 import response, sse_response
from tests.test_openai_streaming import make_engine, Stream, events, streaming_response


def test_abandoned_owned_draft_removes_copy_and_cache_but_preserves_original(tmp_path):
    source = tmp_path / 'original.txt'; source.write_bytes(b'Original source')
    store = AttachmentStore(tmp_path / 'attachments')
    ref = store.import_file(source, draft=True)
    AttachmentProcessor(store).prepare(ref)
    assert store.discard_draft(ref)
    assert not (store.root / ref.id).exists()
    assert source.read_bytes() == b'Original source'
    assert not store.discard_draft(ref)


def test_unowned_shared_sources_are_never_discarded(tmp_path):
    store = AttachmentStore(tmp_path / 'attachments')
    ref = store.import_bytes(b'Historical source', name='history.txt')
    assert not store.discard_draft(ref)
    store.verify(ref)


def test_reopened_store_commit_protects_draft_owned_by_original_store(tmp_path):
    (tmp_path / 'alias').mkdir()
    owner = AttachmentStore(tmp_path / 'alias' / '..' / 'attachments')
    ref = owner.import_bytes(b'Shared root', name='source.txt', draft=True)
    history = ConversationStore(tmp_path / 'chat.json')
    history.begin_turn('Read', attachments=[ref])
    assert not owner.discard_draft(ref)
    owner.verify(ref)


@pytest.mark.parametrize('tamper', ['manifest', 'extra', 'size'])
def test_unexpected_draft_state_is_preserved(tmp_path, tamper):
    store = AttachmentStore(tmp_path / 'attachments')
    ref = store.import_bytes(b'Original', name='source.txt', draft=True)
    folder = store.root / ref.id
    if tamper == 'manifest':
        (folder / 'metadata.json').write_text('{}')
    elif tamper == 'extra':
        (folder / 'unexpected.txt').write_text('Preserve this')
    else:
        (folder / 'content').write_bytes(b'Changed length')
    assert not store.discard_draft(ref)
    assert (folder / 'content').exists()


def test_commit_transfers_draft_ownership_and_archives_keep_source(tmp_path):
    history = ConversationStore(tmp_path / 'chat.json')
    store = history.attachment_store
    ref = store.import_bytes(b'Archive evidence', name='source.txt', draft=True)
    turn = history.begin_turn('Read', attachments=[ref])
    assert not store.discard_draft(ref)
    history.finish_turn(turn, AgentRunResult(status=AgentRunStatus.COMPLETED,
        assistant_text='Done', steps=1, capability_calls=0, protocol_failures=0), 'Done')
    history.new_session(preserve_history=True)
    restored = ConversationStore(next((tmp_path / 'archives').glob('*.json')))
    assert restored.visible_messages()[0].attachments == (ref,)
    restored.attachment_store.verify(ref)
    assert not restored.attachment_store.discard_draft(ref)


def test_failed_save_does_not_transfer_ownership(tmp_path, monkeypatch):
    history = ConversationStore(tmp_path / 'chat.json')
    ref = history.attachment_store.import_bytes(b'Draft', name='source.txt', draft=True)
    def fail(*args):
        raise OSError('Synthetic persistence failure')
    monkeypatch.setattr(history._store, 'save', fail)
    with pytest.raises(TurnHistoryError):
        history.begin_turn('Read', attachments=[ref])
    assert not history.messages()
    assert history.attachment_store.discard_draft(ref)


def test_abandonment_cannot_race_successful_history_commit(tmp_path, monkeypatch):
    history = ConversationStore(tmp_path / 'chat.json')
    ref = history.attachment_store.import_bytes(b'Protected', name='source.txt', draft=True)
    committing, release = Event(), Event()
    actual = history._store.save
    def save(value):
        committing.set()
        assert release.wait(5)
        actual(value)
    monkeypatch.setattr(history._store, 'save', save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(history.begin_turn, 'Read', attachments=[ref])
        assert committing.wait(3)
        deletion = pool.submit(history.attachment_store.discard_draft, ref)
        assert not deletion.done()
        release.set()
        assert pending.result(timeout=3) == 'turn-1'
        assert deletion.result(timeout=3) is False
    history.attachment_store.verify(ref)


@pytest.mark.parametrize('kind', ['cancelled', 'incomplete', 'crashed'])
def test_stopped_and_crashed_turns_reopen_sources_without_replaying_calls(tmp_path, kind):
    history = ConversationStore(tmp_path / 'chat.json')
    ref = history.attachment_store.import_bytes(b'Retained evidence', name='source.txt', draft=True)
    turn = history.begin_turn('Read', attachments=[ref])
    if kind != 'crashed':
        history.finish_turn(turn, AgentRunResult(status=AgentRunStatus(kind), steps=1,
            capability_calls=0, protocol_failures=0, message='Synthetic stop'))
    reopened = ConversationStore(history.path)
    assert reopened.turns()[0].outcome is not None
    assert reopened.visible_messages()[0].attachments == (ref,)
    model = DocumentRecorder()
    service = ConversationService(model, reopened)
    assert service.run('Recall the source') == 'Document reply'
    assert any('Retained evidence' in m.get('content', '') for m in model.requests[-1][0])
    assert not any(m.get('role') == 'capability' for m in model.requests[-1][0])
    assert not history.attachment_store.discard_draft(ref)


@pytest.mark.parametrize('cloud', [False, True])
def test_context_recovery_projects_results_but_keeps_source_group_intact(tmp_path, native_sdk, cloud):
    store = AttachmentStore(tmp_path / 'sources')
    ref = store.import_bytes(b'Exact attachment source evidence', name='source.txt')
    if cloud:
        engine, counts, _, _ = native_sdk()
        engine.set_attachment_store(store)
        engine.prepare_attachment_context([user(ref)])
        engine.context_length = 12_000
        engine.max_response_tokens = 512
        counter = engine
    else:
        engine = DocumentRecorder()
        engine.context_length = 12_000
        engine.max_response_tokens = 512
        counter = LocalDocumentCounter(engine, LocalDocuments(store))
    messages = [{'role': 'system', 'content': 'Keep policy'}, user(ref),
        *exchange('source-turn', 'Result ' * 20_000)]
    before = deepcopy(messages)
    recovered = recover_context_request(counter, messages)
    assert recovered.budget.fits and recovered.projected_results == 1
    assert recovered.messages[:3] == before[:3]
    assert messages == before
    assert 'attachments' in recovered.messages[1] and 'source-turn' in str(recovered.messages[-1])
    assert recovered.messages[-1]['result']['metadata']['context_projection']['complete'] is False
    assert recovered.messages[1]['attachments'] == user(ref)['attachments']
    if cloud:
        assert len(counts) == 1  # Recovery/meter adds no provider calls.


def test_unfitting_protected_sources_are_explicit_not_excerpted(tmp_path):
    store = AttachmentStore(tmp_path / 'sources')
    ref = store.import_bytes(b'Full source ' * 4000, name='source.txt')
    engine = DocumentRecorder(); engine.context_length = 1024
    messages = [{'role': 'system', 'content': 'Policy'}, user(ref)]
    recovered = recover_context_request(LocalDocumentCounter(engine, LocalDocuments(store)), messages)
    assert not recovered.budget.fits and recovered.messages == messages


def test_preflight_rejection_reports_restorable_draft_then_retry_uses_same_snapshot(tmp_path, native_sdk):
    engine, counts, bodies, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'Evidence', name='source.txt', draft=True)
    original = engine.prepare_attachment_context
    def reject(*args, **kwargs):
        raise CloudInferenceError('Synthetic preflight failure', code=CloudErrorCode.RATE_LIMIT)
    engine.prepare_attachment_context = reject
    worker = ConversationWorker(service, 'Read', attachments=[ref])
    rejected, admitted, failed = [], [], []
    worker.draft_rejected.connect(lambda: rejected.append(True))
    worker.admitted.connect(lambda: admitted.append(True))
    worker.failed.connect(failed.append)
    worker.run()
    assert rejected == [True] and not admitted and failed and not service.store.messages()
    assert not counts and not bodies
    engine.prepare_attachment_context = original
    next_worker = ConversationWorker(service, 'Read', attachments=[ref])
    next_worker.admitted.connect(lambda: admitted.append(True))
    next_worker.run()
    assert admitted == [True] and len(bodies) == 1
    assert service.store.visible_messages()[0].attachments == (ref,)
    assert not service.store.attachment_store.discard_draft(ref)


def test_final_provider_context_overflow_has_context_status_and_retained_source(tmp_path, native_sdk, monkeypatch):
    engine, _, _, _ = native_sdk()
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'Evidence', name='source.txt', draft=True)
    def overflow(*args, **kwargs):
        raise CloudInferenceError('Synthetic final context rejection', code=CloudErrorCode.CONTEXT_OVERFLOW)
    monkeypatch.setattr(engine, 'respond_with_attachments', overflow)
    with pytest.raises(CloudInferenceError):
        service.run('Read', attachments=[ref])
    assert service.store.turns()[0].outcome.status == AgentRunStatus.CONTEXT_LIMIT
    assert service.store.visible_messages()[0].attachments == (ref,)
    assert not service.store.attachment_store.discard_draft(ref)


@pytest.mark.parametrize('stage', ['count', 'stream'])
def test_cancel_native_source_request_releases_transport_and_allows_explicit_retry(tmp_path, make_engine, stage):
    waiting, count_closed = Event(), Event()
    bodies, counts = [], []
    stream = Stream(events(response('partial source answer'), terminal=False), hold=True)
    async def handle(request):
        body = json.loads(request.content)
        if request.url.path.endswith('/input_tokens'):
            counts.append(body)
            if stage == 'count' and len(counts) == 1:
                waiting.set()
                try:
                    await asyncio.Future()
                finally:
                    count_closed.set()
            return httpx.Response(200, json={'object': 'response.input_tokens', 'input_tokens': 100})
        bodies.append(body)
        if stage == 'stream' and len(bodies) == 1:
            return streaming_response(stream)
        return sse_response(response('Done'))
    engine = make_engine(handle, max_retries=2)
    service = ConversationService(engine, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(b'Exact source', name='source.txt', draft=True)
    admitted = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.run, 'Read', attachments=[ref],
            admission_observer=lambda: admitted.append(True))
        try:
            assert (waiting if stage == 'count' else stream.waiting).wait(3)
        finally:
            service.cancel_current_task()
        with pytest.raises(IncompleteResponseError):
            pending.result(timeout=3)
    assert engine._request_cancellation is None and engine._text_observer is None
    if stage == 'count':
        assert count_closed.is_set() and not admitted and not service.store.messages() and not bodies
        assert service.run('Read', attachments=[ref]) == 'Done'
    else:
        assert stream.closed.is_set() and admitted == [True] and len(bodies) == 1
        assert service.store.turns()[0].outcome.status == AgentRunStatus.CANCELLED
        assert service.store.visible_messages()[0].attachments == (ref,)
        assert service.run('Continue using the source') == 'Done'
    parts = [part for item in bodies[-1]['input'] if isinstance(item.get('content'), list)
        for part in item['content'] if part['type'] == 'input_file']
    assert len(parts) == 1 and parts[0]['filename'] == 'source.txt'
    assert not service.store.attachment_store.discard_draft(ref)
    runner, client = engine._runner, engine._client
    engine.close()
    assert client.is_closed() and not runner._thread.is_alive() and not engine.has_api_key


def test_cloud_local_cloud_switch_preserves_reference_and_document_contents(tmp_path, native_sdk):
    cloud, _, bodies, _ = native_sdk()
    local = DocumentRecorder()
    inference = HybridInferenceEngine(local=local, cloud=cloud, default_mode='cloud')
    service = ConversationService(inference, ConversationStore(tmp_path / 'chat.json'))
    ref = service.store.attachment_store.import_bytes(word_document(), name='source.docx', draft=True)
    assert service.run('Read', attachments=[ref]) == 'Done'
    inference.set_mode('local')
    assert service.run('Recall the same source') == 'Document reply'
    assert any('Word acceptance code: 164' in m.get('content', '') for m in local.requests[-1][0])
    assert service.store.visible_messages()[0].attachments == (ref,)
    inference.set_mode('cloud')
    assert service.run('Recall it again') == 'Done'
    parts = [part for item in bodies[-1]['input'] if isinstance(item.get('content'), list)
        for part in item['content'] if part['type'] == 'input_file']
    assert len(parts) == 1 and parts[0]['filename'] == 'source.docx'
    service.store.attachment_store.verify(ref)
    assert not service.active_skill and not service.store.attachment_store.discard_draft(ref)
