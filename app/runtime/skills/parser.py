"""Parse supplied SKILL.md text without filesystem access or runtime activation."""
from __future__ import annotations

import math
from pathlib import Path

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from app.runtime.skills.contracts import (
    SkillDefinition,
    SkillParseError,
    SkillParseErrorCode,
)


_MAX_YAML_DEPTH = 32
_MAX_YAML_NODES = 4096
_SUPPORTED_TAGS = frozenset(
    f"tag:yaml.org,2002:{name}"
    for name in ("null", "bool", "int", "float", "str", "seq", "map")
)


class _MetadataError(yaml.YAMLError):
    def __init__(self, code, message, mark):
        super().__init__(message)
        self.code = code
        self.problem_mark = mark


class _SkillLoader(yaml.SafeLoader):
    """Safe YAML with unambiguous keys, no aliases and bounded structure."""

    def __init__(self, stream):
        super().__init__(stream)
        self._skill_depth = 0
        self._skill_nodes = 0

    def compose_node(self, parent, index):
        event = self.peek_event()
        if self.check_event(AliasEvent):
            raise _MetadataError(SkillParseErrorCode.UNSUPPORTED_YAML,
                                 "Skill frontmatter must not contain YAML aliases.",
                                 event.start_mark)
        self._skill_nodes += 1
        if self._skill_depth >= _MAX_YAML_DEPTH or self._skill_nodes > _MAX_YAML_NODES:
            raise _MetadataError(SkillParseErrorCode.UNSUPPORTED_YAML,
                                 "Skill frontmatter exceeds YAML structure limits.",
                                 event.start_mark)
        self._skill_depth += 1
        try:
            node = super().compose_node(parent, index)
        finally:
            self._skill_depth -= 1
        if node.tag not in _SUPPORTED_TAGS:
            raise _MetadataError(SkillParseErrorCode.UNSUPPORTED_YAML,
                                 "Skill frontmatter contains an unsupported YAML tag.",
                                 node.start_mark)
        expected_type = {"tag:yaml.org,2002:map": MappingNode,
                         "tag:yaml.org,2002:seq": SequenceNode}.get(node.tag, ScalarNode)
        if not isinstance(node, expected_type):
            raise _MetadataError(SkillParseErrorCode.INVALID_YAML,
                                 "Skill frontmatter contains a YAML tag with an invalid value type.",
                                 node.start_mark)
        return node

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or not key.strip():
                raise _MetadataError(SkillParseErrorCode.INVALID_METADATA,
                                     "Skill metadata keys must be non-empty strings.",
                                     key_node.start_mark)
            if key in mapping:
                raise _MetadataError(SkillParseErrorCode.DUPLICATE_FIELD,
                                     "Skill frontmatter contains a duplicate field.",
                                     key_node.start_mark)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def parse_skill(
    text: str,
    *,
    root_path: Path,
    source_path: Path,
) -> SkillDefinition:
    """Return a definition or raise SkillParseError; paths are caller-supplied data.

    Frontmatter is a single YAML mapping between exact `---` delimiter lines.
    Optional metadata supports strings, finite numbers, booleans, null, lists,
    and string-keyed mappings. All body characters and line endings are retained.
    File loading, decoding, path normalization and containment belong to Phase 1.2.
    """
    if not isinstance(text, str) or not isinstance(root_path, Path) or not isinstance(source_path, Path):
        raise SkillParseError(SkillParseErrorCode.INVALID_INPUT,
                              "Skill parsing requires text and pathlib.Path source/root values.",
                              source_path=source_path if isinstance(source_path, Path) else None)

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].removeprefix("\ufeff").rstrip("\r\n") != "---":
        raise SkillParseError(SkillParseErrorCode.MISSING_FRONTMATTER,
                              "Skill must begin with YAML frontmatter.", source_path=source_path)
    closing = next((index for index in range(1, len(lines))
                    if lines[index].rstrip("\r\n") == "---"), None)
    if closing is None:
        raise SkillParseError(SkillParseErrorCode.UNCLOSED_FRONTMATTER,
                              "Skill frontmatter has no closing delimiter.", source_path=source_path)

    try:
        metadata = yaml.load("".join(lines[1:closing]), Loader=_SkillLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise SkillParseError(
            exc.code if isinstance(exc, _MetadataError) else SkillParseErrorCode.INVALID_YAML,
            str(exc) if isinstance(exc, _MetadataError) else "Skill frontmatter contains malformed YAML.",
            source_path=source_path,
            line=mark.line + 2 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        ) from None
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        raise SkillParseError(SkillParseErrorCode.INVALID_YAML,
                              "Skill frontmatter contains an invalid YAML value.",
                              source_path=source_path) from None

    if not isinstance(metadata, dict):
        raise SkillParseError(SkillParseErrorCode.INVALID_METADATA,
                              "Skill frontmatter must be a YAML mapping.", source_path=source_path)
    if not _finite_values(metadata):
        raise SkillParseError(SkillParseErrorCode.INVALID_METADATA,
                              "Skill metadata numbers must be finite.", source_path=source_path)
    for name in ("name", "description"):
        if name not in metadata:
            raise SkillParseError(SkillParseErrorCode.MISSING_FIELD,
                                  f'Skill is missing required field "{name}".',
                                  source_path=source_path, field=name)
        if not isinstance(metadata[name], str) or not metadata[name].strip():
            raise SkillParseError(SkillParseErrorCode.INVALID_FIELD,
                                  f'Skill field "{name}" must be a non-empty string.',
                                  source_path=source_path, field=name)

    instructions = "".join(lines[closing + 1:])
    if not instructions.strip():
        raise SkillParseError(SkillParseErrorCode.EMPTY_INSTRUCTIONS,
                              "Skill instructions must not be empty.", source_path=source_path)
    return SkillDefinition(
        name=metadata["name"],
        description=metadata["description"],
        instructions=instructions,
        root_path=root_path,
        source_path=source_path,
        metadata={key: value for key, value in metadata.items() if key not in {"name", "description"}},
    )


def _finite_values(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_values(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite_values(item) for item in value)
    return True
