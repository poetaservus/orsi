# Skill reference count, 8 October 2026

The bounded `codex/skill-reference-count-32` change starts from local main
`69d5856`. A desktop `2d-game-dev` package has 20 Markdown references totaling
47,061 bytes; the largest is 4,612 bytes. Its installation was rejected solely
by the former 16-reference ceiling. Unrestricted native inspection reproduced
that rejection and accepted the package with a temporary 32-file ceiling.

The shared package limit is now 32 reference files. Local and Git installation,
reviewed imports, ownership manifests, and native reference snapshots all use
the same constant. The 16 KiB per-file, 64 KiB combined, directory-depth,
path-validation and excerpt limits remain unchanged. This is a shared package
format change, so it applies in both local and cloud modes.

Cloud prompts still receive main skill guidance and a compact path inventory;
reference bodies enter context only through bounded on-demand reads. Existing
model profiles, rate pacing, tool-call budgets, prompts, selection, sampling and
context policy are unchanged. The four extra inventory paths add 36 tokens under
the adapter's offline estimator. Saved Luna limits are 200,000 TPM and 500 RPM;
these saved account ceilings were not reverified with a paid API request.

## Verification and installation

Boundary checks cover a 32-reference local preview/install, a 33-entry ownership
manifest, native activation/read, idempotence and removal. A real local Git
fixture verifies all 32 references survive repository inspection and installation.
Existing count-rejection fixtures now test 33 references; independent size,
depth, path, stale-reference and transaction checks retain their assertions.

The initial restricted focused run recorded 155 passes, 161 failures and 22
errors in 53.39 seconds. Native file access and Git subprocess restrictions
prevented the Windows checks; this run is retained separately from unrestricted
verification. All runs use repository-local basetemp and ignored JUnit artifacts
under `state/test-artifacts/skill-reference-count-32/`.

Unrestricted focused verification passed all 338 tests in 78.29 seconds,
including both new boundary cases. Dependency consistency and Git whitespace
checks passed. Full native regression passed 2,334 tests and 15 subtests, with
58 separately recorded optional/host-dependent skips and no failures/errors,
in 356.44 seconds. No live model/API gate is claimed.

The actual desktop skill was installed through the transactional CLI into the
default global catalog. All 21 supported files match their original bytes
(55,583 total bytes); the native reader activated the 20-reference package and
returned every reference exactly across 38 bounded excerpt reads. Its owned
reader authority was deactivated. All four previously installed skills retain
their original supported bytes, and the desktop source is unchanged. The
content-free installation summary is in ignored
`state/test-artifacts/skill-reference-count-32/installation.json`. No API requests
were made. Restart a running O.R.S.I. instance to load the new ceiling and
refresh its catalog; then select the skill explicitly in the composer.

## Integration and recovery

Pre-integration refs, worktree identities, status and a complete-history bundle
are retained under ignored `state/backups/skill-reference-count-32-20261008/`.
The verified bundle contains 91 refs and records complete history.
Preserve prior main at `archive/2026-10-08/main-before-skill-reference-count-32`,
commit after verification, fast-forward local main and remove only this merged
local feature branch. Other active worktrees and remote refs are unchanged.
Install through the existing transactional CLI into the user's global O.R.S.I.
skill catalog; no source rewriting or replacement of existing packages is needed.
