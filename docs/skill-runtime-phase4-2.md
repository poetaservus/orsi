# Skill Runtime Phase 4.2 — HTTPS Git installation

## Bounded change

Phase 4.2 adds public HTTPS Git repository installation to the existing skill
command. Only instruction files are installed. Application UI, startup, model
profiles, sampling, context policy, routing, tool permissions and inference source
are unchanged. The user requested proceeding with this phase and deferring the
unrelated regressions until the skills roadmap is finished.

The branch starts at local `main` revision `59bbbd2` (Phase 4.1), under
`codex/skill-git-installer`. No remote branch publication is part of this change.

## Commands and API

```text
ORSI.cmd skill install https://github.com/example/repository
ORSI.cmd skill --storage C:\path\to\isolated\skills install https://github.com/example/repository.git
ORSI.cmd skill list
ORSI.cmd skill info exact-skill-name
ORSI.cmd skill remove exact-skill-name
```

Local directory installation still works. Git installation requires an existing
Git executable on PATH; it never installs Git or package dependencies. Only HTTPS
URLs without credentials, queries or fragments are accepted. SSH, `git://`,
`file://`, external helpers and plain SCP-style Git addresses are unsupported.
Redirects are disabled; repositories which require an HTTP redirect must be
addressed using their final HTTPS repository URL. Authentication prompts and
credential helpers are disabled. The remote's default branch tip is used; refs,
tags, branch selectors and updates in place are not provided in v1.

`GitSkillInstaller(SkillInstaller(registry)).install(url, on_discovered=callback,
cancellation=token)` returns `GitSkillInstallResult` with installed names,
identical existing names and the inspected immutable commit revision. The preview
callback receives detached validated skill definitions before any skill-storage
writes. Its synthetic source paths refer to the already-released temporary copy;
the callback should display metadata, not try to read those paths. Cancellation
is checked before/after the preview and before publication. Once the local
transaction begins, it completes or rolls back using Phase 4.1 behavior.

The explicit install command authorizes copying all validated instruction files;
there is no second confirmation prompt. Invalid/malformed/ambiguous batches are
rejected together. Different content under an existing name still requires
explicit removal first. Project overrides remain read-only. An external CLI
change requires restarting an already-running GUI to refresh its own catalog.

## Inspection and execution boundary

1. Validate the URL and create one exclusive temporary workspace with pinned
   Windows ancestors and an owned directory identity.
2. Run a shallow, single-branch, bare clone with an empty template and hooks path.
   No checkout is performed.
3. Resolve the default-branch commit, then enumerate its complete tree using
   NUL-delimited `ls-tree --full-tree -l -r -z` output.
4. Reject committed symlinks, submodule entries, unsupported objects and oversized
   files, including unsupported resource files. Never initialize submodules.
5. Read only exact-basename `SKILL.md` blobs with raw `cat-file blob` operations.
   Repository paths never become local filesystem paths: each file is put into
   a synthetic package directory. Every matching instruction file in the tree
   participates in validation, even if it is nested below another skill.
6. Reuse the local parser, loader, duplicate-name checks and bounded inspection.
   Retain the validated bytes in memory, then release all Git jobs and remove the
   temporary clone before preview and publication.
7. Reuse the existing local installation transaction, hashed storage names,
   idempotence checks, registry refresh, rollback and removal behavior.

No `setup.py`, shell script, npm lifecycle, repository hook, executable resource,
plugin manifest or other installer is run. Executable-mode regular files are
inert repository data; only `SKILL.md` bytes are copied, without executable flags.
Git attributes, smudge filters, text conversion, LFS hydration and checkout-time
encoding transformations do not run. References, scripts, assets and licenses
are not copied by this instruction-only v1 installer. This does not establish
full operational compatibility for skills which depend on those resources.

Git system/global/inherited Git configuration is isolated. Inherited `GIT_*`,
credential-manager configuration and askpass settings are removed. Command
arguments are passed directly to an existing Git executable with no shell.
Git stderr is discarded and errors use fixed content-free messages rather than
URLs, file bodies, credentials or subprocess diagnostics.

