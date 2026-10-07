"""Immutable, app-owned snapshots. Only small references enter conversation JSON."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, nullcontext
from hashlib import sha256
from io import BytesIO
import mimetypes
import os
from pathlib import Path
import stat
from uuid import uuid4

from app.inference.attachments import AttachmentError, AttachmentReference
from app.runtime.cancellation import CancellationToken
from app.state.storage import JsonStore


_CHUNK_BYTES = 1024 * 1024
DEFAULT_SNAPSHOT_LIMIT = 512 * 1024 * 1024
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}


def _ordinary_components(path: Path) -> None:
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AttachmentError("Attachment storage cannot follow filesystem links.")


@contextmanager
def _snapshot_stream(path, limit, cancellation):
    if os.name == "nt":
        from app.execution.windows_filesystem import open_file_snapshot, pinned_parent
        with pinned_parent(path, cancellation), open_file_snapshot(path, limit, cancellation) as value:
            yield value[0]
    else:
        _ordinary_components(path)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise AttachmentError("Select a regular file within the attachment storage limit.")
            yield stream


class AttachmentStore:
    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_SNAPSHOT_LIMIT):
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("The attachment storage limit must be a positive integer.")
        self.root = Path(root).absolute()
        self.max_bytes = max_bytes

    @contextmanager
    def _pinned_root(self, cancellation, *, create=False):
        _ordinary_components(self.root)
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            from app.execution.windows_filesystem import pinned_parent
            pin = pinned_parent(self.root / "guard", cancellation)
        else:
            pin = nullcontext()
        with pin:
            _ordinary_components(self.root)
            yield

    def import_file(self, source: Path, *, cancellation=None) -> AttachmentReference:
        """Snapshot the selected file, not a live pointer to its original location."""
        token = cancellation or CancellationToken()
        path = Path(source).absolute()
        token.raise_if_cancelled()
        try:
            with _snapshot_stream(path, self.max_bytes, token) as stream:
                return self._import_stream(stream, path.name, token)
        except OSError as exc:
            raise AttachmentError("The selected file could not be copied safely.") from exc
        except ValueError as exc:
            if isinstance(exc, AttachmentError):
                raise
            raise AttachmentError("The selected file exceeds the attachment storage limit.") from exc

    def import_bytes(self, data: bytes, *, name: str, cancellation=None) -> AttachmentReference:
        """Accept already captured clipboard bytes using the same durable format."""
        if not isinstance(data, bytes):
            raise TypeError("Attachment snapshots require bytes.")
        return self._import_stream(BytesIO(data), name, cancellation or CancellationToken())

    def _import_stream(self, stream, name, token):
        suffix = Path(name).suffix.lower()
        media_type = _IMAGE_TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        # Type is an advisory filename classification; decoding belongs to the processing phase.
        reference = AttachmentReference(id="att-" + uuid4().hex, name=name,
            kind="image" if suffix in _IMAGE_TYPES else "file", media_type=media_type,
            size_bytes=0, sha256="0" * 64)
        token.raise_if_cancelled()
        try:
            with self._pinned_root(token, create=True):
                staging = self.root / (".pending-" + uuid4().hex)
                staging.mkdir()
                try:
                    digest, size = sha256(), 0
                    with (staging / "content").open("xb") as output:
                        while chunk := stream.read(_CHUNK_BYTES):
                            token.raise_if_cancelled()
                            size += len(chunk)
                            if size > self.max_bytes:
                                raise AttachmentError("The selected file exceeds the attachment storage limit.")
                            output.write(chunk)
                            digest.update(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    reference = reference.model_copy(update={"size_bytes": size, "sha256": digest.hexdigest()})
                    JsonStore(staging / "metadata.json").save(reference.model_dump(mode="json"))
                    token.raise_if_cancelled()
                    # Publish the blob and its manifest together; no half-imported reference is returned.
                    staging.rename(self.root / reference.id)
                    return reference
                finally:
                    if staging.exists():
                        for child in staging.iterdir():
                            child.unlink()
                        staging.rmdir()
        except OSError as exc:
            raise AttachmentError("Attachment storage failed. The message was not sent.") from exc

    @contextmanager
    def open(self, reference: AttachmentReference, *, cancellation=None):
        """Yield a verified, read-only snapshot held open through provider consumption."""
        reference = AttachmentReference.model_validate(reference)
        token = cancellation or CancellationToken()
        token.raise_if_cancelled()
        with ExitStack() as stack:
            try:
                stack.enter_context(self._pinned_root(token))
                folder = self.root / reference.id
                with _snapshot_stream(folder / "metadata.json", 4096, token) as metadata:
                    recorded = AttachmentReference.model_validate_json(metadata.read(4097))
                if recorded != reference:
                    raise AttachmentError("Attachment metadata does not match its stored snapshot.")
                stream = stack.enter_context(_snapshot_stream(folder / "content", self.max_bytes, token))
                digest, size = sha256(), 0
                while chunk := stream.read(_CHUNK_BYTES):
                    token.raise_if_cancelled()
                    size += len(chunk)
                    if size > self.max_bytes or size > reference.size_bytes:
                        raise AttachmentError("The stored attachment has changed.")
                    digest.update(chunk)
                if size != reference.size_bytes or digest.hexdigest() != reference.sha256:
                    raise AttachmentError("The stored attachment has changed.")
                stream.seek(0)
                token.raise_if_cancelled()
            except (OSError, ValueError) as exc:
                if isinstance(exc, AttachmentError):
                    raise
                raise AttachmentError("The stored attachment is missing or unreadable. Chat history was preserved.") from exc
            # Consumer errors belong to the adapter, not to storage validation.
            yield stream

    def verify(self, reference: AttachmentReference, *, cancellation=None) -> None:
        with self.open(reference, cancellation=cancellation):
            pass
