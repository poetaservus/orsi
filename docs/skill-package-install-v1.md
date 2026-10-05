# Skill package v1: installation (Phase 2)

Date: 5 October 2026. Starting local main: `b6021fc`.
Implementation branch: `codex/skill-package-install-v1`.

## Result and scope

Local folders and public HTTPS Git repositories now install the entry point and
supported Markdown references as one immutable package. Settings accepts folders
and public GitHub repository roots alongside the existing single-file imports.
It previews skill count, reference count, total content bytes and all package names.
Install publishes the reviewed bytes, even if local files or the remote branch
change afterward. Registry refresh and chooser availability retain their existing
behavior.

This implements the installation portion of the
[Phase 1 format](skill-package-format-v1.md). References do not enter the model
prompt yet. No reference tool, recursive link reader, automatic document selector
or new inference request is added. Model profiles, sampling, context policy,
skill selection, main-instruction injection and tool authorization are unchanged.
The tiny `python-clamp` pack and its fixed future live acceptance prompts remain
the same. Tests use isolated storage; the user's installed skills and settings
are not migrated or modified.

## Import modes

| Source | Preserved content |
| --- | --- |
| Local skill folder or repository directory | Each recognized `SKILL.md` and its supported references. |
| Public GitHub repository root in Settings | Complete packages from one default-branch commit; requires Git on PATH. |
| Public HTTPS Git repository through CLI | The same package inspection/publication contract. |
| Local Markdown file or GitHub file/Raw link | That file alone, stored as `SKILL.md`; no sibling inference or fetching. |

Both local and Git enumeration stop at a recognized package root. Nested
`SKILL.md` files do not silently install another skill; inside `references/`,
they are ordinary supporting documents. This aligns Git enumeration with the
existing local package boundary. Separate sibling skill packages still install
as a validated batch. Original Git root paths remain opaque: only validated,
package-relative reference identifiers become paths in synthetic package folders.
No checkout, attributes/filter execution, submodule initialization or scripts run.

The UI reviews the complete repository/folder batch and installs it atomically.
A per-package chooser within a repository is not part of this phase. Refs/branch
selection, private Git authentication and in-place updates remain unsupported.

## Validation and limits

`package_format.py` defines immutable reference snapshots and pure validation.
`installer.py` reads bounded native snapshots before any skill-storage writes.
The contract's 16-reference, 16 KiB per reference, 64 KiB combined reference,
four-level directory, ASCII path and Windows collision limits are enforced.
All supporting bytes also count against the existing 16 MiB installation-batch
limit. Existing main-file, repository/tree/download and registry limits remain.

Reference text must be nonempty UTF-8 (a BOM is allowed), with binary controls
rejected. Original bytes and line endings are preserved. Path aliases, traversal,
reserved names, ambiguous casing, junctions and other redirects are rejected.
Only `references/**/*.md` is copied; unrelated source files remain untouched.
Source reference enumeration is bounded even when unsupported files are present.

Prepared packages carry detached parsed definitions and immutable main/reference
bytes. Publication revalidates them; preview metadata cannot change the installed
instructions. Git resources are released before handing snapshots to the UI or
publication callback. Cancellation and download deadlines keep their existing
boundaries.

## Ownership, conflicts and recovery

Packages with references receive a generated `.orsi-package.json` in installed
storage. This is internal bookkeeping, not an authored instruction or a model
input. Its versioned, bounded inventory records canonical owned paths and SHA-256
digests, including the main file. It is written before reference staging so a
partial stage has an ownership record. Single-file skills retain their original
one-file storage layout and need no migration or new metadata.

The 16 KiB metadata ceiling is separate from the source-content size shown in
preview. The inventory is not cryptographic authentication against a compromised
host; it prevents normal cleanup from treating unrelated files as owned content.
Malformed inventory data cannot grant access outside the package.

Idempotence compares all owned package bytes. Adding/removing/changing a reference
requires explicit removal before reinstalling. Legacy single-file idempotence
still compares its main file and leaves unrelated manually added files untouched.
Removal is stricter: unknown files, edited owned content or invalid inventories
are preserved with a fixed error before quarantine. Users must preserve/reconcile
their manual changes; this phase adds no force-delete or overwrite command.

Staging remains outside discovery. Placement verifies directory identity and
complete bytes, then refreshes the registry. Failures roll back only known owned
files and empty directories. Removal quarantines the validated package and
restores it if registry refresh fails. Cleanup checks the complete tree before
deleting owned files, rejects redirects/unknown content and never uses unrestricted
recursive deletion. Unknown content can cause a preserved stage/quarantine and
an explicit failure, rather than silent data loss.

## Verification

The broad focused skill run passed **520 tests**, with **2 existing skips**.
After aligning Git and local package discovery, the complete Git/package recheck
passed **74 tests**. The final full native Windows regression passed **1,765 tests
and 15 subtests**, with **49 existing skips**, in 207.79 seconds. All runs used
repository-local `--basetemp` directories and ignored caches. Native handle/Qt
checks ran unrestricted. The future model acceptance JSON and authored pack
documents are unchanged.

Coverage includes original single-file parsing/activation, local and real Git
object imports, nested supporting documents, immutable previews, reference-only
conflicts, byte/count/depth limits, invalid text, unsafe identifiers, actual
junctions, ownership preservation, partial-stage rollback, refresh recovery and
Settings publication without inference. Git tests replace only the transport
seam with controlled local repositories; they retain production object inspection
and process ownership. Live public-network Git and local/cloud reference-reader
qualification were not performed. The reader is still a later-phase feature.

An isolated Qt event-loop audit with the bundled Saira font visually verified the
folder preview and installed states. It previewed in 0.063 seconds and installed
in 0.062 seconds, with zero model requests. These timings describe this tiny
fixture on this host, not a portable-SSD performance guarantee. Screenshots and
content-free timing records are under ignored
`state/skill-package-install-review/visual-font/`.

Earlier focused checks encountered a native Git temporary-cleanup failure and
teardown error; the affected limit cases passed their isolated recheck, and the
final standard-runner suite passed. No temporary-cleanup policy was relaxed.
The old four-second Settings test wait also timed out: instrumented workers took
roughly six to seven seconds under polling-based Qt tests. Duplicate inventory
scans were removed and the asynchronous test helper now uses a bounded
15-second wall-clock deadline, retaining all outcome/safety assertions.
An optional stack-sampling diagnostic runner terminated with a native access
violation and was not counted as verification. Final checks used the standard
runner; that diagnostic probe is not application code.

Pre-integration refs/worktrees and a verified complete-history bundle are
preserved under ignored `state/backups/skill-package-install-20261005/`.
The prior main is preserved at
`archive/2026-10-05/main-before-skill-package-install`. Following the working
baseline, the verified change is committed, local main fast-forwards and the
merged feature branch is removed. Other worktrees and remote refs are unchanged.
