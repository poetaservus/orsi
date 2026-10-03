# Skill Runtime check-in — Phase 4.1

Date: 3 October 2026. Starting integration revision: `c065434`.
Implementation branch: `codex/skill-local-installer`.

## Implemented

Local skill management now provides all four requested commands:

```text
orsi skill list
orsi skill install <local-directory>
orsi skill info <exact-name>
orsi skill remove <exact-name>
```

The portable Windows launcher supports the same commands without installing a
console entry point. For example, from PowerShell in the application directory:

```powershell
.\ORSI.cmd skill list
.\ORSI.cmd skill install ".\taste-skill"
.\ORSI.cmd skill info "design-taste-frontend"
.\ORSI.cmd skill remove "design-taste-frontend"
```

Source paths remain relative to the caller's working directory, including when
the launcher is invoked from another folder. Names are exact metadata names,
not directory names. Names with spaces must be quoted. Default storage is the
existing global scope, `~/.orsi/skills`; no project is inferred from cwd.
An explicit isolated storage override is available before the subcommand:

```powershell
.\ORSI.cmd skill --storage ".\state\skill-test-storage" install ".\taste-skill"
```

Skill commands run before application-directory initialization, logging, Qt,
startup or inference composition. The GUI entry point retains its existing
behavior for ordinary launches. Lazy startup delegates preserve its existing
composition and cleanup entry points. Command errors return exit code 1;
invalid command syntax returns argparse's exit code 2. Successful commands
return 0. List displays valid entries and reports catalog rejections separately,
returning 1 if any are present. Untrusted labels are bounded and JSON-escaped.
Info shows name, description, source path and supported filenames, without
printing instruction bodies or interpreting arbitrary metadata.

## Supported package content

The only copied resource is **`SKILL.md`**. Its original bytes, UTF-8 BOM,
Unicode, frontmatter and body line endings are preserved. No scripts, package
manifests, dependencies, hooks, assets, reference files or configuration files
are copied, executed, imported or interpreted as executable behavior.
Optional YAML metadata retains its existing data-only parser contract.

The source can be a single skill folder or a local repository containing skills
in nested directories. Inspection is deterministic and stops descending once
a directory contains `SKILL.md`: that directory is a skill package, and its
other resources are unsupported. This also means skill packages nested inside
another skill package are not independently installed. A repository with no
skills is rejected. Traversed directories and skill sources reject symlinks,
junctions/reparse points, traversal, UNC/device paths, alternate data streams
and ambiguous Windows components through the existing safe path policy.
Unsupported resources inside a recognized skill package are never traversed,
including links to external references; they are never copied.

Limits are 64 skills, 16 MiB of total validated skill bytes, 2,048 enumerated
repository entries and eight levels of directory descent. Each `SKILL.md` uses
the registry's existing per-file limit (1 MiB by default). Storage respects the
registry entry limit (1,024 by default), counting unrelated immediate entries.
The operation lock is a sibling file, so it neither consumes a catalog slot nor
prevents removal when the catalog is full.

## Installation, conflicts and rollback

`SkillInstaller.install(Path(...), on_discovered=...)` safely snapshots and
validates the complete source before touching storage. Malformed skills and
duplicate names reject the entire batch. The optional callback receives detached
definitions after validation and before copying; the CLI uses it to show the
discovered names/descriptions. Installation itself is the user's requested
action; there is no additional interactive confirmation prompt.

Snapshots, rather than reopened source content, are copied. Source changes after
preview cannot silently change what is installed. Directory names are
`skill-<SHA256 of exact metadata name>`, so metadata names cannot become paths,
reserved devices or Windows case collisions. Case-distinct names remain distinct.

Existing global names with byte-identical `SKILL.md` are reported as already
installed. Different content for an existing name is rejected without replacing
it; remove that name explicitly before installing the update. Existing destination
entries are never overwritten, including directories not recognized as skills.
Rejected/ambiguous global storage blocks mutation until resolved. Explicit
project overrides remain read-only and retain their existing precedence.

