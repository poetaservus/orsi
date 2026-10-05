"""Revocable package authority and bounded excerpts, independent of storage/UI."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from threading import RLock
from typing import Protocol
from uuid import uuid4

from app.runtime.cancellation import CancellationToken
from app.runtime.skills.contracts import SkillDefinition
from app.runtime.skills.loader import MAX_SKILL_SIZE
from app.runtime.skills.package_format import (ReferenceFile, validate_references, validate_reference_path,
                                               MAX_REFERENCE_FILES, MAX_REFERENCE_BYTES, MAX_TOTAL_REFERENCE_BYTES)
from app.runtime.skills.parser import parse_skill


DEFAULT_EXCERPT_BYTES = 2048
MAX_EXCERPT_BYTES = 4096
DEFAULT_EXCERPT_LINES = 40
MAX_EXCERPT_LINES = 80


class ReferenceErrorCode(StrEnum):
    DISABLED = "disabled"
    STALE = "stale"
    MISSING = "missing"
    UNSAFE = "unsafe"
    LIMIT_EXCEEDED = "limit_exceeded"
    INVALID_PACKAGE = "invalid_package"
    INVALID_REQUEST = "invalid_request"
    INACCESSIBLE = "inaccessible"


_MESSAGES = {
    ReferenceErrorCode.DISABLED: "Skill reference reading is unavailable for this scope.",
    ReferenceErrorCode.STALE: "The active skill package changed; refresh it before reading references.",
    ReferenceErrorCode.MISSING: "The requested reference is not in the active package inventory.",
    ReferenceErrorCode.UNSAFE: "The skill reference path or storage is unsafe.",
    ReferenceErrorCode.LIMIT_EXCEEDED: "The skill package exceeds reference limits.",
    ReferenceErrorCode.INVALID_PACKAGE: "The skill package contains invalid reference data.",
    ReferenceErrorCode.INVALID_REQUEST: "The reference excerpt request is invalid.",
    ReferenceErrorCode.INACCESSIBLE: "The skill package could not be read safely.",
}


class ReferenceReadError(ValueError):
    def __init__(self, code: ReferenceErrorCode):
        self.code = code
        super().__init__(_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class PackageSnapshot:
    """Storage supplies bounded bytes and an opaque, stable package identity.

    A future unlocked vault can implement the same protocol. Implementations must
    reject redirects and replacement while obtaining a snapshot, support
    cancellation and use fixed ReferenceReadError messages for storage failures.
    """
    identity: str
    main: bytes = field(repr=False)
    references: tuple[ReferenceFile, ...] = field(repr=False)


class ReferenceStorage(Protocol):
    def snapshot(self, skill: SkillDefinition, cancellation: CancellationToken) -> PackageSnapshot: ...


@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ReferenceBinding:
    skill_name: str
    package_id: str
    version: str
    resources: tuple[ReferenceInfo, ...]
    _authority: str = field(repr=False)

    def inventory(self) -> dict:
        return {"skill": self.skill_name, "package_id": self.package_id, "version": self.version,
                "resources": [{"path": r.path, "size_bytes": r.size_bytes, "sha256": r.sha256}
                              for r in self.resources]}


def _validated_version(snapshot: PackageSnapshot, skill: SkillDefinition) -> str:
    if (not isinstance(snapshot, PackageSnapshot) or not isinstance(snapshot.identity, str)
            or not snapshot.identity or len(snapshot.identity) > 256
            or not isinstance(snapshot.main, bytes)):
        raise ReferenceReadError(ReferenceErrorCode.INVALID_PACKAGE)
    if len(snapshot.main) > MAX_SKILL_SIZE:
        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
    if (isinstance(snapshot.references, tuple)
            and all(isinstance(r, ReferenceFile) and isinstance(r.data, bytes) for r in snapshot.references)
            and (len(snapshot.references) > MAX_REFERENCE_FILES
                 or any(len(r.data) > MAX_REFERENCE_BYTES for r in snapshot.references)
                 or sum(len(r.data) for r in snapshot.references) > MAX_TOTAL_REFERENCE_BYTES)):
        raise ReferenceReadError(ReferenceErrorCode.LIMIT_EXCEEDED)
    try:
        validate_references(snapshot.references)
        current = parse_skill(snapshot.main.decode("utf-8"), root_path=skill.root_path,
                              source_path=skill.source_path)
    except (ValueError, TypeError):
        raise ReferenceReadError(ReferenceErrorCode.INVALID_PACKAGE) from None
    if current != skill:
        raise ReferenceReadError(ReferenceErrorCode.STALE)
    digest = sha256(b"orsi-skill-package-v1\0")
    files = (("SKILL.md", snapshot.main),) + tuple((r.path, r.data) for r in
                                                  sorted(snapshot.references, key=lambda r: r.path))
    for path, data in files:
        for item in (path.encode("ascii"), data):
            digest.update(len(item).to_bytes(8, "big"))
            digest.update(item)
    return digest.hexdigest()


class SkillReferenceReader:
    """Application-owned reader; model arguments cannot activate a package.

    Activate only after selecting a valid skill. Deactivate on switch, removal,
    reset, disabled tools or shutdown. Every activation revokes old bindings,
    including identical packages. Reads validate the entire bounded snapshot;
    no reference-body cache survives a call. One instance belongs to one scope.
    """
    def __init__(self, storage: ReferenceStorage):
        self._storage = storage
        self._lock = RLock()
        self._active: tuple[ReferenceBinding, SkillDefinition] | None = None

    def deactivate(self) -> None:
        with self._lock:
            self._active = None

    def validate(self, binding: ReferenceBinding, cancellation: CancellationToken) -> None:
        """Recheck authority/version without returning or caching document text."""
        with self._lock:
            self._current_snapshot(binding, binding.version, cancellation)

    def _current_snapshot(self, binding, version, cancellation):
        cancellation.raise_if_cancelled()
        if self._active is None:
            raise ReferenceReadError(ReferenceErrorCode.DISABLED)
        if binding != self._active[0] or version != binding.version:
            raise ReferenceReadError(ReferenceErrorCode.STALE)
        try:
            snapshot = self._storage.snapshot(self._active[1], cancellation)
            version_now = _validated_version(snapshot, self._active[1]) if self._active is not None else None
        except ReferenceReadError:
            if self._active is not None and self._active[0] == binding:
                self._active = None
            raise
        if self._active is None or self._active[0] != binding:
            raise ReferenceReadError(ReferenceErrorCode.STALE)
        if (sha256(snapshot.identity.encode("utf-8")).hexdigest() != binding.package_id
                or version_now != binding.version):
            self._active = None
            raise ReferenceReadError(ReferenceErrorCode.STALE)
        cancellation.raise_if_cancelled()
        return snapshot

    def activate(self, skill: SkillDefinition, cancellation: CancellationToken) -> ReferenceBinding:
        with self._lock:
            self._active = None  # Failed activation must not retain earlier authority.
            cancellation.raise_if_cancelled()
            skill = deepcopy(skill)
            snapshot = self._storage.snapshot(skill, cancellation)
            version = _validated_version(snapshot, skill)
            cancellation.raise_if_cancelled()
            binding = ReferenceBinding(skill.name, sha256(snapshot.identity.encode("utf-8")).hexdigest(),
                                       version, tuple(ReferenceInfo(r.path, len(r.data), sha256(r.data).hexdigest())
                                                      for r in sorted(snapshot.references, key=lambda r: r.path)),
                                       uuid4().hex)
            self._active = (binding, skill)
            return binding

    def read(self, binding: ReferenceBinding, path: str, *, version: str,
             cancellation: CancellationToken, offset: int = 0,
             max_bytes: int = DEFAULT_EXCERPT_BYTES, max_lines: int = DEFAULT_EXCERPT_LINES) -> dict:
        with self._lock:
            cancellation.raise_if_cancelled()
            if self._active is None:
                raise ReferenceReadError(ReferenceErrorCode.DISABLED)
            if binding != self._active[0] or version != binding.version:
                raise ReferenceReadError(ReferenceErrorCode.STALE)
            try:
                validate_reference_path(path)
            except ValueError:
                raise ReferenceReadError(ReferenceErrorCode.UNSAFE) from None
            if path not in {r.path for r in binding.resources}:
                raise ReferenceReadError(ReferenceErrorCode.MISSING)
            if (type(offset) is not int or offset < 0 or type(max_bytes) is not int
                    or not 4 <= max_bytes <= MAX_EXCERPT_BYTES or type(max_lines) is not int
                    or not 1 <= max_lines <= MAX_EXCERPT_LINES):
                raise ReferenceReadError(ReferenceErrorCode.INVALID_REQUEST)
            snapshot = self._current_snapshot(binding, version, cancellation)
            raw = next(r.data for r in snapshot.references if r.path == path)
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            try:
                if offset > len(raw):
                    raise ValueError
                raw[:offset].decode("utf-8")  # Continuation must begin at a code-point boundary.
            except ValueError:
                raise ReferenceReadError(ReferenceErrorCode.INVALID_REQUEST) from None
            text = raw[offset:offset + max_bytes].decode("utf-8", errors="ignore")
            text = "".join(text.splitlines(keepends=True)[:max_lines])
            end = offset + len(text.encode("utf-8"))
            cancellation.raise_if_cancelled()
            if self._active is None or self._active[0] != binding:
                raise ReferenceReadError(ReferenceErrorCode.STALE)
            return {"skill": binding.skill_name, "package_id": binding.package_id,
                    "version": binding.version, "path": path,
                    "sha256": next(r.sha256 for r in binding.resources if r.path == path),
                    "text": text, "offset": offset, "end_offset": end,
                    "bytes_returned": end - offset, "total_text_bytes": len(raw),
                    "has_more": end < len(raw), "next_offset": end if end < len(raw) else None,
                    "complete_document": offset == 0 and end == len(raw),
                    "content_is_untrusted": True}
