# Skill package v1: format contract (Phase 1)

Date: 5 October 2026. Starting main: `92c3a7b`.
Implementation branch: `codex/skill-package-format-v1`.

This is the Phase 1 contract and historical verification. Phase 2 now implements
package imports; see [package installation](skill-package-install-v1.md).
Phase 3 implements the [controlled reader](skill-reference-reader-v1.md).
Conversation loading remains Phase 4.

## Delivery boundary

Phase 1 defines the package contract and supplies a deliberately tiny test pack.
It does **not** enable reference copying, reference tools or additional prompt
injection. Existing discovery, parsing, installation, routing and activation
remain unchanged. Current installers still copy `SKILL.md` alone.

The next phases implement this contract in order:

1. Package installation and management, including local and GitHub sources.
2. A controlled reader bound to the active package.
3. On-demand conversation loading and context accounting.
4. End-to-end local/cloud qualification and release.

The contract limits below are requirements for those implementations, not new
limits already enforced by the current installer.

## Package layout and compatibility

```text
python-clamp/
  SKILL.md
  references/
    behavior.md
    checks.md
```

`SKILL.md` remains the entry point. Its existing required YAML fields (`name`
and `description`), optional data-only metadata, UTF-8 handling and instruction
body are unchanged. No new frontmatter, authored manifest or resource list is
required. A directory containing only a valid `SKILL.md` remains a valid skill.
The package format identifier is an internal storage/API version; it is not an
instruction or a required model-visible field.

Supporting files are ordinary UTF-8 Markdown beneath `references/`, optionally
in subdirectories. They do not require skill frontmatter and do not become
independent selectable skills. Preserve their original bytes, including BOM and
line endings. Reject empty documents, invalid UTF-8 and binary control content.
Each package has one entry point and one validated resource
inventory. Existing project/global precedence and exact metadata names remain
unchanged; an override selects a complete package rather than mixing resources
from global and project versions.

Only `SKILL.md` and `references/**/*.md` are supported content in this version.
Scripts, dependencies, executable hooks, images, PDFs and sibling files outside
`references/` are not part of the installed package. An unsupported file is not
implicitly executable or readable through the reference reader. A `SKILL.md`
inside `references/` is a supporting Markdown document, not another package.

## Paths and reference meaning

- Store resource identifiers as package-relative paths with `/` separators,
  such as `references/behavior.md`. No host username, SSD drive letter or absolute
  installation directory belongs in the authored reference.
- Ordinary local Markdown links are relative to the document containing them.
  A link in the entry point to `references/checks.md` and a link in
  `references/checks.md` to `behavior.md` identify files in the same package.
- Normalize `.` and `..` for link resolution, then enforce containment in
  `references/`. For example, a nested reference may use `../behavior.md`; a
  reference escaping the package is rejected. Stored inventory identifiers
  themselves must already be canonical and contain no dot segments.
- Reference-reader requests use canonical package-relative identifiers from
  that inventory, not arbitrary link strings or filesystem paths.
- Support a Markdown heading fragment as an advisory navigation hint. It does
  not alter the file identity or imply precise section retrieval in v1.
- Remote URLs remain ordinary text. Neither installation nor reference reading
  follows them, downloads content or activates a different skill.
- V1 resource components use ASCII letters, digits, `_`, `-` and `.`, with a
  lowercase `.md` extension. Reject empty components, Windows reserved device
  names, trailing dots/spaces, backslashes, drive/UNC/device paths, alternate
  data streams and encoded/ambiguous path spellings. Inventory identities must
  be unique under Windows case-insensitive comparison.
- Filesystem access must reject symlinks, junctions and other redirects and
  recheck package identity when reading. Lexical containment alone is not a
  security guarantee; Phase 3 must enforce the filesystem boundary.

The installer inventories supported files; it does not interpret all prose or
attempt to expand every Markdown link. An inventory does not prove that every
reference mentioned in instructions exists.

## Limits and local-model authoring guidance

| Contract limit | V1 ceiling |
| --- | --- |
| Entry point | Existing `MAX_SKILL_SIZE`: 1 MiB |
| Supporting files | 16 per package |
| Individual supporting file | 16 KiB |
| Combined supporting bytes | 64 KiB |
| Combined package bytes | 1 MiB + 64 KiB |
| Subdirectories below `references/` | At most 4 levels |
| Resource component / complete identifier | 64 / 240 ASCII characters |

