# Skill reference reader v1 (Phase 3)

Date: 5 October 2026. Starting main: `e22d6c9`.
Implementation branch: `codex/skill-reference-reader-v1`.

Phase 3 supplies the controlled reader and its scoped `skill.read_reference`
capability adapter. It does not register that tool in the production catalog,
inject inventories into conversations or change automatic skill selection.
Those lifecycle and context-budget connections belong to Phase 4. This is the
historical Phase 3 record; [Phase 4 conversation integration](skill-reference-conversations-v1.md)
now supplies those connections and updates the Settings preview.

## Authority and inventory

`SkillReferenceReader` receives a storage implementation. Application code selects
a valid `SkillDefinition`, activates it and obtains an immutable binding with a
skill name, opaque package identity, SHA-256 content version and a sorted resource
inventory. Inventory entries contain only canonical identifiers, original byte
sizes and document hashes. They contain no document bodies or host paths.

Each activation revokes previous bindings, even for identical content. Failed
activation leaves no old authority. Deactivation ends authority immediately after
any in-progress locked operation completes. The caller must deactivate on skill
switch/removal, reset, tools being disabled and shutdown. One reader belongs to one
application scope; the capability also binds its calls to one session and turn.
Phase 4 must own and connect those lifecycle operations before enabling the tool.

Model arguments specify only an exact inventory path, inventory version and
excerpt bounds. They cannot choose a package, root, skill name, storage provider
or host search location. A stale binding/version, unsafe spelling or missing
inventory member fails with a fixed error. Another reader cannot use the binding.
The read capability has no arbitrary host resource. Its default permission is
still denied unless the application explicitly authorizes this exact capability
in a scoped registry; existing host-read permission rules are unchanged.

Every read obtains and validates a fresh bounded package snapshot, comparing its
identity and complete content version with the binding. Changes to the entry
point, requested/unrequested documents, inventory or physical package replacement
reject the read. Observed storage/content failures revoke the binding; restoring
old bytes does not revive it. There is no persistent reference-body cache. The
version hashes exact main/reference bytes and canonical identifiers using framed
lengths; parsing also verifies the main definition still matches the selected skill.

## Storage boundary

`ReferenceStorage.snapshot(skill, cancellation)` returns a bounded immutable
`PackageSnapshot`. The native filesystem implementation and the memory test
implementation share this interface. A future unlocked vault may provide another
implementation without teaching the reader about encryption or host paths.
This phase does not implement vault storage or encryption.

The Windows adapter opens only the local drive anchor by pathname. All ancestor
components, package directories and supported files are opened relative to verified
directory handles, with reparse processing disabled. Directory enumeration also
uses handles, not host-path scans. It rejects reparse/system objects and retains
supported file handles without write/delete sharing through snapshot validation.
The package retains Phase 1 limits: main at most 1 MiB, 16 reference files, 16 KiB
per document, 64 KiB combined, four subdirectory levels and canonical safe ASCII
identifiers. Enumeration is also bounded to 2,048 entries.

Directory namespace membership and inventories are rechecked before returning,
including a fresh handle-relative traversal of the package location. An open
directory is not assumed to prevent every rename. A native adversarial test enables
directory rename sharing and replaces the package pathname with an actual
junction before document reads. Reads stay on the original handles; the replacement
document is never read and the final namespace check rejects the snapshot.

The native calls follow Microsoft's [NtCreateFile relative-name and reparse
semantics](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[NtQueryDirectoryFile enumeration contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntquerydirectoryfile)
and [FILE_DIRECTORY_INFORMATION layout](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_directory_information).
Other filesystem platforms fail closed. Ordinary local permissions still apply;
this reader cannot authenticate a compromised host or a package altered before
explicit activation. Content versions are integrity/lifecycle identifiers, not
cryptographic signatures or encryption.

## Excerpts and continuation

Defaults are 2,048 UTF-8 text bytes and 40 lines. Hard output ceilings are 4,096
text bytes and 80 lines; the minimum requested byte budget is four so a complete
UTF-8 code point always fits. Storage may validate all bounded documents internally,
but only the requested document's excerpt is returned. No model call is added to
select documents. No links are followed, downloaded, expanded or interpreted as
commands; document-relative Markdown links remain ordinary returned text.

Successful results contain skill/package/version/path provenance, original document
hash, text, start/end byte offsets, bytes returned, total text bytes, `has_more`,
`next_offset`, `complete_document` and `content_is_untrusted: true`. Continuation
offsets refer to UTF-8 text after removing an optional leading BOM; CRLF bytes are
preserved. Offsets must lie on code-point boundaries. Long lines can continue in
later excerpts without silent text loss. A final continuation is not labeled a
complete document unless it started at zero and returned the entire document.

Failures use bounded messages without requested host paths, document excerpts or
storage exception text. The adapter maps them into existing capability error codes
and suppresses unexpected storage tracebacks; cancellation uses the existing
cancellation outcome. Reference bodies are lower-priority untrusted guidance.
Phase 4 must enforce that status and fit inventory, schemas and excerpts within
the existing effective context budget. No model limits, prompts, sampling settings,
routing or context policy are changed here.

## Verification

The final focused Windows run passed **480 tests**, with **2 existing skips**.
It covers 73 new reader cases plus existing installation, Git snapshots, discovery,
registry, activation, capability registry, executor and permission contracts. The
reader cases cover the unchanged tiny clamp pack, memory-backed storage, native
installed/project/single-file packages, stale continuations, switches/deactivation,
removal, limits, invalid text/paths, BOM/CRLF/Unicode, long lines, real junctions,
handle-relative rename protection, cancellation and released handles. A deterministic
check verifies the production catalog still does not advertise the new capability.

The full Windows suite passed **1,838 tests and 15 subtests**, with **49 existing
skips**, no failures, in 213.13 seconds. Both runs used the portable Python runtime,
unrestricted native Windows checks, repository-local
`--basetemp` and ignored cache directories. Live local/cloud reference-loading
acceptance remains deferred until conversation integration. The fixed acceptance
prompts and sample documents are unchanged; deterministic checks do not qualify
live model behavior or portable SSD filesystem performance.

The initial focused run exposed two test/interface mistakes, which were corrected.
A later adversarial check exposed the initial pathname reader's reliance on directory
rename protection. The reader now uses a separate native handle-relative backend;
the existing installer/loader remain unchanged. Earlier failed checks are not counted
as passed verification. No user settings, conversations or credentials were read or
stored in diagnostic snapshots.

Pre-integration refs/worktrees and a verified complete-history bundle are under
ignored `state/backups/skill-reference-reader-20261005/`. The starting main is
preserved at `archive/2026-10-05/main-before-skill-reference-reader`. The verified
change is committed, local main fast-forwards and its merged feature branch is
removed. Other active worktrees and remote refs are unchanged; this phase is not
pushed to GitHub.
