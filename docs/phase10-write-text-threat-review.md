# Phase 10: approved text-file writing

Date: 2026-09-12
Status: second development checkpoint; manual application acceptance pending.

## Scope and authority

- One explicit absolute Windows local-drive file path and one exact UTF-8 text body.
- The operation creates the file if it was absent or replaces the entire existing regular file.
- No append, partial edit, recursive parent creation, binary write, copy, move, trash, permanent
  deletion, shell access, process execution, or elevation.
- Separate feature gate and WRITE/ASK rules. The executor continues to refuse blanket ALLOW for
  WRITE calls.
- User input selects the target and content deterministically. Read/model-selected turns advertise
  only read capabilities; returned file content and previous tool history cannot select or approve
  a text write.
- The UI displays the canonical target path and exact text body as readonly plain text. Cancel is
  the default; closing, Escape, expiry, and shutdown cannot approve. Each approval is consumed once.

## Write boundary

- Text is limited to 65,536 UTF-8 bytes and 1,000 lines before approval is requested.
- The same host-write policy rejects UNC/device/network paths, drive-root children, traversal, ADS,
  reserved names, ambiguous trailing characters, bidirectional display controls, redirected paths,
  O.R.S.I runtime/state, AppData, and standard OS, recovery, program, and configured protected roots.
- Ancestors are pinned with non-following directory handles and no write/delete sharing during
  preparation and execution. The approved parent identity is rechecked after approval.
- The approval binds target state as either missing or a specific regular-file identity. If a file
  appears, disappears, or is replaced between preview and execution, the operation is denied and the
  new entry is preserved.
- Content is written to a unique temporary file in the same directory, flushed, atomically moved into
  place with replace semantics, then verified by final file identity and SHA-256 digest.

## Failure and recovery

- Known pre-write failures return normalized messages without raw exception details.
- If the write completes but verification fails, or an unexpected failure occurs after dispatch, the
  result is conservatively treated as unknown and review-required state blocks further operations.
- If result persistence fails after execution, the live session also blocks; the durable RUNNING
  record becomes unknown after restart. No operation is replayed automatically.
- The durable journal stores digests and outcome metadata, not raw target paths or text content.
  The in-memory approval record contains the exact path and preview text so the trusted UI can show
  the side effect before approval. Conversation text still follows the existing session persistence
  behavior.
- There is no in-app undo yet. Replacing a file is manually reversible only from an external backup
  or version history supplied by the user or host environment.

## Verification and remaining limits

- 370 passed, 14 skipped in the full Windows suite; 28 new text-write tests and 72 total Phase 10
  write tests across folder creation and text writing.
- Tests cover exact preview, denial, create, replace, collision after approval, changed target
  identity, missing parent, directory target, protected path matrix, read/write isolation,
  hostile read content, unknown-outcome blocking and restart recovery, and real Qt approval.
- Manual app acceptance, live-model conversation after a write, denied-ACL variants, removable-drive
  behavior, fresh packaging, and broad custom application/service location discovery remain release
  gates. NTFS was exercised; other local filesystem identities still need dedicated validation.
