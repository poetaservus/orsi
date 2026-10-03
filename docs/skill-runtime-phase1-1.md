# Skill Runtime check-in — Phase 1.1

Date: 3 October 2026. Starting integration revision: `3da153d`.

## Implemented

- `SkillDefinition`: name, description, instructions, caller-supplied root/source paths,
  and optional metadata. Definition fields are frozen; metadata remains an ordinary,
  independently parsed dictionary.
- `parse_skill(text, *, root_path, source_path)`: pure parsing with no file access,
  path resolution, installation, discovery, activation, routing or prompt changes.
- `SkillParseError`: stable error code, safe message, source path, optional required
  field name, and one-based source line/column when available. YAML source excerpts
  and untrusted field names are not included in error messages.
- PyYAML declared in both dependency manifests (`>=6.0.2,<7`); verification uses
  PyYAML 6.0.3 in the project-local Python 3.12.10 runtime.

## Format contract

Opening and closing frontmatter delimiters are exact `---` lines. Opening frontmatter
must be at the start of the supplied text; a leading UTF-8 BOM is accepted. LF, CRLF
and CR line endings are supported. Everything after the closing delimiter is retained
as instructions, including leading/trailing whitespace and original line endings.

Frontmatter must be one YAML mapping with non-empty string `name` and `description`.
Multiline descriptions follow YAML's literal/folded scalar semantics. Empty or
whitespace-only instruction bodies are rejected. Required fields retain their
parsed strings; no name/description normalization or filename policy is introduced.

Unknown metadata fields are preserved without being interpreted. Values support
strings, finite integers/floats, booleans, null, lists and string-keyed mappings.
Duplicate fields at any depth, empty/non-string keys, aliases, merge keys and
unsupported tags are rejected. Timestamp, binary and set tags are unsupported;
date-like values can be quoted to preserve them as strings. YAML composition is
limited to 32 levels and 4,096 nodes before value construction.

The loader derives from [PyYAML SafeLoader](https://pyyaml.org/wiki/PyYAMLDocumentation)
and restricts supported tags before construction. Unsafe object tags are rejected.
These YAML bounds protect parsing; they are separate from the file-size/encoding and
path-containment checks planned for Phase 1.2.

## API

```python
from pathlib import Path
from app.runtime.skills import parse_skill, SkillParseError

try:
    skill = parse_skill(
        supplied_text,
        root_path=Path("skills/frontend"),
        source_path=Path("skills/frontend/SKILL.md"),
    )
except SkillParseError as error:
    # Callers can report the code and safe message without printing source text.
    rejection = {"code": error.code.value, "message": str(error)}
```

Phase 1.1 receives already-decoded text. `load_skill(path)`, decoding, normalized
paths and filesystem containment belong exclusively to Phase 1.2.

## Tests

Focused verification:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_parser.py tests/test_structure.py -p no:cacheprovider --basetemp .pytest-tmp-skill-parser-final
84 passed (82 parser cases, 2 existing structure checks)
```

Cases cover valid/deterministic definitions, multiline descriptions, Markdown and
Unicode preservation, BOM/line endings, optional nested metadata, missing/invalid
fields, empty bodies, malformed YAML, duplicate keys, unsafe/unsupported tags,
non-finite values, malformed tagged scalars, structure limits, invalid API inputs,
and parsing without opening or resolving paths.

The initial restricted-shell full run recorded 917 passed, 82 failed, 53 skipped
and 15 passed subtests. Failures were in existing Windows-native write/approval
workflows under sandbox restrictions. This result is not a product acceptance pass.
The final unrestricted full-suite run passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-full-unrestricted --junitxml=state/test-artifacts/skill-phase1-1-regression.xml
1005 passed, 54 skipped, 15 subtests passed in 158.17 seconds
0 failed; 0 error records
```

The 54 skips comprise 49 opt-in live-model/cloud/UI gates and 5 existing symbolic-link
checks unavailable on this Windows configuration. They are recorded separately from
passed deterministic checks and do not establish live-model qualification. The
local ignored XML report is under `state/test-artifacts/skill-phase1-1-regression.xml`.

Dependency consistency check: `pip check` passed. Whitespace check: `git diff --check`
passed. Pytest's existing cache was not writable in the restricted shell, so final
runs disable only the cache plugin; tests and acceptance prompts are unchanged.

## Manual inspection

- Reviewed model fields, parser complexity, exported API and structured failures.
- Confirmed there are no imports of the new skill package from application startup,
  conversation orchestration, provider adapters or tool execution.
- Existing architecture guard against the abandoned `app/skills` action package
  remains intact; instruction parsing resides under `app/runtime/skills`.
- No model profiles, runtime selection, prompts, tool schemas, permissions,
  conversation persistence or sampling were changed.
- Qwen prompt inspection and skill activation are not applicable until Phase 3.1.

## Files changed

- `app/runtime/skills/__init__.py`
- `app/runtime/skills/contracts.py`
- `app/runtime/skills/parser.py`
- `tests/test_skill_parser.py`
- `pyproject.toml`
- `requirements.txt`
- `docs/skill-runtime-phase1-1.md`

## Next

Phase 1.2 — safe file loading. Do not begin until this checkpoint is accepted.

## Known issues

None blocking Phase 1.1. File loading and model behavior remain deliberately
unimplemented. Existing skipped live/symbolic-link checks remain unverified.