Each operation holds the existing non-following ancestor handles and an exclusive
creation lock shared across installer instances/processes for that storage root.
New directories use the existing native child-directory creation helper. Files
are created exclusively, flushed and compared to their validated snapshots.
All package directories are staged beside storage, outside discovery, before
publication. Windows rename rejects existing destinations. Placed bytes,
directory identity and supported contents are checked again before refresh.

After placement, the authoritative registry is reloaded and installed names are
verified through the existing discovery rules. A copy, placement or refresh
failure triggers reverse-order cleanup of newly created directories and a
registry reload. Existing packages are preserved. Cleanup checks directory
identity and only unlinks `SKILL.md` followed by an empty-directory removal;
it never performs recursive deletion. Unknown resources and changed directory
identities are preserved, with `rollback_failed` reported instead of pretending
the operation completed. Structured error messages contain no raw file contents
or backend exception details.

## Removal and registry refresh

Removal resolves an exact name from global storage, checks that its directory
contains only `SKILL.md`, then renames it to a sibling quarantine outside discovery.
The registry refreshes before final cleanup. If refresh fails, removal restores
the original directory and refreshes again; restoration failures are reported.
Project-only skills cannot be removed through this global installer. Deleting a
global version preserves any project override. Manually copied folders with
extra resources are refused; unrelated files are not deleted.

`SkillInstaller(registry)` refreshes that same registry, so an existing
conversation service using it can select an installed skill on the next turn.
Removal invalidates an explicit selection through the existing Phase 3.1 missing
skill behavior. `list()` and `info()` rescan before returning detached definitions.
The registry exposes read-only anchored global-root and size/entry-limit getters
without filesystem reads. CLI commands refresh their own process's registry;
an already running GUI must be restarted to observe an external CLI change.
This phase adds no filesystem watcher or cross-process application notification.

## Verification