The implementation follows the primary Git documentation for
[bare cloning](https://git-scm.com/docs/git-clone),
[configuration isolation and hooks](https://git-scm.com/docs/git-config),
[tree output](https://git-scm.com/docs/git-ls-tree), and
[raw object access](https://git-scm.com/docs/git-cat-file).

## Resource ownership and limits

Each Git command starts hidden inside a private Windows Job Object, attached
atomically during process creation. Ownership failure never launches an
unguarded process. Standard input/error are null; only an explicit bounded
output file handle is inherited. The private skill helper follows the existing
native ownership pattern without importing or changing inference modules.

Limits:

| Resource | Limit |
| --- | --- |
| Download and inspection deadline | 120 seconds before publication |
| Observed temporary bytes | 128 MiB |
| Temporary filesystem entries | 16,384 |
| Any committed regular blob | 32 MiB |
| Tree listing | 8 MiB / 4,096 entries |
| Instruction files | 64 / 16 MiB combined |
| Individual instruction file | Registry limit, normally 1 MiB |
| Owned job memory / processes | 1 GiB / 16 processes |

Commands are polled every 50 ms, with filesystem/output limits checked while
running and after completion. The observed disk limit is not a strict network
transfer quota: writes can overshoot between checks. Windows enforces the job
memory/process limits independently. The deadline covers download and validation;
cleanup and the existing local transaction have their own completion behavior.

Success, failure, cancellation, timeout and oversize output all close the owned
job and stop descendants. The runner waits for the parent and for the job's
active-process count to reach zero, with a five-second stop bound. Windows can
briefly retain inherited file handles during teardown; cleanup retries only
sharing violations on an owned regular file for at most five seconds. It does
not retry malformed content, authorization failures or other filesystem errors.

Cleanup uses pinned directories and non-following native file handles, including
read-only Git pack files. Directories are removed only after becoming empty.
Reparse points/unknown file types cause cleanup refusal; their targets are never
traversed or deleted. Failed cleanup prevents skill publication and preserves the
remaining owned temporary directory for inspection. Process death can still
leave temporary data, while Windows releases the private job and kills its
children. Phase 4.1's crash/power-loss transaction limits remain unchanged.

## Verification

Focused native Windows checks:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_git_installer.py tests/test_skill_git_process.py tests/test_skill_installer.py tests/test_skill_parser.py tests/test_skill_loader.py tests/test_skill_discovery.py tests/test_skill_registry.py tests/test_skill_activation.py tests/test_skill_selection.py tests/test_application_shutdown.py tests/test_structure.py -p no:cacheprovider --basetemp .pytest-tmp-skill-git-focused --junitxml=state/test-artifacts/skill-phase4-2-focused.xml
```

Result: **426 passed, 2 skipped** in 25.75 seconds. The two existing skips require
host permission to create actual symbolic links. Git-mode `120000` fixtures and
an actual Windows junction were separately exercised successfully; they are not
counted as skipped. Relevant cases include:

- Real Git normal/multi-skill repositories and byte-exact UTF-8 BOM/CRLF files.
- Empty/no-skill repositories, malformed skills and duplicate names.
- Executable scripts, malicious attributes, hooks and inherited Git configuration.
- Committed symlinks and submodules, unsupported tree records, and safe treatment
  of repository paths which would be unsafe Windows filenames.
- Per-file, combined skill, count, tree and observed download limits.
- Preview rejection/cancellation before storage creation; identical reinstall and
  exact-name removal through the existing local installer.
- Owned descendants stopped on timeout, cancellation, output overflow and command
  failure; abrupt owner exit, unrelated-process preservation and handle release.
- Read-only temporary files, cleanup failure preventing publication, and an actual
  temporary junction whose external target remains untouched.
- Local and remote CLI paths, escaped metadata-only output, and a fresh-process
  import guard rejecting UI/inference startup.

Deterministic repository tests replace only the download transport with a local
fixture repository. Production Git clone/object inspection, parsing, native
process ownership, storage transactions and cleanup still run. The test-only
file transport is unavailable to production users.

Real HTTPS smoke checks used the public
[Anthropic skills repository](https://github.com/anthropics/skills), in isolated
ignored storage, with both the `.git` and suffix-free URL forms. Each independently
installed **20** instruction files, verified **20** identical reinstall results,
removed **20**, and left **zero** temporary workspace entries. The inspected
revision was `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`. No upstream executable
content ran and no skills were left in the user's normal catalog. Content-free
summaries are under `state/test-artifacts/skill-phase4-2-live*/summary.json`.
This verifies Git installation and cleanup, not these external skills' model
behavior or asset-dependent functionality. TasteSkill remains Phase 5.1.

Full regression command:

```text
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp .pytest-tmp-skill-git-full --junitxml=state/test-artifacts/skill-phase4-2-full.xml
```

Result: **1,342 passed, 58 skipped, 15 subtests passed** in 163.10 seconds. The
58 existing skips are 7 host-dependent symbolic-link checks and 51 opt-in
live-model/cloud/UI gates. No skipped gate is counted as a pass. This phase
reruns no live-model qualification; the live HTTPS installer smoke is recorded
separately above. Unlike the prior Phase 4.1 combined run, this ordinary full run
passed the existing junction-replacement regression without instrumentation or
changed assertions. That pass does not establish the cause of its earlier
intermittent failure.

Dependency consistency and whitespace checks passed. All pytest temporary paths
are repository-local; native Windows checks use an unrestricted shell. The
unwritable pytest cache remains disabled.

## Files changed

- `app/runtime/skills/git_installer.py`
- `app/runtime/skills/_git_process.py`
- `app/runtime/skills/installer.py` (error codes and shared validated transaction)
- `app/runtime/skills/cli.py` (HTTPS/local dispatch)
- `app/runtime/skills/__init__.py` (public Git installer/result exports)
- `tests/test_skill_git_installer.py`
- `tests/test_skill_git_process.py`
- `tests/test_skill_installer.py` (obsolete HTTPS-rejection fixture becomes HTTP)
- `docs/skill-runtime-phase4-2.md`

## Deferred work

The reported context-window rejection, Qwen trailing punctuation case and prior
intermittent Windows regression failures remain on the final skills verification
list. This phase changes no acceptance prompts, model configuration, context
policy, routing or unrelated application behavior to make those tests pass.

Next roadmap step: Phase 5.1, unchanged TasteSkill compatibility validation.
