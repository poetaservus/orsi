"""Phase 1.1: pure parsing, body preservation, and fail-closed metadata."""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.runtime.skills import SkillDefinition, SkillParseError, SkillParseErrorCode, parse_skill


ROOT = Path("unopened-skills/frontend")
SOURCE = ROOT / "SKILL.md"
HEADER = "name: design-taste-frontend\ndescription: Frontend design guidance.\n"


def parse(frontmatter=HEADER, body="\n# Design\nUse clear spacing.\n", *, newline="\n", bom=""):
    text = bom + "---\n" + frontmatter + "---\n" + body
    return parse_skill(text.replace("\n", newline), root_path=ROOT, source_path=SOURCE)


def assert_failure(text, code, *, field=None):
    with pytest.raises(SkillParseError) as caught:
        parse_skill(text, root_path=ROOT, source_path=SOURCE)
    error = caught.value
    assert error.code == code
    assert error.source_path == SOURCE
    assert error.field == field
    assert str(error)
    return error


def test_valid_frontmatter_returns_complete_deterministic_definition():
    expected = SkillDefinition(
        name="design-taste-frontend", description="Frontend design guidance.",
        instructions="\n# Design\nUse clear spacing.\n", root_path=ROOT, source_path=SOURCE,
    )
    assert parse() == parse() == expected
    with pytest.raises(FrozenInstanceError):
        expected.name = "changed"


@pytest.mark.parametrize("description,expected", [
    ("|\n  First line.\n  Second line.\n", "First line.\nSecond line.\n"),
    (">\n  First line.\n  Second line.\n", "First line. Second line.\n"),
    ('"Spacing: preserve # punctuation"\n', "Spacing: preserve # punctuation"),
])
def test_multiline_and_quoted_descriptions(description, expected):
    skill = parse("name: frontend\ndescription: " + description)
    assert skill.description == expected


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_markdown_unicode_and_line_endings_are_preserved(newline, bom):
    body = "\n# Ízlés 🎨\n\n  Indented text  \n```yaml\n---\nname: body-data\n```\n\n"
    skill = parse(body=body, newline=newline, bom=bom)
    assert skill.instructions == body.replace("\n", newline)
    assert skill.source_path == SOURCE


def test_unicode_metadata_and_utf8_text():
    text = "---\nname: ízlés\ndescription: Интерфейс 🎨\n---\n你好\n"
    skill = parse_skill(text.encode("utf-8").decode("utf-8"), root_path=ROOT, source_path=SOURCE)
    assert (skill.name, skill.description, skill.instructions) == ("ízlés", "Интерфейс 🎨", "你好\n")


def test_unknown_metadata_is_preserved_without_becoming_authority():
    skill = parse(HEADER + 'version: "1.2"\npermissions: [shell, network]\n'
                  'settings:\n  enabled: true\n  level: 8\n  density: 0.5\n  fallback: null\n')
    assert skill.metadata == {"version": "1.2", "permissions": ["shell", "network"],
                              "settings": {"enabled": True, "level": 8, "density": 0.5, "fallback": None}}
    assert skill.instructions == parse().instructions
    skill.metadata["settings"]["level"] = 100
    assert parse(HEADER + "settings: {level: 8}\n").metadata["settings"]["level"] == 8


@pytest.mark.parametrize("body", ["", "\n", " \t\r\n"])
def test_empty_instructions_are_rejected(body):
    assert_failure("---\n" + HEADER + "---\n" + body, SkillParseErrorCode.EMPTY_INSTRUCTIONS)


@pytest.mark.parametrize("field", ["name", "description"])
def test_missing_required_fields(field):
    frontmatter = "description: Design\n" if field == "name" else "name: frontend\n"
    error = assert_failure("---\n" + frontmatter + "---\nBody", SkillParseErrorCode.MISSING_FIELD, field=field)
    assert f'"{field}"' in str(error)


@pytest.mark.parametrize("field", ["name", "description"])
@pytest.mark.parametrize("value", ['""', '"  "', "null", "true", "42", "[]", "{}"])
def test_required_fields_are_nonempty_strings(field, value):
    other = "description: Design\n" if field == "name" else "name: frontend\n"
    assert_failure(f"---\n{other}{field}: {value}\n---\nBody", SkillParseErrorCode.INVALID_FIELD, field=field)


@pytest.mark.parametrize("text", ["", "# No frontmatter", "name: frontend\nBody", "\n---\n" + HEADER + "---\nBody"])
def test_frontmatter_must_be_at_the_start(text):
    assert_failure(text, SkillParseErrorCode.MISSING_FRONTMATTER)


