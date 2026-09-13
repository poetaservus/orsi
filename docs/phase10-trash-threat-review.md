# Phase 10: approved file trashing

Date: 2026-09-13
Status: fifth development checkpoint; manual application accepted and ready for local preservation.

## Scope and authority

- One explicit absolute Windows local-drive file path.
- The operation sends a bounded regular file to the Windows Recycle Bin after exact approval. It does
  not permanently delete files, trash directories, recursively remove contents, execute shell syntax,
  elevate, or access network/device paths.
- Separate feature gate and WRITE/ASK rules. The executor refuses blanket ALLOW for WRITE calls.
- User input selects the target deterministically. Plain `delete` requests are treated as Recycle Bin
  trash requests; requests that ask for permanent deletion are not routed to this capability.
  Read/model-selected turns advertise only reads; returned file content and tool history cannot
  request or approve trashing.

## Trash Boundary

- Trash size is limited to 16 MiB in this checkpoint.
- The host-write policy rejects UNC/device/network paths, drive-root children, traversal, ADS,
  reserved names, ambiguous trailing characters, bidirectional display controls, redirected paths,
  O.R.S.I runtime/state, AppData, and standard OS, recovery, program, and configured protected roots.
- The target must be an existing regular non-reparse file. Its file identity, byte count, and SHA-256
  digest are bound into the approval precondition.
- The target parent is pinned with non-following directory handles and no write/delete sharing during
  precondition calculation. Execution rechecks file identity/digest and parent identity after
  approval. If the file changes after preview, the operation is denied.
- The trusted operation uses the Windows shell file-operation API with Recycle Bin semantics. If the
  file still exists afterward, the call fails; if the shell reports an uncertain post-dispatch state,
  the write outcome is treated as unknown.

## Failure And Recovery

- Known pre-trash failures return normalized messages without raw exception details.
- If dispatch may have occurred but final state cannot be verified, the result is conservatively
  treated as unknown and review-required state blocks further operations.
- If result persistence fails after execution, the live session also blocks; the durable RUNNING
  record becomes unknown after restart. No operation is replayed automatically.
- The durable journal stores digests and outcome metadata, not raw paths or file contents. In-memory
  approval records contain the exact preview details for the trusted UI.
- There is no in-app restore yet. Recovery is through the Windows Recycle Bin UI, host version
  history, backup, or a fresh approved move/copy after manual review.

## Verification And Remaining Limits

- 459 passed, 14 skipped in the full Windows suite; 30 new trash tests and 161 total Phase 10
  mutation tests across folder creation, text writing, file copying, file moving, and file trashing.
- Tests cover exact preview, denial, plain-delete aliasing to Recycle Bin, target changes after
  approval, missing paths, directory targets, protected path matrix, permanent-delete wording
  rejection, read/write isolation, hostile
  read-content isolation, unknown-outcome blocking and restart recovery, and real Qt approval.
- Automated tests fake the Recycle Bin dispatcher to avoid leaving test files in the user's Recycle
  Bin. Manual app acceptance of the real Windows shell trash operation passed on 2026-09-13;
  live-model conversation after
  trash, denied-ACL variants, removable-drive behavior, fresh packaging, and broad custom
  application/service location discovery remain release gates. NTFS was exercised; other local
  filesystem identities still need dedicated validation.
