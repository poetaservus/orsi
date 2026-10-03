# Skill Runtime check-in — Phase 1.2

Date: 3 October 2026. Starting integration revision: `e8a948c`.
Implementation branch: `codex/skill-file-loader`.

## Implemented

- `load_skill(path, *, root_path, max_bytes=MAX_SKILL_SIZE)` loads one explicit
  file under a caller-supplied allowed skill directory.
- `MAX_SKILL_SIZE` defaults to 1 MiB (1,048,576 bytes). A positive integer override
  configures the limit per call; booleans and overflowing read sizes are rejected.
- Strict UTF-8 decoding, including the parser's existing BOM support. Binary reads
  preserve CR/LF/CRLF line endings and all Markdown body characters.
- Root/source paths are normalized to absolute paths. A relative source path is
  relative to the explicit root, rather than the process working directory.
- `SkillLoadError` and stable load-error codes report filesystem, containment,
  byte-limit and encoding failures without file-content excerpts. Format errors
  remain `SkillParseError`, carrying the normalized source path.

## Filesystem boundary

The loader rejects parent (`..`) components, even when traversal would stay within
the root. Absolute sources must lie within that root; sibling names sharing a
prefix do not qualify. Network/device paths, drive-relative/root-relative paths,
alternate data streams, reserved names, wildcard/control characters and trailing
dot/space components are rejected before any file read.

Every path ancestor is inspected before its children. Symbolic links and Windows
reparse points are rejected, including the allowed root itself, ancestor junctions
and links targeting another location inside the root. Paths are normalized without
resolving redirects. Missing roots, non-directory roots and non-regular sources
fail closed.

The actual read reuses existing, unchanged functions from
`app/execution/windows_filesystem.py`: `pinned_parent` holds ancestor handles
without write/delete sharing, and `read_file_snapshot` opens the file without
following its final reparse point. The snapshot independently checks size and
reads at most `max_bytes + 1` bytes. These handle checks prevent a path swap after
the preliminary inspection from reading redirected content. Handles close on
success and on failure; no file identity or content is logged by the loader.

Relevant native handle semantics are documented in
[Microsoft's CreateFileW reference](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
The loader supports the application's Windows runtime. Other platforms return
`unsupported_platform` before inspecting paths; no weaker fallback reader is used.
The pure Phase 1.1 parser remains independent of filesystem/platform support.

## API

```python
from pathlib import Path
from app.runtime.skills import load_skill, SkillLoadError, SkillParseError

try:
    skill = load_skill(
        Path("SKILL.md"),
        root_path=Path("test_skill"),
        max_bytes=1024 * 1024,
    )
except (SkillLoadError, SkillParseError) as error:
    rejection = {"code": error.code.value, "message": str(error)}
```

The caller supplies the permitted root; the loader does not discover directories,
infer installation locations or grant the agent filesystem permission. Skill text
and adjacent scripts remain passive data. No content or installation script is
executed, and no skill is activated or injected into a model request.

## Tests

Focused checks ran with unrestricted native Windows handle access and a
repository-local test directory:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_loader.py tests/test_skill_parser.py tests/test_structure.py -p no:cacheprovider --basetemp .pytest-tmp-skill-loader-focused-final
137 passed, 2 skipped
```

This comprises 53 passed loader cases, the existing 82 parser cases and 2 existing
structure checks. The two new skips are actual file/directory symbolic-link
creation checks unavailable to this Windows account. They are not counted as passes.

Passing loader cases include:

- The Phase 1 integration fixture: create `test_skill/SKILL.md`, load it through
  the real filesystem loader and compare every field of the resulting definition.
- UTF-8/Unicode/BOM and original line endings, relative root/source normalization,
  missing files, invalid roots, directory sources, default/custom size limits,
  exact byte boundaries and invalid encoding.
- Traversal, sibling-prefix escape, alternate streams, ambiguous Windows names,
  and real child/root/ancestor/in-root junction rejection.
- A real junction replacement after inspection, file growth before snapshot,
  file removal before snapshot, and released handles after native failures.
- Sanitized errors, parser error propagation, unsupported-platform rejection,
  and passive instructions/adjacent executable files.

The full unrestricted suite passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-loader-full --junitxml=state/test-artifacts/skill-phase1-2-regression.xml
1058 passed, 56 skipped, 15 subtests passed in 153.93 seconds
0 failed; 0 error records
```

The 56 skips comprise 49 existing opt-in live-model/cloud/UI gates, 5 existing
symbolic-link creation checks and the 2 new symbolic-link creation checks.
Real junction rejection, a junction race and handle-release checks passed.
Skipped checks are recorded separately from deterministic passes and do not
establish live-model qualification. The ignored local XML report is under
`state/test-artifacts/skill-phase1-2-regression.xml`.

Dependency consistency (`pip check`) and whitespace (`git diff --check`) checks
passed. Existing acceptance prompts and tests are unchanged; pytest's cache
plugin remains disabled because the existing cache is not writable in the
restricted shell.

## Manual inspection

- Reviewed the explicit-root contract, byte bounds, path rejection order,
  native read/handle ownership and structured errors.
- No application startup or conversation component imports/activates skills.
- Existing parser behavior, tool definitions, permissions, tool execution code,
  model profiles, runtime selection, sampling, context policy and prompts are unchanged.
- No new dependency, discovery, registry, installer, routing or prompt integration
  was introduced. Live Qwen skill behavior is not applicable in this phase.

## Files changed

- `app/runtime/skills/loader.py`
- `app/runtime/skills/contracts.py`
- `app/runtime/skills/__init__.py`
- `tests/test_skill_loader.py`
- `docs/skill-runtime-phase1-2.md`

## Known issues and limits

No known blocking issue in Phase 1.2. Actual symbolic-link creation checks remain
unverified on this host; real Windows junction checks passed. Filesystem loading
is Windows-only and intentionally rejects all redirected paths.

## Next

Phase 2.1 — discovery. Do not begin until the Phase 1 checkpoint is accepted.
