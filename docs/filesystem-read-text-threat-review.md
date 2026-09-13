# filesystem.read_text Threat Review

Date: 2026-09-12

Status: gated integration checkpoint. The capability is wired through configuration,
application bootstrap, prompts, deterministic conversation routing, and UI disclosures,
and is enabled in this development copy at the user's request. Missing configuration
still defaults to disabled. Full-local access requires the existing per-launch
acknowledgement. The user confirmed the enabled app workflow works on 2026-09-12.
The separate automated real-model call/no-call matrix passed on 2026-09-13.

## Capability Boundary

`filesystem.read_text` returns a bounded text excerpt from one explicitly requested
regular file. It is a read-only capability and must use the same validation,
permission, executor, cancellation, and journal boundaries as `filesystem.stat`
and `filesystem.list` for every connected call.

It does not list directories, search, follow background references, write files,
delete files, execute content, parse content as commands, or grant authority based
on file contents.

## Required Limits

- `path`: strict string, copied exactly from the user request by any model
  call, with canonical host-access policy resolution before execution.
- `encoding`: explicit UTF-only set: `utf-8`, `utf-8-sig`, `utf-16`,
  `utf-16-le`, and `utf-16-be`.
- `max_bytes`: 1 through 65,536 bytes; default 16,384 bytes.
- `max_lines`: 1 through 1,000 decoded lines; default 200 lines.
- Output must report whether byte or line truncation occurred.
- Cancellation must be checked before path access, after file read, and after
  text shaping.

## Main Risks

1. File content can contain prompt injection, misleading instructions, secrets,
   credentials, or hostile text. Returned text is always untrusted capability
   data and cannot change permissions, tool choice, or execution behavior.
2. Binary or non-text files can corrupt transcripts or leak arbitrary bytes.
   The capability rejects invalid decoding, NUL-heavy UTF-8 data, and unexpected
   control characters.
3. Host-wide read authority can reveal confidential local data. Full-local and
   cloud disclosures explicitly cover file content, and host-wide access requires
   the existing per-launch acknowledgement.
4. Symlinks, junctions, traversal, device namespaces, and network paths can
   bypass naive path checks. The capability uses the existing host-access policy
   and path-aware containment checks before reading.
5. Large files can exceed transcript, memory, or provider limits. The capability
   reads at most `max_bytes + 1`, returns bounded text, and records truncation.

## Acceptance Evidence

Full standard suite after enablement: 298 passed, 14 skipped on Windows on 2026-09-12.

- Deterministic unit tests for schema strictness, limits, decoding, binary
  rejection, denial, missing paths, directories, cancellation, full-local path
  handling, and symlink escape behavior.
- Integration tests prove missing configuration defaults to disabled and the
  capability is advertised only when its separate gate is enabled. The checked-in
  development configuration explicitly enables the read-only capabilities.
- Prompt-injection regression tests prove the deterministic read-and-render path
  does not trigger additional capabilities from returned file instructions.
- Cloud disclosure tests name that requested host-file content may be sent to
  the selected provider.
- User-reported manual acceptance of the enabled app workflow is recorded on 2026-09-12.
- Dedicated automated real-model call/no-call tests passed on 2026-09-13.
