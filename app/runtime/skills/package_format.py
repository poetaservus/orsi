"""Pure v1 reference validation; no file access, link expansion or activation."""
from dataclasses import dataclass
from pathlib import PureWindowsPath
import re


MAX_REFERENCE_FILES = 16
MAX_REFERENCE_BYTES = 16 * 1024
MAX_TOTAL_REFERENCE_BYTES = 64 * 1024
MAX_REFERENCE_DEPTH = 4
MANIFEST_NAME = ".orsi-package.json"
MAX_MANIFEST_BYTES = 16 * 1024
_COMPONENT = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")


@dataclass(frozen=True, slots=True)
class ReferenceFile:
    path: str
    data: bytes


def validate_reference_path(path: str) -> None:
    if not isinstance(path, str) or len(path) > 240:
        raise ValueError("Invalid reference path.")
    parts = path.split("/")
    if (len(parts) < 2 or parts[0] != "references" or not parts[-1].endswith(".md")
            or len(parts) - 2 > MAX_REFERENCE_DEPTH):
        raise ValueError("Invalid reference path.")
    for part in parts:
        if (not _COMPONENT.fullmatch(part) or part in (".", "..")
                or part.endswith(".") or PureWindowsPath(part).is_reserved()):
            raise ValueError("Invalid reference path.")


def validate_references(references: tuple[ReferenceFile, ...]) -> None:
    if not isinstance(references, tuple) or len(references) > MAX_REFERENCE_FILES:
        raise ValueError("Reference limit exceeded.")
    total, names, components = 0, set(), {}
    for reference in references:
        if not isinstance(reference, ReferenceFile) or not isinstance(reference.data, bytes):
            raise ValueError("Invalid reference snapshot.")
        validate_reference_path(reference.path)
        if reference.path.casefold() in names:
            raise ValueError("Ambiguous reference paths.")
        names.add(reference.path.casefold())
        # Reject differently cased directories too, before a Windows collision.
        parts = reference.path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            previous = components.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise ValueError("Ambiguous reference paths.")
        if len(reference.data) > MAX_REFERENCE_BYTES:
            raise ValueError("Reference limit exceeded.")
        total += len(reference.data)
        text = reference.data.decode("utf-8-sig")
        if not text.strip() or any(ord(c) < 32 and c not in "\t\n\r\f" or ord(c) == 127 for c in text):
            raise ValueError("References must be nonempty UTF-8 text.")
    if total > MAX_TOTAL_REFERENCE_BYTES:
        raise ValueError("Reference limit exceeded.")
    for name in names:
        if any("/".join(name.split("/")[:index]) in names for index in range(1, len(name.split("/")))):
            raise ValueError("Reference file/directory collision.")