def test_frontmatter_requires_closing_delimiter():
    assert_failure("---\n" + HEADER + "Body", SkillParseErrorCode.UNCLOSED_FRONTMATTER)


@pytest.mark.parametrize("frontmatter", ["", "null\n", "42\n", "plain string\n", "- name\n- description\n"])
def test_frontmatter_must_be_a_mapping(frontmatter):
    assert_failure("---\n" + frontmatter + "---\nBody", SkillParseErrorCode.INVALID_METADATA)


def test_malformed_yaml_has_safe_error_and_source_position(caplog):
    error = assert_failure("---\n" + HEADER + "secret: [PRIVATE-CONTENT\n---\nBody", SkillParseErrorCode.INVALID_YAML)
    assert error.line is not None and error.line >= 2
    assert error.column is not None and error.column >= 1
    assert "PRIVATE-CONTENT" not in str(error)
    assert "PRIVATE-CONTENT" not in caplog.text


@pytest.mark.parametrize("extra", ["name: duplicate\n", "description: duplicate\n",
                                    "custom: 1\ncustom: 2\n", "custom: {key: 1, key: 2}\n"])
def test_duplicate_fields_are_rejected_at_any_depth(extra):
    assert_failure("---\n" + HEADER + extra + "---\nBody", SkillParseErrorCode.DUPLICATE_FIELD)


@pytest.mark.parametrize("extra", ["1: value\n", "true: value\n", '"": value\n',
                                    '"  ": value\n', "custom: {1: value}\n"])
def test_metadata_keys_must_be_nonempty_strings(extra):
    assert_failure("---\n" + HEADER + extra + "---\nBody", SkillParseErrorCode.INVALID_METADATA)


@pytest.mark.parametrize("extra", [
    "custom: !!python/object/apply:builtins.eval ['1 + 1']\n",
    "custom: !unknown value\n", "custom: 2026-10-03\n", "custom: !!binary SGVsbG8=\n",
    "custom: !!set {value: null}\n",
    "custom: &shared [one]\ncopy: *shared\n", "custom: &loop [*loop]\n",
    "custom: {<<: {value: 1}}\n",
])
def test_unsafe_or_unsupported_yaml_is_rejected(extra):
    assert_failure("---\n" + HEADER + extra + "---\nBody", SkillParseErrorCode.UNSUPPORTED_YAML)


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf", "[.nan]", "{nested: .inf}"])
def test_nonfinite_metadata_is_rejected(value):
    assert_failure("---\n" + HEADER + f"custom: {value}\n---\nBody", SkillParseErrorCode.INVALID_METADATA)


@pytest.mark.parametrize("value", ["!!int invalid", "!!float invalid", "!!bool invalid",
                                   "!!int ''", "!!float ''", "!!int +", "!!int 0x",
                                   "!!map value", "!!seq value", "!!null [value]"])
def test_invalid_tagged_scalar_is_a_structured_failure(value):
    assert_failure("---\n" + HEADER + f"custom: {value}\n---\nBody", SkillParseErrorCode.INVALID_YAML)


@pytest.mark.parametrize("extra", ["custom: " + "[" * 40 + "null" + "]" * 40 + "\n",
                                    "custom: [" + ",".join(["null"] * 4096) + "]\n"])
def test_yaml_structure_limits_prevent_unbounded_or_recursive_metadata(extra):
    assert_failure("---\n" + HEADER + extra + "---\nBody", SkillParseErrorCode.UNSUPPORTED_YAML)


def test_yaml_document_end_followed_by_another_document_is_rejected():
    assert_failure("---\n" + HEADER + "...\nother: value\n---\nBody", SkillParseErrorCode.INVALID_YAML)


@pytest.mark.parametrize("text,root,source", [(b"bytes", ROOT, SOURCE), (None, ROOT, SOURCE),
                                            ("text", str(ROOT), SOURCE), ("text", ROOT, str(SOURCE))])
def test_invalid_api_input_is_a_structured_failure(text, root, source):
    with pytest.raises(SkillParseError) as caught:
        parse_skill(text, root_path=root, source_path=source)
    assert caught.value.code == SkillParseErrorCode.INVALID_INPUT


def test_parser_does_not_open_or_normalize_paths(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Phase 1.1 must not access the filesystem")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "resolve", forbidden)
        root = Path("unopened/../skill")
        source = root / "SKILL.md"
        skill = parse_skill("---\n" + HEADER + "---\nBody", root_path=root, source_path=source)
    assert skill.root_path == root
    assert skill.source_path == source
