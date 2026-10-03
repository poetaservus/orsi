"""Instruction-only skill definitions and content-free parsing/loading failures."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    description: str
    instructions: str
    root_path: Path
    source_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillParseErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    MISSING_FRONTMATTER = "missing_frontmatter"
    UNCLOSED_FRONTMATTER = "unclosed_frontmatter"
    INVALID_YAML = "invalid_yaml"
    UNSUPPORTED_YAML = "unsupported_yaml"
    DUPLICATE_FIELD = "duplicate_field"
    INVALID_METADATA = "invalid_metadata"
    MISSING_FIELD = "missing_field"
    INVALID_FIELD = "invalid_field"
    EMPTY_INSTRUCTIONS = "empty_instructions"


class SkillParseError(ValueError):
    """A stable code and safe message, never an excerpt of untrusted content."""

    def __init__(
        self,
        code: SkillParseErrorCode,
        message: str,
        *,
        source_path: Path | None = None,
        field: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.source_path = source_path
        self.field = field
        self.line = line
        self.column = column


class SkillLoadErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_ROOT = "invalid_root"
    OUTSIDE_ROOT = "outside_root"
    UNSAFE_PATH = "unsafe_path"
    FILE_NOT_FOUND = "file_not_found"
    NOT_FILE = "not_file"
    TOO_LARGE = "too_large"
    INVALID_ENCODING = "invalid_encoding"
    IO_ERROR = "io_error"
    UNSUPPORTED_PLATFORM = "unsupported_platform"


class SkillLoadError(ValueError):
    """Filesystem rejection with a stable code and no file-content excerpts."""

    def __init__(
        self,
        code: SkillLoadErrorCode,
        message: str,
        *,
        source_path: Path | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.source_path = source_path
