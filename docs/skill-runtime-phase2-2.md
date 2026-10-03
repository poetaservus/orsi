# Skill Runtime check-in — Phase 2.2

Date: 3 October 2026. Starting integration revision: `3bae353`.
Implementation branch: `codex/skill-registry`.

## Implemented

`SkillRegistry` owns the effective skill catalog and provides `discover()`,
`get(name)`, `list()` and `reload()`. Its `report` property exposes the latest
catalog and structured discovery rejections. Registration happens only through
the existing safe discovery/loader pipeline; there is no manual registration
method that bypasses validation.

Construction does not scan or create directories. The default global scope is
`~/.orsi/skills/`. An explicit `global_root` names the skill-storage directory;
an explicit `project_root` enables `<project>/.orsi/skills/`. Roots are validated
before normalization and anchored at construction, so a later change to the
working directory or home setting does not redirect reload. No project is
inferred from the working directory or application checkout.

`get()` returns a definition by exact metadata name, or `None` for a missing
name. Non-string lookups raise `TypeError`. `list()` returns a name-sorted tuple.
Reads use the cached catalog and perform no filesystem access. Definitions and
reports returned by every API are detached copies, including nested optional
metadata, so callers cannot mutate the authoritative catalog through them.

`discover()` and `reload()` replace the whole catalog using the same configured
scopes and limits. They do not accumulate registrations. Removed, renamed,
malformed, oversized, ambiguous or redirected entries are not retained from a
previous scan. Existing project precedence, duplicate rejection and safe override
logging are inherited from Phase 2.1. Removing a project override exposes a still
valid global definition on the next reload.

A lock serializes scans and reads. Readers wait for the complete new snapshot;
concurrent refreshes cannot interleave publication. Ordinary filesystem/parser
rejections become discovery issues. Unexpected refresh exceptions clear the
old catalog and propagate to the caller rather than retaining stale instructions.
The empty report after such an exception is not a successful scan result.

## Application ownership

`build_application()` constructs and discovers one registry, then passes it to
`ConversationService.skill_registry`. Ordinary startup discovers only the global
scope. A caller that explicitly knows the project can supply a configured registry
through `skill_registry_override`. Startup rescans that registry rather than
assuming its existing snapshot is current.

Direct construction of `ConversationService` accepts a supplied registry, or
creates an empty registry without discovering implicitly. No conversation turn,
agent component or prompt builder independently reads skill directories. The
standalone parsing/loading/discovery APIs remain available for their existing
tests and explicit inspection.

No settings are migrated or written. There is no project-selection UI, skill
activation, router, installer, prompt section or model call in the registry.

## API

```python
from pathlib import Path
from app.runtime.skills import SkillRegistry

registry = SkillRegistry(project_root=Path("chosen-project"))
report = registry.discover()
skill = registry.get("design-taste-frontend")  # None if absent/rejected
catalog = registry.list()
updated_report = registry.reload()
```

Application callers can pass this registry to
`build_application(skill_registry_override=registry)`. Skill instructions remain
passive data in this phase and cannot change permissions, tools or configuration.

## Tests

Focused checks ran with unrestricted native Windows handle access and a
repository-local temporary directory:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_registry.py tests/test_skill_discovery.py tests/test_skill_loader.py tests/test_skill_parser.py tests/test_structure.py tests/test_conversation.py -p no:cacheprovider --basetemp .pytest-tmp-skill-registry-focused
220 passed, 2 skipped in 2.12 seconds
```

The 39 new registry checks all passed. Registry coverage includes
registration/retrieval, missing and exact names,
deterministic ordering, no implicit scans, detached nested metadata from every
read/refresh API, additions/updates/removals on reload, newly malformed files,
duplicate rejection and repair, project overrides and removal, ambiguous project
names, stable relative/default-home scopes, rejected inputs and unsafe paths,
configured limits, released native handles, a real Windows junction substituted
between refreshes, unexpected failure clearing, serialized snapshot reads and
fresh-process independence from inference imports.

The Phase 2 integration fixture invokes the real application startup and service
with three global skills, one project-only skill, one project override and one
malformed skill. It exposes exactly four effective definitions, selects the
project override and reports the malformed entry separately. A normal turn sends
exactly the same messages as startup with an empty catalog. Inference is replaced
with a recording test double; this is deterministic startup/conversation
integration, not a live Qwen or GUI qualification run. Default startup with a
fixture home also verifies global discovery without an inferred project.

The initial focused run found three cleanup errors in the new tests, which called
`close()` instead of the existing `shutdown()` method. Correcting the test cleanup
produced the passing result above; application behavior was not changed for it.

The full unrestricted regression suite passed:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-registry-full --junitxml=state/test-artifacts/skill-phase2-2-regression.xml
1129 passed, 56 skipped, 15 subtests passed in 159.79 seconds
0 failed; 0 error records
```

The 56 skips are unchanged: 49 opt-in live-model/cloud/UI gates and 7 actual
symbolic-link creation checks. They are separate from the passed deterministic
checks and do not establish live-model qualification. The registry's real junction,
native handle release, startup integration and inference-independence checks passed.
The ignored local report is under `state/test-artifacts/skill-phase2-2-regression.xml`.

Dependency consistency (`pip check`) and staged whitespace checks passed.
Existing acceptance prompts are unchanged; the existing unwritable pytest cache
remains disabled.

## Manual inspection

- Reviewed catalog ownership, scope anchoring, refresh replacement, lock lifetime,
  metadata isolation and structured rejection behavior.
- Verified startup delegates scanning to the registry and conversation code only
  stores that registry. No independent skill-directory reads were added elsewhere.
- Prompt construction, acceptance prompts, model profiles, runtime selection,
  sampling, context policy, permission checks and the capability catalog are unchanged.
- Parser, loader and discovery implementations are unchanged.

## Files changed

- `app/runtime/skills/registry.py`
- `app/runtime/skills/__init__.py`
- `app/startup.py`
- `app/conversation/orchestrator.py`
- `tests/test_skill_registry.py`
- `docs/skill-runtime-phase2-2.md`

## Known issues and limits

No known blocking issue in Phase 2.2. Safe filesystem discovery remains
Windows-only. Project discovery requires an explicit registry scope; no project
chooser was introduced. Filesystem changes are reflected only after explicit
discover/reload, and readers wait during a scan. Existing live qualification and
symbolic-link creation skips remain unverified.

## Next

Phase 3.1 — explicit activation and prompt integration. Do not begin until this
checkpoint is accepted.
