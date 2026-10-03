# Skill Runtime check-in — Phase 2.1

Date: 3 October 2026. Starting integration revision: `fb118e4`.
Implementation branch: `codex/skill-discovery`.

## Implemented

- `discover_skills()` scans `~/.orsi/skills/` by default. An explicit
  `global_root` override names that scope's skill-storage directory.
- An explicit `project_root` enables `<project>/.orsi/skills/`. The current
  working directory is never inferred as the project.
- Only immediate child directories are considered, and only their direct
  `SKILL.md` file is loaded through the existing Phase 1.2 loader.
- `SkillDiscoveryReport` returns a name-sorted tuple of effective definitions
  and a deterministically sorted tuple of `SkillDiscoveryIssue` rejections.
  Issues contain scope, source path, stable code and safe message.
- Valid project skills override valid global skills with exactly matching names.
  Overrides are logged with escaped, bounded skill names and no body/path content.

## Discovery and collision contract

Names use the exact strings supplied by the existing parser; no case/whitespace
normalization or directory-name inference is added. Definitions and unknown
metadata are preserved unchanged. Repeated discovery of an unchanged filesystem
returns equivalent reports; no registry, cache or reload lifecycle is introduced.

All same-name definitions within one scope are rejected with `duplicate_name`
issues. A project duplicate also removes a matching global definition from the
effective set, preventing a silent fallback for a known ambiguous override.
A unique valid project definition can still supersede an ambiguous global name.
Malformed project files do not replace valid global definitions; their rejected
format is reported separately.

Missing scope directories are empty and are never created. Empty directories,
ordinary files, scope-root `SKILL.md` files and deeper layouts such as
`skills/bundle/nested/SKILL.md` are ignored. No other project/home directories
or files are scanned. A child directory without a direct `SKILL.md` is ignored.
Malformed, unreadable or oversized packages are reported while unrelated valid
packages remain available.

`max_bytes` forwards the existing per-file byte limit (default 1 MiB).
`max_entries` defaults to `MAX_DISCOVERY_ENTRIES = 1024`, independently for each
scope. Enumeration is streaming and collects at most that many immediate entries
plus the single lookahead needed to reject an over-limit scope. Ordinary files
also count toward the limit. Over-limit scopes return no partial catalog and an
`entry_limit` issue; other valid scopes can still contribute skills.

## Filesystem and logging boundary

The existing loader path policy rejects unsafe scope paths and redirected ancestors.
Scope enumeration and file loading occur while existing native Windows handles
pin the scope directory and its ancestors. Child reparse points/junctions are
rejected before attempting to load their content. The Phase 1.2 loader independently
checks and pins each package's path during its bounded read. No filesystem policy
or native execution code was modified.

Scope enumeration failures withhold that scope's results and return content-free
diagnostics. Handles close on failures and over-limit early returns. Filesystem
discovery inherits the existing Windows-only safe-read boundary; the parser
remains independently usable with supplied text.

The only new log event is the required project-over-global override. Its skill
name is limited to 128 characters and JSON-escaped to prevent multiline/log-control
injection. Instructions, descriptions, metadata bodies, host paths and exception
excerpts are not logged.

## API

```python
from pathlib import Path
from app.runtime.skills import discover_skills

report = discover_skills(project_root=Path("chosen-project"))
valid_skills = report.skills
rejections = report.issues
```

There is no LLM dependency, selection, activation, prompt injection, installer,
registry object or startup wiring in Phase 2.1. Discovery is a passive filesystem
operation and skill content remains an instruction source without runtime authority.

## Tests

Focused checks ran with unrestricted native Windows handle access and a
repository-local temporary directory:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_discovery.py tests/test_skill_loader.py tests/test_skill_parser.py tests/test_structure.py -p no:cacheprovider --basetemp .pytest-tmp-skill-discovery-focused
169 passed, 2 skipped
```

This includes 32 new discovery checks, 53 loader checks, 82 parser checks and
2 existing structure checks. The two skips are the existing loader symbolic-link
creation checks unavailable on this Windows account; they are not counted as passes.

Discovery tests cover missing/empty scopes, single/multiple skills, exact definition
and line-ending preservation, stable ordering, invalid/valid mixtures, same-scope
duplicates, project precedence, ambiguous project overrides, default home scope,
explicit project scope, no cwd inference, unrelated files and nested layouts,
entry/file limits, unsafe roots, real Windows junction roots/children and a junction
swap after inspection, sanitized errors, handle release, escaped/bounded override
logs and invalid API arguments. A fresh-process test blocks all `app.inference`
imports while importing and running discovery against a real fixture.

The full unrestricted regression suite passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-discovery-full --junitxml=state/test-artifacts/skill-phase2-1-regression.xml
1090 passed, 56 skipped, 15 subtests passed in 154.08 seconds
0 failed; 0 error records
```

The 56 skips are unchanged: 49 opt-in live-model/cloud/UI gates and 7 actual
symbolic-link creation checks. They are recorded separately from passed checks
and do not establish live-model qualification. The new real junction and
LLM-independence checks passed. The ignored local report is under
`state/test-artifacts/skill-phase2-1-regression.xml`.

Dependency consistency (`pip check`) and whitespace (`git diff --check`) passed.
Existing acceptance prompts are unchanged; the existing unwritable pytest cache
remains disabled.

## Manual inspection

- Reviewed scan depth, approved scope construction, deterministic ordering,
  collision handling, native handle lifetimes and content-free rejection messages.
- Verified that application startup, conversation orchestration and agent code
  do not import/activate the new discovery API.
- Existing parser/loader implementation, tool catalog, permission enforcement,
  model profiles, runtime selection, sampling, prompts and context policy are unchanged.
- No registry/reload API, installation, routing, model call or UI management was added.

## Files changed

- `app/runtime/skills/discovery.py`
- `app/runtime/skills/contracts.py`
- `app/runtime/skills/__init__.py`
- `tests/test_skill_discovery.py`
- `docs/skill-runtime-phase2-1.md`

## Known issues and limits

No known blocking issue in Phase 2.1. Safe filesystem discovery is Windows-only.
Previously skipped live qualification and actual symbolic-link creation checks
remain unverified; new real junction and LLM-independence checks passed.

## Next

Phase 2.2 — SkillRegistry. Do not begin until this checkpoint is accepted.
