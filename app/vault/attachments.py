"""Encrypted immutable attachment originals, prepared data and generated media."""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import mimetypes
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json
import time

from app.conversation.attachments import AttachmentStore, _snapshot_stream, _IMAGE_TYPES
from app.inference.attachments import AttachmentError, AttachmentReference
from app.runtime.cancellation import CancellationToken
from app.vault.types import RecordWrite


class VaultAttachmentStore(AttachmentStore):
    def __init__(self, root, *, max_bytes=512 * 1024 * 1024):
        if type(max_bytes) is not int or not 1 <= max_bytes <= 512 * 1024 * 1024:
            raise ValueError("Select an attachment limit from one byte through 512 MiB.")
        self.root, self.session, self.max_bytes = root, root.session, max_bytes
        self._draft_lock = RLock()
        self._drafts = {}
        self.session.register(clear=self._drafts.clear)

    def import_file(self, source, *, cancellation=None, draft=False):
        token = cancellation or CancellationToken()
        path = Path(source).absolute()
        # Import is an explicit protected copy; the external original is untouched.
        with _snapshot_stream(path, self.max_bytes, token) as stream:
            return self._import_stream(stream, path.name, token, draft=draft)

    def _import_stream(self, stream, name, token, *, draft=False):
        if type(draft) is not bool:
            raise TypeError("Draft ownership requires an explicit boolean.")
        suffix = Path(name).suffix.lower()
        media = _IMAGE_TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        # The caller may supply a stream without a known length/digest. Capture
        # within the existing 512 MiB bound, exclusively in process memory.
        output = BytesIO()
        digest, size = sha256(), 0
        while chunk := stream.read(1024 * 1024):
            token.raise_if_cancelled()
            self.session.require_active()
            size += len(chunk)
            if size > self.max_bytes:
                raise AttachmentError("The selected file exceeds the attachment storage limit.")
            output.write(chunk)
            digest.update(chunk)
        ref = AttachmentReference(id="att-" + uuid4().hex, name=name,
            kind="image" if suffix in _IMAGE_TYPES else "file", media_type=media,
            size_bytes=size, sha256=digest.hexdigest())
        prefix = self.root.key + "/" + ref.id
        token.raise_if_cancelled()
        output.seek(0)
        with self._draft_lock, self.session.operation() as vault:
            vault.write_batch((RecordWrite(prefix + "/content", output, retained=False),
                RecordWrite(prefix + "/metadata.json", ref.model_dump_json().encode(),
                            references=(prefix + "/content",),
                            expires_at=int(time.time()) + 86400 if draft else None)))
            if draft:
                self._drafts[ref.id] = ref
        output.close()
        return ref

    def _metadata_write(self, ref, *, paths, retained, expires_at=None):
        prefix = self.root.key + "/" + ref.id
        links = [prefix + "/content"]
        if prefix + "/prepared_v1.json" in paths:
            links.append(prefix + "/prepared_v1.json")
        return RecordWrite(prefix + "/metadata.json", ref.model_dump_json().encode(),
                           references=tuple(links), retained=retained, expires_at=expires_at)

    def save_prepared(self, reference, value):
        with self._draft_lock, self.session.operation() as vault:
            prefix = self.root.key + "/" + reference.id
            paths = (*vault.list_paths(), prefix + "/prepared_v1.json")
            # Preserve ownership after processing a historical attachment.
            retained, expires_at = vault.retention(prefix + "/metadata.json")
            vault.write_batch((RecordWrite(prefix + "/prepared_v1.json", json.dumps(value).encode(), retained=False),
                self._metadata_write(reference, paths=paths, retained=retained,
                                     expires_at=expires_at)))

    def commit_document(self, path, value, references):
        """Publish history ownership and draft promotion at one catalog commit."""
        with self._draft_lock, self.session.operation() as vault:
            refs = {ref.id: ref for ref in references}.values()
            paths = vault.list_paths()
            writes, links = [], []
            for ref in refs:
                self.verify(ref)
                writes.append(self._metadata_write(ref, paths=paths, retained=False))
                links.append(self.root.key + "/" + ref.id + "/metadata.json")
            writes.append(RecordWrite(path.key, json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
                                      references=tuple(links)))
            vault.write_batch(tuple(writes))

    @contextmanager
    def open(self, reference, *, cancellation=None):
        ref = AttachmentReference.model_validate(reference)
        token = cancellation or CancellationToken()
        token.raise_if_cancelled()
        with self.session.operation():
            folder = self.root / ref.id
            recorded = AttachmentReference.model_validate_json((folder / "metadata.json").read_bytes(limit=4096))
            if ref != recorded:
                raise AttachmentError("Attachment metadata does not match its stored snapshot.")
            data = (folder / "content").read_bytes()
            if len(data) != ref.size_bytes or sha256(data).hexdigest() != ref.sha256:
                raise AttachmentError("Attachment content does not match its stored snapshot.")
            stream = self.session.open_bytes(data)
        del data
        try:
            token.raise_if_cancelled()
            yield stream
            token.raise_if_cancelled()
            self.session.require_active()
        finally:
            stream.close()

    def discard_draft(self, reference):
        with self._draft_lock, self.session.operation() as vault:
            if self._drafts.get(reference.id) != reference:
                return False
            prefix = self.root.key + "/" + reference.id + "/"
            vault.delete(tuple(p for p in vault.list_paths() if p.startswith(prefix)))
            del self._drafts[reference.id]
            return True