Final focused native Windows checks:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_installer.py tests/test_skill_parser.py tests/test_skill_loader.py tests/test_skill_discovery.py tests/test_skill_registry.py tests/test_skill_activation.py tests/test_skill_selection.py tests/test_application_shutdown.py tests/test_structure.py -p no:cacheprovider --basetemp .pytest-tmp-skill-installer-focused-capacity --junitxml=state/test-artifacts/skill-phase4-1-focused.xml
360 passed, 2 skipped in 10.37 seconds
```

All 60 new installer checks passed. Coverage includes the requested single and
multi-skill cases, duplicates, malformed input, partial copy/placement failure,
rollback/rollback failure, remove/reinstall, registry refresh and restoration,
source changes, post-placement byte changes, limits/full capacity, unknown-resource
preservation, script isolation, unsafe names/paths, actual Windows junctions,
concurrent installers, project overrides and install-to-conversation integration.
Fresh-process tests block UI, inference and startup imports while actually
installing through the production entry point. The actual portable launcher
installs from a relative source containing spaces and returns failure exit codes.
The two focused skips are existing actual symbolic-link creation checks.

The first focused failure was a new Unicode fixture encoded as escaped surrogate
values in YAML rather than literal UTF-8. The fixture was corrected without
changing the parser. Review found the initial in-storage lock consumed a catalog
slot; the sibling lock and exact-capacity install/removal check correct that
boundary. Existing acceptance requests, routing, model profiles, sampling,
context policy, tool definitions and permissions are unchanged.

The initial full regression recorded 1 failure, 1,274 passes, 58 skips and 15
passed subtests in 169.31 seconds. The unchanged registry test
`test_reload_rejects_scope_replaced_by_real_junction` encountered Windows
access-denied while renaming its fixture. Its isolated unrestricted recheck
passed in 0.19 seconds. The original failure report is preserved at
`state/test-artifacts/skill-phase4-1-regression-first-run.xml`; it is not relabelled
as a pass. The ordinary full rerun includes the capacity fix and added boundary
test: 1,275 passed, 1 failed, 58 skipped and 15 subtests passed in 169.48 seconds.
The same unchanged junction test failed at the fixture rename. That second report
is preserved at `state/test-artifacts/skill-phase4-1-regression-second-run.xml`.

An isolated archive of pre-installer `main` (`c065434`) also ran the old full
suite: 1,215 passed, 1 failed, 58 skipped and 15 subtests passed in 169.70 seconds.
The junction test passed there; the failure was the existing 30 ms agent timeout
test's assertion that its capability had already started. This comparison does
not establish the cause of the candidate's rename failure. Its source and
report remain ignored local diagnostics, without copying persistent user state.

The full suite passed with a temporary diagnostic wrapper around the native
handles used only by the unchanged junction test:

```text
runtime/python/python.exe -B state/test-artifacts/skill-phase4-1-handle-audit.py
1276 passed, 58 skipped, 15 subtests passed in 170.00 seconds
0 failed; 0 error records
```

The audit recorded 18 native opens, 17 explicit closes and zero live native
handles at test completion. The remaining file-snapshot handle closes through
its transferred Python file descriptor. The wrapper added no retry, skip,
assertion change or product change. This passing instrumented run does not
identify the cause of the two ordinary runs' rename failures. Reports are
`state/test-artifacts/skill-phase4-1-regression-audit.xml` and
`state/test-artifacts/skill-phase4-1-handle-audit.json`.

The existing 30 ms agent timeout check also failed its standalone recheck before
the capability started, while passing in the complete candidate suite. Its
threshold and runtime were not changed; this remains timing-sensitive baseline
evidence, separate from installer acceptance.

The final uninstrumented combined confirmation repeated the same fixture rename
failure: 1,275 passed, 1 failed, 58 skipped and 15 subtests passed in 168.20 seconds.
Its report is `state/test-artifacts/skill-phase4-1-regression-confirm.xml`. These
failures remain unresolved evidence; the instrumented pass does not replace them.
The existing suite passed separately in its original order, excluding only the
60 new installer tests already passed in the focused check:

```text
runtime/python/python.exe -B -m pytest --ignore=tests/test_skill_installer.py -p no:cacheprovider --basetemp .pytest-tmp-skill-installer-existing --junitxml=state/test-artifacts/skill-phase4-1-existing-regression.xml
1216 passed, 58 skipped, 15 subtests passed in 151.45 seconds
0 failed; 0 error records
```

Every pre-existing check was collected, including the junction test. The new
installer tests were separately verified, not counted as skipped or as part of
these 1,216 passes. The ordinary combined-run rename failure remains an unresolved
verification limitation even though focused, existing-suite and full audited
checks pass. The bounded installer is verified; this is not a claim of fully
qualified arbitrary Windows timing or broad live-model behavior.

Tests use repository-local temporary storage and unrestricted native Windows
handles. Dependency consistency and whitespace checks passed; the existing
unwritable pytest cache remains disabled. No live model is needed for local
filesystem installation. All 58 skips are existing gates: 7 actual symbolic-link
creation checks and 51 opt-in live-model/cloud/UI checks. They are not passes;
this phase reruns no live model gates.

## Files changed

- `app/runtime/skills/installer.py`
- `app/runtime/skills/cli.py`
- `app/runtime/skills/__init__.py`
- `app/runtime/skills/registry.py`
- `app/main.py`
- `ORSI.cmd`
- `tests/test_skill_installer.py`
- `docs/skill-runtime-phase4-1.md`

## Known limits and next phase

Safe installation is Windows-only. Only `SKILL.md` is supported; references/assets
are neither installed nor available to the skill runtime. Git/URL installation
and real upstream TasteSkill compatibility are not claimed by this checkpoint.
These remain Phases 4.2 and 5.1.

Rollback handles ordinary in-process failures, not power loss or process death.
A crashed operation can leave a sibling lock, staged/quarantined directories or
a partially published batch. Stale locks are deliberately not removed
automatically because another process may own them. Recovery requires confirming
the operation has stopped and inspecting those local artifacts; unrelated files
are never recursively purged. Another process explicitly reloading the registry
during publication may briefly observe a partial batch. Existing running GUI
catalogs require restart after external CLI changes, as noted above.

Next: Phase 4.2 — Git repository installer. Do not begin until this checkpoint
is accepted.
