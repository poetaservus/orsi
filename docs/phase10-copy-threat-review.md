# Phase 10: approved file copying

Date: 2026-09-12
Status: third development checkpoint; manual application acceptance pending.

## Scope and authority

- One explicit absolute Windows local-drive source file and one explicit absolute Windows local-drive
  destination file path.
- The operation copies a bounded regular file. It never copies directories, recursively creates
  parents, moves, deletes, executes, opens shell syntax, elevates, or accesses network/device paths.
- Collision policy is explicit: `fail` refuses an existing destination; `replace` replaces only the
  exact destination file state that was previewed and approved.
- Separate feature gate and WRITE/ASK rules. The executor refuses blanket ALLOW for WRITE calls.
- User input selects source, destination, and collision policy deterministically. Read/model-selected
  turns advertise only reads; returned file content and tool history cannot request or approve a copy.

## Copy boundary

- Copy size is limited to 16 MiB in this checkpoint.
- The host-write policy rejects UNC/device/network paths, drive-root children, traversal, ADS,
  reserved names, ambiguous trailing characters, bidirectional display controls, redirected paths,
  O.R.S.I runtime/state, AppData, and standard OS, recovery, program, and configured protected roots.
- The source must be an existing regular non-reparse file. Its file identity, byte count, and SHA-256
  digest are bound into the approval precondition.
- The destination parent is pinned with non-following directory handles and no write/delete sharing.
  The approval also binds whether the destination was missing or a specific regular-file identity.
- Execution rechecks source identity/digest and destination state after approval. A changed source,
  new destination, or replaced destination fails before placing the copy.
- Data is written to a unique temporary file in the destination directory, flushed, then atomically
  placed with `rename` for fail-on-collision or `replace` for explicit replacement. The final file is
  verified by identity and SHA-256 digest.

## Failure and recovery

- Known pre-copy failures return normalized messages without raw exception details.
- If placement completes but verification fails, or an unexpected failure occurs after dispatch, the
  result is conservatively treated as unknown and review-required state blocks further operations.
- If result persistence fails after execution, the live session also blocks; the durable RUNNING
  record becomes unknown after restart. No operation is replayed automatically.
- The durable journal stores digests and outcome metadata, not raw paths or copied file contents.
  In-memory approval records contain the exact preview details for the trusted UI.
- There is no in-app undo yet. Replacing a destination is manually reversible only from a backup or
  host version history.

## Verification and remaining limits

- 399 passed, 14 skipped in the full Windows suite; 29 new copy tests and 101 total Phase 10 write
  tests across folder creation, text writing, and file copying.
- Tests cover exact preview, denial, create, explicit replace, default collision refusal, destination
  appearing after approval, source changes after approval, missing paths, directory targets,
  protected path matrix, read/write isolation, hostile read-content isolation, unknown-outcome
  blocking and restart recovery, and real Qt approval.
- Manual app acceptance, live-model conversation after copy, denied-ACL variants, removable-drive
  behavior, fresh packaging, and broad custom application/service location discovery remain release
  gates. NTFS was exercised; other local filesystem identities still need dedicated validation.