Existing repository download, batch installation and catalog ceilings remain
additional limits. Future installation must count supporting bytes in batch
totals, snapshot all supported files before publication and reject the whole
package on an exceeded limit. Removal must distinguish owned package resources
from unrelated files; it must not introduce unrestricted recursive deletion.

Storage limits are not permission to fill the local model's context. Prefer:

- An entry-point body below 150 words, describing one narrow task.
- Supporting documents below 100 words each, with one clear purpose.
- Explicit filenames and direct instructions about when to read each file.
- One relevant document first; further reads only when the task needs them.
- No recursive automatic expansion, automatic skill chaining or new model calls
  to select a document in this version.

At activation the eventual runtime supplies the entry-point instructions and a
bounded inventory, not all document bodies. Reference excerpts, tool schemas and
the current user request must fit the effective model budget. Large documents
need bounded continuation; no implementation may increase model limits, truncate
the user task or silently replace the current context policy to admit them.

## Runtime and failure contract

The planned `skill.read_reference` reader is application-provided and available
only for a valid active package when the relevant tool mode is enabled. A skill
cannot grant itself tools or broader host access. Bind reads to the selected
package/version; another skill's resources are outside this reader's authority.
References remain lower-priority skill guidance and cannot change permissions,
core instructions, model configuration or runtime policy.

| Condition | Required future behavior |
| --- | --- |
| A requested reference is absent | Return a fixed missing-reference error; do not guess its contents or search the host automatically. |
| The package changes during use | Reject stale identity/version, refresh explicitly and invalidate cached reference bytes. |
| A requested file is oversized or unsafe | Return a bounded, content-free error; no partial unsafe access. |
| A document exceeds the available excerpt budget | Return explicit truncation/continuation information within the existing context rules. |
| Reference tools are disabled | Keep single-file guidance usable; for tasks requiring reference knowledge, explain that the document is unavailable and request its content. |
| The skill is removed or switched | End its reader authority and invalidate caches; old references must not masquerade as the active skill. |

Successful reads need provenance (package/version and relative identifier) and
explicit completeness information. Cache access must enforce the same active
package boundary as a fresh read. User conversations may retain history, but
reference bodies and credentials must not enter diagnostic logs. Storage access
should be replaceable so a future unlocked vault can supply package documents.

## Tiny acceptance pack

The authored fixture is `tests/fixtures/skill_package_v1/python-clamp/`: one
integer `clamp` function, one behavior reference and one plain-assertion reference.
It needs no dependency installation, generated project, framework or execution
tool. Each file is ASCII and comfortably below the authoring targets above.
The reference documents contain details absent from the entry point, so tests
can distinguish actual retrieval from merely injecting the main instructions.

Fixed future live prompts and expectations are in
`tests/fixtures/skill_package_v1/acceptance.json`. Preserve those prompts while
implementing the next phases. Begin with explicit skill selection so reference
loading can be assessed separately from the automatic selector. Test automatic
selection separately after the reader works. Exercise each live case on each
supported local model; report results per model rather than treating cloud
success as local qualification.

Today the fixture can be parsed and its entry point activated. Installing it
through the current installer intentionally omits the references. That boundary
is tested; it is **not** a successful end-to-end reference-loading demonstration.
Reference import/loading live gates are deferred until their implementation.

## Phase 1 verification

The focused parser/loader/installer/import/activation/compatibility run passed
266 tests, with 2 existing skips. The full native Windows regression passed
1,724 tests and 15 subtests, with 49 existing skips and no failures. Both runs
used the portable Python runtime, repository-local `--basetemp` directories and
ignored cache directories. Native filesystem checks ran unrestricted.

The three new deterministic checks verify entry-point parsing/injection without
reference-body injection, the fixture's document-relative links and small size,
and current install/idempotence/removal behavior. The authored pack totals
1,591 bytes; the entry-point body has 76 whitespace-separated words, with 66 and
78 words in the two references. These are size measurements, not tokenizer or
live model performance measurements.

Reference copying, controlled reads, conversation loading and the fixed live
acceptance cases have not run because those features belong to later phases.
No local/cloud inference qualification is claimed. Model settings, sampling,
context policy, prompts, tool behavior and user runtime state are unchanged.

Pre-integration refs/worktrees and a verified complete-history bundle are
preserved under ignored `state/backups/skill-package-format-20261005/`.
The starting main is preserved at
`archive/2026-10-05/main-before-skill-package-format`. Following the working
baseline, verification is followed by committing this bounded change,
fast-forwarding local main and removing the merged local feature branch.
Other active worktrees and remote branches are unchanged.
