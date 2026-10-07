from pathlib import Path

import pytest

from app.conversation.attachments import AttachmentStore
from app.inference.attachments import AttachmentError
from app.runtime.cancellation import CancellationSource, TaskCancelled


def denial(code):
    error = PermissionError("snapshot publication denied")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
def test_publication_retries_same_flushed_snapshot_and_preserves_source(tmp_path, monkeypatch, code):
    store = AttachmentStore(tmp_path / "attachments")
    source = CancellationSource()
    rename = Path.rename
    attempts, delays = [], []
    monkeypatch.setattr(source.token, "wait", delays.append)
    def blocked(self, target):
        attempts.append((self, target, (self / "content").read_bytes(), (self / "metadata.json").read_bytes()))
        assert not target.exists()
        if len(attempts) < 3:
            raise denial(code)
        return rename(self, target)
    monkeypatch.setattr(Path, "rename", blocked)
    ref = store.import_bytes(b"exact document bytes", name="file.txt", cancellation=source.token)
    assert delays == [0.02, 0.04] and len(attempts) == 3
    assert all(attempt == attempts[0] for attempt in attempts)
    assert sorted(p.name for p in store.root.iterdir()) == [ref.id]
    with store.open(ref) as stream:
        assert stream.read() == b"exact document bytes"


def test_permanent_publication_denial_is_bounded_and_removes_only_pending_copy(tmp_path, monkeypatch):
    store = AttachmentStore(tmp_path / "attachments")
    earlier = store.import_bytes(b"previous", name="earlier.txt")
    source = CancellationSource()
    attempts, delays = [], []
    monkeypatch.setattr(source.token, "wait", delays.append)
    def blocked(self, target):
        attempts.append((self, target))
        raise denial(5)
    monkeypatch.setattr(Path, "rename", blocked)
    with pytest.raises(AttachmentError, match="storage failed"):
        store.import_bytes(b"new", name="new.txt", cancellation=source.token)
    assert len(attempts) == 8 and sum(delays) <= 0.91
    assert all(attempt == attempts[0] for attempt in attempts)
    assert sorted(p.name for p in store.root.iterdir()) == [earlier.id]
    store.verify(earlier)


@pytest.mark.parametrize("error", [PermissionError("unclassified denial"), FileExistsError("destination exists")])
def test_unrelated_publish_errors_never_retry_or_return_a_reference(tmp_path, monkeypatch, error):
    store = AttachmentStore(tmp_path / "attachments")
    source = CancellationSource()
    monkeypatch.setattr(source.token, "wait", lambda delay: pytest.fail("Unexpected retry"))
    monkeypatch.setattr(Path, "rename", lambda *args: (_ for _ in ()).throw(error))
    with pytest.raises(AttachmentError):
        store.import_bytes(b"new", name="file.txt", cancellation=source.token)
    assert not list(store.root.iterdir())


def test_cancellation_during_retry_prevents_publication_and_cleans_pending_copy(tmp_path, monkeypatch):
    store = AttachmentStore(tmp_path / "attachments")
    source = CancellationSource()
    attempts = []
    def blocked(self, target):
        attempts.append((self, target))
        raise denial(32)
    monkeypatch.setattr(Path, "rename", blocked)
    monkeypatch.setattr(source.token, "wait", lambda delay: source.cancel())
    with pytest.raises(TaskCancelled):
        store.import_bytes(b"cancel", name="file.txt", cancellation=source.token)
    assert len(attempts) == 1 and not list(store.root.iterdir())
